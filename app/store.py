"""Storage layer.

One interface, two implementations:

  MemoryStore     -- local development, zero credentials, zero setup
  FirestoreStore  -- production on Cloud Run, survives restarts

Both sit behind BaseStore, which layers a short-TTL cache in front of the
opportunity collection. Listings are read-only reference data, so caching
them keeps read volume near zero no matter how many judges browse.
"""

import threading
import time
from typing import Dict, List, Optional

from . import config


def _norm(value) -> str:
    """Lowercase + strip. Keeps filter comparisons forgiving."""
    return str(value or "").strip().lower()


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
    """Caching wrapper. Subclasses implement the five _raw_* methods."""

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
        self._seq = 0

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


_store: Optional[BaseStore] = None


def get_store() -> BaseStore:
    """Firestore when GCP_PROJECT is set, otherwise in-memory."""
    global _store
    if _store is None:
        if config.GCP_PROJECT:
            _store = FirestoreStore()
        else:
            _store = MemoryStore()
    return _store
