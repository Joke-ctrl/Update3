"""
Auth-flow support tables:

- RegistrationCode: single-use, admin-emailed code required to approve a
  newly registered (pending) account.
- LoginOTP: separate short-lived, single-use second-factor code for the
  optional login OTP step. Never interchangeable with a RegistrationCode.
- RefreshToken: server-side record of issued refresh tokens so they can be
  rotated on use and revoked on logout/compromise. Only a hash of the JWT
  is stored, never the raw token.

Codes/tokens are never stored in plaintext: only a SHA-256 hash is
persisted, and lookups re-hash the candidate value and compare digests.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RegistrationCode(Base):
    __tablename__ = "registration_codes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SHA-256 hex digest of the plaintext code. Unique so the same code
    # string can never be issued to (and thus never belong to) more than
    # one user — the "one code, one user, never reused" requirement.
    code_hash: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class LoginOTP(Base):
    __tablename__ = "login_otps"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # JWT "jti" claim, not the full token — used to look up this row when a
    # refresh/logout request presents a token, without ever storing the
    # signed token string itself.
    jti: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # jti of the token this one was rotated into, for audit/debugging only.
    replaced_by_jti: Mapped[str | None] = mapped_column(String, nullable=True)
