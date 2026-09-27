r"""Prove the file backend survives a process restart.

MemoryStore loses everything on restart. On a laptop-hosted demo behind a
Cloudflare tunnel, that means a judge refreshing the page sees an empty app.
This creates data, restarts the app, and checks it is still there.

Run: .\.venv\Scripts\python.exe tests\test_persistence.py
"""

import http.cookiejar
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "http://127.0.0.1:8080"
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
# Unique per run: the file backend keeps prior accounts, so a fixed address
# would collide with the previous run and 409 on signup.
EMAIL = f"persist-{int(time.time())}@fit.edu.in"
PASSWORD = "Persist12345"

# The session cookie must survive the restart too, so use a real cookie jar
# rather than assuming an open connection.
_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))

fails = 0


def check(label, ok, extra=""):
    global fails
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}{('  ' + extra) if extra else ''}")
    fails += not ok


def post(path, payload, timeout=30):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with _opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def get(path, timeout=30):
    with _opener.open(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode())


def cookies_present():
    return [c.name for c in _jar]


def code_for(email, log="server.err"):
    """Read the newest OTP for this address out of the server log."""
    import re

    with open(os.path.join(ROOT, log), encoding="utf-8", errors="ignore") as fh:
        hits = re.findall(rf"OTP for {re.escape(email)}: (\d{{6}})", fh.read())
    return hits[-1] if hits else None


def wait_up(timeout=40):
    for _ in range(timeout):
        try:
            get("/healthz", timeout=5)
            return True
        except Exception:
            time.sleep(1)
    return False


def kill_app():
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-NetTCPConnection -LocalPort 8080 -State Listen | "
         "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"],
        capture_output=True)
    time.sleep(2)


def start_app():
    subprocess.Popen(
        [PY, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8080"],
        cwd=ROOT, stdout=open(os.path.join(ROOT, "server.log"), "w"),
        stderr=open(os.path.join(ROOT, "server.err"), "w"))
    return wait_up()


if __name__ == "__main__":
    print("before restart")
    check("app is up", wait_up(10))
    store = get("/api/meta")["store"]
    check("using the file backend", store == "FileStore", f"store={store}")

    su = post("/api/auth/signup", {"name": "Persist Test", "email": EMAIL, "password": PASSWORD})
    check("signup accepted", su.get("otpRequired") is True)

    time.sleep(1)
    code = code_for(EMAIL)
    check("OTP captured from the log", bool(code), str(code))
    if not code:
        print("\nFAILED at setup; aborting")
        sys.exit(1)

    v = post("/api/auth/verify-otp", {"email": EMAIL, "code": code})
    check("session cookie issued", "oh_session" in cookies_present(), str(cookies_present()))
    sid = v["studentId"]
    p = post("/api/auth/update-profile",
             {"year": "3rd Year", "skills": ["Python", "React", "SQL"],
              "categories": ["internship", "hackathon"]})
    sid = p["id"]
    # bookmark a real listing
    first_opp = get("/api/opportunities")["items"][0]["id"]
    bm = post("/api/bookmarks", {"studentId": sid, "opportunityId": first_opp})
    check("bookmark saved", bm["saved"] is True)
    before = get("/api/bookmarks/" + sid)["total"]
    check("1 bookmark before restart", before == 1, str(before))

    print("\nrestarting the app (this is what a laptop refresh looks like)")
    kill_app()
    check("app is down", not wait_up(6))
    check("app restarts", start_app())

    print("\nafter restart")
    meta = get("/api/meta")
    check("still the file backend", meta["store"] == "FileStore", meta["store"])
    check("listings survived", meta["total"] == 66, str(meta["total"]))
    check("no re-seed / no duplicate listings", meta["total"] == 66, str(meta["total"]))

    student = get(f"/api/students/{sid}")
    check("profile survived", student.get("year") == "3rd Year", str(student.get("year")))
    check("skills survived", student.get("skills") == ["Python", "React", "SQL"],
          str(student.get("skills")))

    after = get(f"/api/bookmarks/{sid}")["total"]
    check("bookmark survived", after == 1, str(after))

    rec = get(f"/api/recommendations/{sid}")["items"][0]
    check("recommendations recomputed from disk", rec["score"] > 0,
          f"{rec['score']}% {rec['title']}")

    me = get("/auth/me".replace("/auth/me", "/api/auth/me"))
    check("session survived the restart", me.get("authenticated") is True, str(me))

    try:
        post("/api/auth/login", {"email": EMAIL, "password": PASSWORD})
        check("login works after restart", True)
    except urllib.error.HTTPError as e:
        check("login works after restart", False, f"HTTP {e.code}")

    print(f"\n{'ALL PASS' if not fails else f'{fails} FAILURES'}")
    sys.exit(1 if fails else 0)
