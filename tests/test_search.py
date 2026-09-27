r"""Verify search tolerates spaces, and that typing no longer rebuilds the view.

Run: .\.venv\Scripts\python.exe tests\test_search.py
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8080"
fails = 0


def api(path):
    with urllib.request.urlopen(BASE + path, timeout=15) as r:
        return json.loads(r.read().decode())


def check(label, ok, extra=""):
    global fails
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}{('  ' + extra) if extra else ''}")
    fails += not ok


def q(term):
    return api("/api/opportunities?q=" + urllib.parse.quote(term))["total"]


if __name__ == "__main__":
    print("search tolerates whitespace (the space-bar bug)")
    spaced = q("open source")
    check("'open source' returns results", spaced > 0, f"{spaced} hits")

    check("trailing space gives the same result", q("open source ") == spaced,
          f"{q('open source ')} vs {spaced}")
    check("extra internal spaces collapse", q("open   source") == spaced,
          f"{q('open   source')} vs {spaced}")
    check("leading/trailing whitespace tolerated", q("  open source  ") == spaced,
          f"{q('  open source  ')} vs {spaced}")
    check("casing is ignored", q("OPEN SOURCE") == spaced, f"{q('OPEN SOURCE')} vs {spaced}")
    check("'deep ' (partial word, trailing space) still works", q("deep ") > 0,
          f"{q('deep ')} hits")
    check("nonsense returns 0, not everything", q("zzzznotathing") == 0)

    print("\nsearch still combines with other filters")
    check("category + query", api("/api/opportunities?q=scholarship&category=scholarship")["total"] > 0)
    check("closing + query", api("/api/opportunities?q=code&closing=30")["total"] > 0)
    check("mode + query", api("/api/opportunities?q=data&mode=remote")["total"] > 0)

    print("\nfrontend does not rebuild the view while typing")
    with urllib.request.urlopen(BASE + "/static/app.js", timeout=15) as r:
        js = r.read().decode()

    check("debounced input calls refreshResults, not renderDiscover",
          "debounce = setTimeout(refreshResults" in js)
    check("typing path never calls renderDiscover",
          not re.search(r"setTimeout\([^)]*renderDiscover", js))
    check("repaintChips() exists for in-place chip updates", "function repaintChips" in js)
    check("out-of-order responses are discarded", "state.searchToken" in js)
    check("search token state declared", "searchToken: 0" in js)
    check("empty state echoes the query back",
          "Try a shorter word" in js)

    api_src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "app", "api.py"), encoding="utf-8").read()
    check("server normalises query whitespace", '" ".join(str(q).split())' in api_src)

    print(f"\n{'ALL PASS' if not fails else f'{fails} FAILURES'}")
    sys.exit(1 if fails else 0)
