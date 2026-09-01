"""
Auth endpoints.

Accounts are pre-seeded (see seed_users.py) -- there's no public
"create account" endpoint here on purpose; only people already added to
the users table can get in. Flow for a first-time (or password-reset)
login:

  1. POST /auth/request-access {email}   -- must already exist in the DB
     and be a @vitstudent.ac.in address. Generates a temp password,
     emails it (see core/email.py), marks the account must_set_password.
  2. POST /auth/login {email, password}  -- works with the temp password
     too. Always returns a JWT; must_set_password in the response tells
     the frontend whether to force a "set new password" screen before
     letting them do anything else.
  3. POST /auth/set-password {new_password} -- JWT-protected (the token
     from step 2 works even though must_set_password is still true --
     this is the one action they're allowed to take before setting a
     real password). Clears must_set_password.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from uuid import UUID

from app.db.session import get_db
from app.models.user import User, is_college_email, ALLOWED_EMAIL_DOMAIN
from app.core.security import (
    hash_password,
    verify_password,
    generate_temp_password,
    create_access_token,
    decode_access_token,
)
from app.core.email import send_email

router = APIRouter(prefix="/auth", tags=["auth"])


class RequestAccessPayload(BaseModel):
    email: str


class LoginPayload(BaseModel):
    email: str
    password: str


class SetPasswordPayload(BaseModel):
    new_password: str


class ProfileUpdatePayload(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    registration_number: Optional[str] = None


class UserOut(BaseModel):
    id: UUID
    email: str
    name: Optional[str]
    phone: Optional[str]
    registration_number: Optional[str]
    must_set_password: bool

    @staticmethod
    def from_model(user: User) -> "UserOut":
        return UserOut(
            id=user.id,
            email=user.email,
            name=user.name,
            phone=user.phone,
            registration_number=user.registration_number,
            must_set_password=user.must_set_password == "true",
        )


class LoginResponse(BaseModel):
    access_token: str
    must_set_password: bool
    user: UserOut


def get_current_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)) -> User:
    """Reads `Authorization: Bearer <token>`. Deliberately allows a user
    whose must_set_password is still true -- individual endpoints decide
    whether that matters (set_password itself must work either way)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Not authenticated")

    token = authorization.removeprefix("Bearer ").strip()
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(401, "Invalid or expired session -- please log in again")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(401, "Invalid session")
    return user


@router.post("/request-access")
def request_access(payload: RequestAccessPayload, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if not is_college_email(email):
        raise HTTPException(400, f"Only @{ALLOWED_EMAIL_DOMAIN} email addresses can be used.")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        # Deliberately vague about *why* -- doesn't confirm/deny whether
        # an email is registered, so this can't be used to enumerate the
        # user list.
        raise HTTPException(404, "No account found for this email. Ask an admin to add you.")

    temp_password = generate_temp_password()
    user.password_hash = hash_password(temp_password)
    user.must_set_password = "true"
    db.commit()

    send_email(
        to_email=user.email,
        subject="Your FindIt Campus login",
        body=(
            "Hi,\n\n"
            f"Your temporary password is: {temp_password}\n\n"
            "Log in with this at the FindIt Campus site -- you'll be asked "
            "to set a real password right away, before you can do anything else.\n\n"
            "If you didn't request this, you can ignore this email."
        ),
    )
    return {"message": "A temporary password has been emailed to you."}


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginPayload, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()

    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        # Same message whether the email doesn't exist or the password's
        # wrong -- don't leak which one it was.
        raise HTTPException(401, "Incorrect email or password.")

    token = create_access_token(str(user.id))
    return LoginResponse(
        access_token=token,
        must_set_password=user.must_set_password == "true",
        user=UserOut.from_model(user),
    )


@router.post("/set-password")
def set_password(
    payload: SetPasswordPayload,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if len(payload.new_password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")

    user.password_hash = hash_password(payload.new_password)
    user.must_set_password = "false"
    db.commit()
    return {"message": "Password updated."}


@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)):
    return UserOut.from_model(user)


@router.patch("/me", response_model=UserOut)
def update_me(
    payload: ProfileUpdatePayload,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.name is not None:
        user.name = payload.name
    if payload.phone is not None:
        user.phone = payload.phone
    if payload.registration_number is not None:
        user.registration_number = payload.registration_number
    db.commit()
    db.refresh(user)
    return UserOut.from_model(user)