"""
CustodyRecord = the audit trail entry created when an item actually
changes hands. Your abstract: "every handover is documented and entered
onto a custody record ... item name, claimant, verifying party, date."

This is deliberately a separate table from Match -- a Match is "we think
these two reports describe the same item"; a CustodyRecord is "this item
was physically handed over, here's proof." Keeping them separate means
you can have confirmed matches that never get physically claimed (item
stays in the found-items office) without polluting the handover log.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


class CustodyRecord(Base):
    __tablename__ = "custody_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    match_id = Column(UUID(as_uuid=True), ForeignKey("matches.id"), nullable=False)

    item_name = Column(String(200), nullable=False)
    claimant_name = Column(String(200), nullable=False)
    claimant_contact = Column(String(200), nullable=True)  # phone/email, only revealed post-verification
    verifier_name = Column(String(200), nullable=False)    # staff/volunteer who confirmed handover
    # Which admin account actually clicked "mark handed over" (see
    # custody.py's confirm_handover) -- verifier_name above stays as the
    # human-readable display copy, this is the real FK for auditing.
    admin_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    handover_datetime = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)

    # For high-risk items (ID, phone, docs): redact photos until this is set
    identity_verified = Column(String(5), default="false")  # "true"/"false"