"""Matching + skill-gap analysis.

Deliberately explainable rather than ML: a judge can see exactly why an
opportunity scored what it did, and it costs 30 minutes instead of 3 hours.
"""

from typing import Dict, List, Optional

# Weights are deliberately visible -- they show up in the UI.
W_SKILL = 3
W_INTEREST_TAG = 2
W_INTEREST_TEXT = 1
W_CATEGORY = 2

# Points needed for a 100% match. Linear and hand-checkable: a judge can add
# up the weights and confirm the number, which a black-box model could not do.
POINTS_FOR_FULL_MATCH = 15

CAP_TEXT = 3


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

    points = (
        W_SKILL * len(matched_skills)
        + W_INTEREST_TAG * len(matched_interests)
        + W_INTEREST_TEXT * len(text_hits)
        + (W_CATEGORY if category_hit else 0)
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

    return {
        "score": score,
        "points": points,
        "matchedSkills": [skill_display[s] for s in matched_skills],
        "matchedInterests": [interest_display[i] for i in matched_interests],
        "reasons": reasons,
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
