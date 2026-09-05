"""Transactional account-verification email delivery."""
from __future__ import annotations

import html
import logging
from urllib.parse import quote

import httpx

import config as _cfg


logger = logging.getLogger(__name__)


async def send_verification_email(email: str, name: str, token: str) -> None:
    verification_url = f"{_cfg.FRONTEND_URL.rstrip('/')}/verify-email?token={quote(token)}"
    if not _cfg.RESEND_API_KEY:
        if _cfg.ENVIRONMENT == "production":
            raise RuntimeError("Verification email delivery is not configured")
        logger.warning("Development verification URL for %s: %s", email, verification_url)
        return

    safe_name = html.escape(name or "writer")
    safe_url = html.escape(verification_url, quote=True)
    payload = {
        "from": _cfg.AUTH_EMAIL_FROM,
        "to": [email],
        "subject": "Verify your Roundtable email",
        "html": (
            f"<p>Hello {safe_name},</p>"
            "<p>Confirm your email address to finish creating your Roundtable account.</p>"
            f'<p><a href="{safe_url}">Verify email address</a></p>'
            f'<p>If the button does not work, open:<br><a href="{safe_url}">{safe_url}</a></p>'
            "<p>This link expires soon. If you did not create this account, you can ignore this email.</p>"
        ),
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {_cfg.RESEND_API_KEY}", "Content-Type": "application/json"},
            json=payload,
        )
    if response.status_code not in {200, 201}:
        logger.error("Verification email delivery failed (%s): %s", response.status_code, response.text)
        raise RuntimeError("Verification email could not be sent")
