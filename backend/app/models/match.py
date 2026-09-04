"""
Match = one candidate pairing between a lost report and a found report,
produced by fusion.py + calibration.py. Kept as its own table (rather than
recomputing on the fly every time) so:
  1. you have an audit trail of what the system suggested and when
  2. the disambiguation flow can ask a follow-up question and update
     the SAME match record instead of losing context
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, Float, DateTime, Enum, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class MatchStatus(str, enum.Enum):
    CANDIDATE = "candidate"            # system suggested it, nobody's acted yet
    NEEDS_DISAMBIGUATION = "needs_disambiguation"  # top candidates too close, asked a follow-up
    # Claimant answered the hidden_question correctly, but the item hasn't
    # physically changed hands yet -- it's still sitting with admin. The
    # owner sees a persistent "go collect it from admin" status until an
    # admin marks the handover done (see custody.py's confirm_handover),
    # which is what actually moves this to CONFIRMED.
    VERIFIED = "verified"
    CONFIRMED = "confirmed"            # admin has physically handed the item over
    REJECTED = "rejected"              # claimant failed verification, or a human rejected it


class Match(Base):
    __tablename__ = "matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    lost_report_id = Column(UUID(as_uuid=True), ForeignKey("reports.id"), nullable=False)
    found_report_id = Column(UUID(as_uuid=True), ForeignKey("reports.id"), nullable=False)

    # Raw composite score from fusion.composite_score() -- see backend/app/matching/fusion.py
    raw_score = Column(Float, nullable=False)
    # Calibrated probability from calibration.MatchCalibrator -- interpretable 0-1
    match_probability = Column(Float, nullable=True)

    # Which signals were actually used (text/image/geo/time) -- from fusion.py's
    # "used_signals" output. Stored as JSON so the UI can show "matched on
    # text + location" and explain low-confidence matches (e.g. no photo available).
    used_signals = Column(JSON, nullable=True)
    signal_weights = Column(JSON, nullable=True)

    status = Column(Enum(MatchStatus), default=MatchStatus.CANDIDATE, nullable=False)

    # If disambiguation was triggered, store the question asked + answer given
    disambiguation_question = Column(String(300), nullable=True)
    disambiguation_answer = Column(String(300), nullable=True)

    # Set when verify_claim succeeds (status -> VERIFIED) -- held here
    # until an admin actually hands the item over (custody.py's
    # confirm_handover), at which point it's copied into the real
    # CustodyRecord. Kept on Match rather than writing a CustodyRecord
    # immediately, since a CustodyRecord is supposed to mean "this
    # physically happened", not "someone typed the right answer online".
    pending_claimant_name = Column(String(200), nullable=True)
    pending_claimant_contact = Column(String(200), nullable=True)
    pending_claimant_notes = Column(String(500), nullable=True)
    # Registration number the claimant typed in on the claim form -- an
    # extra cross-check alongside the hidden_answer, similar in spirit to
    # the registration_number check in /auth/request-access. Verified
    # against the logged-in user's own User.registration_number in
    # verify_claim before this even gets set.
    pending_claimant_registration_number = Column(String(50), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lost_report = relationship("Report", foreign_keys=[lost_report_id], back_populates="matches_as_lost")
    found_report = relationship("Report", foreign_keys=[found_report_id], back_populates="matches_as_found")