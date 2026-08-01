"""
Report = one lost OR found submission. Same table for both, distinguished
by `report_type` -- this mirrors your abstract: "supports lost and found
reports with text, photos, location and date/time".

text_embedding / image_embedding are stored via pgvector so Postgres can
do fast nearest-neighbour search directly in SQL (no need to pull every
row into Python to compare). They're nullable because a report might be
missing a photo (fusion.py already handles that as a missing signal).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, Enum, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.db.session import Base


class ReportType(str, enum.Enum):
    LOST = "lost"
    FOUND = "found"


class ReportStatus(str, enum.Enum):
    OPEN = "open"           # still searching for a match
    MATCHED = "matched"     # a candidate match exists, pending verification
    RESOLVED = "resolved"   # item returned to owner, custody record closed
    ESCALATED = "escalated" # unclaimed high-risk item (ID/phone/docs), flagged


class Report(Base):
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_type = Column(Enum(ReportType), nullable=False)
    status = Column(Enum(ReportStatus), default=ReportStatus.OPEN, nullable=False)

    # Core report content
    title = Column(String(200), nullable=False)          # e.g. "Black wallet"
    description = Column(Text, nullable=False)            # free-text description
    category = Column(String(100), nullable=True)         # e.g. "wallet", "phone", "ID card"
    color = Column(String(50), nullable=True)
    brand = Column(String(100), nullable=True)

    # High-risk items (ID, phone, academic docs) get flagged for priority handling
    is_high_risk = Column(String(5), default="false")     # "true"/"false" -- simple flag

    # Photos: paths to uploaded images (local disk or cloud storage URLs)
    photo_paths = Column(ARRAY(String), default=list)

    # Location + time
    location_name = Column(String(200), nullable=True)    # e.g. "Library, 2nd floor"
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    item_datetime = Column(DateTime, nullable=False)       # when lost/found

    # Embeddings for matching (nullable -- fusion.py handles missing signals)
    text_embedding = Column(Vector(384), nullable=True)    # from Sentence-Transformers
    image_embedding = Column(Vector(512), nullable=True)   # from CLIP

    # Asymmetric verification: only used when report_type == FOUND.
    # This question/answer never appears in the public report -- it's what
    # a claimant must answer correctly before contact info is revealed.
    hidden_question = Column(Text, nullable=True)
    hidden_answer = Column(Text, nullable=True)

    # Reporter (nullable for now until auth is wired up)
    reporter_id = Column(UUID(as_uuid=True), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    matches_as_lost = relationship(
        "Match", foreign_keys="Match.lost_report_id", back_populates="lost_report"
    )
    matches_as_found = relationship(
        "Match", foreign_keys="Match.found_report_id", back_populates="found_report"
    )