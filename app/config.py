"""Runtime configuration.

Everything is env-driven so the exact same image runs locally (in-memory)
and on Cloud Run (Firestore) with zero code changes.
"""

import os

from dotenv import load_dotenv

# Load local .env if present. On Cloud Run the real env vars are injected by
# gcloud, and there is no .env file -- missing values just stay empty.
load_dotenv()

# Firestore project. On Cloud Run the default service account already has
# datastore access, so no key file is ever needed.
GCP_PROJECT = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
FIRESTORE_DATABASE = os.environ.get("FIRESTORE_DATABASE", "(default)")

# MongoDB (Atlas or local). Takes effect only when MONGODB_URI is set.
MONGODB_URI = os.environ.get("MONGODB_URI", "")
MONGODB_DB = os.environ.get("MONGODB_DB", "fitfest")

# Where the frontend is reachable, used to build password-reset links.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")

# Secret for signing anything sensitive. Generated per environment; without it
# session/reset tokens are still random, but there is nothing to bind to.
SECRET_KEY = os.environ.get("SECRET_KEY", "")

# Gmail SMTP for OTP verification and password reset.
EMAIL_USER = os.environ.get("EMAIL_USER", "")
EMAIL_PASS = os.environ.get("EMAIL_PASS", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")

OTP_TTL_MINUTES = int(os.environ.get("OTP_TTL_MINUTES", "10"))
SESSION_TTL_DAYS = int(os.environ.get("SESSION_TTL_DAYS", "30"))

# Seed the opportunity collection on first boot only. Seeding is idempotent.
SEED_ON_START = os.environ.get("SEED_ON_START", "1") not in ("0", "false", "False")

# Opportunity listings are read-only reference data. Caching them keeps us
# far away from Firestore's 50k reads/day free-tier ceiling when many judges
# hammer the same search page.
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "60"))

# Set to "1" once MONGODB_URI / GCP_PROJECT are configured, so the in-memory
# fallback can never be used by accident in production.
REQUIRE_DB = os.environ.get("REQUIRE_DB", "0") not in ("0", "false", "False")

CATEGORIES = [
    "internship",
    "hackathon",
    "scholarship",
    "course",
    "certification",
    "competition",
    "workshop",
]

MODES = ["remote", "onsite", "hybrid"]
