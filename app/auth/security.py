"""
Password hashing, JWT creation/verification, and short-code (registration
approval code / login OTP) generation and hashing.
"""
import hashlib
import hmac
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Unambiguous alphabet (no 0/O/1/I) for codes an admin has to read aloud or
# retype from an email.
_CODE_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "01OI")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str, expires_minutes: int | None = None) -> tuple[str, int]:
    expire_minutes = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "type": "access",
        # Sub-second issued-at so two tokens for the same user minted in
        # the same second-resolution `exp` bucket are never byte-identical.
        "iat": now.timestamp(),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, expire_minutes * 60


def create_refresh_token(subject: str, expires_minutes: int | None = None) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at). The caller persists a RefreshToken
    row keyed by jti so the token can be looked up, rotated, and revoked
    without ever storing the raw JWT."""
    expire_minutes = expires_minutes or settings.REFRESH_TOKEN_EXPIRE_MINUTES
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    jti = str(uuid.uuid4())
    payload: dict[str, Any] = {"sub": subject, "exp": expire, "type": "refresh", "jti": jti}
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, jti, expire


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


def generate_code(length: int) -> str:
    """Cryptographically random, human-typeable code (e.g. registration
    approval code or login OTP)."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def hash_code(code: str) -> str:
    """One-way hash for storing codes at rest. Codes are high-entropy
    random strings (not user-chosen secrets like passwords), so a fast,
    deterministic hash is appropriate here — it lets lookups query by
    hash directly, unlike bcrypt's per-call salt."""
    normalized = code.strip().upper()
    return hashlib.sha256(f"{settings.SECRET_KEY}:{normalized}".encode("utf-8")).hexdigest()


def codes_match(candidate: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_code(candidate), code_hash)
