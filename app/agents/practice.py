"""Practice agent: builds a fresh question for a skill and level, then asks the verifier to approve it."""
from __future__ import annotations

import random
from fractions import Fraction
from typing import Optional

from .verifier import verify

SKILLS = {
    "moving_terms": "Moving terms across =",
    "variables_both_sides": "x on both sides",
    "division_step": "Dividing to finish",
    "brackets": "Brackets",
    "arithmetic": "Careful arithmetic",
    "general": "Mixed practice",
    "overall": "Overall",
}
PRACTICE_SKILLS = [s for s in SKILLS if s != "overall"]


def _lin(a: int, b: int) -> str:
    x = "x" if a == 1 else "-x" if a == -1 else f"{a}x"
    if a == 0:
        return str(b)
    return x if b == 0 else f"{x} {'+' if b > 0 else '-'} {abs(b)}"


def _nz(rng: random.Random, lo: int, hi: int) -> int:
    return rng.choice([n for n in range(lo, hi + 1) if n != 0])


def _build(skill: str, level: str, rng: random.Random) -> tuple[str, int]:
    span = {"easy": 6, "medium": 9, "hard": 14}[level]
    x0 = _nz(rng, -9, 9)
    if skill == "division_step":
        a = _nz(rng, 2, {"easy": 5, "medium": 9, "hard": 12}[level])
        if level == "hard" and rng.random() < 0.5:
            a = -a
        return f"{_lin(a, 0)} = {a * x0}", x0
    if skill == "variables_both_sides":
        a, c = rng.randint(2, 6), rng.randint(1, 5)
        if level != "hard" and a <= c:
            a = c + rng.randint(1, 3)
        if a == c:
            a += 1
        b = _nz(rng, -span, span)
        d = a * x0 + b - c * x0
        return f"{_lin(a, b)} = {_lin(c, d)}", x0
    if skill == "brackets":
        a = _nz(rng, 2, 6)
        b = _nz(rng, -span, span) if level != "easy" else rng.randint(1, span)
        inside = f"x {'+' if b > 0 else '-'} {abs(b)}"
        if level == "hard":
            c = a + rng.choice([-2, -1, 1, 2])
            d = a * (x0 + b) - c * x0
            return f"{a}({inside}) = {_lin(c, d)}", x0
        return f"{a}({inside}) = {a * (x0 + b)}", x0
    # moving_terms, arithmetic, general: x + b = c  ->  ax + b = c
    b = _nz(rng, -span, span)
    if level == "easy":
        return f"x {'+' if b > 0 else '-'} {abs(b)} = {x0 + b}", x0
    a = _nz(rng, 2, 6 if level == "medium" else 12)
    return f"{_lin(a, b)} = {a * x0 + b}", x0


def generate(skill: str, level: str, rng: Optional[random.Random] = None) -> tuple[str, str]:
    """Return (question, answer). Retries until the verifier agrees with the generator."""
    rng = rng or random.Random()
    for _ in range(10):
        question, answer = _build(skill, level, rng)
        if verify(question, Fraction(answer)):
            return question, str(answer)
    raise RuntimeError("could not generate a verified question")
