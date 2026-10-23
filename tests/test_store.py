import pytest
from app.store import MemoryStore, FirestoreStore, create_store, level_for, MAX_PENDING


def test_level_for_tiers():
    assert level_for(0.0) == "easy"
    assert level_for(0.35) == "easy"
    assert level_for(0.40) == "medium"
    assert level_for(0.70) == "medium"
    assert level_for(0.75) == "hard"
    assert level_for(1.0) == "hard"


def test_memory_store_mastery_and_weakest():
    store = MemoryStore()
    uid = "student_alpha"
    # Initial state
    assert store.get_mastery(uid) == {}
    assert store.weakest_skill(uid, default="moving_terms") == "moving_terms"

    # Update with correct answer
    m1 = store.update_mastery(uid, "brackets", True)
    assert m1["attempts"] == 1
    assert m1["correct"] == 1
    assert m1["score"] > 0.3

    # Update with incorrect answer
    m2 = store.update_mastery(uid, "division_step", False)
    assert m2["attempts"] == 1
    assert m2["correct"] == 0
    assert m2["score"] < 0.3

    # Weakest skill should now be division_step
    assert store.weakest_skill(uid, default="general") == "division_step"


def test_memory_store_pending_questions_and_fifo():
    store = MemoryStore()
    uid = "student_beta"

    # Insert MAX_PENDING + 2 questions
    for i in range(MAX_PENDING + 2):
        store.put_question(uid, f"q_{i}", f"{i}", "moving_terms")

    # Earliest questions (q_0 and q_1) should have been pruned by FIFO
    assert store.pop_question(uid, "q_0") is None
    assert store.pop_question(uid, "q_1") is None

    # Latest question should still exist
    popped = store.pop_question(uid, f"q_{MAX_PENDING + 1}")
    assert popped is not None
    assert popped["answer"] == str(MAX_PENDING + 1)
    assert popped["skill"] == "moving_terms"

    # One-shot: cannot pop twice
    assert store.pop_question(uid, f"q_{MAX_PENDING + 1}") is None


def test_memory_store_class_summary_aggregation():
    store = MemoryStore()
    store.add_event("s1", "diagnosis", "moving_terms", "sign_error_constant", False)
    store.add_event("s1", "diagnosis", "moving_terms", "sign_error_constant", False)
    store.add_event("s2", "diagnosis", "brackets", "distribution_error", True)
    store.add_event("s3", "practice", "moving_terms", None, False)

    summary = store.class_summary()
    assert summary["students"] == 3
    assert summary["checks"] == 3  # 3 diagnosis events
    assert summary["needs_teacher"] == 1
    mis_dict = dict(summary["misconceptions"])
    assert mis_dict["sign_error_constant"] == 2
    assert mis_dict["distribution_error"] == 1


def test_create_store_factory():
    mem = create_store("memory")
    assert isinstance(mem, MemoryStore)
    
    fs = create_store("firestore")
    assert isinstance(fs, FirestoreStore)
    
    # Default is memory
    default_store = create_store("unknown_backend")
    assert isinstance(default_store, MemoryStore)


def test_firestore_store_fallback_when_db_none():
    fs = FirestoreStore(db=None)
    # When Firestore client is None/unreachable, it transparently falls back to internal MemoryStore
    m = fs.update_mastery("fallback_user", "brackets", True)
    assert m["correct"] == 1
    assert fs.get_mastery("fallback_user")["brackets"]["correct"] == 1
    
    fs.put_question("fallback_user", "q1", "5", "brackets")
    assert fs.pop_question("fallback_user", "q1") == {"answer": "5", "skill": "brackets"}
    assert fs.pop_question("fallback_user", "q1") is None
