"""
User = a college member's account.

Auth model, per how this is actually being rolled out: accounts are
PRE-SEEDED (see seed_users.py), not self-signup -- there's no public
"create account" endpoint. A pre-seeded user starts with no password
(password_hash is null, must_set_password is true). They request one by
email (POST /auth/request-access), get a temp password mailed to them,
log in with it, then are forced to set a real password
(POST /auth/set-password) before doing anything else.

registration_number is nullable on purpose -- seeded accounts start with
it blank and it gets filled in later via the profile endpoint
(PATCH /auth/me), once the real roster of registration numbers is ready.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base

# Only this college's email domain is accepted, everywhere a User is
# created -- seed_users.py, and any future admin "add user" endpoint.
ALLOWED_EMAIL_DOMAIN = "vitstudent.ac.in"


def is_college_email(email: str) -> bool:
    return bool(email) and email.strip().lower().endswith(f"@{ALLOWED_EMAIL_DOMAIN}")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    email = Column(String(255), unique=True, nullable=False, index=True)
    registration_number = Column(String(50), unique=True, nullable=True)
    name = Column(String(200), nullable=True)
    phone = Column(String(20), nullable=True)

    # Null until they set a real password via /auth/set-password.
    password_hash = Column(String(255), nullable=True)
    # "true"/"false" string, same pattern as Report.is_high_risk elsewhere
    # in this codebase -- forces a "set new password" screen on first login.
    must_set_password = Column(String(5), default="true")

    created_at = Column(DateTime, default=datetime.utcnow)