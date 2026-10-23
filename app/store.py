"""Data store interface and implementations.

Provides an abstract BaseStore with in-memory (MemoryStore) and Google Cloud Firestore (FirestoreStore)
backends matching the Firestore security rules in firestore.rules.
"""
from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import Counter, OrderedDict, defaultdict, deque
from typing import Any, Optional

log = logging.getLogger("learnloop")
MAX_PENDING = 20
MAX_EVENTS = 5000


def level_for(score: float) -> str:
    """Map mastery score [0.0, 1.0] to practice difficulty tier."""
    return "easy" if score < 0.4 else "medium" if score < 0.75 else "hard"


class BaseStore(ABC):
    """Abstract store interface for student mastery, practice session state, and teacher analytics."""

    @abstractmethod
    def update_mastery(self, uid: str, skill: str, correct: bool) -> dict[str, Any]:
        """Update exponentially weighted average score for student uid on skill."""
        ...

    @abstractmethod
    def get_mastery(self, uid: str) -> dict[str, dict[str, Any]]:
        """Return dict of skill -> {score, attempts, correct} for student uid."""
        ...

    @abstractmethod
    def weakest_skill(self, uid: str, default: str) -> str:
        """Find the skill tag with lowest score for student uid."""
        ...

    @abstractmethod
    def put_question(self, uid: str, qid: str, answer: str, skill: str) -> None:
        """Store pending one-shot practice question on the server."""
        ...

    @abstractmethod
    def pop_question(self, uid: str, qid: str) -> Optional[dict[str, str]]:
        """Pop and verify a pending question once. Returns None if expired or already answered."""
        ...

    @abstractmethod
    def add_event(self, uid: str, kind: str, skill: str, misconception: Optional[str], needs_teacher: bool) -> None:
        """Log an anonymised event for teacher analytics."""
        ...

    @abstractmethod
    def class_summary(self) -> dict[str, Any]:
        """Produce aggregated class statistics without identifying individual students."""
        ...


class MemoryStore(BaseStore):
    """Fast, thread-safe in-memory store for local runs, evaluations, and tests."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.mastery: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self.pending: dict[str, OrderedDict[str, dict[str, str]]] = defaultdict(OrderedDict)
        self.events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)

    def update_mastery(self, uid: str, skill: str, correct: bool) -> dict[str, Any]:
        with self.lock:
            m = self.mastery[uid].setdefault(skill, {"score": 0.3, "attempts": 0, "correct": 0})
            m["score"] = round(0.7 * m["score"] + 0.3 * (1.0 if correct else 0.0), 3)
            m["attempts"] += 1
            m["correct"] += int(correct)
            return dict(m)

    def get_mastery(self, uid: str) -> dict[str, dict[str, Any]]:
        with self.lock:
            return {k: dict(v) for k, v in self.mastery[uid].items()}

    def weakest_skill(self, uid: str, default: str) -> str:
        m = self.get_mastery(uid)
        return min(m, key=lambda k: m[k]["score"]) if m else default

    def put_question(self, uid: str, qid: str, answer: str, skill: str) -> None:
        with self.lock:
            q = self.pending[uid]
            q[qid] = {"answer": answer, "skill": skill}
            while len(q) > MAX_PENDING:
                q.popitem(last=False)

    def pop_question(self, uid: str, qid: str) -> Optional[dict[str, str]]:
        with self.lock:
            return self.pending[uid].pop(qid, None)

    def add_event(self, uid: str, kind: str, skill: str, misconception: Optional[str], needs_teacher: bool) -> None:
        with self.lock:
            self.events.append({
                "t": time.time(), "uid": uid, "kind": kind, "skill": skill,
                "misconception": misconception, "needs_teacher": needs_teacher,
            })

    def class_summary(self) -> dict[str, Any]:
        with self.lock:
            events = list(self.events)
            students = set(self.mastery) | {e["uid"] for e in events}
            per_skill: dict[str, list[float]] = defaultdict(list)
            for skills in self.mastery.values():
                for skill, m in skills.items():
                    per_skill[skill].append(m["score"])

        checks = 0
        needs_teacher = 0
        mis: Counter[str] = Counter()
        for e in events:
            if e["kind"] == "diagnosis":
                checks += 1
                if e["needs_teacher"]:
                    needs_teacher += 1
                if e["misconception"]:
                    mis[e["misconception"]] += 1

        return {
            "students": len(students),
            "checks": checks,
            "needs_teacher": needs_teacher,
            "misconceptions": mis.most_common(),
            "skills": {k: round(sum(v) / len(v), 2) for k, v in per_skill.items() if v},
        }


class FirestoreStore(BaseStore):
    """Cloud Firestore backed persistence implementing firestore.rules hierarchy."""

    def __init__(self, db: Optional[Any] = None) -> None:
        self._db = db
        self._memory_fallback = MemoryStore()

    def _get_db(self):
        if self._db is None:
            try:
                from firebase_admin import firestore
                self._db = firestore.client()
            except Exception as exc:
                log.warning("Firestore connection failed, using fallback: %s", exc)
                return None
        return self._db

    def update_mastery(self, uid: str, skill: str, correct: bool) -> dict[str, Any]:
        db = self._get_db()
        if db is None:
            return self._memory_fallback.update_mastery(uid, skill, correct)
        doc_ref = db.collection("students").document(uid).collection("mastery").document(skill)
        doc = doc_ref.get()
        curr = doc.to_dict() if doc.exists else {"score": 0.3, "attempts": 0, "correct": 0}
        curr["score"] = round(0.7 * curr["score"] + 0.3 * (1.0 if correct else 0.0), 3)
        curr["attempts"] += 1
        curr["correct"] += int(correct)
        doc_ref.set(curr)
        return curr

    def get_mastery(self, uid: str) -> dict[str, dict[str, Any]]:
        db = self._get_db()
        if db is None:
            return self._memory_fallback.get_mastery(uid)
        docs = db.collection("students").document(uid).collection("mastery").stream()
        return {d.id: d.to_dict() for d in docs}

    def weakest_skill(self, uid: str, default: str) -> str:
        m = self.get_mastery(uid)
        return min(m, key=lambda k: m[k]["score"]) if m else default

    def put_question(self, uid: str, qid: str, answer: str, skill: str) -> None:
        db = self._get_db()
        if db is None:
            return self._memory_fallback.put_question(uid, qid, answer, skill)
        db.collection("students").document(uid).collection("pending").document(qid).set({
            "answer": answer, "skill": skill, "created_at": time.time(),
        })

    def pop_question(self, uid: str, qid: str) -> Optional[dict[str, str]]:
        db = self._get_db()
        if db is None:
            return self._memory_fallback.pop_question(uid, qid)
        ref = db.collection("students").document(uid).collection("pending").document(qid)
        doc = ref.get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        ref.delete()
        return {"answer": data["answer"], "skill": data["skill"]}

    def add_event(self, uid: str, kind: str, skill: str, misconception: Optional[str], needs_teacher: bool) -> None:
        db = self._get_db()
        if db is None:
            return self._memory_fallback.add_event(uid, kind, skill, misconception, needs_teacher)
        db.collection("events").add({
            "t": time.time(), "uid": uid, "kind": kind, "skill": skill,
            "misconception": misconception, "needs_teacher": needs_teacher,
        })

    def class_summary(self) -> dict[str, Any]:
        db = self._get_db()
        if db is None:
            return self._memory_fallback.class_summary()
        doc = db.collection("aggregates").document("class_overview").get()
        if doc.exists:
            return doc.to_dict()
        return self._memory_fallback.class_summary()


# Backward-compatible alias
Store = MemoryStore


def create_store(backend: str = "memory", **kwargs) -> BaseStore:
    """Factory creating the appropriate store instance."""
    if backend.lower() == "firestore":
        return FirestoreStore(**kwargs)
    return MemoryStore()
