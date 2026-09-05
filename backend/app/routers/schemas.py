"""
Pydantic schemas -- these define what JSON shape the API accepts/returns.
Kept separate from the SQLAlchemy models (app/models/) on purpose: DB
models describe storage, schemas describe the wire format. E.g. we never
want `hidden_answer` to leak out in a response schema, even though it's
a real DB column -- separating the two makes that an explicit choice.
"""

from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def _assume_utc(v):
    """
    The DB columns backing these fields (created_at, item_datetime,
    handover_datetime, verified_at -- see app/models/report.py and
    app/models/custody.py) are plain `DateTime`, populated via
    `datetime.utcnow()`. That gives a real UTC instant, but as a *naive*
    Python datetime -- no timezone attached. Pydantic then serializes it
    to JSON with no "Z"/"+00:00" suffix (e.g. "2026-09-05T14:20:00"),
    and the frontend's `new Date(...)` interprets a suffix-less string as
    LOCAL time, not UTC -- silently shifting every timestamp by the
    browser's UTC offset (5.5 hours for IST).

    This tags the value as UTC before it leaves the API, without touching
    how it's stored -- so the JSON always carries an explicit offset and
    the frontend parses it correctly.
    """
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v


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
    # LOST reports only -- when the owner lost it (must be within the last
    # week; validated in create_report). FOUND reports ignore this and use
    # the submission time.
    item_datetime: Optional[datetime] = None
    # Only relevant when report_type == "found": the question a claimant
    # must answer before contact info is revealed.
    hidden_question: Optional[str] = None
    hidden_answer: Optional[str] = None
    # Only relevant when report_type == "found": where the finder physically
    # handed the item to admin, e.g. "Main Gate security desk". This is
    # what the owner is told once verified -- see ReportOut.collection_point.
    collection_point: Optional[str] = None


class VerificationCheckRequest(BaseModel):
    """Advisory pre-submit check payload -- everything a claimant would see,
    plus the proposed verification question + answer."""
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    color: Optional[str] = None
    brand: Optional[str] = None
    location_name: Optional[str] = None
    hidden_question: Optional[str] = None
    hidden_answer: Optional[str] = None


class VerificationCheckResponse(BaseModel):
    leaked: bool
    reason: str = ""


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

    @field_validator("item_datetime", "created_at", mode="before")
    @classmethod
    def _tag_utc(cls, v):
        return _assume_utc(v)

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

    @field_validator("handover_datetime", mode="before")
    @classmethod
    def _tag_utc(cls, v):
        return _assume_utc(v)


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
    answer the finder's hidden_question correctly. claimant_name,
    claimant_registration_number, and claimant_email are all required so
    admin has a filled-in identity record to check the claimant against
    at physical handover, on top of the hidden-answer check itself.
    claimant_registration_number and claimant_email are cross-checked
    against the logged-in user's own account in verify_claim -- they
    can't be used to claim as someone else. claimant_contact (a second,
    optional contact detail) is the only optional field."""
    claimant_name: str
    claimant_registration_number: str
    claimant_email: str
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

    @field_validator("handover_datetime", mode="before")
    @classmethod
    def _tag_utc(cls, v):
        return _assume_utc(v)

    class Config:
        from_attributes = True


class CheckAnswerRequest(BaseModel):
    """Step 1 of the two-step claim form: just the verification-question
    answer, nothing else. Lets the frontend tell the claimant right away
    whether they got it right, before asking them to fill in their name,
    registration number, etc. Doesn't touch match/report state either
    way -- see check_answer below."""
    hidden_answer: str


class CheckAnswerResponse(BaseModel):
    correct: bool
    # Set once the claimant has burned all their attempts (see
    # MAX_CLAIM_ATTEMPTS in matches.py) -- the frontend then stops offering
    # a retry and points them at the admin desk instead.
    locked: bool = False
    attempts_left: Optional[int] = None
    # Human-readable outcome for a wrong/locked answer (the frontend shows
    # this verbatim). None on a correct answer.
    message: Optional[str] = None


class AdminVerifyRequest(BaseModel):
    """An admin completing verification on a student's behalf (they failed
    online / got locked out, but showed proof in person). The admin types
    the claimant's identity details in for the record; no hidden answer is
    needed -- the admin IS the verification here."""
    claimant_name: str
    claimant_registration_number: Optional[str] = None
    claimant_email: Optional[str] = None
    claimant_contact: Optional[str] = None
    notes: Optional[str] = None


class MyClaimOut(BaseModel):
    """One row in the logged-in user's own 'Things I claimed' list --
    merges VERIFIED-but-not-yet-handed-over matches (status='pending')
    with actual completed handovers (status='completed') into a single
    timeline, since from the claimant's point of view both are 'things
    I claimed', just at different stages. See custody.py's
    list_my_claims.

    `id` stays as-is for backward compatibility (match id for pending
    rows, custody record id for completed rows) -- `match_id` is the
    field the frontend should actually use to display/reference the
    underlying match, since it's reliably the same kind of id in both
    branches.
    """
    id: str
    match_id: str
    item_name: str
    status: str  # "pending" | "completed"
    handover_datetime: Optional[datetime] = None
    collection_point: Optional[str] = None

    @field_validator("handover_datetime", mode="before")
    @classmethod
    def _tag_utc(cls, v):
        return _assume_utc(v)


class ClaimResponse(BaseModel):
    verified: bool
    message: str
    match: Optional[MatchOut] = None
    custody_record: Optional[CustodyRecordOut] = None
    # Only set when verified=true -- where the owner needs to go to
    # physically collect the item from admin. Mirrors the found report's
    # collection_point so the frontend doesn't need a second fetch.
    collection_point: Optional[str] = None
    # True once all attempts are used up -- online claiming is closed for
    # this match and the claimant must verify in person with an admin.
    locked: bool = False
    attempts_left: Optional[int] = None


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

    @field_validator("verified_at", mode="before")
    @classmethod
    def _tag_utc(cls, v):
        return _assume_utc(v)

    class Config:
        from_attributes = True