"""Authentication: password hashing, OTP, sessions, and OTP email delivery.

Password hashing and session tokens use only the standard library (PBKDF2 +
secrets), so there is no bcrypt/passlib/itsdangerous dependency to install or
get wrong. Token generation never touches a predictable RNG.
"""

import hashlib
import hmac
import os
import random
import smtplib
import ssl
import time
from email.message import EmailMessage
from typing import Optional, Tuple

from . import config

PBKDF2_ROUNDS = 200_000
HASH_PREFIX = "pbkdf2_sha256"


# --------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"{HASH_PREFIX}${PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time compare. Never raises on malformed stored values."""
    try:
        algo, rounds, salt_hex, want_hex = stored.split("$")
        if algo != HASH_PREFIX:
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(dk.hex(), want_hex)
    except (ValueError, AttributeError, TypeError):
        return False


# ------------------------------------------------------------------- OTP
def generate_otp() -> str:
    return f"{random.SystemRandom().randrange(0, 1_000_000):06d}"


def otp_is_expired(record: dict, ttl_minutes: int) -> bool:
    return (time.time() - float(record.get("createdAt", 0))) > ttl_minutes * 60


def otp_attempts_left(record: dict) -> int:
    return max(0, 5 - int(record.get("attempts", 0)))


# -------------------------------------------------------------- sessions
def new_session_token() -> str:
    import secrets

    return secrets.token_urlsafe(32)


# ----------------------------------------------------------------- email
def send_otp_email(to: str, otp: str) -> Tuple[bool, str]:
    """Returns (sent, detail). Never raises -- callers fall back to UI display."""
    user = config.EMAIL_USER
    password = config.EMAIL_PASS
    if not (user and password):
        return False, "email_not_configured"

    msg = EmailMessage()
    msg["Subject"] = f"{otp} is your OpportunityHub verification code"
    msg["From"] = config.EMAIL_FROM or f"OpportunityHub <{user}>"
    msg["To"] = to
    msg.set_content(
        f"Your OpportunityHub verification code is:\n\n"
        f"    {otp}\n\n"
        f"It expires in {config.OTP_TTL_MINUTES} minutes.\n\n"
        f"If you did not request this, you can safely ignore this email.\n"
    )

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
            s.login(user, password)
            s.send_message(msg)
        return True, "sent"
    except smtplib.SMTPAuthenticationError:
        # Almost always a wrong app password, or 2FA not enabled.
        return False, "smtp_auth_failed"
    except smtplib.SMTPRecipientsRefused:
        return False, "smtp_recipient_rejected"
    except Exception as exc:  # network, rate limit, DNS
        return False, f"smtp_error: {type(exc).__name__}"


def _reset_base_url() -> str:
    """Where the reset link should point.

    PUBLIC_BASE_URL is the right answer, but a laptop tunnel is the common case
    here and its quick-tunnel URL is random each start. Falling back to
    public-url.txt means the link in the email actually works right now instead
    of printing a bare token nobody can use.
    """
    base = (config.PUBLIC_BASE_URL or "").strip().rstrip("/")
    if base:
        return base
    try:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "public-url.txt")
        with open(path, encoding="utf-8") as fh:
            found = fh.read().strip()
        if found.startswith("http"):
            return found
    except OSError:
        pass
    return ""


def send_password_reset_email(to: str, link_token: str) -> Tuple[bool, str]:
    user = config.EMAIL_USER
    password = config.EMAIL_PASS
    if not (user and password):
        return False, "email_not_configured"

    base = _reset_base_url()
    link = f"{base}/#/reset?token={link_token}" if base else ""

    msg = EmailMessage()
    msg["Subject"] = "Reset your OpportunityHub password"
    msg["From"] = config.EMAIL_FROM or f"OpportunityHub <{user}>"
    msg["To"] = to

    if link:
        msg.set_content(
            f"Click the link below to choose a new password:\n\n    {link}\n\n"
            f"The link expires in {config.OTP_TTL_MINUTES} minutes.\n\n"
            f"If the button does not work, copy this address into your browser:\n"
            f"    {link}\n\n"
            f"If you did not request this, ignore this email -- your password is unchanged.\n"
        )
        msg.add_alternative(
            f"""<html><body style="font-family:system-ui,Arial,sans-serif;background:#0f172a;
            color:#e2e8f0;padding:24px">
            <div style="max-width:520px;margin:auto;background:#1e293b;padding:28px;border-radius:12px">
              <h2 style="margin:0 0 6px">Reset your password</h2>
              <p style="color:#94a3b8;margin:0 0 20px">
                This link expires in {config.OTP_TTL_MINUTES} minutes.</p>
              <a href="{link}"
                 style="background:#7c3aed;color:#fff;text-decoration:none;padding:12px 22px;
                        border-radius:8px;font-weight:600;display:inline-block">
                 Choose a new password</a>
              <p style="color:#64748b;font-size:12px;margin:24px 0 0">
                If you did not request this, ignore this email &mdash; your password is unchanged.</p>
            </div></body></html>""",
            subtype="html",
        )
    else:
        # No known base URL. Still give the token, but say plainly that the
        # deployment has no public address configured, rather than sending
        # something that looks like a broken link.
        msg.set_content(
            "This deployment has no public address configured, so there is no\n"
            "link to click. Take the token below to the app's reset page and\n"
            f"paste it there:\n\n    token: {link_token}\n\n"
            f"The token expires in {config.OTP_TTL_MINUTES} minutes.\n"
            "If you did not request this, ignore this email -- your password is unchanged.\n\n"
            "Tip: set PUBLIC_BASE_URL in .env so reset emails contain a real link.\n"
        )

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
            s.login(user, password)
            s.send_message(msg)
        return True, "sent"
    except Exception as exc:
        return False, f"smtp_error: {type(exc).__name__}"
