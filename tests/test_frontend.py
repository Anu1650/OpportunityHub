r"""Static checks for the frontend that catch errors HTTP tests cannot.

The `A.view.innerHTML` bug shipped through a full API test pass because it only
manifests in a browser: a render function wrote to an element that was null. No
amount of curl testing finds that. These checks are the cheapest substitute for
having a browser available.

Run:  .\.venv\Scripts\python.exe tests\test_frontend.py
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "static")


def read(name: str) -> str:
    with open(os.path.join(STATIC, name), encoding="utf-8") as fh:
        return fh.read()


index = read("index.html")
app_js = read("app.js")
auth_js = read("auth.js")
all_js = app_js + "\n" + auth_js


def defined_ids() -> set:
    """Every id that exists in the static HTML, a JS template, or is assigned
    to a created element (e.g. the modal: `el.id = "modal"`)."""
    ids = set(re.findall(r'\bid=["\']([\w-]+)["\']', index))
    ids |= set(re.findall(r'\bid=["\']([\w-]+)["\']', all_js))
    ids |= set(re.findall(r'\.id\s*=\s*["\']([\w-]+)["\']', all_js))
    return ids


def referenced_ids() -> set:
    """Ids the JS looks up, which must exist or they evaluate to null."""
    ids = set(re.findall(r'\$\("#([\w-]+)"\)', all_js))
    ids |= set(re.findall(r'getElementById\("([\w-]+)"\)', all_js))
    ids |= set(re.findall(r'querySelector\("#([\w-]+)"\)', all_js))
    return ids


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}{('  ' + detail) if detail else ''}")
    return ok


if __name__ == "__main__":
    failed = 0
    ids = defined_ids()

    print("DOM id integrity")
    missing = sorted(referenced_ids() - ids)
    failed += not check(
        "every id looked up in JS exists in HTML or a template",
        not missing,
        f"missing: {missing}" if missing else f"({len(ids)} ids known)",
    )

    print("\nnull-container guards")
    # The exact bug that shipped: a render helper writing through a field that
    # was initialised to null and never assigned.
    failed += not check(
        "no `X.view.innerHTML` through an unassigned field",
        not re.search(r"\b[A-Z]\.view\.innerHTML", all_js),
    )
    failed += not check(
        "no `A.view` reference (A owns no view field)",
        "A.view" not in all_js,
    )
    failed += not check(
        "`view` is defined in app.js and used, not redeclared, in auth.js",
        "const view = " in app_js and "const view" not in auth_js,
    )

    print("\nscript load order")
    # app.js calls into auth.js (A, paintAuth), so auth.js must load second and
    # boot must be deferred until both files are parsed.
    i_app = index.find("/static/app.js")
    i_auth = index.find("/static/auth.js")
    failed += not check("app.js loads before auth.js", -1 < i_app < i_auth)
    failed += not check(
        "boot() deferred to DOMContentLoaded",
        'addEventListener("DOMContentLoaded", async function boot' in app_js,
    )

    print("\nno guest/demo leftovers")
    failed += not check(
        "no demo-profile endpoint call", "/api/demo-profile" not in all_js
    )
    failed += not check("no demo-profile route in api.py",
                        "/demo-profile" not in open(os.path.join(ROOT, "app", "api.py"),
                                                    encoding="utf-8").read())

    print("\nOTP never reaches the client")
    api_py = open(os.path.join(ROOT, "app", "api.py"), encoding="utf-8").read()
    # An OTP in an API response is readable from devtools or a shared screen,
    # which defeats the point of email verification.
    failed += not check("no devCode in any response", "devCode" not in api_py)
    failed += not check("no devToken in any response", "devToken" not in api_py)
    failed += not check("no devCode/devToken in the frontend",
                        "devCode" not in all_js and "devToken" not in all_js)
    failed += not check("OTP is captured server-side", "OTP for %s: %s" in api_py)

    print(f"\n{'ALL PASS' if not failed else f'{failed} FAILURES'}")
    sys.exit(1 if failed else 0)
