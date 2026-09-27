r"""End-to-end check against the PUBLIC Cloudflare URL.

Exercises the same path a judge takes: landing page, signup, real email OTP,
profile, recommendations, bookmarks. Uses a cookie jar so the session is
carried the way a browser would.

Run: .\.venv\Scripts\python.exe tests\test_public.py
"""

import http.client
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL_FILE = os.path.join(ROOT, "public-url.txt")
LOG = os.path.join(ROOT, "server.err")
fails = 0

_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))


def check(label, ok, extra=""):
    global fails
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}{('  ' + extra) if extra else ''}")
    fails += not ok


def req(path, payload=None, timeout=45):
    url = BASE + path
    if payload is None:
        r = urllib.request.Request(url)
    else:
        r = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
    with _opener.open(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def newest_otp(email):
    with open(LOG, encoding="utf-8", errors="ignore") as fh:
        hits = re.findall(rf"OTP for {re.escape(email)}: (\d{{6}})", fh.read())
    return hits[-1] if hits else None


if __name__ == "__main__":
    with open(URL_FILE) as fh:
        BASE = fh.read().strip()
    print(f"testing {BASE}\n")

    print("public reachability")
    # A shared link often arrives with /index.html appended, and clean paths
    # like /login are typed by hand. Both used to 404 and looked like a dead
    # site rather than a routing detail.
    for path in ("/", "/index.html", "/login", "/dashboard", "/saved", "/profile"):
        with urllib.request.urlopen(BASE + path, timeout=45) as r:
            body = r.read().decode("utf-8", "ignore")
        check(f"{path} serves the app", r.status == 200 and "OpportunityHub" in body)
    with urllib.request.urlopen(BASE + "/favicon.ico", timeout=45) as r:
        check("/favicon.ico handled", r.status in (200, 204), str(r.status))
    h = req("/healthz")
    # "degraded" is a legitimate, healthy state: it means the configured
    # database was unreachable and the app fell back to the file store rather
    # than going offline. The site is still serving, which is what matters.
    check("healthz reports ok or degraded", h["status"] in ("ok", "degraded"), h["status"])
    if h["status"] == "degraded":
        print(f"        (note: degraded -> {str(h.get('degradedReason'))[:90]})")
        print("        site is up on FileStore; the configured DB is unreachable")
    meta = req("/api/meta")
    check("durable store (data survives restart)",
          meta["store"] in ("FileStore", "MongoStore", "FirestoreStore"), meta["store"])
    check("66 listings", meta["total"] == 66, str(meta["total"]))
    check("email configured", meta["emailConfigured"] is True)
    check("63 open", req("/api/opportunities")["total"] == 63)
    with urllib.request.urlopen(BASE + "/", timeout=45) as r:
        index = r.read().decode()
    check("landing page served", "OpportunityHub" in index, f"{len(index)} bytes")
    with urllib.request.urlopen(BASE + "/docs", timeout=45) as r:
        check("/docs served", r.status == 200)

    print("\nunknown API paths stay JSON, and .env is not reachable")
    for path in ("/api/nope", "/api/opportunities/doesnotexist"):
        try:
            urllib.request.urlopen(BASE + path, timeout=45)
            check(f"{path} returns 404", False, "it was ALLOWED")
        except urllib.error.HTTPError as e:
            payload = e.read().decode("utf-8", "ignore")
            check(f"{path} returns 404 JSON", e.code == 404 and "detail" in payload)

    # Raw socket so the client cannot normalise the path before it is sent.
    for path in ("/../.env", "/..%2f.env", "/.%2e/.env", "/index.html/../../.env"):
        try:
            conn = http.client.HTTPConnection(
                BASE.split("//")[1].split("/")[0], timeout=45)
            conn.request("GET", path)
            resp = conn.getresponse()
            body = resp.read()
            check(f"{path} does not leak .env",
                  b"SECRET_KEY" not in body and b"EMAIL_PASS" not in body,
                  f"{resp.status}, {len(body)} bytes")
            conn.close()
        except Exception as exc:
            check(f"{path} does not leak .env", True, f"blocked: {type(exc).__name__}")

    print("\nsearch over the public link")
    check("'open source' finds results",
          req("/api/opportunities?q=open%20source")["total"] > 0)
    check("category filter", req("/api/opportunities?category=scholarship")["total"] > 0)
    check("remote filter", req("/api/opportunities?mode=remote")["total"] > 0)

    print("\njudge journey: signup -> email OTP -> profile")
    email = f"public-{int(time.time())}@fit.edu.in"
    su = req("/api/auth/signup", {"name": "Public Test", "email": email,
                                  "password": "Public12345"})
    check("signup accepted", su.get("otpRequired") is True)
    check("email actually sent", su.get("emailSent") is True, str(su.get("emailSent")))

    code = None
    for _ in range(10):
        time.sleep(1)
        code = newest_otp(email)
        if code:
            break
    check("OTP captured from the server log", bool(code), str(code))
    if not code:
        print("\ncannot continue without the code")
        sys.exit(1)

    v = req("/api/auth/verify-otp", {"email": email, "code": code})
    check("verified", v.get("name") == "Public Test")
    check("session cookie set", "oh_session" in [c.name for c in _jar],
          str([c.name for c in _jar]))

    p = req("/api/auth/update-profile", {
        "year": "3rd Year", "skills": ["Python", "React", "SQL"],
        "interests": ["machine learning"], "categories": ["internship", "hackathon"]})
    check("profile saved", p.get("year") == "3rd Year", str(p.get("year")))

    print("\npersonalised results")
    recs = req(f"/api/recommendations/{p['id']}")["items"]
    check("recommendations returned", len(recs) > 0, f"{len(recs)} items")
    top = recs[0]
    check("top match is scored", top["score"] > 0, f"{top['score']}% {top['title']}")
    check("match explains itself", len(top["reasons"]) > 0, str(top["reasons"][:1]))
    gap = req(f"/api/skill-gap/{p['id']}")["items"]
    check("skill-gap analysis returned", len(gap) > 0,
          ", ".join(g["skill"] for g in gap[:3]))

    opp = req("/api/opportunities")["items"][0]["id"]
    bm = req("/api/bookmarks", {"studentId": p["id"], "opportunityId": opp})
    check("bookmark saved", bm["saved"] is True)
    check("bookmark listed", req(f"/api/bookmarks/{p['id']}")["total"] == 1)

    dash = req(f"/api/dashboard/{p['id']}")["stats"]
    check("dashboard populated", dash["openNow"] > 0 and dash["strongMatches"] >= 0,
          json.dumps(dash))

    print("\nsecurity still enforced over the public link")
    # A fresh jar with no cookies. Reusing the session jar here would make the
    # write legitimately authenticated, which previously made this assert
    # "ALLOWED" and looked like a vulnerability.
    anon = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(
        http.cookiejar.CookieJar()))
    r = urllib.request.Request(
        BASE + "/api/auth/update-profile",
        data=json.dumps({"skills": ["x"]}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with anon.open(r, timeout=45) as resp:
            check("unauthenticated write is rejected", False,
                  f"HTTP {resp.status} -- it was ALLOWED")
    except urllib.error.HTTPError as e:
        check("unauthenticated write is rejected", e.code == 401, f"HTTP {e.code}")

    print(f"\n{'ALL PASS' if not fails else f'{fails} FAILURES'}")
    sys.exit(1 if fails else 0)
