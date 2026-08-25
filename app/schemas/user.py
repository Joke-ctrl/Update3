"""
Pydantic schemas for User create/read and the full auth flow (register,
registration-code verify/resend, login, login-OTP verify, refresh, logout).
"""
from datetime import datetime

from pydantic import BaseModel, EmailStr, ConfigDict, field_validator

from app.models.user import UserRole


class UserCreate(BaseModel):
    """POST /auth/register body. Field is `name` (not `full_name`) to match
    the Flutter app's request payload exactly."""

    name: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Name must not be blank")
        return v.strip()


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str | None = None
    role: UserRole
    is_active: bool
    is_approved: bool
    is_email_verified: bool
    notifications_enabled: bool
    created_at: datetime


class Token(BaseModel):
    """Legacy access-only token shape, kept for any existing non-auth-flow
    call sites that still reference it."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AuthTokens(BaseModel):
    """Shape returned by every endpoint that issues a session:
    POST /auth/login (direct success), /auth/login/verify-otp."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserRead


class StatusMessage(BaseModel):
    status: str
    message: str = ""


class RegistrationVerifyRequest(BaseModel):
    email: EmailStr
    code: str


class RegistrationResendRequest(BaseModel):
    email: EmailStr


class LoginOtpRequired(BaseModel):
    status: str = "otp_required"


class LoginOtpVerifyRequest(BaseModel):
    email: EmailStr
    code: str


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str
