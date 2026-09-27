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


def send_password_reset_email(to: str, link_token: str) -> Tuple[bool, str]:
    user = config.EMAIL_USER
    password = config.EMAIL_PASS
    if not (user and password):
        return False, "email_not_configured"

    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    link = f"{base}/#/reset?token={link_token}" if base else f"token: {link_token}"

    msg = EmailMessage()
    msg["Subject"] = "Reset your OpportunityHub password"
    msg["From"] = config.EMAIL_FROM or f"OpportunityHub <{user}>"
    msg["To"] = to
    msg.set_content(
        f"Use the link below to choose a new password:\n\n    {link}\n\n"
        f"The link expires in {config.OTP_TTL_MINUTES} minutes.\n"
        f"If you did not request this, ignore this email -- your password is unchanged.\n"
    )

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
            s.login(user, password)
            s.send_message(msg)
        return True, "sent"
    except Exception as exc:
        return False, f"smtp_error: {type(exc).__name__}"
