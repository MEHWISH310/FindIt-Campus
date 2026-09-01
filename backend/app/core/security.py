"""
Password hashing (PBKDF2-HMAC-SHA256, stdlib only) + JWT session tokens.

Not using bcrypt/passlib isn't a security downgrade at this project's
scale -- PBKDF2 with a high iteration count and a random salt per user is
a well-established, correct choice, and it means one fewer compiled
dependency (bcrypt needs a C extension) in an already dependency-heavy
requirements.txt.
"""

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Optional

import jwt

from app.core.config import settings

PBKDF2_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    # iterations$salt$hash, all base64 -- self-describing so the iteration
    # count can be bumped later without breaking existing hashes.
    return f"{PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        iterations_str, salt_b64, hash_b64 = stored_hash.split("$")
        iterations = int(iterations_str)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, AttributeError, TypeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    # Constant-time comparison -- a plain `==` here leaks timing info that
    # can be used to guess the hash byte-by-byte.
    return hmac.compare_digest(dk, expected)


def generate_temp_password(length: int = 10) -> str:
    """Random temp password emailed to first-time/reset users. Excludes
    visually-confusable characters (0/O, 1/l/I) since it's read off an
    email and typed back in by hand."""
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> Optional[str]:
    """Returns the user id encoded in the token, or None if it's missing,
    expired, or invalid -- callers just treat None as "not authenticated"."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None