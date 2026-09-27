"""HTTP API. Thin controllers -- all logic lives in store.py / recommend.py."""

import hmac
import time
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response

from . import auth, config
from .models import (
    BookmarkIn,
    ForgotIn,
    LoginIn,
    ProfileUpdateIn,
    ResetIn,
    SignupIn,
    StudentIn,
    VerifyOtpIn,
)
from .recommend import score_opportunity, skill_gap
from .store import get_store

router = APIRouter(prefix="/api")

SESSION_COOKIE = "oh_session"



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
        "emailConfigured": bool(config.EMAIL_USER and config.EMAIL_PASS),
    }


# ==========================================================================
# AUTH
# ==========================================================================
# Session tokens are opaque random strings held server-side, not signed blobs.
# Nothing about the student is encoded in the cookie, so it leaks no data and
# can be revoked server-side on logout or password reset.
def _public_user(record: dict) -> dict:
    return {
        "studentId": record.get("studentId"),
        "name": record.get("name"),
        "email": record.get("email"),
    }


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=config.SESSION_TTL_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=False,  # flip to True once served over HTTPS
        path="/",
    )


def _start_session(store, record: dict, response: Response) -> None:
    token = auth.new_session_token()
    store.session_put(token, {
        "studentId": record.get("studentId"),
        "email": record.get("email"),
        "createdAt": time.time(),
    })
    _set_session_cookie(response, token)


def _issue_otp(store, email: str) -> dict:
    code = auth.generate_otp()
    store.otp_put(email, {"code": code, "createdAt": time.time(), "attempts": 0})
    sent, _ = auth.send_otp_email(email, code)
    return {"code": code, "sent": sent}


@router.post("/auth/signup")
def signup(payload: SignupIn, response: Response):
    store = get_store()
    email = str(payload.email).strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(400, "Enter a valid email address")

    if store.auth_user_get(email):
        raise HTTPException(409, "That email is already registered. Try logging in.")

    otp = _issue_otp(store, email)
    store.auth_user_put(email, {
        "name": payload.name.strip(),
        "email": email,
        "passwordHash": auth.hash_password(payload.password),
        "verified": False,
        "studentId": None,
    })
    return {
        "email": email,
        "otpRequired": True,
        "emailSent": otp["sent"],
        # Shown in the UI only when SMTP is unconfigured, so the signup flow
        # still completes on a machine with no mail credentials.
        "devCode": None if otp["sent"] else otp["code"],
    }


@router.post("/auth/verify-otp")
def verify_otp(payload: VerifyOtpIn, response: Response):
    store = get_store()
    email = str(payload.email).strip().lower()
    record = store.auth_user_get(email)
    if not record:
        raise HTTPException(404, "No signup found for that email")
    if record.get("verified"):
        raise HTTPException(400, "That account is already verified")

    otp = store.otp_get(email)
    if not otp:
        raise HTTPException(400, "Request a new code")
    if auth.otp_is_expired(otp, config.OTP_TTL_MINUTES):
        store.otp_clear(email)
        raise HTTPException(400, "That code expired. Request a new one.")
    if auth.otp_attempts_left(otp) <= 0:
        store.otp_clear(email)
        raise HTTPException(429, "Too many wrong attempts. Request a new code.")
    if not hmac.compare_digest(str(payload.code).strip(), str(otp.get("code", ""))):
        otp["attempts"] = int(otp.get("attempts", 0)) + 1
        store.otp_put(email, otp)
        raise HTTPException(400, "Incorrect code")

    student = store.save_student({
        "name": record["name"], "email": email,
        "university": "", "year": "", "degree": "",
        "skills": [], "interests": [], "categories": [],
    })
    record["verified"] = True
    record["studentId"] = student["id"]
    store.auth_user_put(email, record)
    store.otp_clear(email)
    _start_session(store, record, response)
    return {"ok": True, **_public_user(record)}


@router.post("/auth/resend-otp")
def resend_otp(payload: ForgotIn):
    store = get_store()
    email = str(payload.email).strip().lower()
    if not store.auth_user_get(email):
        raise HTTPException(404, "No account found for that email")
    otp = _issue_otp(store, email)
    return {"emailSent": otp["sent"], "devCode": None if otp["sent"] else otp["code"]}


@router.post("/auth/login")
def login(payload: LoginIn, response: Response):
    store = get_store()
    email = str(payload.email).strip().lower()
    record = store.auth_user_get(email)
    # Identical message for unknown email and wrong password, so this endpoint
    # cannot be used to discover which addresses have accounts.
    if not record or not auth.verify_password(payload.password, record.get("passwordHash", "")):
        raise HTTPException(401, "Incorrect email or password")
    if not record.get("verified"):
        raise HTTPException(403, "Verify your email first, then log in.")

    _start_session(store, record, response)
    return {"ok": True, **_public_user(record)}


@router.post("/auth/logout")
def logout(request: Request, response: Response):
    store = get_store()
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        store.session_delete(token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request):
    store = get_store()
    token = request.cookies.get(SESSION_COOKIE)
    session = store.session_get(token) if token else None
    if not session or not session.get("studentId"):
        return {"authenticated": False}
    record = store.auth_user_get(session.get("email", "")) or {}
    return {"authenticated": True, **_public_user(record)}


# ---------------------------------------------------------- password reset
@router.post("/auth/forgot")
def forgot(payload: ForgotIn):
    store = get_store()
    email = str(payload.email).strip().lower()
    record = store.auth_user_get(email)
    if not record:
        # Deliberately identical response, for the same anti-enumeration reason.
        return {"ok": True, "devToken": None}

    token = auth.new_session_token()
    store.reset_put(email, {"token": token, "createdAt": time.time()})
    sent, _ = auth.send_password_reset_email(email, token)
    return {"ok": True, "devToken": None if sent else token}


@router.post("/auth/reset")
def reset_password(payload: ResetIn):
    store = get_store()
    email = store.reset_email_for_token(payload.token)
    if not email:
        raise HTTPException(400, "Invalid or expired reset token")

    record = store.reset_get(email)
    if auth.otp_is_expired(record, config.OTP_TTL_MINUTES):
        store.reset_clear(email)
        raise HTTPException(400, "That reset link has expired. Request a new one.")

    user = store.auth_user_get(email)
    if not user:
        raise HTTPException(404, "Account not found")

    user["passwordHash"] = auth.hash_password(payload.password)
    store.auth_user_put(email, user)
    store.reset_clear(email)
    # Old sessions were issued against the previous password -- revoke them.
    store.sessions_delete_for_email(email)
    return {"ok": True}


@router.post("/auth/update-profile")
def update_profile(payload: ProfileUpdateIn, request: Request):
    """Auth-guarded profile write, so a session owns its own profile."""
    store = get_store()
    token = request.cookies.get(SESSION_COOKIE)
    session = store.session_get(token) if token else None
    if not session or not session.get("studentId"):
        raise HTTPException(401, "Sign in first")

    student = store.get_student(session["studentId"])
    if not student:
        raise HTTPException(404, "Profile not found")

    student.update(payload.model_dump())
    return store.save_student({k: v for k, v in student.items() if k != "id"})


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
