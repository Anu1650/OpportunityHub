r"""Preflight check: is this machine able to reach and use each backend?

Run before deploying so problems surface now, not in front of a judge.

    .\.venv\Scripts\python.exe tests\check_backends.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config  # noqa: E402

fails = 0


def check(label, ok, detail=""):
    global fails
    print(f"  {'ok  ' if ok else 'WARN'}  {label}{('  ' + detail) if detail else ''}")
    if not ok:
        fails += 1


if __name__ == "__main__":
    print(f"DB_BACKEND = {config.DB_BACKEND!r}")
    print(f"REQUIRE_DB = {config.REQUIRE_DB}\n")

    print("config")
    check("DB_BACKEND is valid",
          config.DB_BACKEND in ("auto", "memory", "mongo", "firestore"))
    check("MONGODB_URI set", bool(config.MONGODB_URI),
          "-> resolves to mongo" if config.MONGODB_URI else "")
    check("GCP_PROJECT set", bool(config.GCP_PROJECT))
    check("EMAIL_USER set", bool(config.EMAIL_USER))
    check("EMAIL_PASS set", len(config.EMAIL_PASS) == 16,
          f"len={len(config.EMAIL_PASS)} (Gmail app passwords are 16 chars, spaces stripped)")
    check("SECRET_KEY set", bool(config.SECRET_KEY))

    print("\nwhat this machine would use right now")
    try:
        from app.store import get_store

        store = get_store()
        count = store.count_opportunities()
        check("backend reachable", True, f"{type(store).__name__}, {count} listings")
    except Exception as exc:
        check("backend reachable", False, f"{type(exc).__name__}: {str(exc)[:110]}")

    print("\ntooling")
    import shutil

    check("gcloud on PATH", shutil.which("gcloud") is not None,
          "needed for Cloud Run" if shutil.which("gcloud") is None else "")
    check("docker on PATH", shutil.which("docker") is not None,
          "not required - `gcloud run deploy --source .` builds in Cloud Build")

    print(f"\n{'ALL GOOD' if not fails else f'{fails} item(s) need attention'}")
    sys.exit(0)
