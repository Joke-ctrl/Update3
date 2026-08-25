"""
Delivery orchestration for the admin-gated auth flow.

Both registration-approval codes and login OTPs are delivered
Telegram-first, with SMTP email as an automatic backup — never both.
Telegram is attempted first; email is only used if Telegram is disabled,
unconfigured, unreachable, or returns a failed response. If Telegram
succeeds, no email is sent. Nothing here ever raises — call sites
schedule this via FastAPI BackgroundTasks, so an unhandled exception
would only be logged by Starlette and never reach the user, but we still
guard explicitly per requirements: registration/login must never fail or
crash because a notification provider had a temporary issue.
Success/failure is logged; the code itself and all credentials are never
logged.

  - Registration-approval codes go to the admin (settings.TELEGRAM_CHAT_ID,
    falling back to settings.ADMIN_EMAIL) — never to the registering user.
  - Login OTPs also go to the admin's Telegram chat first now (not the
    user's own email), falling back to the logging-in user's own email
    (settings-independent — see app/notifications/email.py) only if
    Telegram is unavailable.
"""
import logging

from app.notifications.email import send_login_otp_email, send_registration_code_email
from app.notifications.telegram import send_telegram_login_otp, send_telegram_registration_code

logger = logging.getLogger(__name__)


def _deliver(
    *,
    kind: str,
    telegram_send,
    email_send,
    user_email: str,
    code: str,
    expires_minutes: int,
) -> bool:
    """Shared Telegram-first/email-fallback orchestration. `telegram_send`
    and `email_send` are the two-way delivery callables for the given
    notification kind (registration code or login OTP), each with
    signature (user_email, code, expires_minutes) -> bool. Never raises;
    never sends email once Telegram has already succeeded."""
    telegram_ok = False
    try:
        telegram_ok = telegram_send(user_email, code, expires_minutes)
    except Exception:
        # Defense in depth: the Telegram send function already catches
        # its own errors, but a notification failure must never
        # propagate out of a background task and must never affect the
        # registration/login response.
        logger.exception("Unexpected error attempting Telegram delivery of %s.", kind)
        telegram_ok = False

    if telegram_ok:
        logger.info("%s delivered via Telegram.", kind)
        return True

    logger.info("Telegram delivery of %s unavailable or failed — falling back to email.", kind)

    email_ok = False
    try:
        email_ok = email_send(user_email, code, expires_minutes)
    except Exception:
        logger.exception("Unexpected error attempting email delivery of %s.", kind)
        email_ok = False

    if email_ok:
        logger.info("%s delivered via email (fallback).", kind)
    else:
        logger.error("%s delivery FAILED on both Telegram and email.", kind)

    return email_ok


def send_registration_code_notification(user_email: str, code: str, expires_minutes: int) -> bool:
    """Deliver a registration-approval code to the admin: Telegram first,
    email fallback. Returns True if delivered by either channel."""
    return _deliver(
        kind="Registration approval code",
        telegram_send=send_telegram_registration_code,
        email_send=send_registration_code_email,
        user_email=user_email,
        code=code,
        expires_minutes=expires_minutes,
    )


def send_login_otp_notification(user_email: str, code: str, expires_minutes: int) -> bool:
    """Deliver a login OTP to the admin's Telegram chat first, falling
    back to emailing the logging-in user directly if Telegram is
    disabled, unconfigured, unreachable, or fails. Returns True if
    delivered by either channel."""
    return _deliver(
        kind="Login OTP",
        telegram_send=send_telegram_login_otp,
        email_send=send_login_otp_email,
        user_email=user_email,
        code=code,
        expires_minutes=expires_minutes,
    )
