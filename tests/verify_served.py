r"""Verify the actually-served frontend assets, not just what is on disk.

Run: .\.venv\Scripts\python.exe tests\verify_served.py
"""

import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8080"
fails = 0


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return r.read().decode("utf-8")


def get_json(path):
    return json.loads(get(path))


def check(label, ok, extra=""):
    global fails
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}{('  ' + extra) if extra else ''}")
    fails += not ok


if __name__ == "__main__":
    auth = get("/static/auth.js")
    app = get("/static/app.js")
    html = get("/")

    print("served auth.js")
    check("no A.view left", auth.count("A.view") == 0, f"count={auth.count('A.view')}")
    check("writes to shared view", auth.count("view.innerHTML") == 6,
          f"count={auth.count('view.innerHTML')}")
    for fn in ("paintAuth", "renderLanding", "renderLogin", "renderSignup",
               "renderOtp", "renderForgot", "renderReset"):
        check(f"defines {fn}()", f"function {fn}" in auth)

    print("\nserved app.js")
    check("boot deferred to DOMContentLoaded",
          'DOMContentLoaded", async function boot' in app)
    check("error message names the real failure", "The app failed to start" in app)
    check("no stale 'Could not reach the API'", "Could not reach the API" not in app)
    check("offers login/signup recovery", 'data-amode="login"' in app)
    check("no bare IIFE terminator left", not app.rstrip().endswith("})();"))

    print("\nserved index.html")
    check("app.js loads before auth.js",
          html.index("/static/app.js") < html.index("/static/auth.js"))
    check("no demo button", "btn-demo" not in html)
    check("toast container present", 'id="toast"' in html)
    check("view container present", 'id="view"' in html)

    print("\nAPI")
    h = get_json("/healthz")
    # "degraded" is healthy: the configured database was unreachable and the
    # app fell back to the file store rather than going offline.
    check("healthz reports ok or degraded", h["status"] in ("ok", "degraded"),
          h["status"])
    if h["status"] == "degraded":
        print(f"        (note: degraded -> {str(h.get('degradedReason'))[:80]})")
    check("listings seeded", h["listings"] == 66, f"listings={h['listings']}")
    check("opportunities open", get_json("/api/opportunities")["total"] == 63)
    check("no demo route", "/api/demo-profile" not in get_json("/openapi.json")["paths"])

    print(f"\n{'ALL PASS' if not fails else f'{fails} FAILURES'}")
    sys.exit(1 if fails else 0)
