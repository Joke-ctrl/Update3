"""
Outbound Telegram delivery for the admin-gated auth flow, via the
official Telegram Bot API (https://core.telegram.org/bots/api).

Both registration-approval codes and login OTPs are sent to
settings.TELEGRAM_CHAT_ID (the admin's chat with the bot) as the primary
channel — see app/notifications/dispatch.py for the Telegram-first,
email-fallback orchestration. This module is intentionally synchronous
(httpx) — call sites schedule it via FastAPI BackgroundTasks so a
slow/unreachable Telegram API never blocks or fails the API response. A
delivery failure is logged and returned as False, never raised. Nothing
here ever logs the approval code/OTP, the bot token, or any other
credential.

Setup: message @BotFather to create a bot and obtain a bot token, then
message your bot at least once and read the "chat" -> "id" field from
https://api.telegram.org/bot<token>/getUpdates to get your chat_id.
Both values are supplied only via TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
environment variables — never hard-coded here.
"""
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Telegram caps sendMessage text at 4096 UTF-8 characters; our messages
# are a few lines, so this is just a defensive ceiling.
_MAX_BODY_LENGTH = 4096


def _is_configured(settings) -> bool:
    return bool(
        settings.TELEGRAM_ENABLED
        and settings.TELEGRAM_BOT_TOKEN
        and settings.TELEGRAM_CHAT_ID
    )


def _send_text(body: str) -> bool:
    """Low-level Bot API call. Returns True only on a confirmed 2xx
    "ok" response from Telegram. Never raises."""
    settings = get_settings()

    if not _is_configured(settings):
        logger.info(
            "Telegram is not configured (TELEGRAM_ENABLED/BOT_TOKEN/"
            "CHAT_ID) — skipping Telegram send."
        )
        return False

    if len(body) > _MAX_BODY_LENGTH:
        body = body[:_MAX_BODY_LENGTH]

    url = f"{settings.TELEGRAM_API_URL.rstrip('/')}/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": settings.TELEGRAM_CHAT_ID,
        "text": body,
        "disable_web_page_preview": True,
    }

    try:
        response = httpx.post(url, json=payload, timeout=15)
    except httpx.TimeoutException:
        logger.warning("Telegram API request timed out.")
        return False
    except httpx.RequestError:
        logger.warning("Telegram API request failed (network/connection error).", exc_info=True)
        return False

    if response.status_code >= 200 and response.status_code < 300:
        try:
            if response.json().get("ok") is True:
                return True
        except Exception:
            pass
        logger.warning("Telegram API returned a 2xx but did not confirm ok=true.")
        return False

    # Log the failure reason without ever including the message body
    # (which may contain the approval code) or the bot token. The bot
    # token appears in the request URL, not in the response body, so
    # this is safe to log as-is.
    try:
        error_detail = response.json().get("description", "unknown error")
    except Exception:
        error_detail = f"HTTP {response.status_code}"
    logger.warning("Telegram API rejected the message: %s (status=%s)", error_detail, response.status_code)
    return False


def send_telegram_registration_code(user_email: str, code: str, expires_minutes: int) -> bool:
    body = (
        f"MarketKill3r: New registration pending approval.\n"
        f"User: {user_email}\n"
        f"Approval code: {code}\n"
        f"Expires in {expires_minutes} minutes. Relay to the user out-of-band."
    )
    return _send_text(body)


def send_telegram_login_otp(user_email: str, code: str, expires_minutes: int) -> bool:
    body = (
        f"MarketKill3r: Login verification code requested.\n"
        f"User: {user_email}\n"
        f"OTP: {code}\n"
        f"Expires in {expires_minutes} minutes. Relay to the user out-of-band."
    )
    return _send_text(body)
