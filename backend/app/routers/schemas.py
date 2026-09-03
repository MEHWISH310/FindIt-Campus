"""
Pydantic schemas -- these define what JSON shape the API accepts/returns.
Kept separate from the SQLAlchemy models (app/models/) on purpose: DB
models describe storage, schemas describe the wire format. E.g. we never
want `hidden_answer` to leak out in a response schema, even though it's
a real DB column -- separating the two makes that an explicit choice.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ReportCreate(BaseModel):
    report_type: str = Field(..., description="'lost' or 'found'")
    title: str
    description: str
    category: Optional[str] = None
    color: Optional[str] = None
    brand: Optional[str] = None
    location_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    item_datetime: datetime
    # Only relevant when report_type == "found": the question a claimant
    # must answer before contact info is revealed.
    hidden_question: Optional[str] = None
    hidden_answer: Optional[str] = None
    # Only relevant when report_type == "found": where the finder physically
    # handed the item to admin, e.g. "Main Gate security desk". This is
    # what the owner is told once verified -- see ReportOut.collection_point.
    collection_point: Optional[str] = None


class ReporterInfoOut(BaseModel):
    """Who filed this report. Only ever populated when the requester is an
    admin (see reports.py's _serialize_report) -- regular users never learn
    who filed a report, even one they're matched against; only admins,
    who physically handle the handover, need to know."""
    id: UUID
    name: Optional[str]
    email: str
    phone: Optional[str]


class ReportOut(BaseModel):
    id: UUID
    # Kept (just the UUID, not identity) so the frontend can still tell
    # "is this my report" (see NoticeCard.jsx/Profile.jsx) without leaking
    # who anyone else is -- a bare UUID isn't resolvable to a name/email by
    # a non-admin. Actual identity only ever comes through in `reporter`
    # below, and only for admins.
    reporter_id: Optional[UUID] = None
    report_type: str
    status: str
    title: str
    description: str
    category: Optional[str]
    color: Optional[str]
    brand: Optional[str]
    location_name: Optional[str]
    item_datetime: datetime
    created_at: datetime
    photo_paths: List[str] = []
    is_high_risk: bool = False
    days_open: int = 0
    is_stale: bool = False
    # Safe to expose (unlike hidden_answer) -- this is what a claimant needs
    # to see in order to know what they're being asked to prove. Only ever
    # set on FOUND reports; null on LOST reports.
    hidden_question: Optional[str] = None
    # Only meaningful on FOUND reports -- where admin is physically holding
    # the item. Shown to the owner once their claim is verified.
    collection_point: Optional[str] = None
    # True while photo_paths point at pixelated copies (high-risk + still
    # unclaimed) -- see matching/redaction.py. Lets the frontend show a
    # "photo hidden until claim is verified" notice instead of just
    # silently rendering a blurry image with no explanation.
    photos_redacted: bool = False
    # Admin-only (see ReporterInfoOut docstring) -- null for everyone else,
    # including the reports someone filed themselves (they already know).
    reporter: Optional[ReporterInfoOut] = None

    @field_validator("is_high_risk", mode="before")
    @classmethod
    def _coerce_high_risk(cls, v):
        # DB stores this as the string "true"/"false" (see models/report.py) --
        # normalize to a real bool before it reaches the frontend.
        if isinstance(v, str):
            return v.lower() == "true"
        return bool(v)

    class Config:
        from_attributes = True


class FoundContactOut(BaseModel):
    """The FOUND reporter's contact details -- only ever attached to a
    MatchOut when the requester is the LOST reporter AND the match is
    CONFIRMED (see matches.py's get_current_user_optional + the
    found_contact assembly in GET /matches/{match_id})."""
    name: Optional[str]
    email: str
    phone: Optional[str]


class ClaimantInfoOut(BaseModel):
    """Who claimed the item -- only ever attached to a MatchOut when the
    requester is the FOUND reporter AND the match is CONFIRMED."""
    claimant_name: str
    claimant_contact: Optional[str]
    handover_datetime: datetime


class MatchOut(BaseModel):
    id: UUID
    lost_report_id: UUID
    found_report_id: UUID
    raw_score: float
    match_probability: Optional[float]
    used_signals: Optional[List[str]]
    status: str
    # Set only when this match is part of a close-scoring cluster (see
    # matches.py's competing_cluster()) -- the frontend shows this as a
    # forced-choice question instead of just a bare score. Null otherwise.
    disambiguation_question: Optional[str] = None
    # Both null unless the requester is authorized to see them -- see the
    # FoundContactOut / ClaimantInfoOut docstrings above.
    found_contact: Optional[FoundContactOut] = None
    claimant_info: Optional[ClaimantInfoOut] = None

    class Config:
        from_attributes = True


class ClaimRequest(BaseModel):
    """Submitted by whoever is trying to claim a FOUND item -- they must
    answer the finder's hidden_question correctly. claimant_contact is
    optional (e.g. they hand it over in person and just want it logged)."""
    claimant_name: str
    claimant_contact: Optional[str] = None
    hidden_answer: str
    notes: Optional[str] = None


class CustodyRecordOut(BaseModel):
    id: UUID
    match_id: UUID
    item_name: str
    claimant_name: str
    claimant_contact: Optional[str]
    verifier_name: str
    handover_datetime: datetime
    notes: Optional[str]
    identity_verified: bool = False

    @field_validator("identity_verified", mode="before")
    @classmethod
    def _coerce_verified(cls, v):
        if isinstance(v, str):
            return v.lower() == "true"
        return bool(v)

    class Config:
        from_attributes = True


class ClaimResponse(BaseModel):
    verified: bool
    message: str
    match: Optional[MatchOut] = None
    custody_record: Optional[CustodyRecordOut] = None
    # Only set when verified=true -- where the owner needs to go to
    # physically collect the item from admin. Mirrors the found report's
    # collection_point so the frontend doesn't need a second fetch.
    collection_point: Optional[str] = None


class PendingPickupOut(BaseModel):
    """One row in the admin dashboard's 'ready for handover' list -- a
    match that's VERIFIED (claimant answered correctly) but not yet
    CONFIRMED (admin hasn't physically handed the item over). Admin-only,
    see custody.py's list_pending_pickups."""
    match_id: UUID
    item_title: str
    category: Optional[str]
    collection_point: Optional[str]
    found_report_id: UUID
    lost_report_id: UUID
    # Who found it and handed it to admin, and who's coming to collect it --
    # only ever shown to admins, this is the whole point of this endpoint.
    finder: Optional[ReporterInfoOut] = None
    owner: Optional[ReporterInfoOut] = None
    verified_at: datetime

    class Config:
        from_attributes = True