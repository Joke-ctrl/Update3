"""
Outbound email for the admin-gated auth flow.

Registration-approval codes are sent (as a fallback, when Telegram
delivery is unavailable — see app/notifications/dispatch.py) to
settings.ADMIN_EMAIL, since an admin must manually review and relay them.
Login OTPs are also now Telegram-first (see app/notifications/dispatch.py);
this module's send_login_otp_email is the fallback, sent directly to the
logging-in user's own email address. This module is intentionally
synchronous (stdlib
smtplib); call sites schedule it via FastAPI BackgroundTasks so a
slow/unreachable SMTP server never blocks or fails the API response, and
a delivery failure is logged rather than raised — it must never surface
as a 500 to the user mid-registration/login.
"""
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _send(subject: str, body: str, to_address: str) -> bool:
    settings = get_settings()

    if not settings.SMTP_HOST:
        logger.warning(
            "SMTP_HOST is not configured — skipping email send (subject=%r, to=%r). "
            "Set SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD to enable delivery.",
            subject,
            to_address,
        )
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.EMAIL_FROM
    message["To"] = to_address
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(message)
        return True
    except Exception:
        logger.exception("Failed to send email (subject=%r, to=%r)", subject, to_address)
        return False


def send_registration_code_email(user_email: str, code: str, expires_minutes: int) -> bool:
    settings = get_settings()
    subject = f"[MarketKill3r] Registration approval code for {user_email}"
    body = (
        f"A new account registration is pending approval.\n\n"
        f"User email: {user_email}\n"
        f"Approval code: {code}\n"
        f"This code expires in {expires_minutes} minutes and can be used once.\n\n"
        f"Relay this code to the user out-of-band to let them complete "
        f"registration verification. Do not forward this email to the user."
    )
    if not settings.SMTP_HOST:
        logger.warning(
            "SMTP not configured — registration code email to admin (%s) was not sent.",
            user_email,
        )
    return _send(subject, body, settings.ADMIN_EMAIL)


def send_login_otp_email(user_email: str, code: str, expires_minutes: int) -> bool:
    settings = get_settings()
    subject = "[MarketKill3r] Your login verification code"
    body = (
        f"Your MarketKill3r login verification code is: {code}\n\n"
        f"This code expires in {expires_minutes} minutes and can be used once.\n\n"
        f"If you did not attempt to log in, you can ignore this email."
    )
    if not settings.SMTP_HOST:
        logger.warning(
            "SMTP not configured — login OTP email to %s was not sent.", user_email
        )
    # Fallback destination only — sent directly to the logging-in user's
    # own address when Telegram delivery (the primary channel; see
    # app/notifications/dispatch.py) is unavailable.
    return _send(subject, body, user_email)
