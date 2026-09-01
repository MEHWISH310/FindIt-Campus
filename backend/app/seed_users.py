"""
Seeds the real, pre-registered college accounts (see models/user.py's
docstring -- this app has no public signup, only pre-seeded accounts).

Run with:
    cd backend
    python -m app.seed_users

Idempotent: safe to run more than once. For each email in SEED_ACCOUNTS:
  - if the user doesn't exist yet -> created, with registration_number
    filled in and a starting password set (must_set_password=true, so
    they're forced onto /auth/set-password on first login).
  - if the user already exists -> left completely alone. This script
    never overwrites a password or registration_number for an account
    that's already there, so re-running it after someone has already
    logged in and set their own password can't accidentally reset them.

The starting password is the same for all three (printed below) --
that's fine, since must_set_password forces each of them to replace it
with something private on first login. In production you'd usually mail
this instead of printing it, but request_access()/forgot_password() in
routers/auth.py already cover "email me a temp password" for any account
that's lost or forgotten theirs -- this script's password is just the
very first way in.
"""

from app.db.session import SessionLocal
from app.models.user import User, is_college_email, ALLOWED_EMAIL_DOMAIN
from app.core.security import hash_password

STARTING_PASSWORD = "FindItCampus#2026"

# Real accounts (not dummy data) -- registration numbers as provided.
# Every email is validated against ALLOWED_EMAIL_DOMAIN below; if any of
# these were ever pasted in with a typo'd domain, this script refuses to
# create that one account rather than silently seeding a bad row.
SEED_ACCOUNTS = [
    {"email": "mehwish.2023@vitstudent.ac.in", "registration_number": "23BCE0854", "name": "Mehwish"},
    {"email": "mansi.sharma2023@vitstudent.ac.in", "registration_number": "23BCE0856", "name": "Mansi Sharma"},
    {"email": "aarushi.chaudhary2023@vitstudent.ac.in", "registration_number": "23BCE0905", "name": "Aarushi Chaudhary"},
]


def seed():
    db = SessionLocal()
    created, skipped = [], []
    try:
        for account in SEED_ACCOUNTS:
            email = account["email"].strip().lower()

            if not is_college_email(email):
                print(f"SKIPPED (not an @{ALLOWED_EMAIL_DOMAIN} address): {email}")
                skipped.append(email)
                continue

            existing = db.query(User).filter(User.email == email).first()
            if existing:
                print(f"SKIPPED (already exists, left untouched): {email}")
                skipped.append(email)
                continue

            user = User(
                email=email,
                registration_number=account["registration_number"],
                name=account["name"],
                password_hash=hash_password(STARTING_PASSWORD),
                must_set_password="true",
            )
            db.add(user)
            created.append(email)

        db.commit()
    finally:
        db.close()

    print("\n----- Seed complete -----")
    if created:
        print(f"Created {len(created)} account(s):")
        for email in created:
            print(f"  {email}")
        print(f"\nStarting password for all newly-created accounts: {STARTING_PASSWORD}")
        print("Each one must set their own password on first login (must_set_password=true).")
    if skipped:
        print(f"\nSkipped {len(skipped)} (already existed or invalid domain).")


if __name__ == "__main__":
    seed()