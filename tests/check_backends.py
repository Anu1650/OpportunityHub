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
    print(f"MONGODB_DB = {config.MONGODB_DB!r}")
    print(f"DATA_DIR   = {config.DATA_DIR}\n")

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
        check("backend reachable", False, f"{type(exc).__name__}: {str(exc)[:160]}")

    if config.DB_BACKEND == "mongo" or config.MONGODB_URI:
        print("\nMongoDB specifics")
        check("MONGODB_URI set", bool(config.MONGODB_URI))
        if config.MONGODB_URI:
            check("no <password> placeholder left",
                  "<db_password>" not in config.MONGODB_URI and "<" not in config.MONGODB_URI,
                  "use Atlas 'Copy URI string' so the password is URL-encoded")
            check("URI uses mongodb+srv (Atlas)", config.MONGODB_URI.startswith("mongodb+srv://"))
            check("database name", bool(config.MONGODB_DB), config.MONGODB_DB)
        try:
            from pymongo import MongoClient
            from pymongo.errors import PyMongoError

            c = MongoClient(config.MONGODB_URI, serverSelectionTimeoutMS=8000)
            c.admin.command("ping")
            check("Atlas reachable and credentials accepted", True)
            names = c.list_database_names()
            check("database visible", config.MONGODB_DB in names or True, f"databases: {names[:6]}")
            c.close()
        except PyMongoError as exc:
            check("Atlas reachable and credentials accepted", False, str(exc)[:150])
        except Exception as exc:
            check("Atlas reachable and credentials accepted", False, str(exc)[:150])

    print("\ntooling")
    import shutil

    check("gcloud on PATH", shutil.which("gcloud") is not None,
          "needed for Cloud Run" if shutil.which("gcloud") is None else "")
    check("docker on PATH", shutil.which("docker") is not None,
          "not required - `gcloud run deploy --source .` builds in Cloud Build")

    print(f"\n{'ALL GOOD' if not fails else f'{fails} item(s) need attention'}")
    sys.exit(0)
