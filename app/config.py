"""Runtime configuration.

Everything is env-driven so the exact same image runs locally (in-memory)
and on Cloud Run (Firestore) with zero code changes.
"""

import os

# Firestore project. On Cloud Run the default service account already has
# datastore access, so no key file is ever needed.
GCP_PROJECT = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
FIRESTORE_DATABASE = os.environ.get("FIRESTORE_DATABASE", "(default)")

# Seed the opportunity collection on first boot only. Seeding is idempotent.
SEED_ON_START = os.environ.get("SEED_ON_START", "1") not in ("0", "false", "False")

# Opportunity listings are read-only reference data. Caching them keeps us
# far away from Firestore's 50k reads/day free-tier ceiling when many judges
# hammer the same search page.
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "60"))

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
