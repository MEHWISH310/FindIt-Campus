"""
Endpoints for submitting and listing lost/found reports.

Note: this computes the text embedding as part of report creation on a
worker thread via asyncio.to_thread(), so it never blocks the event loop.

The matching pipeline (run_matching_and_notify -- scoring against every
open opposite-type report, upserting Match rows, and possibly sending a
real-time ping + an email) used to be awaited inline here, which meant the
reporter sat waiting for a full DB scan/scoring pass and a potential SMTP
round-trip before they ever got their report back. It's now fired off as a
background asyncio task (_run_matching_safely) right after the report is
committed: the reporter gets an instant response, and matching/notifying
happens moments later. The background task opens its own DB session,
since the request's `db` session closes as soon as the response is
returned.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import case, and_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db, SessionLocal
from app.models.report import (
    Report,
    ReportType,
    ReportStatus,
    HIGH_RISK_CATEGORIES,
    STALE_DAYS_THRESHOLD,
    ESCALATION_DAYS_THRESHOLD,
)
from app.models.match import Match
from app.matching.leak_check import answer_leaks
from app.matching.verification_guard import llm_leak_check
from app.routers.schemas import (
    ReportCreate,
    ReportOut,
    ReporterInfoOut,
    VerificationCheckRequest,
    VerificationCheckResponse,
)
from app.matching.embeddings import encode_text, encode_images
from app.matching.redaction import redact_photo, originals_dir
from app.realtime import sio
from app.models.user import User
from app.routers.auth import get_current_user, get_current_user_optional, require_admin
from app.routers.matches import run_matching_and_notify

router = APIRouter(prefix="/reports", tags=["reports"])

logger = logging.getLogger("findit.reports")

# Only accept real image types -- anything else gets rejected before it
# ever touches disk or the CLIP model.
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}
MAX_PHOTOS_PER_REPORT = 5
MAX_FILE_SIZE_BYTES = 8 * 1024 * 1024  # 8 MB per photo


def _serialize_report(report: Report, viewer: User | None, db: Session) -> ReportOut:
    """Builds the ReportOut for one report, attaching `reporter` (name/
    email/phone) only when the viewer is an admin. Everyone else gets it
    as null -- reporter_id (just a UUID) stays visible to everyone so the
    frontend can still tell "is this my report", but actual identity is
    admin-only. See ReporterInfoOut's docstring in schemas.py."""
    out = ReportOut.model_validate(report)
    if viewer is not None and viewer.is_admin == "true" and report.reporter_id:
        reporter_user = db.query(User).filter(User.id == report.reporter_id).first()
        if reporter_user:
            out.reporter = ReporterInfoOut(
                id=reporter_user.id,
                name=reporter_user.name,
                email=reporter_user.email,
                phone=reporter_user.phone,
            )
    return out


async def _run_matching_safely(report_id: uuid.UUID):
    """
    Runs the matching pipeline (score against every open opposite-type
    report, upsert Match rows, and -- if warranted -- send the real-time
    "match found" ping and the "possible match" email) as a background
    task, fully decoupled from the create_report request/response cycle.

    Opens its own DB session because the request-scoped `db` (from
    Depends(get_db)) is closed as soon as create_report returns -- by the
    time this task actually runs, that session is gone.

    Swallows and logs any failure here (bad embedding, transient DB
    hiccup, SMTP failure, etc.) rather than letting it propagate: the
    report itself is already safely committed regardless of whether
    matching succeeds, and there's no request left waiting on this to
    raise anything to.
    """
    db = SessionLocal()
    try:
        report = db.query(Report).filter(Report.id == report_id).first()
        if report is None:
            logger.warning("Report %s vanished before background matching ran", report_id)
            return
        await run_matching_and_notify(report, db)
    except Exception:
        logger.exception("Matching pipeline failed for report %s", report_id)
    finally:
        db.close()


@router.post("/", response_model=ReportOut)
async def create_report(
    payload: ReportCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if payload.report_type not in (ReportType.LOST.value, ReportType.FOUND.value):
        raise HTTPException(400, "report_type must be 'lost' or 'found'")

    if payload.report_type == ReportType.FOUND.value and not payload.hidden_question:
        raise HTTPException(
            400,
            "Found reports need a hidden_question for asymmetric verification "
            "(see abstract section on asymmetric verification)",
        )

    if payload.report_type == ReportType.FOUND.value and not payload.hidden_answer:
        raise HTTPException(
            400,
            "Found reports need a hidden_answer too -- a question with no "
            "correct answer means nobody could ever pass verify_claim.",
        )

    # A verification answer that's already sitting in the public text makes
    # the whole check pointless -- anyone browsing could pass it. Reject it
    # here so the finder has to pick something only the owner would know (or
    # make the description less specific).
    if payload.report_type == ReportType.FOUND.value and answer_leaks(
        payload.hidden_answer,
        payload.title,
        payload.description,
        payload.color,
        payload.brand,
        payload.category,
        payload.location_name,
    ):
        raise HTTPException(
            422,
            "Your verification answer is visible in the public description. "
            "Pick something only the true owner would know, or make the "
            "description less specific.",
        )

    # FOUND: the item was already in the finder's hands when they filed, so
    # "when" is just now -- we don't ask. LOST: the owner picks the time,
    # but it can't be in the future or more than two weeks ago (older
    # losses are past the matching/escalation window anyway).
    now = datetime.utcnow()
    if payload.report_type == ReportType.FOUND.value:
        item_datetime = now
    else:
        if payload.item_datetime is None:
            raise HTTPException(400, "Tell us roughly when you lost it.")
        item_datetime = payload.item_datetime
        if item_datetime.tzinfo is not None:
            item_datetime = item_datetime.astimezone(timezone.utc).replace(tzinfo=None)
        if item_datetime > now + timedelta(minutes=5):
            raise HTTPException(422, "The date you lost it can't be in the future.")
        if item_datetime < now - timedelta(days=14):
            raise HTTPException(
                422,
                "Please report items lost within the last two weeks. For an "
                "older loss, contact the lost & found desk.",
            )

    report = Report(
        reporter_id=user.id,
        report_type=payload.report_type,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        color=payload.color,
        brand=payload.brand,
        location_name=payload.location_name,
        latitude=payload.latitude,
        longitude=payload.longitude,
        item_datetime=item_datetime,
        hidden_question=payload.hidden_question,
        hidden_answer=payload.hidden_answer,
        collection_point=payload.collection_point,
        # Auto-detected, not client-supplied -- a reporter shouldn't be able
        # to mark their own item high-risk (or dodge the flag). Matched
        # case-insensitively since category is free text, not a fixed enum.
        is_high_risk="true" if (payload.category or "").strip().lower() in HIGH_RISK_CATEGORIES else "false",
    )

    # Compute text embedding now so it's ready for matching immediately.
    # Run on a worker thread -- encode_text() is a blocking CPU-bound call
    # (Sentence-Transformers/CLIP inference), and running it directly on
    # the event loop would stall every other request the server is
    # handling (including the chatbot's own internal HTTP calls) until it
    # finishes. asyncio.to_thread() hands it to a thread pool instead, so
    # the loop stays free.
    # (Image embedding would be computed similarly once photo upload is wired up.)
    report.text_embedding = await asyncio.to_thread(encode_text, payload.description)

    db.add(report)
    db.commit()
    db.refresh(report)

    # Real-time notification -- see app/realtime.py. This endpoint is async
    # specifically so it can await this; the DB calls above stay plain
    # SQLAlchemy (sync), which is fine at this scale (see docstring at top).
    await sio.emit(
        "report:created",
        {
            "id": str(report.id),
            "report_type": report.report_type.value if hasattr(report.report_type, "value") else report.report_type,
            "title": report.title,
            "is_high_risk": report.is_high_risk == "true",
        },
    )

    # Build the response now, with the report already safely persisted --
    # everything below this point (matching against existing open reports,
    # possibly sending a "match found" ping/email) is fired off as a
    # background task instead of being awaited here, so the reporter isn't
    # stuck waiting on a full DB scan/scoring pass or an SMTP round-trip
    # just to get a "your report was created" response back. See
    # _run_matching_safely's docstring above for the full reasoning, and
    # run_matching_and_notify's docstring in matches.py for why this is
    # the ONLY place matching+notify ever gets triggered (as opposed to
    # find_matches, which just recomputes/displays without notifying).
    out = _serialize_report(report, user, db)
    asyncio.create_task(_run_matching_safely(report.id))
    return out


@router.post("/check-verification", response_model=VerificationCheckResponse)
async def check_verification_question(payload: VerificationCheckRequest):
    """
    Advisory pre-submit check for a FOUND report's verification Q&A: does the
    answer leak from what a claimant can already see? Runs the cheap string
    heuristic first, then an LLM pass for the semantic cases it misses.

    Advisory only -- the frontend shows this as an overridable warning while
    the finder types. The hard gate is the same string check inside
    POST /reports/ (the LLM result never blocks a submission).
    """
    public_text = " ".join(
        p
        for p in (
            payload.title,
            payload.description,
            payload.color,
            payload.brand,
            payload.category,
            payload.location_name,
        )
        if p
    )

    if answer_leaks(
        payload.hidden_answer,
        payload.title,
        payload.description,
        payload.color,
        payload.brand,
        payload.category,
        payload.location_name,
    ):
        return VerificationCheckResponse(
            leaked=True,
            reason="The answer appears in your public description.",
        )

    result = await llm_leak_check(
        public_text=public_text,
        question=payload.hidden_question or "",
        answer=payload.hidden_answer or "",
    )
    return VerificationCheckResponse(
        leaked=result["leaked"],
        reason=result["reason"] or (
            "A claimant could likely answer this from the public description."
            if result["leaked"]
            else ""
        ),
    )


@router.get("/", response_model=List[ReportOut])
def list_reports(
    report_type: str | None = None,
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_current_user_optional),
):
    query = db.query(Report)

    # The Lost/Found pages are a personal view for regular users: they only
    # ever see the reports they filed themselves. Browsing everyone's
    # reports is an admin-only capability (the admin dashboard). Anonymous
    # callers get nothing -- every Lost/Found route sits behind login.
    is_admin = viewer is not None and viewer.is_admin == "true"
    if not is_admin:
        if viewer is None:
            return []
        query = query.filter(Report.reporter_id == viewer.id)

    if report_type:
        query = query.filter(Report.report_type == report_type)

    # Push stale OPEN lost reports (no activity in STALE_DAYS_THRESHOLD days)
    # toward the bottom, without ever hiding them -- fresh reports get
    # visibility first but nothing silently disappears.
    stale_cutoff = datetime.utcnow() - timedelta(days=STALE_DAYS_THRESHOLD)
    stale_rank = case(
        (
            and_(
                Report.report_type == ReportType.LOST,
                Report.status == ReportStatus.OPEN,
                Report.item_datetime < stale_cutoff,
            ),
            1,
        ),
        else_=0,
    )

    reports = query.order_by(stale_rank.asc(), Report.created_at.desc()).all()
    return [_serialize_report(r, viewer, db) for r in reports]


@router.get("/{report_id}", response_model=ReportOut)
def get_report(
    report_id: str,
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_current_user_optional),
):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")
    return _serialize_report(report, viewer, db)


@router.delete("/{report_id}")
def delete_report(
    report_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Lets a reporter delete their own lost/found report. Only the person
    who created it (reporter_id match) can delete it -- not just anyone
    who's logged in. Related Match rows are deleted first since they have
    a foreign key back to reports.id.
    """
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")

    if report.reporter_id != user.id:
        raise HTTPException(403, "You can only delete your own reports")

    # A resolved report has been through a handover and has a CustodyRecord
    # attached to its Match -- that's the audit trail an admin relies on, so
    # it must not be deletable from here. (The frontend also hides the
    # Delete button once a card is resolved; this is the backstop.)
    if report.status == ReportStatus.RESOLVED:
        raise HTTPException(
            409, "This report has already been resolved and is part of the handover record."
        )

    db.query(Match).filter(
        (Match.lost_report_id == report.id) | (Match.found_report_id == report.id)
    ).delete(synchronize_session=False)

    db.delete(report)
    db.commit()
    return {"message": "Report deleted."}


@router.post("/escalate-stale", response_model=List[ReportOut])
async def escalate_stale_high_risk(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Finds FOUND high-risk reports (ID/phone/academic docs) that have sat
    OPEN and unclaimed for ESCALATION_DAYS_THRESHOLD+ days, and flips their
    status to ESCALATED so staff can prioritize following up.

    Admin-only -- it's a moderation action that mutates report state, and
    the "Run escalation check" button that triggers it only shows on the
    admin dashboard. No cron/scheduler is wired into this stack yet (could
    be hooked into a scheduled task later).
    """
    cutoff = datetime.utcnow() - timedelta(days=ESCALATION_DAYS_THRESHOLD)

    candidates = (
        db.query(Report)
        .filter(
            Report.report_type == ReportType.FOUND,
            Report.status == ReportStatus.OPEN,
            Report.is_high_risk == "true",
            Report.item_datetime < cutoff,
        )
        .all()
    )

    for report in candidates:
        report.status = ReportStatus.ESCALATED

    db.commit()
    for report in candidates:
        db.refresh(report)

    if candidates:
        await sio.emit(
            "report:escalated",
            {
                "count": len(candidates),
                "reports": [{"id": str(r.id), "title": r.title} for r in candidates],
            },
        )

    return candidates


@router.post("/{report_id}/photos", response_model=ReportOut)
def upload_photos(
    report_id: str,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """
    Attach 1-5 photos to an existing report and recompute the image
    embedding (mean-pooled across all photos on the report -- see
    app/matching/embeddings.py's encode_images docstring for why).

    Kept as a separate endpoint from report creation (rather than one big
    multipart form) so the frontend can create the report first, get an
    id back, then upload photos with a progress indicator -- and so a
    report can still be submitted even if a photo fails to upload.

    This is a plain `def` (not `async def`) on purpose: FastAPI runs sync
    path operations in its worker thread pool automatically, so the
    blocking encode_images() call below does NOT stall the event loop the
    way a blocking call inside an `async def` would. No asyncio.to_thread
    needed here -- it's already off the loop.
    """
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")

    existing_count = len(report.photo_paths or [])
    if existing_count + len(files) > MAX_PHOTOS_PER_REPORT:
        raise HTTPException(
            400, f"Maximum {MAX_PHOTOS_PER_REPORT} photos per report "
                 f"({existing_count} already uploaded)"
        )

    report_dir = os.path.join(settings.upload_dir, str(report.id))
    os.makedirs(report_dir, exist_ok=True)

    saved_paths = []
    for f in files:
        if f.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(400, f"Unsupported file type: {f.content_type}")

        ext = os.path.splitext(f.filename or "")[1] or ".jpg"
        filename = f"{uuid.uuid4().hex}{ext}"
        disk_path = os.path.join(report_dir, filename)

        contents = f.file.read()
        if len(contents) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(400, f"{f.filename} exceeds 8MB limit")

        with open(disk_path, "wb") as out:
            out.write(contents)

        # Redact high-risk items immediately -- the public /uploads path
        # gets pixelated, the clear original is tucked away in originals/
        # for matching and for reveal-on-claim (see matches.py's
        # verify_claim and matching/redaction.py's docstring for why).
        if report.is_high_risk == "true":
            redact_photo(report_dir, filename)

        # Web-accessible path -- main.py mounts settings.upload_dir at /uploads
        saved_paths.append(f"/uploads/{report.id}/{filename}")

    report.photo_paths = (report.photo_paths or []) + saved_paths

    # Recompute the image embedding across ALL of this report's photos
    # (old + new). Always reads from the clear original when one exists
    # (high-risk reports), never the pixelated public copy -- otherwise
    # redaction would quietly wreck match quality for exactly the items
    # that most need to be found (IDs, phones, documents).
    all_disk_paths = []
    for p in report.photo_paths:
        filename = os.path.basename(p)
        original_path = os.path.join(originals_dir(report_dir), filename)
        if report.is_high_risk == "true" and os.path.exists(original_path):
            all_disk_paths.append(original_path)
        else:
            all_disk_paths.append(os.path.join(report_dir, filename))
    report.image_embedding = encode_images(all_disk_paths)

    db.add(report)
    db.commit()
    db.refresh(report)
    return report