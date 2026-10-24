"""Password hashing, user storage, session helpers."""
from __future__ import annotations
import hashlib
import hmac
import secrets
from typing import Optional
import data

PBKDF2_ITERATIONS = 100_000

def hash_password(password: str, salt: bytes | None = None) -> str:
    if salt is None: salt = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${h.hex()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256": return False
        salt = bytes.fromhex(salt_hex)
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iters))
        return hmac.compare_digest(h.hex(), hash_hex)
    except Exception:
        return False

def get_user(username: str) -> Optional[dict]:
    return data.get_user(username)

def authenticate(username: str, password: str) -> Optional[dict]:
    user = get_user(username)
    if not user: return None
    if verify_password(password, user.get("password_hash", "")): return user
    return None

def is_admin(user: dict | None) -> bool:
    return bool(user) and user.get("role") == "admin"

def current_user(request) -> Optional[dict]:
    username = request.session.get("username")
    if not username: return None
    return get_user(username)

def users_public_list() -> list[dict]:
    return data.get_users()