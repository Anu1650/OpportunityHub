r"""Create the MongoDB URI in .env for you, then test it.

Connection strings are easy to mistype -- a doubled prefix, an unescaped
@, a literal placeholder. This script takes the credentials directly,
encodes them correctly, writes .env, and verifies the result, so
nothing has to be assembled by hand.

Run:  .\.venv\Scripts\python.exe tests\set_mongo.py

Enter the username shown in Atlas > Database Access, and the password
for that user. The password is typed blind and never printed.
"""

import getpass
import os
import sys
from urllib.parse import quote_plus, urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT, ".env")
HOST = "cluster0.9c5fn.mongodb.net"
DB = "fitfest"


def read_env(path):
    lines = open(path, encoding="utf-8").read().splitlines() if os.path.exists(path) else []
    return [ln for ln in lines if not ln.strip().startswith("#")]


def set_var(lines, key, value):
    out, replaced = [], False
    for ln in lines:
        if ln.split("=", 1)[0].strip() == key:
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(ln)
    if not replaced:
        out.append(f"{key}={value}")
    return out


if __name__ == "__main__":
    print(__doc__)
    print("Values come from Atlas > Database Access.\n")

    username = input("Atlas username (e.g. fitfestapp): ").strip()
    if not username:
        print("Username is required.")
        sys.exit(1)

    password = getpass.getpass("Password for that user (hidden): ")
    if not password:
        print("Password is required.")
        sys.exit(1)

    # An unescaped @ or / silently truncates the password at the first @.
    encoded = quote_plus(password)
    uri = f"mongodb+srv://{quote_plus(username)}:{encoded}@{HOST}/?retryWrites=true&w=majority"

    print(f"\nusername   : {username}")
    print(f"host       : {HOST}")
    print(f"database   : {DB}")
    print(f"password   : <hidden, {len(password)} chars, encoded to {len(encoded)}>")
    print(f"at-signs   : {uri.count('@')} (must be 1)")

    ok = input("\nWrite this to .env? [y/N] ").strip().lower() == "y"
    if not ok:
        print("Cancelled. Nothing written.")
        sys.exit(1)

    lines = read_env(ENV_PATH)
    lines = set_var(lines, "MONGODB_URI", uri)
    lines = set_var(lines, "MONGODB_DB", DB)
    with open(ENV_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"Wrote {ENV_PATH}")

    print("\nTesting the connection ...")
    try:
        from pymongo import MongoClient
        from pymongo.errors import PyMongoError

        client = MongoClient(uri, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000)
        servers = list(client.topology_description.server_descriptions().keys())
        client.admin.command("ping")
        client.close()
        print(f"  ok    network reachable ({len(servers)} shard hosts)")
        print("  ok    credentials accepted")
        print("\nCONNECTED. Now switch the backend:")
        print("    set DB_BACKEND=mongo in .env, then restart the app.")
        sys.exit(0)
    except PyMongoError as exc:
        text = str(exc).lower()
        print("  FAIL  connection failed")
        if "bad auth" in text or "authentication failed" in text:
            print("""
        Atlas reached but rejected the login. Either:
          - the username is not exactly what you typed (case-sensitive), or
          - the password is not the one you just set.
        Re-run this script and copy the Username column from
        Atlas > Database Access character for character.""")
        elif "timed out" in text:
            print("""
        Atlas never answered. Add 0.0.0.0/0 under
        Atlas > Network Access > IP Access List.""")
        else:
            print(f"        {str(exc)[:200]}")
        sys.exit(1)
