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
from sqlalchemy.orm import Session, aliased

from app.core.config import settings
from app.core.email import send_email
from app.db.session import get_db
from app.models.custody import CustodyRecord
from app.models.match import Match, MatchStatus
from app.models.report import Report, ReportStatus
from app.models.user import User
from app.routers.auth import get_current_user, require_admin
from app.routers.schemas import (
    AdminVerifyRequest,
    CustodyRecordOut,
    PendingPickupOut,
    ReporterInfoOut,
    MyClaimOut,
)
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


@router.get("/mine/claims", response_model=List[MyClaimOut])
def list_my_claims(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Everything the logged-in user has claimed, at ANY stage -- this is
    what powers the "Things I claimed" section on their profile. Two
    different underlying states get merged into one timeline here,
    since from the claimant's point of view both count as "claimed":

      - "pending": match.status == VERIFIED -- they answered the
        verification question correctly, but admin hasn't physically
        handed the item over yet. No CustodyRecord exists for these
        yet (see matches.py's verify_claim), so they're pulled straight
        from Match.
      - "completed": an actual CustodyRecord already exists -- the item
        has physically changed hands (see confirm_handover below).

    Pending items are listed first (they're the ones needing action),
    then completed ones most-recent-first.

    Each row also carries match_id -- distinct from `id`, which stays
    match id for pending rows but custody-record id for completed rows
    (kept as-is for backward compatibility) -- so the frontend has one
    reliable field to show/reference regardless of which stage the
    claim is in.
    """
    out = []

    pending_matches = (
        db.query(Match)
        .join(Report, Report.id == Match.lost_report_id)
        .filter(Report.reporter_id == user.id, Match.status == MatchStatus.VERIFIED)
        .order_by(Match.updated_at.desc())
        .all()
    )
    for match in pending_matches:
        found_report = db.query(Report).filter(Report.id == match.found_report_id).first()
        if not found_report:
            continue
        out.append(
            MyClaimOut(
                id=str(match.id),
                match_id=str(match.id),
                item_name=found_report.title,
                status="pending",
                handover_datetime=None,
                collection_point=found_report.collection_point,
            )
        )

    # CustodyRecord only stores item_name, not collection_point -- pull that
    # from the found report via Match. Report is joined twice here (once as
    # the lost report, to check ownership; once as the found report, for
    # collection_point), so both need aliasing.
    LostReport = aliased(Report)
    FoundReport = aliased(Report)
    completed_rows = (
        db.query(CustodyRecord, FoundReport.collection_point)
        .join(Match, Match.id == CustodyRecord.match_id)
        .join(LostReport, LostReport.id == Match.lost_report_id)
        .join(FoundReport, FoundReport.id == Match.found_report_id)
        .filter(LostReport.reporter_id == user.id)
        .order_by(CustodyRecord.handover_datetime.desc())
        .all()
    )
    for record, collection_point in completed_rows:
        out.append(
            MyClaimOut(
                id=str(record.id),
                match_id=str(record.match_id),
                item_name=record.item_name,
                status="completed",
                handover_datetime=record.handover_datetime,
                collection_point=collection_point,
            )
        )

    return out


@router.get("/{record_id}", response_model=CustodyRecordOut)
def get_custody_record(record_id: str, db: Session = Depends(get_db)):
    record = db.query(CustodyRecord).filter(CustodyRecord.id == record_id).first()
    if not record:
        raise HTTPException(404, "Custody record not found")
    return record


def _pending_pickup_out(match: Match, db: Session) -> PendingPickupOut | None:
    """Shape one VERIFIED match into the admin pickup-queue row. Returns
    None if either underlying report has since been deleted."""
    found_report = db.query(Report).filter(Report.id == match.found_report_id).first()
    lost_report = db.query(Report).filter(Report.id == match.lost_report_id).first()
    if not found_report or not lost_report:
        return None

    finder = db.query(User).filter(User.id == found_report.reporter_id).first() if found_report.reporter_id else None
    owner = db.query(User).filter(User.id == lost_report.reporter_id).first() if lost_report.reporter_id else None

    return PendingPickupOut(
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
    return [row for row in (_pending_pickup_out(m, db) for m in matches) if row]


@router.post("/admin/{match_id}/verify", response_model=PendingPickupOut)
async def admin_verify_claim(
    match_id: str,
    payload: AdminVerifyRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Admin-only. Verification done in person: a student failed the online
    check (or ran out of attempts and got locked), came to the desk, and
    proved the item is theirs some other way. The admin fills in the
    claimant's identity details here and this stands in for the answered
    verification question -- the match jumps to VERIFIED and lands in the
    pickup queue, exactly as a successful online claim would, so the admin
    can then hand it over via the usual "Mark handed over".

    Resets the failed-attempt counter (so nothing stays stuck "locked")
    and records that this was an admin-assisted verification.
    """
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise HTTPException(404, "Match not found")
    if match.status == MatchStatus.CONFIRMED:
        raise HTTPException(400, "This item has already been handed over.")
    if match.status == MatchStatus.REJECTED:
        raise HTTPException(400, "This match was rejected and can no longer be claimed.")

    found_report = db.query(Report).filter(Report.id == match.found_report_id).first()
    lost_report = db.query(Report).filter(Report.id == match.lost_report_id).first()
    if not found_report or not lost_report:
        raise HTTPException(404, "One of the reports behind this match no longer exists")

    match.pending_claimant_name = payload.claimant_name.strip()
    match.pending_claimant_contact = (payload.claimant_contact or "").strip() or None
    match.pending_claimant_notes = (payload.notes or "").strip() or None
    match.pending_claimant_registration_number = (
        (payload.claimant_registration_number or "").strip().upper() or None
    )
    match.status = MatchStatus.VERIFIED
    match.verified_by_admin = "true"
    match.failed_claim_attempts = 0
    db.commit()
    db.refresh(match)

    await sio.emit(
        "match:verified",
        {
            "match_id": str(match.id),
            "item_name": found_report.title,
            "claimant_name": match.pending_claimant_name,
        },
    )

    return _pending_pickup_out(match, db)


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