"""
Read-only endpoint for the "Claimed items" page: a log of every handover
that's actually happened, written by matches.py's POST /matches/{id}/verify.
Deliberately separate from matches.py -- this router is about the audit
trail (CustodyRecord), not the matching pipeline.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.custody import CustodyRecord
from app.models.match import Match
from app.models.report import Report
from app.models.user import User
from app.routers.auth import get_current_user
from app.routers.schemas import CustodyRecordOut

router = APIRouter(prefix="/custody", tags=["custody"])


@router.get("/", response_model=List[CustodyRecordOut])
def list_custody_records(db: Session = Depends(get_db)):
    return (
        db.query(CustodyRecord)
        .order_by(CustodyRecord.handover_datetime.desc())
        .all()
    )


@router.get("/mine", response_model=List[CustodyRecordOut])
def list_my_custody_records(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Handovers where the logged-in user is the claimant -- i.e. the person
    who filed the LOST report behind the match. CustodyRecord itself only
    stores the free-text claimant_name typed into the claim form, so
    ownership is derived by walking match -> lost report -> reporter_id.
    """
    return (
        db.query(CustodyRecord)
        .join(Match, Match.id == CustodyRecord.match_id)
        .join(Report, Report.id == Match.lost_report_id)
        .filter(Report.reporter_id == user.id)
        .order_by(CustodyRecord.handover_datetime.desc())
        .all()
    )


@router.get("/{record_id}", response_model=CustodyRecordOut)
def get_custody_record(record_id: str, db: Session = Depends(get_db)):
    record = db.query(CustodyRecord).filter(CustodyRecord.id == record_id).first()
    if not record:
        raise HTTPException(404, "Custody record not found")
    return record