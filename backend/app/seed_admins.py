"""
Seeds the two admin accounts. Run once (locally or against the deployed
DB) with:

    python -m app.seed_admins

Admin accounts are gmail addresses, not @vitstudent.ac.in -- so they can't
go through the normal /auth/request-access flow (that's domain-locked).
Instead this script sets a password directly. /auth/login doesn't check
the email domain at all (only request-access/forgot-password do), so
these accounts can log in immediately with the temp password below --
they'll just be forced through the "set a new password" screen first
time, same as everyone else (must_set_password="true").

Each admin is tied to one Building (see app/models/building.py) --
that's what scopes their "Ready for pickup" queue in custody.py's
list_pending_pickups to their own desk.

Safe to re-run: if a row already exists for an email it just makes sure
is_admin/name/assigned_building are correct rather than creating a
duplicate.
"""

from app.db.session import SessionLocal
from app.core.security import hash_password, generate_temp_password
from app.models.user import User
from app.models.building import Building

ADMINS = [
    {"email": "mehwish310@gmail.com", "name": "PRP Admin", "assigned_building": Building.PRP},
    {"email": "mansisharma9218@gmail.com", "name": "SJT Admin", "assigned_building": Building.SJT},
]

db = SessionLocal()
try:
    for admin in ADMINS:
        email = admin["email"].strip().lower()
        user = db.query(User).filter(User.email == email).first()
        temp_password = generate_temp_password()

        if user is None:
            user = User(
                email=email,
                name=admin["name"],
                is_admin="true",
                assigned_building=admin["assigned_building"],
                password_hash=hash_password(temp_password),
                must_set_password="true",
            )
            db.add(user)
            print(f"Created admin {email} ({admin['assigned_building'].value}) -- temp password: {temp_password}")
        else:
            user.is_admin = "true"
            user.name = admin["name"]
            user.assigned_building = admin["assigned_building"]
            if not user.password_hash:
                user.password_hash = hash_password(temp_password)
                user.must_set_password = "true"
                print(f"Admin {email} already existed, no password -- set temp password: {temp_password}")
            else:
                print(f"Admin {email} already existed -- left password alone, confirmed is_admin/name/{admin['assigned_building'].value}")

    db.commit()
finally:
    db.close()