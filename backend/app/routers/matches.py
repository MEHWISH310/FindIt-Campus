"""
POST /matches/find/{report_id} runs the actual matching pipeline:
  1. pull the report + every opposite-type OPEN report
  2. score each pair with fusion.composite_score()
  3. save the results as Match rows, sorted best-first

Calibration (turning raw_score into a probability) is intentionally
optional here -- until you've trained MatchCalibrator on real labelled
pairs (your evaluation phase), match_probability stays null and the UI
should just show raw_score/ranking. Wire in a trained, persisted
calibrator once you have one (pickle it, load it here).
"""

import math
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.report import Report, ReportType, ReportStatus
from app.models.match import Match, MatchStatus
from app.models.custody import CustodyRecord
from app.routers.schemas import MatchOut, ClaimRequest, ClaimResponse
from app.matching.embeddings import cosine_sim
from app.matching.fusion import ReportSignals, composite_score
from app.realtime import sio

router = APIRouter(prefix="/matches", tags=["matches"])

# If the top two candidates' raw scores are within this margin, trigger
# disambiguation instead of auto-picking the top one (per your abstract:
# "if the leading candidates are not too far apart... asks a targeted
# disambiguation question").
DISAMBIGUATION_MARGIN = 0.05

# A raw_score at or above this is worth a real-time "match found" ping --
# below this it's a weak candidate that would just be noise in a notification.
NOTIFY_SCORE_THRESHOLD = 0.6


def _haversine_meters(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance between two lat/lon points, in meters."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


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

    # Decide status: needs disambiguation if top 2 are too close
    needs_disambiguation = (
        len(scored) >= 2 and (scored[0][1]["score"] - scored[1][1]["score"]) < DISAMBIGUATION_MARGIN
    )

    saved_matches = []
    for candidate, result in scored[:5]:  # keep top 5 candidates
        lost_id = report.id if report.report_type == ReportType.LOST else candidate.id
        found_id = candidate.id if report.report_type == ReportType.LOST else report.id

        match = Match(
            lost_report_id=lost_id,
            found_report_id=found_id,
            raw_score=result["score"],
            used_signals=result["used_signals"],
            signal_weights=result["weights"],
            status=MatchStatus.NEEDS_DISAMBIGUATION if needs_disambiguation else MatchStatus.CANDIDATE,
        )
        db.add(match)
        saved_matches.append(match)

    db.commit()
    for m in saved_matches:
        db.refresh(m)

    # Real-time "match found" ping -- only for a genuinely strong top
    # candidate, so this doesn't fire for every low-confidence guess.
    if scored and scored[0][1]["score"] >= NOTIFY_SCORE_THRESHOLD:
        await sio.emit(
            "match:found",
            {
                "report_id": str(report.id),
                "report_title": report.title,
                "score": round(scored[0][1]["score"], 3),
                "needs_disambiguation": needs_disambiguation,
            },
        )

    return saved_matches


@router.post("/{match_id}/verify", response_model=ClaimResponse)
async def verify_claim(match_id: str, payload: ClaimRequest, db: Session = Depends(get_db)):
    """
    Asymmetric verification (per your abstract): whoever is claiming the
    item must answer the FOUND report's hidden_question correctly -- we
    never show them hidden_answer, we just check equality server-side.

    On a correct answer:
      - match.status -> CONFIRMED
      - both the lost and found reports -> RESOLVED
      - a CustodyRecord is written as the audit trail of the handover

    On a wrong answer: 200 with verified=false (not a 4xx -- this is an
    expected outcome the frontend needs to render inline, not an error),
    match/report state is left untouched so they can retry.

    No staff/auth layer exists yet, so verifier_name is a placeholder --
    swap this for the logged-in staff/volunteer's name once auth (backlog
    Task 8) lands.
    """
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(404, "Match not found")

    if match.status == MatchStatus.CONFIRMED:
        raise HTTPException(400, "This match has already been confirmed and claimed.")
    if match.status == MatchStatus.REJECTED:
        raise HTTPException(400, "This match was rejected and can no longer be claimed.")

    found_report = db.query(Report).filter(Report.id == match.found_report_id).first()
    lost_report = db.query(Report).filter(Report.id == match.lost_report_id).first()
    if not found_report or not lost_report:
        raise HTTPException(404, "One of the reports behind this match no longer exists")

    if not found_report.hidden_answer:
        raise HTTPException(400, "This found report has no verification question set up")

    # Case/whitespace-insensitive so "iPhone" vs "iphone" doesn't fail
    # someone over a genuinely correct answer.
    is_correct = payload.hidden_answer.strip().lower() == found_report.hidden_answer.strip().lower()

    if not is_correct:
        return ClaimResponse(
            verified=False,
            message="That answer doesn't match. You can try again.",
            match=match,
            custody_record=None,
        )

    match.status = MatchStatus.CONFIRMED
    found_report.status = ReportStatus.RESOLVED
    lost_report.status = ReportStatus.RESOLVED

    record = CustodyRecord(
        match_id=match.id,
        item_name=found_report.title,
        claimant_name=payload.claimant_name,
        claimant_contact=payload.claimant_contact,
        verifier_name="Self-service verification (no staff auth yet)",
        notes=payload.notes,
        identity_verified="true",
    )
    db.add(record)
    db.commit()
    db.refresh(match)
    db.refresh(record)

    await sio.emit(
        "item:claimed",
        {
            "match_id": str(match.id),
            "item_name": record.item_name,
            "claimant_name": record.claimant_name,
        },
    )

    return ClaimResponse(
        verified=True,
        message="Verified! This item has been marked as returned to its owner.",
        match=match,
        custody_record=record,
    )