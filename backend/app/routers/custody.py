"""
Read-only endpoint for the "Claimed items" page: a log of every handover
that's actually happened, written by this router's own confirm_handover
(admin-only -- see below). Deliberately separate from matches.py -- this
router is about the audit trail (CustodyRecord) and the actual physical
handover, not the matching pipeline itself.
"""

import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.email import send_email
from app.db.session import get_db
from app.models.custody import CustodyRecord
from app.models.match import Match, MatchStatus
from app.models.report import Report, ReportStatus
from app.models.user import User
from app.routers.auth import get_current_user, require_admin
from app.routers.schemas import CustodyRecordOut, PendingPickupOut, ReporterInfoOut
from app.matching.redaction import reveal_photos
from app.realtime import sio

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


@router.get("/admin/pending-pickups", response_model=List[PendingPickupOut])
def list_pending_pickups(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Admin-only. Every match that's VERIFIED (claimant answered correctly)
    but not yet CONFIRMED (admin hasn't handed the item over yet) -- this
    is the queue admin works off of at the collection point: look up the
    report's unique id, confirm the person in front of them, hand over,
    click confirm.
    """
    matches = db.query(Match).filter(Match.status == MatchStatus.VERIFIED).order_by(Match.updated_at.asc()).all()

    out = []
    for match in matches:
        found_report = db.query(Report).filter(Report.id == match.found_report_id).first()
        lost_report = db.query(Report).filter(Report.id == match.lost_report_id).first()
        if not found_report or not lost_report:
            continue

        finder = db.query(User).filter(User.id == found_report.reporter_id).first() if found_report.reporter_id else None
        owner = db.query(User).filter(User.id == lost_report.reporter_id).first() if lost_report.reporter_id else None

        out.append(
            PendingPickupOut(
                match_id=match.id,
                item_title=found_report.title,
                category=found_report.category,
                collection_point=found_report.collection_point,
                found_report_id=found_report.id,
                lost_report_id=lost_report.id,
                finder=ReporterInfoOut(id=finder.id, name=finder.name, email=finder.email, phone=finder.phone) if finder else None,
                owner=ReporterInfoOut(id=owner.id, name=owner.name, email=owner.email, phone=owner.phone) if owner else None,
                verified_at=match.updated_at,
            )
        )
    return out


@router.post("/admin/{match_id}/handover", response_model=CustodyRecordOut)
async def confirm_handover(
    match_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Admin-only. The actual physical moment: the owner is standing in
    front of admin, admin has checked the match's unique id and confirms
    this really is their item, and now clicks this to:
      - write the real CustodyRecord (audit trail of the handover)
      - flip match.status -> CONFIRMED, both reports -> RESOLVED
      - un-redact high-risk photos (the item's genuinely back with its
        owner now, no reason to keep the public copy pixelated)
      - email the FINDER that their found item has been successfully
        claimed -- this is the one point in the whole flow that email
        goes out, deliberately after the fact rather than at verification
    """
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(404, "Match not found")
    if match.status != MatchStatus.VERIFIED:
        raise HTTPException(400, "This match isn't in a verified/awaiting-pickup state.")

    found_report = db.query(Report).filter(Report.id == match.found_report_id).first()
    lost_report = db.query(Report).filter(Report.id == match.lost_report_id).first()
    if not found_report or not lost_report:
        raise HTTPException(404, "One of the reports behind this match no longer exists")

    record = CustodyRecord(
        match_id=match.id,
        item_name=found_report.title,
        claimant_name=match.pending_claimant_name or "Unknown",
        claimant_contact=match.pending_claimant_contact,
        verifier_name=admin.name or admin.email,
        admin_id=admin.id,
        notes=match.pending_claimant_notes,
        identity_verified="true",
    )
    db.add(record)

    match.status = MatchStatus.CONFIRMED
    found_report.status = ReportStatus.RESOLVED
    lost_report.status = ReportStatus.RESOLVED

    if found_report.is_high_risk == "true" and found_report.photo_paths:
        report_dir = os.path.join(settings.upload_dir, str(found_report.id))
        filenames = [os.path.basename(p) for p in found_report.photo_paths]
        reveal_photos(report_dir, filenames)

    db.commit()
    db.refresh(record)
    db.refresh(match)

    await sio.emit(
        "item:claimed",
        {
            "match_id": str(match.id),
            "item_name": record.item_name,
            "claimant_name": record.claimant_name,
        },
    )

    if found_report.reporter_id:
        finder = db.query(User).filter(User.id == found_report.reporter_id).first()
        if finder:
            send_email(
                to_email=finder.email,
                subject="Your found item has been claimed",
                body=(
                    f"Hi {finder.name or ''},\n\n"
                    f"The item you reported found (\"{found_report.title}\") has been successfully "
                    f"handed over to its owner by {admin.name or admin.email}.\n\n"
                    "Thanks for helping return it!"
                ),
            )

    return record