"""Runtime configuration.

Everything is env-driven so the exact same code runs locally, behind a
Cloudflare tunnel, and on Cloud Run.

Note the `env()` helper: os.environ.get(name, default) returns "" when the
variable is *present but blank*, so a stray `EMAIL_PASS=` in .env would silently
override a default with an empty string instead of falling back. env() treats
blank as unset.
"""

import os

from dotenv import load_dotenv

# Load local .env if present. On Cloud Run the real env vars are injected by
# gcloud, and there is no .env file -- missing values just stay empty.
load_dotenv()


def env(name: str, default: str = "") -> str:
    v = os.environ.get(name, "").strip()
    return v if v else default


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, "1" if default else "0").lower() in ("1", "true", "yes", "on")


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except ValueError:
        return default


# Firestore project. On Cloud Run the default service account already has
# datastore access, so no key file is ever needed.
GCP_PROJECT = env("GCP_PROJECT") or env("GOOGLE_CLOUD_PROJECT")
FIRESTORE_DATABASE = env("FIRESTORE_DATABASE", "(default)")

# MongoDB (Atlas or local). Takes effect only when MONGODB_URI is set.
MONGODB_URI = env("MONGODB_URI")
MONGODB_DB = env("MONGODB_DB", "fitfest")

# Where the frontend is reachable, used to build password-reset links.
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL")

# Secret for binding anything environment-specific. Without it, session and
# reset tokens are still random, but there is nothing to tie them to.
SECRET_KEY = env("SECRET_KEY")

# Gmail SMTP for OTP verification and password reset.
EMAIL_USER = env("EMAIL_USER")
# Gmail shows app passwords as "abcd efgh ijkl mnop". Pasting one verbatim
# keeps those spaces and makes SMTP auth fail with an opaque error, so internal
# whitespace is stripped here.
EMAIL_PASS = "".join(env("EMAIL_PASS").split())
EMAIL_FROM = env("EMAIL_FROM")

OTP_TTL_MINUTES = env_int("OTP_TTL_MINUTES", 10)
SESSION_TTL_DAYS = env_int("SESSION_TTL_DAYS", 30)

# Seed the opportunity collection on first boot only. Seeding is idempotent.
SEED_ON_START = env_bool("SEED_ON_START", True)

# Opportunity listings are read-only reference data. Caching them keeps us far
# away from Firestore's 50k reads/day free-tier ceiling when many judges
# hammer the same search page.
CACHE_TTL_SECONDS = env_int("CACHE_TTL_SECONDS", 60)

# Which backend to use: "auto" | "memory" | "file" | "mongo" | "firestore".
# Explicit rather than implicit precedence -- previously a stray MONGODB_URI
# silently shadowed GCP_PROJECT, which is nearly impossible to diagnose from a
# deployed URL.
#   auto      -> mongo if MONGODB_URI, else firestore if GCP_PROJECT, else memory
#   memory    -> in-process only; everything is lost on restart
#   file      -> JSON on disk; survives restarts. Fine on a laptop or VM
#   mongo     -> require MONGODB_URI
#   firestore -> require GCP_PROJECT and cloud credentials
DB_BACKEND = env("DB_BACKEND", "auto").lower()

# Where the file backend persists. A plain file is fine on a laptop or a VM, but
# NOT on Cloud Run: its container filesystem is ephemeral and is wiped on every
# restart, so use Firestore or MongoDB when deployed there.
DATA_DIR = env(
    "DATA_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
)

# Set to "1" once a durable backend is configured, so the in-memory fallback
# can never be used by accident in production.
REQUIRE_DB = env_bool("REQUIRE_DB", False)

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
