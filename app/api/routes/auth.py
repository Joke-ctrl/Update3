"""
Authentication endpoints.

Flow implemented (matches the Flutter app's BACKEND_API_CONTRACT.md):

  POST /auth/register              -> create pending account, email admin
  POST /auth/registration/verify   -> admin-relayed code approves account
  POST /auth/registration/resend   -> re-issue/re-notify (optional convenience)
  POST /auth/login                 -> password check; pending/otp/tokens
  POST /auth/login/verify-otp      -> second factor -> tokens
  POST /auth/refresh               -> rotate refresh token -> new tokens
  POST /auth/logout                -> revoke refresh token (bearer required)

Registration-approval codes are sent to the admin only (Telegram first,
falling back to settings.ADMIN_EMAIL) — never to the user — since an
admin must manually review and relay them. Login OTPs now also go to
the admin's Telegram chat first (falling back to the logging-in user's
own email only if Telegram is unavailable), since Telegram is the
primary notification channel for this deployment. Codes are single-use,
expiring, and stored as hashes — never in plaintext.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.security import (
    codes_match,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_code,
    hash_code,
    hash_password,
    verify_password,
)
from app.core.config import get_settings
from app.database.session import get_db
from app.models.auth_tokens import LoginOTP, RefreshToken, RegistrationCode
from app.models.user import User
from app.notifications.dispatch import send_login_otp_notification, send_registration_code_notification
from app.schemas.user import (
    AuthTokens,
    LoginOtpVerifyRequest,
    LogoutRequest,
    RefreshRequest,
    RefreshResponse,
    RegistrationResendRequest,
    RegistrationVerifyRequest,
    StatusMessage,
    UserCreate,
    UserLogin,
    UserRead,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    """SQLite round-trips DateTime(timezone=True) columns as naive
    datetimes (unlike Postgres), so a value loaded back from the DB can
    lose its tzinfo. Normalize to UTC-aware before comparing against
    `_utcnow()` so this behaves identically on SQLite (tests/dev) and
    Postgres (production)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _issue_tokens(user: User, db: Session) -> AuthTokens:
    access_token, _ = create_access_token(subject=user.id)
    refresh_token, jti, expires_at = create_refresh_token(subject=user.id)

    db.add(RefreshToken(user_id=user.id, jti=jti, expires_at=expires_at))
    db.commit()

    return AuthTokens(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserRead.model_validate(user),
    )


def _create_and_send_registration_code(
    user: User, db: Session, background_tasks: BackgroundTasks
) -> None:
    # Revoke any previously issued, still-active codes for this user so
    # only the newest one is valid.
    db.query(RegistrationCode).filter(
        RegistrationCode.user_id == user.id,
        RegistrationCode.used_at.is_(None),
        RegistrationCode.revoked.is_(False),
    ).update({"revoked": True})

    code = generate_code(settings.REGISTRATION_CODE_LENGTH)
    expires_at = _utcnow() + timedelta(minutes=settings.REGISTRATION_CODE_EXPIRE_MINUTES)

    # Extremely unlikely, but guard against a hash collision on the unique
    # column by retrying generation rather than failing registration.
    for _ in range(5):
        record = RegistrationCode(user_id=user.id, code_hash=hash_code(code), expires_at=expires_at)
        db.add(record)
        try:
            db.commit()
            break
        except Exception:
            db.rollback()
            code = generate_code(settings.REGISTRATION_CODE_LENGTH)
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate a registration code. Please try again.",
        )

    # Telegram first, automatically falling back to email when Telegram
    # fails, is unreachable, or is not configured. See
    # app/notifications/dispatch.py.
    background_tasks.add_task(
        send_registration_code_notification,
        user.email,
        code,
        settings.REGISTRATION_CODE_EXPIRE_MINUTES,
    )


# ============================================================
# REGISTRATION
# ============================================================


@router.post("/register", response_model=StatusMessage, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> StatusMessage:
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.name,
        is_approved=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    _create_and_send_registration_code(user, db, background_tasks)

    return StatusMessage(
        status="pending_approval",
        message="Registration received. An admin must approve your account before you can log in.",
    )


@router.post("/registration/verify", response_model=StatusMessage)
def verify_registration(payload: RegistrationVerifyRequest, db: Session = Depends(get_db)) -> StatusMessage:
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid, expired, or already-used registration code.",
    )

    user = db.query(User).filter(User.email == payload.email).first()
    if user is None:
        raise invalid

    candidates = (
        db.query(RegistrationCode)
        .filter(
            RegistrationCode.user_id == user.id,
            RegistrationCode.used_at.is_(None),
            RegistrationCode.revoked.is_(False),
            RegistrationCode.expires_at > _utcnow(),
        )
        .all()
    )

    match = next((c for c in candidates if codes_match(payload.code, c.code_hash)), None)
    if match is None:
        raise invalid

    match.used_at = _utcnow()
    user.is_approved = True
    db.add(match)
    db.add(user)
    db.commit()

    return StatusMessage(status="approved", message="Account approved. You can now log in.")


@router.post("/registration/resend", response_model=StatusMessage)
def resend_registration_notice(
    payload: RegistrationResendRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> StatusMessage:
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No pending registration for this email.")
    if user.is_approved:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This account is already approved.")

    _create_and_send_registration_code(user, db, background_tasks)

    return StatusMessage(status="pending_approval", message="Admin has been re-notified.")


# ============================================================
# LOGIN
# ============================================================


@router.post("/login")
def login(payload: UserLogin, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_approved:
        # Flat body (not nested under "detail") — the Flutter app reads
        # top-level "status" on a 403 to route back to the waiting screen.
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"status": "pending_approval"},
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    if not settings.LOGIN_OTP_ENABLED:
        return _issue_tokens(user, db)

    code = generate_code(settings.LOGIN_OTP_LENGTH)
    expires_at = _utcnow() + timedelta(minutes=settings.LOGIN_OTP_EXPIRE_MINUTES)

    for _ in range(5):
        record = LoginOTP(user_id=user.id, code_hash=hash_code(code), expires_at=expires_at)
        db.add(record)
        try:
            db.commit()
            break
        except Exception:
            db.rollback()
            code = generate_code(settings.LOGIN_OTP_LENGTH)
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate a login code. Please try again.",
        )

    # Telegram first (to the admin's chat), automatically falling back
    # to emailing the logging-in user directly when Telegram fails, is
    # unreachable, or is not configured. See app/notifications/dispatch.py.
    background_tasks.add_task(send_login_otp_notification, user.email, code, settings.LOGIN_OTP_EXPIRE_MINUTES)

    return {"status": "otp_required"}


@router.post("/login/verify-otp", response_model=AuthTokens)
def verify_login_otp(payload: LoginOtpVerifyRequest, db: Session = Depends(get_db)) -> AuthTokens:
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired code.",
    )

    user = db.query(User).filter(User.email == payload.email).first()
    if user is None:
        raise invalid

    candidates = (
        db.query(LoginOTP)
        .filter(
            LoginOTP.user_id == user.id,
            LoginOTP.used_at.is_(None),
            LoginOTP.revoked.is_(False),
            LoginOTP.expires_at > _utcnow(),
        )
        .all()
    )

    match = next((c for c in candidates if codes_match(payload.code, c.code_hash)), None)
    if match is None:
        raise invalid

    match.used_at = _utcnow()
    db.add(match)
    db.commit()

    return _issue_tokens(user, db)


# ============================================================
# REFRESH / LOGOUT
# ============================================================


@router.post("/refresh", response_model=RefreshResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> RefreshResponse:
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token.",
    )

    decoded = decode_token(payload.refresh_token)
    if decoded is None or decoded.get("type") != "refresh":
        raise invalid

    jti = decoded.get("jti")
    user_id = decoded.get("sub")
    if not jti or not user_id:
        raise invalid

    record = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
    if record is None or record.revoked_at is not None:
        raise invalid
    if _aware(record.expires_at) <= _utcnow():
        raise invalid

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active or not user.is_approved:
        raise invalid

    new_access, _ = create_access_token(subject=user.id)
    new_refresh, new_jti, new_expires_at = create_refresh_token(subject=user.id)

    record.revoked_at = _utcnow()
    record.replaced_by_jti = new_jti
    db.add(record)
    db.add(RefreshToken(user_id=user.id, jti=new_jti, expires_at=new_expires_at))
    db.commit()

    return RefreshResponse(access_token=new_access, refresh_token=new_refresh)


@router.post("/logout")
def logout(
    payload: LogoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    decoded = decode_token(payload.refresh_token)
    if decoded is not None and decoded.get("type") == "refresh":
        jti = decoded.get("jti")
        if jti:
            record = (
                db.query(RefreshToken)
                .filter(RefreshToken.jti == jti, RefreshToken.user_id == current_user.id)
                .first()
            )
            if record is not None and record.revoked_at is None:
                record.revoked_at = _utcnow()
                db.add(record)
                db.commit()

    # Best-effort, always 2xx per contract — the client clears its local
    # session regardless of whether a matching token was found.
    return {"status": "ok"}
