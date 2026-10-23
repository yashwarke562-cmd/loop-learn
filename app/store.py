"""In-memory store. Swap this class for Firestore in production (see firestore.rules)."""
from __future__ import annotations

import threading
import time
from collections import Counter, OrderedDict, defaultdict, deque

MAX_PENDING = 20
MAX_EVENTS = 5000


def level_for(score: float) -> str:
    return "easy" if score < 0.4 else "medium" if score < 0.75 else "hard"


class Store:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.mastery: dict[str, dict[str, dict]] = defaultdict(dict)
        self.pending: dict[str, OrderedDict] = defaultdict(OrderedDict)
        self.events: deque = deque(maxlen=MAX_EVENTS)

    # mastery -----------------------------------------------------------------
    def update_mastery(self, uid: str, skill: str, correct: bool) -> dict:
        with self.lock:
            m = self.mastery[uid].setdefault(skill, {"score": 0.3, "attempts": 0, "correct": 0})
            m["score"] = round(0.7 * m["score"] + 0.3 * (1.0 if correct else 0.0), 3)
            m["attempts"] += 1
            m["correct"] += int(correct)
            return dict(m)

    def get_mastery(self, uid: str) -> dict:
        with self.lock:
            return {k: dict(v) for k, v in self.mastery[uid].items()}

    def weakest_skill(self, uid: str, default: str) -> str:
        m = self.get_mastery(uid)
        return min(m, key=lambda k: m[k]["score"]) if m else default

    # practice questions (answers never leave the server) -----------------------
    def put_question(self, uid: str, qid: str, answer: str, skill: str) -> None:
        with self.lock:
            q = self.pending[uid]
            q[qid] = {"answer": answer, "skill": skill}
            while len(q) > MAX_PENDING:
                q.popitem(last=False)

    def pop_question(self, uid: str, qid: str):
        with self.lock:
            return self.pending[uid].pop(qid, None)

    # anonymised events for the teacher dashboard ---------------------------------
    def add_event(self, uid: str, kind: str, skill: str, misconception: str | None, needs_teacher: bool) -> None:
        with self.lock:
            self.events.append({
                "t": time.time(), "uid": uid, "kind": kind, "skill": skill,
                "misconception": misconception, "needs_teacher": needs_teacher,
            })

    def class_summary(self) -> dict:
        with self.lock:
            events = list(self.events)
            students = set(self.mastery) | {e["uid"] for e in events}
            per_skill: dict[str, list[float]] = defaultdict(list)
            for skills in self.mastery.values():
                for skill, m in skills.items():
                    per_skill[skill].append(m["score"])
        diag = [e for e in events if e["kind"] == "diagnosis"]
        mis = Counter(e["misconception"] for e in diag if e["misconception"])
        return {
            "students": len(students),
            "checks": len(diag),
            "needs_teacher": sum(1 for e in diag if e["needs_teacher"]),
            "misconceptions": mis.most_common(),
            "skills": {k: round(sum(v) / len(v), 2) for k, v in per_skill.items()},
        }
