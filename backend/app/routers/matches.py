"""
POST /matches/find/{report_id} runs the actual matching pipeline:
  1. pull the report + every opposite-type OPEN report
  2. score each pair with fusion.composite_score()
  3. save the results as Match rows, sorted best-first -- reusing any
     Match row that already exists for a given lost/found pair instead
     of inserting a duplicate every time this endpoint is called (e.g.
     every time someone opens/refreshes the matches page)

The real-time ping and "possible match" email only fire the first time
a given pair becomes the top match, not on every subsequent call -- see
the notes on the notification block below.

Calibration (turning raw_score into a probability) loads a persisted,
pre-fitted MatchCalibrator from disk if one exists (see
app/matching/train_calibrator.py) -- until enough confirmed matches exist
to train on, no calibrator.pkl exists yet and match_probability stays
null, so the UI falls back to showing raw_score/ranking.
"""

import logging
import math
from datetime import datetime
from pathlib import Path
from typing import List

import joblib
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from typing import Optional

from app.core.config import settings
from app.db.session import get_db
from app.models.report import Report, ReportType, ReportStatus
from app.models.match import Match, MatchStatus
from app.models.custody import CustodyRecord
from app.models.user import User
from app.routers.schemas import (
    MatchOut,
    ClaimRequest,
    ClaimResponse,
    CheckAnswerRequest,
    CheckAnswerResponse,
    FoundContactOut,
    ClaimantInfoOut,
)
from app.matching.embeddings import cosine_sim
from app.matching.fusion import ReportSignals, composite_score, competing_cluster
from app.matching.calibration import MatchCalibrator
from app.realtime import sio
from app.core.email import send_email
from app.routers.auth import get_current_user_optional, get_current_user

router = APIRouter(prefix="/matches", tags=["matches"])

logger = logging.getLogger("findit.claims")

# Wrong hidden-answer tries allowed against a match before online claiming
# is locked. After this, the only path forward is an admin verifying the
# claimant in person (custody.py's admin_verify_claim). A correct answer
# at any point resets the counter.
MAX_CLAIM_ATTEMPTS = 3

CLAIM_LOCKED_MESSAGE = (
    "Verification failed -- you've used all 3 attempts. If this item is really "
    "yours, go to the lost & found admin desk to verify in person."
)

# If the top two candidates' raw scores are within this margin, trigger
# disambiguation instead of auto-picking the top one (per your abstract:
# "if the leading candidates are not too far apart... asks a targeted
# disambiguation question").
DISAMBIGUATION_MARGIN = 0.05

# Disambiguation is only meaningful when the candidates being compared are
# actually plausible matches -- being "close to each other" isn't enough
# on its own. Without this floor, two totally unrelated weak candidates
# (e.g. a lost water bottle and a found set of keys, both scoring ~20%
# just because their embeddings are within DISAMBIGUATION_MARGIN of one
# another) get shown to the user as "which one is yours?", which is both
# wrong and confusing. This must match the frontend's MIN_MATCH_PERCENT
# (Matches.jsx) so a candidate that clears disambiguation is guaranteed to
# still be visible once resolved -- otherwise "This one" can pick a match
# that then gets hidden by the frontend's own display threshold, leaving
# the user staring at "No candidate matches yet" right after choosing.
MIN_DISAMBIGUATION_SCORE = 0.5

# A raw_score at or above this is worth a real-time "match found" ping --
# below this it's a weak candidate that would just be noise in a notification.
NOTIFY_SCORE_THRESHOLD = 0.6

_CALIBRATOR_PATH = Path(__file__).resolve().parent.parent / "matching" / "calibrator.pkl"


def _load_calibrator():
    """Best-effort load of a pre-fitted calibrator. Missing file, corrupt
    pickle, or an unfitted model all just mean "no calibrator yet" -- the
    caller falls back to raw_score, so this never needs to raise."""
    if not _CALIBRATOR_PATH.exists():
        return None
    try:
        calibrator = joblib.load(_CALIBRATOR_PATH)
    except Exception:
        return None
    if isinstance(calibrator, MatchCalibrator) and calibrator.fitted:
        return calibrator
    return None


_calibrator = _load_calibrator()


def _haversine_meters(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance between two lat/lon points, in meters."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _build_match_out(match: Match, db: Session, user: Optional[User]) -> MatchOut:
    """
    Assembles a MatchOut with found_contact / claimant_info filled in only
    when the requester is authorized to see them:

      - found_contact (the FOUND reporter's email/phone): only once the
        match is CONFIRMED, and only for the LOST reporter -- "found wale
        ki details lost wale ko tabhi dikhni chahiye jab usne claim ka
        question sahi answer kiya ho".
      - claimant_info (who claimed it): only once the match is CONFIRMED,
        and only for the FOUND reporter -- so the finder can see who
        claimed their item and its handover record.

    Anonymous requests (user is None) never get either field, regardless
    of match status.
    """
    out = MatchOut.model_validate(match)
    if not user or match.status != MatchStatus.CONFIRMED:
        return out

    lost_report = db.query(Report).filter(Report.id == match.lost_report_id).first()
    found_report = db.query(Report).filter(Report.id == match.found_report_id).first()

    if lost_report and lost_report.reporter_id == user.id and found_report:
        finder = db.query(User).filter(User.id == found_report.reporter_id).first()
        if finder:
            out.found_contact = FoundContactOut(name=finder.name, email=finder.email, phone=finder.phone)

    if found_report and found_report.reporter_id == user.id:
        record = (
            db.query(CustodyRecord)
            .filter(CustodyRecord.match_id == match.id)
            .order_by(CustodyRecord.handover_datetime.desc())
            .first()
        )
        if record:
            out.claimant_info = ClaimantInfoOut(
                claimant_name=record.claimant_name,
                claimant_contact=record.claimant_contact,
                handover_datetime=record.handover_datetime,
            )

    return out


def _disambiguation_question(candidate: Report) -> str:
    """
    Rule-based, deterministic question surfacing the candidate's own
    distinguishing details -- no NLP/LLM involved, consistent with the
    exact-match style verify_claim() already uses. Paired with a
    forced-choice UI ("does this describe your item? -> This one"), so the
    question just needs to give the user enough to recognize their item,
    not to be answered in free text.
    """
    descriptor = " ".join(part for part in (candidate.color, candidate.brand) if part) or candidate.category or "item"
    where = candidate.location_name or "an unspecified location"
    when = candidate.item_datetime.strftime("%b %d, %I:%M %p") if candidate.item_datetime else "an unspecified time"
    return f"A {descriptor} found near {where} around {when} -- is this yours?"


@router.get("/{match_id}", response_model=MatchOut)
def get_match(
    match_id: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    """Fetch a single match. Logged in as the lost reporter of a CONFIRMED
    match -> found_contact is filled in. Logged in as the found reporter
    of a CONFIRMED match -> claimant_info is filled in. Everyone else
    (including anonymous callers) gets both as null -- see
    _build_match_out."""
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(404, "Match not found")
    return _build_match_out(match, db, user)


@router.post("/find/{report_id}", response_model=List[MatchOut])
async def find_matches(report_id: str, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")

    opposite_type = ReportType.FOUND if report.report_type == ReportType.LOST else ReportType.LOST
    candidates = (
        db.query(Report)
        .filter(Report.report_type == opposite_type, Report.status == ReportStatus.OPEN)
        .all()
    )

    scored = []
    for candidate in candidates:
        distance_m = None
        if report.latitude is not None and candidate.latitude is not None:
            distance_m = _haversine_meters(
                report.latitude, report.longitude, candidate.latitude, candidate.longitude
            )

        hours_apart = None
        if report.item_datetime and candidate.item_datetime:
            hours_apart = abs((report.item_datetime - candidate.item_datetime).total_seconds()) / 3600

        signals = ReportSignals(
            text_sim=cosine_sim(report.text_embedding, candidate.text_embedding),
            image_sim=cosine_sim(report.image_embedding, candidate.image_embedding),
            distance_m=distance_m,
            hours_apart=hours_apart,
        )
        result = composite_score(signals)
        scored.append((candidate, result))

    scored.sort(key=lambda x: x[1]["score"], reverse=True)

    # Cluster every candidate within DISAMBIGUATION_MARGIN of the TOP score
    # (not just top-1 vs top-2) -- so a clear #1 with a distant #3/#4/#5
    # doesn't drag the whole top-5 batch into "needs review".
    #
    # Gated on the top score actually clearing MIN_DISAMBIGUATION_SCORE
    # first: being "close together" only matters among candidates that are
    # plausible matches to begin with. Two weak, unrelated candidates that
    # happen to score similarly low should never be presented as a
    # forced-choice -- the honest answer there is "no good match yet", not
    # "pick one of these".
    top_score = scored[0][1]["score"] if scored else 0.0
    if top_score >= MIN_DISAMBIGUATION_SCORE:
        cluster_indices = competing_cluster([result["score"] for _, result in scored], DISAMBIGUATION_MARGIN)
        competing_ids = {scored[i][0].id for i in cluster_indices}
    else:
        competing_ids = set()
    needs_disambiguation = len(competing_ids) >= 2

    # Dedupe against matches already saved for this report (from an
    # earlier call to this same endpoint -- e.g. someone just refreshing
    # the matches page). Without this, every single page-load created
    # brand-new duplicate Match rows for the same lost/found pair AND
    # re-sent the "possible match" email every time, regardless of
    # whether anything had actually changed -- that's what was causing a
    # dozens-of-emails-in-minutes spam storm from repeat visits/refreshes.
    existing_by_pair = {
        (m.lost_report_id, m.found_report_id): m
        for m in db.query(Match)
        .filter((Match.lost_report_id == report.id) | (Match.found_report_id == report.id))
        .all()
    }

    saved_matches = []
    top_match_is_new = False
    for i, (candidate, result) in enumerate(scored[:5]):  # keep top 5 candidates
        lost_id = report.id if report.report_type == ReportType.LOST else candidate.id
        found_id = candidate.id if report.report_type == ReportType.LOST else report.id
        in_cluster = needs_disambiguation and candidate.id in competing_ids

        match_probability = _calibrator.predict_proba(result["score"]) if _calibrator else None

        existing = existing_by_pair.get((lost_id, found_id))
        is_new = existing is None

        if existing:
            match = existing
            # Only refresh the score/signals if nobody's acted on this
            # match yet -- once it's VERIFIED/CONFIRMED/REJECTED, leave it
            # alone instead of silently rewriting state out from under
            # whatever the claimant/admin already did.
            if match.status in (MatchStatus.CANDIDATE, MatchStatus.NEEDS_DISAMBIGUATION):
                match.raw_score = result["score"]
                match.match_probability = match_probability
                match.used_signals = result["used_signals"]
                match.signal_weights = result["weights"]
                match.status = MatchStatus.NEEDS_DISAMBIGUATION if in_cluster else MatchStatus.CANDIDATE
                match.disambiguation_question = _disambiguation_question(candidate) if in_cluster else None
        else:
            match = Match(
                lost_report_id=lost_id,
                found_report_id=found_id,
                raw_score=result["score"],
                match_probability=match_probability,
                used_signals=result["used_signals"],
                signal_weights=result["weights"],
                status=MatchStatus.NEEDS_DISAMBIGUATION if in_cluster else MatchStatus.CANDIDATE,
                disambiguation_question=_disambiguation_question(candidate) if in_cluster else None,
            )
            db.add(match)

        if i == 0:
            top_match_is_new = is_new
        saved_matches.append(match)

    db.commit()
    for m in saved_matches:
        db.refresh(m)

    # Real-time "match found" ping + email -- only for a genuinely strong
    # top candidate, AND only the first time this exact pair shows up as
    # the top match. Otherwise every subsequent page visit for the same
    # report (by the owner, or by anyone who can reach the matches page)
    # would re-trigger both, which is what caused the email spam.
    if scored and scored[0][1]["score"] >= NOTIFY_SCORE_THRESHOLD and top_match_is_new:
        top_candidate, top_result = scored[0]
        top_probability = _calibrator.predict_proba(top_result["score"]) if _calibrator else None
        await sio.emit(
            "match:found",
            {
                "report_id": str(report.id),
                "report_title": report.title,
                "score": round(top_result["score"], 3),
                "probability": round(top_probability, 3) if top_probability is not None else None,
                "needs_disambiguation": needs_disambiguation,
            },
        )

        # Email the LOST-side reporter -- whichever of report/top_candidate
        # is the lost report, since they're the one who should hear "a
        # similar item was found", regardless of which side triggered this
        # search. Best-effort: a missing reporter_id/user (e.g. an older
        # report from before auth was wired up) just means no email, not
        # an error for the caller.
        lost_report = report if report.report_type == ReportType.LOST else top_candidate
        if lost_report.reporter_id:
            lost_reporter = db.query(User).filter(User.id == lost_report.reporter_id).first()
            if lost_reporter:
                send_email(
                    to_email=lost_reporter.email,
                    subject="A possible match was found for your lost item",
                    body=(
                        f"Hi {lost_reporter.name or ''},\n\n"
                        f"An item similar to what you reported lost (\"{lost_report.title}\") "
                        "has been found and matched by FindIt Campus.\n\n"
                        f"Check the site for details: {settings.frontend_base_url}/matches/{lost_report.id}\n\n"
                        "If it looks right, you can claim it there by answering the "
                        "finder's verification question."
                    ),
                )

    return saved_matches


@router.post("/{match_id}/check-answer", response_model=CheckAnswerResponse)
async def check_answer(
    match_id: str,
    payload: CheckAnswerRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Step 1 of the two-step claim flow: just checks the verification-question
    answer and reports back correct/incorrect -- nothing is saved, no match
    state changes either way. This is what lets the claim form ask "answer
    first, THEN fill in your details" instead of collecting everything
    upfront only to reject it all on a wrong answer.

    Same ownership check as verify_claim (only the lost report's own
    reporter can even attempt this) -- otherwise this would just be an
    easier oracle to guess someone else's hidden_answer against, without
    even the friction of typing in a name/reg number first.
    """
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(404, "Match not found")

    if match.status in (MatchStatus.VERIFIED, MatchStatus.CONFIRMED):
        raise HTTPException(400, "This match has already been verified and is awaiting/complete pickup.")
    if match.status == MatchStatus.REJECTED:
        raise HTTPException(400, "This match was rejected and can no longer be claimed.")

    found_report = db.query(Report).filter(Report.id == match.found_report_id).first()
    lost_report = db.query(Report).filter(Report.id == match.lost_report_id).first()
    if not found_report or not lost_report:
        raise HTTPException(404, "One of the reports behind this match no longer exists")

    if lost_report.reporter_id != user.id:
        raise HTTPException(
            403,
            "Only the person who filed the lost report can claim this match.",
        )

    if not found_report.hidden_answer:
        raise HTTPException(400, "This found report has no verification question set up")

    if match.failed_claim_attempts >= MAX_CLAIM_ATTEMPTS:
        return CheckAnswerResponse(
            correct=False, locked=True, attempts_left=0, message=CLAIM_LOCKED_MESSAGE
        )

    is_correct = payload.hidden_answer.strip().lower() == found_report.hidden_answer.strip().lower()

    if is_correct:
        if match.failed_claim_attempts:
            match.failed_claim_attempts = 0
            db.commit()
        return CheckAnswerResponse(correct=True)

    match.failed_claim_attempts += 1
    db.commit()
    left = max(0, MAX_CLAIM_ATTEMPTS - match.failed_claim_attempts)
    logger.warning(
        "wrong claim answer: user=%s match=%s (%d/%d used)",
        user.id, match.id, match.failed_claim_attempts, MAX_CLAIM_ATTEMPTS,
    )
    return CheckAnswerResponse(
        correct=False,
        locked=left == 0,
        attempts_left=left,
        message=(
            CLAIM_LOCKED_MESSAGE
            if left == 0
            else f"That answer doesn't match. {left} attempt{'' if left == 1 else 's'} left."
        ),
    )


@router.post("/{match_id}/verify", response_model=ClaimResponse)
async def verify_claim(
    match_id: str,
    payload: ClaimRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Asymmetric verification (per your abstract): whoever is claiming the
    item must answer the FOUND report's hidden_question correctly -- we
    never show them hidden_answer, we just check equality server-side.

    Only the person who actually filed the LOST report behind this match
    is allowed to attempt the claim -- otherwise anyone who stumbled onto
    (or guessed) a match_id could try to answer the finder's verification
    question for someone else's item. So this now requires login
    (get_current_user, not get_current_user_optional) and checks
    lost_report.reporter_id == user.id before even looking at the
    submitted answer. A lost report filed before auth was wired up (no
    reporter_id) has no verifiable owner, so it's rejected too --
    nobody can claim on its behalf.

    On a correct answer:
      - match.status -> VERIFIED (NOT yet CONFIRMED -- the item is still
        sitting with admin; the finder already handed it over physically
        when they filed the found report, and admin only marks it
        CONFIRMED once they've actually handed it to the owner in person.
        See custody.py's confirm_handover.)
      - reports are left as-is (still MATCHED) -- they only flip to
        RESOLVED at the actual handover, not at verification time
      - no CustodyRecord yet, no email to the finder yet -- both happen
        at handover, so the finder is only told once the item has
        genuinely left admin's hands, not just because someone answered
        a question correctly online

    On a wrong answer: 200 with verified=false (not a 4xx -- this is an
    expected outcome the frontend needs to render inline, not an error),
    match/report state is left untouched so they can retry.
    """
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(404, "Match not found")

    if match.status in (MatchStatus.VERIFIED, MatchStatus.CONFIRMED):
        raise HTTPException(400, "This match has already been verified and is awaiting/complete pickup.")
    if match.status == MatchStatus.REJECTED:
        raise HTTPException(400, "This match was rejected and can no longer be claimed.")

    found_report = db.query(Report).filter(Report.id == match.found_report_id).first()
    lost_report = db.query(Report).filter(Report.id == match.lost_report_id).first()
    if not found_report or not lost_report:
        raise HTTPException(404, "One of the reports behind this match no longer exists")

    if lost_report.reporter_id != user.id:
        raise HTTPException(
            403,
            "Only the person who filed the lost report can claim this match.",
        )

    # claimant_email and claimant_registration_number are shown pre-filled
    # in the UI from the logged-in account, but we still check them against
    # that account server-side rather than trusting the submitted values --
    # same reasoning as the reporter_id check above, just one level more
    # paranoid, since these two are meant to double as the identity record
    # admin checks the claimant against at physical handover.
    if payload.claimant_email.strip().lower() != user.email.strip().lower():
        raise HTTPException(400, "Email doesn't match your logged-in account.")
    if not user.registration_number or (
        payload.claimant_registration_number.strip().upper() != user.registration_number.strip().upper()
    ):
        raise HTTPException(400, "Registration number doesn't match our records for your account.")

    if not found_report.hidden_answer:
        raise HTTPException(400, "This found report has no verification question set up")

    if match.failed_claim_attempts >= MAX_CLAIM_ATTEMPTS:
        return ClaimResponse(
            verified=False,
            message=CLAIM_LOCKED_MESSAGE,
            match=_build_match_out(match, db, user),
            custody_record=None,
            locked=True,
            attempts_left=0,
        )

    # Case/whitespace-insensitive so "iPhone" vs "iphone" doesn't fail
    # someone over a genuinely correct answer.
    is_correct = payload.hidden_answer.strip().lower() == found_report.hidden_answer.strip().lower()

    if not is_correct:
        match.failed_claim_attempts += 1
        db.commit()
        left = max(0, MAX_CLAIM_ATTEMPTS - match.failed_claim_attempts)
        logger.warning(
            "wrong claim answer: user=%s match=%s (%d/%d used)",
            user.id, match.id, match.failed_claim_attempts, MAX_CLAIM_ATTEMPTS,
        )
        return ClaimResponse(
            verified=False,
            message=(
                CLAIM_LOCKED_MESSAGE
                if left == 0
                else f"That answer doesn't match. {left} attempt{'' if left == 1 else 's'} left."
            ),
            match=_build_match_out(match, db, user),
            custody_record=None,
            locked=left == 0,
            attempts_left=left,
        )

    match.failed_claim_attempts = 0

    match.status = MatchStatus.VERIFIED
    # Stash who's coming to collect it and how to reach them -- admin needs
    # this at handover time to write the real CustodyRecord (see
    # custody.py's confirm_handover).
    match.pending_claimant_name = payload.claimant_name
    match.pending_claimant_contact = payload.claimant_contact
    match.pending_claimant_notes = payload.notes
    match.pending_claimant_registration_number = payload.claimant_registration_number
    db.commit()
    db.refresh(match)

    await sio.emit(
        "match:verified",
        {
            "match_id": str(match.id),
            "item_name": found_report.title,
            "claimant_name": payload.claimant_name,
        },
    )

    return ClaimResponse(
        verified=True,
        message=(
            f"Verified! Go collect this item from admin"
            f"{f' at {found_report.collection_point}' if found_report.collection_point else ''}."
        ),
        match=_build_match_out(match, db, user),
        custody_record=None,
        collection_point=found_report.collection_point,
    )


@router.post("/{match_id}/disambiguate", response_model=List[MatchOut])
async def resolve_disambiguation(match_id: str, db: Session = Depends(get_db)):
    """
    Forced-choice resolution: the user was shown every NEEDS_DISAMBIGUATION
    candidate for this lost_report_id side by side (with their generated
    disambiguation_question) and picked THIS one as their item. Promote it
    back to a normal CANDIDATE (so ClaimForm/verify_claim proceeds as
    usual) and reject the rest of the cluster it competed against.
    """
    chosen = db.query(Match).filter(Match.id == match_id).first()
    if not chosen:
        raise HTTPException(404, "Match not found")
    if chosen.status != MatchStatus.NEEDS_DISAMBIGUATION:
        raise HTTPException(400, "This match isn't awaiting disambiguation.")

    cluster = (
        db.query(Match)
        .filter(
            Match.lost_report_id == chosen.lost_report_id,
            Match.status == MatchStatus.NEEDS_DISAMBIGUATION,
        )
        .all()
    )

    for m in cluster:
        is_chosen = m.id == chosen.id
        m.status = MatchStatus.CANDIDATE if is_chosen else MatchStatus.REJECTED
        m.disambiguation_answer = "chosen" if is_chosen else "not chosen"

    db.commit()
    for m in cluster:
        db.refresh(m)

    return cluster