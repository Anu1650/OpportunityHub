r"""Diagnose the MongoDB connection without hand-writing a connection string.

Builds the URI from .env so there is no template to misfill, then separates
the three things that all look like the same "bad auth" error:

  1. the hostname / cluster does not exist
  2. the network or IP access list blocks us
  3. the username or password is wrong

Run:  .\.venv\Scripts\python.exe tests\check_mongo.py
"""

import os
import sys
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient                     # noqa: E402
from pymongo.errors import (                         # noqa: E402
    ConfigurationError,
    OperationFailure,
    PyMongoError,
    ServerSelectionTimeoutError,
)

from app import config                              # noqa: E402

fails = 0


def check(label, ok, extra=""):
    global fails
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}{('  ' + extra) if extra else ''}")
    fails += not ok


def verdict(exc) -> str:
    text = str(exc).lower()
    if "bad auth" in text or "authentication failed" in text:
        return ("USERNAME OR PASSWORD WRONG. The connection reached Atlas and Atlas "
                "rejected the login.\n"
                "        -> Check the exact Username text in Atlas > Database Access. "
                "It is often an email address, and it IS case-sensitive.\n"
                "        -> Passwords cannot be viewed, only reset: Edit the user and "
                "set a new one using letters and digits only.")
    if "timed out" in text or "server selection" in text:
        return ("NETWORK BLOCKED or cluster asleep. Atlas never answered.\n"
                "        -> Atlas > Network Access > IP Access List must include "
                "0.0.0.0/0\n"
                "        -> A free M0 cluster pauses when idle; the first request can "
                "take a minute to wake.")
    if "does not exist" in text or "srv" in text:
        return "WRONG HOSTNAME, or the cluster has been deleted. Copy the hostname fresh from Atlas."
    return f"OTHER ERROR: {str(exc)[:160]}"


if __name__ == "__main__":
    uri = config.MONGODB_URI

    print("URI shape (read from .env, nothing to misfill)")
    if not uri:
        print("  MONGODB_URI is empty. Nothing to test.")
        sys.exit(1)

    parts = urlsplit(uri)
    check("scheme is mongodb+srv", parts.scheme == "mongodb+srv", parts.scheme)
    check("exactly one @ in the URI", uri.count("@") == 1, f"count={uri.count('@')}")
    check("no <placeholder> left", "<" not in uri and ">" not in uri)
    check("hostname present", bool(parts.hostname), parts.hostname or "")
    check("username present", bool(parts.username), parts.username or "(none)")
    check("password present", bool(parts.password), f"len={len(parts.password or '')}")
    check("password is letters/digits only",
          all(ch.isalnum() for ch in (parts.password or "")),
          "special chars are fine but must be URL-encoded")

    print(f"\nconnecting to {parts.hostname} as user '{parts.username}'")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000)
        servers = list(client.topology_description.server_descriptions().keys())
        check("DNS/SRV resolved to shard hosts", bool(servers),
              f"{len(servers)} shard(s), e.g. {servers[0][0] if servers else '-'}")
        client.admin.command("ping")
        check("AUTHENTICATED", True, "credentials accepted")
        client.close()
    except (OperationFailure, ServerSelectionTimeoutError, ConfigurationError,
            PyMongoError) as exc:
        check("AUTHENTICATED", False, "")
        print(f"\n  -> {verdict(exc)}\n")
    except Exception as exc:
        check("AUTHENTICATED", False, "")
        print(f"\n  -> UNEXPECTED {type(exc).__name__}: {str(exc)[:200]}\n")

    print(f"\n{'CONNECTED' if not fails else 'NOT CONNECTED'}")
    sys.exit(1 if fails else 0)
