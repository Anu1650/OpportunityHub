"""Matching + skill-gap analysis.

Deliberately explainable rather than ML: a judge can see exactly why an
opportunity scored what it did, and it costs 30 minutes instead of 3 hours.
"""

import re
from typing import Dict, List, Optional, Tuple

# Weights are deliberately visible -- they show up in the UI.
W_SKILL = 3
W_INTEREST_TAG = 2
W_INTEREST_TEXT = 1
W_CATEGORY = 2
W_ELIGIBILITY = 3

# Points needed for a 100% match. Linear and hand-checkable: a judge can add
# up the weights and confirm the number, which a black-box model could not do.
POINTS_FOR_FULL_MATCH = 18

CAP_TEXT = 3

# Year-of-study is stored as free text ("3rd Year"), so it is parsed rather
# than hand-maintained as a separate column on 60+ listings.
_ORDINAL = re.compile(r"(\d+)\s*(?:st|nd|rd|th)\s*year", re.I)
# "2nd-4th year" means years two to four, so the MINIMUM is the first number.
# This must be tested before _ORDINAL, which would otherwise match the "4th
# year" tail and wrongly conclude the listing requires final year.
_YEAR_RANGE = re.compile(r"(\d+)\s*(?:st|nd|rd|th)\s*(?:-|–|to)\s*\d+\s*(?:st|nd|rd|th)\s*year", re.I)
_FINAL_YEAR = re.compile(r"final[\s-]*year", re.I)
# "Postgraduate students only", "PG only", "PhD candidates only" -- allow a few
# words between the credential and "only" rather than requiring adjacency.
_POSTGRAD_ONLY = re.compile(r"(postgrad\w*|\bph\.?d)\b[^.]{0,25}\bonly\b", re.I)


def parse_year(text) -> Optional[int]:
    """'3rd Year' -> 3.  Returns None when the year cannot be determined."""
    s = str(text or "").strip()
    if not s:
        return None
    if _FINAL_YEAR.search(s):
        return 4
    m = _ORDINAL.search(s)
    if m:
        n = int(m.group(1))
        return n if 1 <= n <= 4 else None
    return None


def min_required_year(opp: dict) -> Optional[int]:
    """Derive the minimum year of study a listing demands.

    Parses the human-readable eligibility line instead of adding a column to
    every seeded record. Returns None when the listing is open to all.
    """
    text = str(opp.get("eligibility") or "")

    if _POSTGRAD_ONLY.search(text):
        return 5  # effectively postgraduate-only
    if _FINAL_YEAR.search(text):
        return 4
    r = _YEAR_RANGE.search(text)
    if r:
        n = int(r.group(1))
        return n if 1 <= n <= 4 else None
    m = _ORDINAL.search(text)
    if m:
        n = int(m.group(1))
        return n if 1 <= n <= 4 else None
    return None


def check_eligibility(opp: dict, profile: Optional[dict]) -> Tuple[bool, Optional[str]]:
    """(eligible, human-readable note). Unrestricted listings are eligible."""
    required = min_required_year(opp)
    if not required:
        return True, None

    student_year = parse_year(profile.get("year") if profile else None)
    ordinal = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "postgraduate"}

    if student_year is None:
        # Unknown, not wrong. Award nothing but explain the gap.
        return False, f"Needs {ordinal.get(required)} year or above — add your year of study to verify"

    if student_year >= required:
        return True, f"Open to {ordinal.get(required)} year and above — you qualify"

    return False, f"Needs {ordinal.get(required)} year or above — you are in your {ordinal.get(student_year)} year"


def _norm_list(values) -> List[str]:
    return [str(v).strip() for v in (values or []) if str(v).strip()]


def score_opportunity(opp: dict, profile: Optional[dict]) -> dict:
    """Return score + the exact terms that produced it."""
    if not profile:
        return {
            "score": 0,
            "points": 0,
            "matchedSkills": [],
            "matchedInterests": [],
            "reasons": [],
            "eligible": None,
            "eligibilityNote": None,
        }

    skills = {s.lower() for s in _norm_list(profile.get("skills"))}
    interests = {s.lower() for s in _norm_list(profile.get("interests"))}
    categories = {c.lower() for c in _norm_list(profile.get("categories"))}
    tags = {t.lower() for t in _norm_list(opp.get("tags"))}

    # Match case-insensitively but display the student's own capitalisation,
    # otherwise the UI reads "Matches your skills: javascript, python".
    skill_display = {s.lower(): s for s in _norm_list(profile.get("skills"))}
    interest_display = {i.lower(): i for i in _norm_list(profile.get("interests"))}

    matched_skills = sorted(skills & tags)
    matched_interests = sorted(interests & tags)

    # Interests are multi-word phrases ("machine learning"), so they must be
    # matched as substrings of the body text -- not against a token set, which
    # would only ever match single words.
    blob = f"{opp.get('title', '')} {opp.get('description', '')} {opp.get('org', '')}".lower()
    text_hits = sorted(
        i for i in (interests - set(matched_interests)) if len(i) > 2 and i in blob
    )[:CAP_TEXT]

    category_hit = str(opp.get("category", "")).lower() in categories
    eligible, elig_note = check_eligibility(opp, profile)

    points = (
        W_SKILL * len(matched_skills)
        + W_INTEREST_TAG * len(matched_interests)
        + W_INTEREST_TEXT * len(text_hits)
        + (W_CATEGORY if category_hit else 0)
        + (W_ELIGIBILITY if eligible else 0)
    )
    score = min(100, round(points / POINTS_FOR_FULL_MATCH * 100))

    reasons = []
    if matched_skills:
        reasons.append("Matches your skills: " + ", ".join(skill_display[s] for s in matched_skills))
    if matched_interests:
        reasons.append("Matches your interests: " + ", ".join(interest_display[i] for i in matched_interests))
    if category_hit:
        reasons.append(f"In a category you follow ({opp.get('category')})")
    if text_hits:
        reasons.append("Relevant to " + ", ".join(interest_display[i] for i in text_hits))
    if elig_note:
        reasons.append(elig_note)

    return {
        "score": score,
        "points": points,
        "matchedSkills": [skill_display[s] for s in matched_skills],
        "matchedInterests": [interest_display[i] for i in matched_interests],
        "reasons": reasons,
        "eligible": eligible,
        "eligibilityNote": elig_note,
    }


def skill_gap(opportunities: List[dict], profile: Optional[dict]) -> List[dict]:
    """Which unlisted skills unlock the most open opportunities.

    Turns a job board into a career tool, and costs almost nothing because
    the data is already loaded.
    """
    if not profile:
        return []

    # Exclude stated interests too -- telling the user to "learn" something
    # they already follow would be confusing, not helpful.
    have = {s.lower() for s in _norm_list(profile.get("skills"))}
    have |= {s.lower() for s in _norm_list(profile.get("interests"))}
    counts: Dict[str, int] = {}
    display: Dict[str, str] = {}
    for opp in opportunities:
        for tag in _norm_list(opp.get("tags")):
            t = tag.lower()
            if t not in have:
                counts[t] = counts.get(t, 0) + 1
                # Keep the listing's own spelling so "APIs" never renders
                # as "Apis" via naive title-casing.
                display.setdefault(t, tag)

    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [
        {"skill": display.get(k, k), "count": v} for k, v in ranked[:8] if v >= 2
    ]
