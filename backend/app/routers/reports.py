"""
Endpoints for submitting and listing lost/found reports.

Note: this does NOT compute embeddings synchronously inside the request --
loading Sentence-Transformers/CLIP on every single report submission would
make the API slow. In a real deployment you'd push embedding computation
to a background task (FastAPI's BackgroundTasks, or a queue like Celery).
For now this endpoint saves the report and computes the embedding inline,
which is fine for a college-project scale, but is called out here so you
know it's the first thing to move to a background job under real load.
"""

import os
import uuid
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import case, and_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.report import (
    Report,
    ReportType,
    ReportStatus,
    HIGH_RISK_CATEGORIES,
    STALE_DAYS_THRESHOLD,
    ESCALATION_DAYS_THRESHOLD,
)
from app.routers.schemas import ReportCreate, ReportOut
from app.matching.embeddings import encode_text, encode_images

router = APIRouter(prefix="/reports", tags=["reports"])

# Only accept real image types -- anything else gets rejected before it
# ever touches disk or the CLIP model.
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}
MAX_PHOTOS_PER_REPORT = 5
MAX_FILE_SIZE_BYTES = 8 * 1024 * 1024  # 8 MB per photo


@router.post("/", response_model=ReportOut)
def create_report(payload: ReportCreate, db: Session = Depends(get_db)):
    if payload.report_type not in (ReportType.LOST.value, ReportType.FOUND.value):
        raise HTTPException(400, "report_type must be 'lost' or 'found'")

    if payload.report_type == ReportType.FOUND.value and not payload.hidden_question:
        raise HTTPException(
            400,
            "Found reports need a hidden_question for asymmetric verification "
            "(see abstract section on asymmetric verification)",
        )

    report = Report(
        report_type=payload.report_type,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        color=payload.color,
        brand=payload.brand,
        location_name=payload.location_name,
        latitude=payload.latitude,
        longitude=payload.longitude,
        item_datetime=payload.item_datetime,
        hidden_question=payload.hidden_question,
        hidden_answer=payload.hidden_answer,
        # Auto-detected, not client-supplied -- a reporter shouldn't be able
        # to mark their own item high-risk (or dodge the flag). Matched
        # case-insensitively since category is free text, not a fixed enum.
        is_high_risk="true" if (payload.category or "").strip().lower() in HIGH_RISK_CATEGORIES else "false",
    )

    # Compute text embedding now so it's ready for matching immediately.
    # (Image embedding would be computed similarly once photo upload is wired up.)
    report.text_embedding = encode_text(payload.description)

    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.get("/", response_model=List[ReportOut])
def list_reports(report_type: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Report)
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

    return query.order_by(stale_rank.asc(), Report.created_at.desc()).all()


@router.get("/{report_id}", response_model=ReportOut)
def get_report(report_id: str, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")
    return report


@router.post("/escalate-stale", response_model=List[ReportOut])
def escalate_stale_high_risk(db: Session = Depends(get_db)):
    """
    Finds FOUND high-risk reports (ID/phone/academic docs) that have sat
    OPEN and unclaimed for ESCALATION_DAYS_THRESHOLD+ days, and flips their
    status to ESCALATED so staff can prioritize following up.

    No cron/scheduler is wired into this stack yet -- this is triggered
    manually via the "Run escalation check" button on the frontend
    dashboard (or could be hooked into a scheduled task later).
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

        # Web-accessible path -- main.py mounts settings.upload_dir at /uploads
        saved_paths.append(f"/uploads/{report.id}/{filename}")

    report.photo_paths = (report.photo_paths or []) + saved_paths

    # Recompute the image embedding across ALL of this report's photos
    # (old + new) using local disk paths, not the web-facing ones.
    all_disk_paths = [
        os.path.join(settings.upload_dir, str(report.id), os.path.basename(p))
        for p in report.photo_paths
    ]
    report.image_embedding = encode_images(all_disk_paths)

    db.add(report)
    db.commit()
    db.refresh(report)
    return report