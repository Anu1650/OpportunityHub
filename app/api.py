"""HTTP API. Thin controllers -- all logic lives in store.py / recommend.py."""

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from . import config
from .models import BookmarkIn, StudentIn
from .recommend import check_eligibility, score_opportunity, skill_gap
from .seed_data import DEMO_STUDENT
from .store import get_store

router = APIRouter(prefix="/api")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _days_left(deadline: Optional[str]) -> Optional[int]:
    if not deadline:
        return None
    try:
        d = datetime.strptime(str(deadline)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (d - date.today()).days


def _matches(o: dict, q: str, skills: str, category: str, mode: str, closing: str) -> bool:
    if q:
        blob = f"{o.get('title', '')} {o.get('org', '')} {o.get('description', '')}".lower()
        if q.lower() not in blob:
            return False
    if category and o.get("category") != category:
        return False
    if mode and o.get("mode") != mode:
        return False
    if skills:
        want = {s.strip().lower() for s in skills.split(",") if s.strip()}
        have = {t.lower() for t in o.get("tags", [])}
        if not (want & have):
            return False
    if closing:
        left = _days_left(o.get("deadline"))
        if left is None:
            return False
        if closing == "7" and not (0 <= left <= 7):
            return False
        if closing == "30" and not (0 <= left <= 30):
            return False
    return True


def _decorate(o: dict, profile: Optional[dict], saved_ids: set) -> dict:
    row = dict(o)
    row["daysLeft"] = _days_left(o.get("deadline"))
    row["saved"] = o.get("id") in saved_ids
    row.update(score_opportunity(o, profile))
    return row


def _sort_key(r: dict):
    """Open first, then by relevance, then by deadline."""
    left = r.get("daysLeft")
    if left is None:
        bucket = 2
    elif left < 0:
        bucket = 1
    else:
        bucket = 0
    return (bucket, -int(r.get("score") or 0), left if left is not None else 9999)


# --------------------------------------------------------------------------
# meta
# --------------------------------------------------------------------------
@router.get("/meta")
def meta():
    store = get_store()
    opps = store.list_opportunities()
    tags = sorted({t for o in opps for t in o.get("tags", [])})
    return {
        "categories": config.CATEGORIES,
        "modes": config.MODES,
        "tags": tags,
        "total": len(opps),
        "store": type(store).__name__,
    }


# --------------------------------------------------------------------------
# students
# --------------------------------------------------------------------------
@router.post("/students")
def upsert_student(payload: StudentIn):
    store = get_store()
    return store.save_student(payload.model_dump())


@router.get("/students/{student_id}")
def get_student(student_id: str):
    student = get_store().get_student(student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    return student


@router.post("/demo-profile")
def demo_profile():
    """One-click sample profile so a judge never lands on an empty state."""
    return get_store().save_student(dict(DEMO_STUDENT))


# --------------------------------------------------------------------------
# opportunities
# --------------------------------------------------------------------------
@router.get("/opportunities")
def list_opportunities(
    q: str = "",
    category: str = "",
    mode: str = "",
    skills: str = "",
    closing: str = "",
    studentId: str = "",
    minScore: int = 0,
    includeExpired: bool = False,
    eligibleOnly: bool = False,
    sort: str = Query("smart", pattern="^(smart|deadline|newest|relevance)$"),
    limit: int = Query(200, ge=1, le=500),
):
    store = get_store()
    profile = store.get_student(studentId) if studentId else None
    saved_ids = store.bookmark_ids(studentId) if studentId else set()

    rows = []
    for o in store.list_opportunities():
        if not _matches(o, q, skills, category, mode, closing):
            continue
        if not includeExpired:
            left = _days_left(o.get("deadline"))
            if left is not None and left < 0:
                continue
        row = _decorate(o, profile, saved_ids)
        if eligibleOnly and row.get("eligible") is False:
            continue
        rows.append(row)

    if minScore:
        rows = [r for r in rows if (r.get("score") or 0) >= minScore]

    if sort == "deadline":
        rows.sort(key=lambda r: r["daysLeft"] if r["daysLeft"] is not None else 9999)
    elif sort == "relevance":
        rows.sort(key=lambda r: -int(r.get("score") or 0))
    else:
        rows.sort(key=_sort_key)

    return {"total": len(rows), "items": rows[:limit]}


@router.get("/opportunities/{opp_id}")
def get_opportunity(opp_id: str, studentId: str = ""):
    store = get_store()
    o = store.get_opportunity(opp_id)
    if not o:
        raise HTTPException(404, "Opportunity not found")
    profile = store.get_student(studentId) if studentId else None
    return _decorate(o, profile, store.bookmark_ids(studentId) if studentId else set())


# --------------------------------------------------------------------------
# recommendations
# --------------------------------------------------------------------------
@router.get("/recommendations/{student_id}")
def recommendations(student_id: str, limit: int = 12):
    store = get_store()
    profile = store.get_student(student_id)
    if not profile:
        raise HTTPException(404, "Student not found")
    saved = store.bookmark_ids(student_id)

    rows = []
    for o in store.list_opportunities():
        left = _days_left(o.get("deadline"))
        if left is not None and left < 0:
            continue
        rows.append(_decorate(o, profile, saved))

    rows.sort(key=lambda r: -int(r.get("score") or 0))
    return {"items": rows[:limit]}


@router.get("/skill-gap/{student_id}")
def get_skill_gap(student_id: str, limit: int = 10):
    store = get_store()
    profile = store.get_student(student_id)
    if not profile:
        raise HTTPException(404, "Student not found")

    open_opps = [
        o for o in store.list_opportunities()
        if (_days_left(o.get("deadline")) or 1) >= 0
    ]
    return {"items": skill_gap(open_opps, profile)[:limit]}


# --------------------------------------------------------------------------
# bookmarks
# --------------------------------------------------------------------------
@router.get("/bookmarks/{student_id}")
def list_bookmarks(student_id: str):
    store = get_store()
    profile = store.get_student(student_id)
    if not profile:
        raise HTTPException(404, "Student not found")

    saved = store.bookmark_ids(student_id)
    rows = [
        _decorate(o, profile, saved)
        for o in store.list_opportunities()
        if o.get("id") in saved
    ]
    rows.sort(key=lambda r: r["daysLeft"] if r["daysLeft"] is not None else 9999)
    return {"total": len(rows), "items": rows}


@router.post("/bookmarks")
def toggle_bookmark(payload: BookmarkIn):
    store = get_store()
    if not store.get_student(payload.studentId):
        raise HTTPException(404, "Student not found")
    if not store.get_opportunity(payload.opportunityId):
        raise HTTPException(404, "Opportunity not found")
    saved = store.toggle_bookmark(payload.studentId, payload.opportunityId)
    return {"saved": saved, "opportunityId": payload.opportunityId}


# --------------------------------------------------------------------------
# dashboard
# --------------------------------------------------------------------------
@router.get("/dashboard/{student_id}")
def dashboard(student_id: str):
    store = get_store()
    profile = store.get_student(student_id)
    if not profile:
        raise HTTPException(404, "Student not found")

    all_opps = store.list_opportunities()
    saved_ids = store.bookmark_ids(student_id)

    open_opps = [o for o in all_opps if (_days_left(o.get("deadline")) or 1) >= 0]
    saved_rows = [_decorate(o, profile, saved_ids) for o in all_opps if o.get("id") in saved_ids]

    closing_soon = sorted(
        (_decorate(o, profile, saved_ids) for o in open_opps if (_days_left(o.get("deadline")) or 999) <= 14),
        key=lambda r: r["daysLeft"],
    )[:6]

    by_category: dict = {}
    for o in open_opps:
        by_category[o.get("category", "other")] = by_category.get(o.get("category", "other"), 0) + 1

    recs = sorted(
        (_decorate(o, profile, saved_ids) for o in open_opps),
        key=lambda r: -int(r.get("score") or 0),
    )[:6]

    return {
        "profile": profile,
        "stats": {
            "openNow": len(open_opps),
            "totalListings": len(all_opps),
            "saved": len(saved_ids),
            "closingThisWeek": sum(
                1 for o in open_opps if 0 <= (_days_left(o.get("deadline")) or 999) <= 7
            ),
            "strongMatches": sum(
                1 for o in open_opps if score_opportunity(o, profile)["score"] >= 60
            ),
        },
        "byCategory": by_category,
        "closingSoon": closing_soon,
        "recommended": recs,
        "savedItems": sorted(
            saved_rows, key=lambda r: r["daysLeft"] if r["daysLeft"] is not None else 9999
        )[:8],
        "skillGap": skill_gap(open_opps, profile)[:6],
    }
