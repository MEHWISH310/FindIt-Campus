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
    CONFIRMED = "confirmed"            # claimant verified successfully
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

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lost_report = relationship("Report", foreign_keys=[lost_report_id], back_populates="matches_as_lost")
    found_report = relationship("Report", foreign_keys=[found_report_id], back_populates="matches_as_found")