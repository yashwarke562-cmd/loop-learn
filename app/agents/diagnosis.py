"""Diagnosis agent: reads a student's work (typed or photographed) and finds the first broken step."""
from __future__ import annotations

import logging
from typing import Any, Optional

from ..algebra import check_steps
from ..security import looks_like_injection

log = logging.getLogger("learnloop")
MAX_LINES = 15


def split_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.replace("\r", "").split("\n") if ln.strip()]


def _template_message(res: dict) -> str:
    if res["status"] == "blocked":
        return "That looks like instructions, not algebra, so I ignored it. Write your equations one per line."
    if res["status"] == "unreadable":
        return ("I could not read that as algebra. Write one equation per line, like 2x + 3 = 11, "
                "using only numbers, x, + - * / and brackets.")
    if res["is_correct"]:
        return ("Every line holds up. Nice work." if res["complete"]
                else "Every line so far is right. Keep going until you reach x = a number.")
    return f"Line {res['first_error_step']} is where it went off track. {res['misconception']['tip']}"


def diagnose(question: str, steps_text: str, image: Optional[tuple[bytes, str]], llm: Optional[Any] = None) -> dict:
    """Return a diagnosis dict. `image` is (bytes, mime) already validated by the caller."""
    source = "checker"
    if image is not None:
        if llm is None:
            return {"status": "no_vision", "message": "Reading photos needs Gemini to be configured. "
                    "Type your steps instead, or set GEMINI_API_KEY and restart."}
        try:
            lines = llm.transcribe(*image)
            source = "gemini+checker"
        except Exception as exc:
            log.warning("transcription failed: %s", type(exc).__name__)
            return {"status": "unreadable", "message": "I could not read that photo. Try a clearer, "
                    "well-lit picture or type the steps."}
    else:
        lines = split_lines(steps_text)

    if len(lines) > MAX_LINES:
        return {"status": "unreadable", "message": f"Please send at most {MAX_LINES} lines."}
    if not lines:
        return {"status": "unreadable", "message": "No steps found. Add at least one line of working."}

    injection = looks_like_injection("\n".join(lines))
    res = check_steps(question, lines)
    res["injection_suspected"] = injection
    res["transcription"] = lines
    res["source"] = source
    if injection:
        res["status"] = "blocked"
        res["is_correct"] = False
    res["needs_teacher"] = res["status"] == "ok" and res["confidence"] < 0.6

    message = _template_message(res)
    if res["status"] == "ok" and not res["is_correct"] and llm is not None and not injection:
        try:
            facts = {"question": question, "line_number": res["first_error_step"],
                     "student_line": res["review"][res["first_error_step"] - 1]["text"],
                     "previous_line": res["prev_line"], "mistake": res["misconception"]["title"]}
            extra = llm.explain(facts)
            if extra:
                message = f"Line {res['first_error_step']}: {extra}"
        except Exception as exc:
            log.warning("explanation failed: %s", type(exc).__name__)
    res["message"] = message
    return res
