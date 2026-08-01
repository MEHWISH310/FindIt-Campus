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

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.report import Report, ReportType
from app.routers.schemas import ReportCreate, ReportOut
from app.matching.embeddings import encode_text

router = APIRouter(prefix="/reports", tags=["reports"])


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
    return query.order_by(Report.created_at.desc()).all()


@router.get("/{report_id}", response_model=ReportOut)
def get_report(report_id: str, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")
    return report