r"""Confirm /api/auth/update-profile really is session-guarded.

A previous run of test_public.py reported "it was ALLOWED" for an
unauthenticated write. Before treating that as a vulnerability, check whether
the test itself was at fault -- it shared a cookie jar that already held a
valid session, so the write was legitimately authenticated.
"""

import http.cookiejar
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080"
fails = 0


def check(label, ok, extra=""):
    global fails
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}{('  ' + extra) if extra else ''}")
    fails += not ok


def call(path, payload, jar):
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    r = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with opener.open(r, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, None


if __name__ == "__main__":
    body = {"skills": ["Python"], "year": "3rd Year"}

    print("genuinely anonymous client (empty jar, no cookie)")
    empty = http.cookiejar.CookieJar()
    code, payload = call("/api/auth/update-profile", body, empty)
    check("rejected with 401", code == 401, f"HTTP {code}")
    check("no data returned", payload is None)

    print("\nsame client, after a bogus cookie is injected")
    bad = http.cookiejar.CookieJar()
    bad.set_cookie(http.cookiejar.Cookie(
        version=0, name="oh_session", value="totally-made-up-token",
        port=None, port_specified=False, domain="127.0.0.1", domain_specified=False,
        domain_initial_dot=False, path="/", path_specified=True,
        secure=False, expires=None, discard=True, comment=None, comment_url=None,
        rest={}, rfc2109=False))
    code, payload = call("/api/auth/update-profile", body, bad)
    check("rejected with 401", code == 401, f"HTTP {code}")

    print("\ntampered cookie: a real token with one character changed")
    # /api/students needs no auth, so obtain a genuine session via the normal
    # signup -> OTP -> verify flow, then flip one character of the token.
    import re
    import time

    email = f"authz-{int(time.time())}@fit.edu.in"
    jar = http.cookiejar.CookieJar()
    call("/api/auth/signup", {"name": "Authz", "email": email,
                              "password": "Authz12345"}, jar)
    with open("server.err", encoding="utf-8", errors="ignore") as fh:
        hits = re.findall(rf"OTP for {re.escape(email)}: (\d{{6}})", fh.read())
    check("OTP issued", bool(hits))
    if hits:
        call("/api/auth/verify-otp", {"email": email, "code": hits[-1]}, jar)
    real = next((c.value for c in jar if c.name == "oh_session"), None)
    check("a genuine session was issued", bool(real))

    if real:
        tampered = http.cookiejar.CookieJar()
        mutated = real[:-1] + ("A" if real[-1] != "A" else "B")
        tampered.set_cookie(http.cookiejar.Cookie(
            version=0, name="oh_session", value=mutated, port=None,
            port_specified=False, domain="127.0.0.1", domain_specified=False,
            domain_initial_dot=False, path="/", path_specified=True, secure=False,
            expires=None, discard=True, comment=None, comment_url=None, rest={},
            rfc2109=False))
        code, _ = call("/api/auth/update-profile", body, tampered)
        check("tampered session rejected", code == 401, f"HTTP {code}")

    print(f"\n{'ALL PASS' if not fails else f'{fails} FAILURES'}")
    sys.exit(1 if fails else 0)
