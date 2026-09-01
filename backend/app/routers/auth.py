"""
Auth endpoints.

Two ways an account can exist:
  1. Admin pre-seeds a row (see seed_users.py / a future admin-add-user
     tool) with just an email -- registration_number left blank.
  2. A student signs up themselves via POST /auth/request-access with an
     email that has no existing row at all -- a fresh account is created
     right there.

Either way, the account starts with no password (password_hash null,
must_set_password true). Full flow:

  1. POST /auth/request-access {email, registration_number}
     - Must be a @vitstudent.ac.in address.
     - If no row exists for the email, creates one (this is what makes
       self-signup possible).
     - If a row exists with no registration_number yet (admin-seeded),
       this submission claims it.
     - If a row exists with a registration_number already set, this
       submission must match it exactly, or it's rejected.
     Either way, on success generates a temp password, emails it (see
     core/email.py), and marks the account must_set_password.
  2. POST /auth/login {email, password}  -- works with the temp password
     too. Always returns a JWT; must_set_password in the response tells
     the frontend whether to force a "set new password" screen before
     letting them do anything else.
  3. POST /auth/set-password {new_password} -- JWT-protected (the token
     from step 2 works even though must_set_password is still true --
     this is the one action they're allowed to take before setting a
     real password). Clears must_set_password.

Note on identity: registration_number alone isn't proof of anything --
anyone could type in someone else's. The real verification is the email
loop: only whoever controls the @vitstudent.ac.in inbox ever sees the
temp password, so only they can actually log in. registration_number is
just there to (a) let admin-seeded rows get filled in by the right
person, and (b) catch someone fat-fingering their own number.
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
    registration_number: str


class ForgotPasswordPayload(BaseModel):
    email: str


class LoginPayload(BaseModel):
    email: str
    password: str


class SetPasswordPayload(BaseModel):
    new_password: str


class ChangePasswordPayload(BaseModel):
    old_password: str
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


def get_current_user_optional(
    authorization: Optional[str] = Header(None), db: Session = Depends(get_db)
) -> Optional[User]:
    """Same as get_current_user, but returns None instead of raising for
    anonymous/invalid requests. Used by endpoints like GET /matches/{id}
    that work for anyone but reveal extra gated fields only when the
    caller is logged in and authorized -- see matches.py."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    user_id = decode_access_token(authorization.removeprefix("Bearer ").strip())
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def _issue_temp_password(user: User, db: Session, reason: str) -> None:
    """Shared by /request-access (first-time signup) and /forgot-password
    (already used the app, forgot their password) -- both are really the
    same action: mint a fresh temp password, email it, force a
    set-password screen on next login."""
    temp_password = generate_temp_password()
    user.password_hash = hash_password(temp_password)
    user.must_set_password = "true"
    db.commit()

    send_email(
        to_email=user.email,
        subject="Your FindIt Campus login",
        body=(
            "Hi,\n\n"
            f"{reason}\n\n"
            f"Your temporary password is: {temp_password}\n\n"
            "Log in with this at the FindIt Campus site -- you'll be asked "
            "to set a real password right away, before you can do anything else.\n\n"
            "If you didn't request this, you can ignore this email."
        ),
    )


@router.post("/request-access")
def request_access(payload: RequestAccessPayload, db: Session = Depends(get_db)):
    """
    Signup / first-time access for a @vitstudent.ac.in email.

    - If a row already exists for the email (admin-seeded, or a previous
      partial signup) with no registration_number yet, this claims it.
    - If a row exists with a registration_number already set, this must
      match it, or the request is rejected.
    - If NO row exists at all, a brand-new account is created here --
      this is what makes self-signup possible instead of admin-only.
    """
    email = payload.email.strip().lower()
    reg_number = payload.registration_number.strip()
    if not is_college_email(email):
        raise HTTPException(400, f"Only @{ALLOWED_EMAIL_DOMAIN} email addresses can be used.")
    if not reg_number:
        raise HTTPException(400, "Registration number is required.")

    user = db.query(User).filter(User.email == email).first()

    if user is None:
        # Brand-new student, no admin-seeded row -- make sure this
        # registration number isn't already tied to a different account
        # before creating a fresh one.
        existing_reg = db.query(User).filter(User.registration_number == reg_number).first()
        if existing_reg:
            raise HTTPException(400, "That registration number is already registered to an account.")

        user = User(email=email, registration_number=reg_number)
        db.add(user)
        db.commit()
        db.refresh(user)
    elif not user.registration_number:
        # First person to submit this email claims the registration
        # number that goes with it.
        user.registration_number = reg_number
    elif user.registration_number != reg_number:
        raise HTTPException(400, "That registration number doesn't match our records for this email.")

    _issue_temp_password(user, db, reason="You requested access to your FindIt Campus account.")
    return {"message": "A temporary password has been emailed to you."}


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordPayload, db: Session = Depends(get_db)):
    """Already has an account and has logged in before, but forgot their
    password. Same mechanism as request_access (fresh temp password by
    email, forced set-password on next login) -- kept as a separate route
    so the frontend can show a distinct "Forgot password" screen with its
    own copy, separate from the first-time "Sign up" screen."""
    email = payload.email.strip().lower()
    if not is_college_email(email):
        raise HTTPException(400, f"Only @{ALLOWED_EMAIL_DOMAIN} email addresses can be used.")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        # Deliberately vague about *why* -- doesn't confirm/deny whether
        # an email is registered, so this can't be used to enumerate the
        # user list.
        raise HTTPException(404, "No account found for this email. Ask an admin to add you.")

    _issue_temp_password(user, db, reason="You requested a password reset for your FindIt Campus account.")
    return {"message": "A temporary password has been emailed to you. Log in with it, then set a new password."}


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


@router.post("/change-password")
def change_password(
    payload: ChangePasswordPayload,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """For someone already logged in who wants to change their password
    on purpose (as opposed to /set-password, which is specifically the
    forced first-login/post-reset flow). Requires the current password so
    someone who grabs an already-open session can't lock the real owner
    out just by changing it."""
    if not user.password_hash or not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(401, "Current password is incorrect.")
    if len(payload.new_password) < 8:
        raise HTTPException(400, "New password must be at least 8 characters.")

    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"message": "Password changed."}


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