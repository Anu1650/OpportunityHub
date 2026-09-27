r"""Sanity checks for the eligibility parser.

Run:  .\.venv\Scripts\python.exe -m tests.test_eligibility
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.recommend import min_required_year, parse_year

REQUIRED = [
    ("UG engineering students, 2nd-4th year", 2),
    ("UG students, 3rd year and above", 3),
    ("Final-year UG engineering students", 4),
    ("Postgraduate and final-year undergraduate science students", 4),
    ("All UG/PG students across India", None),
    ("UG students, any year", None),
    ("Open to students aged 18+ worldwide", None),
    ("All skill levels", None),
    ("Class 9-12 students", None),
    ("Postgraduate students only", 5),
]

YEARS = [("1st Year", 1), ("2nd year", 2), ("3rd Year", 3), ("Final Year", 4),
         ("Postgraduate", None), ("", None)]

if __name__ == "__main__":
    failed = 0
    print("min_required_year()")
    for text, want in REQUIRED:
        got = min_required_year({"eligibility": text})
        ok = got == want
        failed += not ok
        print(f"  {'ok ' if ok else 'FAIL'}  got={got!s:<5} want={want!s:<5} {text}")

    print("\nparse_year()")
    for text, want in YEARS:
        got = parse_year(text)
        ok = got == want
        failed += not ok
        print(f"  {'ok ' if ok else 'FAIL'}  got={got!s:<5} want={want!s:<5} {text!r}")

    print(f"\n{'ALL PASS' if not failed else f'{failed} FAILURES'}")
    sys.exit(1 if failed else 0)
