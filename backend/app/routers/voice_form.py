"""
POST /voice-form/extract -- turns one English voice transcript into
suggested values for the existing lost/found form.

It never creates, edits or deletes anything. The only way a report is saved
is still POST /reports/, triggered by the user pressing "Submit report".
Requires login (same get_current_user as the rest of the API), is rate
limited per user, and stores nothing.
"""

import math
from datetime import datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.user import User
from app.routers.auth import get_current_user
from app.voice.extraction import (
    CLIENT_NOW_FORMAT,
    ExtractionError,
    RateLimiter,
    extract_fields,
)

router = APIRouter(prefix="/voice-form", tags=["voice-form"])

# 10 AI calls per user per minute -- generous for a spoken conversation,
# small enough to protect the shared Gemini quota.
_limiter = RateLimiter(max_calls=10, window_seconds=60)

# UTC-12 .. UTC+14 plus slack: a client clock further off than this is wrong.
_MAX_CLOCK_SKEW = timedelta(hours=15)


class CurrentFields(BaseModel):
    """What the form currently holds. hidden_answer is intentionally NOT a
    field here and extras are ignored, so even a buggy client can't push it
    through to Gemini."""

    model_config = ConfigDict(extra="ignore")

    title: str = ""
    description: str = ""
    category: str = ""
    color: str = ""
    brand: str = ""
    location_name: str = ""
    item_datetime: str = ""
    collection_point: str = ""
    hidden_question: str = ""

    @field_validator("*", mode="before")
    @classmethod
    def _coerce(cls, v):
        return "" if v is None else str(v)[:1000]


class VoiceExtractRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    report_type: Literal["lost", "found"]
    transcript: str = Field(..., min_length=1, max_length=1000)
    current_fields: CurrentFields = Field(default_factory=CurrentFields)
    asking_for: Optional[
        Literal[
            "title", "description", "category", "color", "brand",
            "location_name", "item_datetime", "collection_point", "hidden_question",
            "several",
        ]
    ] = None
    # The browser's local time as "YYYY-MM-DDTHH:mm" -- used to resolve
    # "yesterday" etc. in the user's own timezone.
    client_now: str


class VoiceNote(BaseModel):
    field: str
    code: str


class VoiceExtractResponse(BaseModel):
    fields: dict[str, str]
    notes: list[VoiceNote] = []
    # Fields the speaker explicitly asked to change (may replace typed text).
    explicit: list[str] = []
    # The speaker asked to submit. Informational only: nothing is ever submitted here.
    submit_requested: bool = False


@router.post("/extract", response_model=VoiceExtractResponse)
async def extract(payload: VoiceExtractRequest, user: User = Depends(get_current_user)):
    try:
        client_now = datetime.strptime(payload.client_now, CLIENT_NOW_FORMAT)
    except ValueError:
        raise HTTPException(400, "client_now must look like 2026-10-14T15:30")
    # Compare as naive "local" vs UTC: any real timezone is within 15 hours.
    if abs(client_now - datetime.utcnow()) > _MAX_CLOCK_SKEW:
        raise HTTPException(400, "Your device clock looks wrong. Please fix it or fill in the form manually.")

    wait = _limiter.check(str(user.id))
    if wait:
        raise HTTPException(
            429,
            "You're going a bit fast for the voice assistant. Please wait a few seconds.",
            headers={"Retry-After": str(math.ceil(wait))},
        )

    try:
        return await extract_fields(
            report_type=payload.report_type,
            transcript=payload.transcript,
            current_fields=payload.current_fields.model_dump(),
            asking_for=payload.asking_for,
            client_now=client_now,
        )
    except ExtractionError as exc:
        raise HTTPException(exc.status_code, exc.message)
