"""Storage layer.

One interface, three implementations, selected by config.DB_BACKEND:

  MemoryStore     -- local development, zero credentials, zero setup
  MongoStore      -- MongoDB / Atlas
  FirestoreStore  -- Google Cloud Run with Application Default Credentials

All sit behind BaseStore, which layers a short-TTL cache in front of the
opportunity collection. Listings are read-only reference data, so caching
them keeps read volume near zero no matter how many judges browse.
"""

import logging
import threading
import time
from typing import Dict, List, Optional

from . import config

log = logging.getLogger("fitfest.store")


def _norm(value) -> str:
    """Lowercase + strip. Keeps filter comparisons forgiving."""
    return str(value or "").strip().lower()


def _next_object_id() -> str:
    """Readable, collision-resistant id without needing bson at import time."""
    import uuid

    return uuid.uuid4().hex[:12]


def _norm_list(values) -> List[str]:
    """Dedupe + strip, preserving the author's capitalisation.

    Casing matters in the UI ("Python", not "python"). All matching is
    case-insensitive and lowercases at the point of comparison instead.
    """
    seen, out = set(), []
    for v in values or []:
        t = str(v).strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


class BaseStore:
    """Caching wrapper. Subclasses implement the _raw_* and _auth_* methods."""

    def __init__(self) -> None:
        self._cache: Optional[List[dict]] = None
        self._cache_ts: float = 0.0
        self._lock = threading.Lock()

    # ---- cache-aware read ------------------------------------------------
    def list_opportunities(self) -> List[dict]:
        with self._lock:
            fresh = (
                self._cache is not None
                and (time.time() - self._cache_ts) < config.CACHE_TTL_SECONDS
            )
            if fresh:
                return list(self._cache or [])
        rows = self._list_opportunities()
        with self._lock:
            self._cache = rows
            self._cache_ts = time.time()
        return list(rows)

    def invalidate_cache(self) -> None:
        with self._lock:
            self._cache = None
            self._cache_ts = 0.0

    # ---- implemented by subclasses ---------------------------------------
    def _list_opportunities(self) -> List[dict]:
        raise NotImplementedError

    def _list_students(self) -> List[dict]:
        raise NotImplementedError

    def _put_student(self, student: dict) -> dict:
        raise NotImplementedError

    def _get_student(self, student_id: str) -> Optional[dict]:
        raise NotImplementedError

    def _get_opportunity(self, opportunity_id: str) -> Optional[dict]:
        raise NotImplementedError

    def _list_bookmarks(self, student_id: str) -> List[dict]:
        raise NotImplementedError

    def _add_bookmark(self, student_id: str, opportunity_id: str) -> dict:
        raise NotImplementedError

    def _remove_bookmark(self, student_id: str, opportunity_id: str) -> None:
        raise NotImplementedError

    def _count_opportunities(self) -> int:
        raise NotImplementedError

    # ---- key/value auth collections -------------------------------------
    # Implemented once per backend so all auth logic lives in this class
    # rather than being triplicated across Memory / Mongo / Firestore.
    def _auth_get(self, col: str, key: str) -> Optional[dict]:
        raise NotImplementedError

    def _auth_put(self, col: str, key: str, value: dict) -> None:
        raise NotImplementedError

    def _auth_del(self, col: str, key: str) -> None:
        raise NotImplementedError

    def _auth_iter(self, col: str) -> List[tuple]:
        """All (key, value) pairs in an auth collection. Needed to resolve a
        reset token to its email, and to revoke a user's sessions."""
        raise NotImplementedError

    # ---- auth API --------------------------------------------------------
    def auth_user_get(self, email: str) -> Optional[dict]:
        return self._auth_get("users", _norm(email))

    def auth_user_put(self, email: str, record: dict) -> None:
        self._auth_put("users", _norm(email), record)

    def otp_get(self, email: str) -> Optional[dict]:
        return self._auth_get("otps", _norm(email))

    def otp_put(self, email: str, record: dict) -> None:
        self._auth_put("otps", _norm(email), record)

    def otp_clear(self, email: str) -> None:
        self._auth_del("otps", _norm(email))

    def session_get(self, token: str) -> Optional[dict]:
        return self._auth_get("sessions", token)

    def session_put(self, token: str, record: dict) -> None:
        self._auth_put("sessions", token, record)

    def session_delete(self, token: str) -> None:
        self._auth_del("sessions", token)

    def reset_get(self, email: str) -> Optional[dict]:
        return self._auth_get("resets", _norm(email))

    def reset_put(self, email: str, record: dict) -> None:
        self._auth_put("resets", _norm(email), record)

    def reset_clear(self, email: str) -> None:
        self._auth_del("resets", _norm(email))

    def reset_email_for_token(self, token: str) -> Optional[str]:
        """Resolve a reset token back to the account it belongs to."""
        for key, record in self._auth_iter("resets"):
            if record and record.get("token") == token:
                return key
        return None

    def sessions_delete_for_email(self, email: str) -> int:
        """Revoke every session for an account. Called after a password reset
        so tokens issued against the old password stop working."""
        revoked = 0
        for key, record in self._auth_iter("sessions"):
            if (record or {}).get("email") == email:
                self._auth_del("sessions", key)
                revoked += 1
        return revoked

    # ---- shared public API ----------------------------------------------
    def count_opportunities(self) -> int:
        return len(self.list_opportunities())

    def get_opportunity(self, opportunity_id: str) -> Optional[dict]:
        for row in self.list_opportunities():
            if row["id"] == opportunity_id:
                return row
        return None

    def save_student(self, data: dict) -> dict:
        """Insert or update keyed on email -- identity is email-only (MVP)."""
        email = _norm(data.get("email"))
        existing = None
        for s in self._list_students():
            if _norm(s.get("email")) == email:
                existing = s
                break

        record = dict(data)
        record["email"] = email
        record["skills"] = _norm_list(data.get("skills"))
        record["interests"] = _norm_list(data.get("interests"))
        # Categories come from a fixed enum, so normalising them is safe.
        record["categories"] = _norm_list(
            [_norm(c) for c in (data.get("categories") or [])]
        )
        record["name"] = str(data.get("name") or "").strip()

        if existing:
            record["id"] = existing["id"]
            record["createdAt"] = existing.get("createdAt")
        else:
            record["createdAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return self._put_student(record)

    def get_student(self, student_id: str) -> Optional[dict]:
        return self._get_student(student_id)

    def bookmark_ids(self, student_id: str) -> set:
        return {b.get("opportunityId") for b in self._list_bookmarks(student_id)}

    def toggle_bookmark(self, student_id: str, opportunity_id: str) -> bool:
        """Returns True if now saved, False if now removed."""
        saved = self.bookmark_ids(student_id)
        if opportunity_id in saved:
            self._remove_bookmark(student_id, opportunity_id)
            return False
        self._add_bookmark(student_id, opportunity_id)
        return True


class MemoryStore(BaseStore):
    """In-process store. Data resets on restart -- local dev only."""

    def __init__(self) -> None:
        super().__init__()
        self.students: Dict[str, dict] = {}
        self.opportunities: Dict[str, dict] = {}
        self.bookmarks: Dict[str, dict] = {}
        self._auth: Dict[str, Dict[str, dict]] = {}
        self._seq = 0

    def _auth_get(self, col: str, key: str) -> Optional[dict]:
        return self._auth.get(col, {}).get(key)

    def _auth_put(self, col: str, key: str, value: dict) -> None:
        self._auth.setdefault(col, {})[key] = value

    def _auth_del(self, col: str, key: str) -> None:
        self._auth.get(col, {}).pop(key, None)

    def _auth_iter(self, col: str) -> List[tuple]:
        return list(self._auth.get(col, {}).items())

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}{self._seq:04d}"

    def seed(self, rows: List[dict]) -> int:
        # Idempotent: only seed into an empty collection.
        if self.opportunities:
            return 0
        for row in rows:
            self.opportunities[self._next_id("opp")] = dict(row)
        return len(rows)

    def _list_opportunities(self) -> List[dict]:
        return [dict(v, id=k) for k, v in self.opportunities.items()]

    def _list_students(self) -> List[dict]:
        return [dict(v, id=k) for k, v in self.students.items()]

    def _put_student(self, student: dict) -> dict:
        sid = student.get("id") or self._next_id("stu")
        student["id"] = sid
        self.students[sid] = student
        return student

    def _get_student(self, student_id: str) -> Optional[dict]:
        s = self.students.get(student_id)
        return dict(s, id=student_id) if s else None

    def _get_opportunity(self, opportunity_id: str) -> Optional[dict]:
        o = self.opportunities.get(opportunity_id)
        return dict(o, id=opportunity_id) if o else None

    def _list_bookmarks(self, student_id: str) -> List[dict]:
        return [b for b in self.bookmarks.values() if b["studentId"] == student_id]

    def _add_bookmark(self, student_id: str, opportunity_id: str) -> dict:
        bid = f"{student_id}:{opportunity_id}"
        self.bookmarks[bid] = {
            "id": bid,
            "studentId": student_id,
            "opportunityId": opportunity_id,
        }
        return self.bookmarks[bid]

    def _remove_bookmark(self, student_id: str, opportunity_id: str) -> None:
        self.bookmarks.pop(f"{student_id}:{opportunity_id}", None)


class FirestoreStore(BaseStore):
    """Cloud Run production store. Uses ADC -- no key file on disk."""

    def __init__(self) -> None:
        super().__init__()
        from google.cloud import firestore  # imported lazily so local dev never needs it

        self._db = firestore.Client(
            project=config.GCP_PROJECT, database=config.FIRESTORE_DATABASE
        )
        self.students = self._db.collection("students")
        self.opportunities = self._db.collection("opportunities")
        self.bookmarks = self._db.collection("bookmarks")

    def seed(self, rows: List[dict]) -> int:
        if self.count_opportunities() > 0:
            return 0
        for row in rows:
            self.opportunities.document().set(row)
        self.invalidate_cache()
        return len(rows)

    def _list_opportunities(self) -> List[dict]:
        return [doc.to_dict() for doc in self.opportunities.stream()]

    def _list_students(self) -> List[dict]:
        return [doc.to_dict() for doc in self.students.stream()]

    def _put_student(self, student: dict) -> dict:
        sid = student["id"]
        self.students.document(sid).set(student)
        return student

    def _get_student(self, student_id: str) -> Optional[dict]:
        snap = self.students.document(student_id).get()
        return snap.to_dict() if snap.exists else None

    def _get_opportunity(self, opportunity_id: str) -> Optional[dict]:
        snap = self.opportunities.document(opportunity_id).get()
        return snap.to_dict() if snap.exists else None

    def _list_bookmarks(self, student_id: str) -> List[dict]:
        return [
            d.to_dict()
            for d in self.bookmarks.stream()
            if d.to_dict().get("studentId") == student_id
        ]

    def _add_bookmark(self, student_id: str, opportunity_id: str) -> dict:
        doc = {
            "studentId": student_id,
            "opportunityId": opportunity_id,
            "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self.bookmarks.document(f"{student_id}__{opportunity_id}").set(doc)
        return doc

    def _remove_bookmark(self, student_id: str, opportunity_id: str) -> None:
        self.bookmarks.document(f"{student_id}__{opportunity_id}").delete()

    def _auth_get(self, col: str, key: str) -> Optional[dict]:
        snap = self._db.collection(col).document(key).get()
        return snap.to_dict() if snap.exists else None

    def _auth_put(self, col: str, key: str, value: dict) -> None:
        self._db.collection(col).document(key).set(value)

    def _auth_del(self, col: str, key: str) -> None:
        self._db.collection(col).document(key).delete()

    def _auth_iter(self, col: str) -> List[tuple]:
        return [(d.id, d.to_dict()) for d in self._db.collection(col).stream()]


class MongoStore(BaseStore):
    """MongoDB / Atlas backend.

    Selected when MONGODB_URI is set. Note the free-tier caveat: an Atlas M0
    cluster pauses after inactivity, so the first request after a quiet period
    can take a minute or two to wake.
    """

    def __init__(self) -> None:
        super().__init__()
        from pymongo import MongoClient

        # Server-selection timeouts kept short so a paused cluster surfaces as
        # an error fast rather than hanging the request indefinitely.
        self._client = MongoClient(
            config.MONGODB_URI, serverSelectionTimeoutMS=8000, connectTimeoutMS=8000
        )
        self._db = self._client[config.MONGODB_DB]
        self.students = self._db["students"]
        self.opportunities = self._db["opportunities"]
        self.bookmarks = self._db["bookmarks"]

        self.students.create_index("email", unique=True)
        self.bookmarks.create_index([("studentId", 1), ("opportunityId", 1)], unique=True)

    def seed(self, rows: List[dict]) -> int:
        if self.count_opportunities() > 0:
            return 0
        for row in rows:
            row = dict(row)
            if "id" not in row:
                row["id"] = _next_object_id()
            self.opportunities.insert_one(row)
        self.invalidate_cache()
        return len(rows)

    def _list_opportunities(self) -> List[dict]:
        return [{k: v for k, v in d.items() if k != "_id"} for d in self.opportunities.find({})]

    def _list_students(self) -> List[dict]:
        return [{k: v for k, v in d.items() if k != "_id"} for d in self.students.find({})]

    def _put_student(self, student: dict) -> dict:
        sid = student["id"]
        self.students.update_one({"id": sid}, {"$set": student}, upsert=True)
        return student

    def _get_student(self, student_id: str) -> Optional[dict]:
        d = self.students.find_one({"id": student_id}, {"_id": 0})
        return d

    def _get_opportunity(self, opportunity_id: str) -> Optional[dict]:
        return self.opportunities.find_one({"id": opportunity_id}, {"_id": 0})

    def _list_bookmarks(self, student_id: str) -> List[dict]:
        return list(self.bookmarks.find({"studentId": student_id}, {"_id": 0}))

    def _add_bookmark(self, student_id: str, opportunity_id: str) -> dict:
        doc = {
            "studentId": student_id,
            "opportunityId": opportunity_id,
            "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self.bookmarks.update_one(
            {"studentId": student_id, "opportunityId": opportunity_id},
            {"$set": doc},
            upsert=True,
        )
        return doc

    def _remove_bookmark(self, student_id: str, opportunity_id: str) -> None:
        self.bookmarks.delete_one({"studentId": student_id, "opportunityId": opportunity_id})

    def _auth_get(self, col: str, key: str) -> Optional[dict]:
        return self._db[col].find_one({"_id": key})

    def _auth_put(self, col: str, key: str, value: dict) -> None:
        self._db[col].update_one({"_id": key}, {"$set": value}, upsert=True)

    def _auth_del(self, col: str, key: str) -> None:
        self._db[col].delete_one({"_id": key})

    def _auth_iter(self, col: str) -> List[tuple]:
        return [(d["_id"], d) for d in self._db[col].find({})]


_store: Optional[BaseStore] = None


def get_store() -> BaseStore:
    """Build the configured backend.

    DB_BACKEND makes the choice explicit. In "auto" mode a stray MONGODB_URI
    silently shadowed GCP_PROJECT, which is nearly impossible to diagnose from a
    deployed URL, so the resolution is now logged rather than hidden.
    """
    global _store
    if _store is not None:
        return _store

    backend = config.DB_BACKEND
    resolved = backend

    if backend == "auto":
        if config.MONGODB_URI:
            resolved = "mongo"
        elif config.GCP_PROJECT:
            resolved = "firestore"
        else:
            resolved = "memory"
    elif backend not in ("memory", "mongo", "firestore"):
        raise RuntimeError(
            f"DB_BACKEND={backend!r} is not valid. Use auto, memory, mongo or firestore."
        )

    if resolved == "mongo":
        if not config.MONGODB_URI:
            raise RuntimeError("DB_BACKEND=mongo but MONGODB_URI is empty.")
        _store = MongoStore()
    elif resolved == "firestore":
        if not config.GCP_PROJECT:
            raise RuntimeError("DB_BACKEND=firestore but GCP_PROJECT is empty.")
        _store = FirestoreStore()
    else:
        if config.REQUIRE_DB:
            raise RuntimeError(
                f"REQUIRE_DB=1 but resolved backend is 'memory' (DB_BACKEND={backend!r}, "
                "MONGODB_URI and GCP_PROJECT both unset). Configure a real database."
            )
        _store = MemoryStore()

    log.info("store=%s (DB_BACKEND=%s resolved=%s)", type(_store).__name__, backend, resolved)
    return _store
