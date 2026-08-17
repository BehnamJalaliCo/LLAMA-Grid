import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .config import settings

_password_hasher = PasswordHasher()


def hash_password(value: str) -> str:
    return _password_hasher.hash(value)


def verify_password(value: str, encoded: str) -> bool:
    try:
        return _password_hasher.verify(encoded, value)
    except VerifyMismatchError:
        return False


def issue_session(user_id: str) -> str:
    expires = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
    payload = f"{user_id}.{expires}"
    signature = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def read_session(value: str | None) -> str | None:
    if not value:
        return None
    parts = value.split(".")
    if len(parts) != 3:
        return None
    user_id, expires, signature = parts
    try:
        if int(expires) < int(datetime.now(timezone.utc).timestamp()):
            return None
    except ValueError:
        return None
    payload = f"{user_id}.{expires}"
    expected = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return user_id if hmac.compare_digest(signature, expected) else None


def generate_api_key(prefix: str = "bg") -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def api_key_digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
