"""Transactional account-verification email delivery."""
from __future__ import annotations

import html
import logging
from urllib.parse import quote

import httpx

import config as _cfg


logger = logging.getLogger(__name__)


async def _send_auth_email(email: str, subject: str, html_body: str, development_url: str) -> None:
    if not _cfg.RESEND_API_KEY:
        if _cfg.ENVIRONMENT == "production":
            raise RuntimeError("Account email delivery is not configured")
        logger.warning("Development account URL for %s: %s", email, development_url)
        return
    payload = {
        "from": _cfg.AUTH_EMAIL_FROM,
        "to": [email],
        "subject": subject,
        "html": html_body,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {_cfg.RESEND_API_KEY}", "Content-Type": "application/json"},
            json=payload,
        )
    if response.status_code not in {200, 201}:
        logger.error("Account email delivery failed (%s): %s", response.status_code, response.text)
        raise RuntimeError("Account email could not be sent")


async def send_verification_email(email: str, name: str, token: str) -> None:
    url = f"{_cfg.FRONTEND_URL.rstrip('/')}/verify-email?token={quote(token, safe='')}"
    safe_name, safe_url = html.escape(name or "writer"), html.escape(url, quote=True)
    await _send_auth_email(
        email,
        "Verify your Roundtable email",
        f"<p>Hello {safe_name},</p>"
        "<p>Confirm your email address to finish creating your Roundtable account.</p>"
        f'<p><a href="{safe_url}">Verify email address</a></p>'
        f'<p>If the button does not work, open:<br><a href="{safe_url}">{safe_url}</a></p>'
        "<p>This link expires soon. If you did not create this account, you can ignore this email.</p>",
        url,
    )


async def send_password_reset_email(email: str, name: str, token: str) -> None:
    url = f"{_cfg.FRONTEND_URL.rstrip('/')}/reset-password?token={quote(token, safe='')}"
    safe_name, safe_url = html.escape(name or "writer"), html.escape(url, quote=True)
    await _send_auth_email(
        email,
        "Reset your Roundtable password",
        f"<p>Hello {safe_name},</p>"
        "<p>We received a request to reset your Roundtable password.</p>"
        f'<p><a href="{safe_url}">Choose a new password</a></p>'
        f'<p>If the button does not work, open:<br><a href="{safe_url}">{safe_url}</a></p>'
        "<p>This link expires soon. If you did not request it, you can ignore this email.</p>",
        url,
    )
