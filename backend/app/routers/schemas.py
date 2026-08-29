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


class ReportOut(BaseModel):
    id: UUID
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


class MatchOut(BaseModel):
    id: UUID
    lost_report_id: UUID
    found_report_id: UUID
    raw_score: float
    match_probability: Optional[float]
    used_signals: Optional[List[str]]
    status: str

    class Config:
        from_attributes = True