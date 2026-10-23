"""Safe linear-equation parser, solver and step checker.

No eval(), no sympy: a tiny recursive-descent parser that only accepts digits, x, + - * / ( ) . and =.
Anything else (including prompt-injection text) fails to parse and is treated as unreadable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal, Optional, Union

MAX_LEN = 80
_ALLOWED = re.compile(r"^[0-9x+\-*/().=]+$")
_NUM = re.compile(r"\d+(?:\.\d+)?")

Solution = Union[Fraction, Literal["all", "none"]]  # Fraction, "all" (identity) or "none" (contradiction)


class AlgebraError(ValueError):
    pass


def _normalize(text: str) -> str:
    s = text.lower().strip()
    for a, b in (("×", "*"), ("·", "*"), ("÷", "/"), ("−", "-"), ("–", "-"), ("—", "-")):
        s = s.replace(a, b)
    return re.sub(r"\s+", "", s)


def _tokenize(s: str) -> list[Union[Fraction, str]]:
    tokens: list[Union[Fraction, str]] = []
    i = 0
    while i < len(s):
        m = _NUM.match(s, i)
        if m:
            if len(m.group()) > 9:
                raise AlgebraError("number too long")
            tokens.append(Fraction(m.group()))
            i = m.end()
        else:
            tokens.append(s[i])
            i += 1
    return tokens


# A linear expression is a tuple (a, b, is_group) meaning a*x + b.
Lin = tuple[Fraction, Fraction, bool]


class _Parser:
    def __init__(self, tokens: list[Union[Fraction, str]], dist_bug: bool = False) -> None:
        self.t = tokens
        self.i = 0
        self.bug = dist_bug

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def next(self):
        tok = self.peek()
        self.i += 1
        return tok

    def parse(self) -> Lin:
        out = self.expr()
        if self.peek() is not None:
            raise AlgebraError("unexpected token")
        return out

    def expr(self) -> Lin:
        left = self.term()
        while self.peek() in ("+", "-"):
            op = self.next()
            right = self.term()
            if op == "+":
                left = (left[0] + right[0], left[1] + right[1], False)
            elif self.bug and right[2]:
                left = (left[0] - right[0], left[1] + right[1], False)  # forgets to flip inside bracket
            else:
                left = (left[0] - right[0], left[1] - right[1], False)
        return left

    def term(self) -> Lin:
        left = self.factor()
        while True:
            p = self.peek()
            if p == "*":
                self.next()
                left = self._mul(left, self.factor())
            elif p == "/":
                self.next()
                left = self._div(left, self.factor())
            elif p == "x" or p == "(" or isinstance(p, Fraction):
                left = self._mul(left, self.factor())  # implicit multiplication: 2x, 3(x+1), (x+1)2
            else:
                return left

    def factor(self) -> Lin:
        p = self.next()
        if p == "+":
            return self.factor()
        if p == "-":
            inner = self.factor()
            if self.bug and inner[2]:
                return (-inner[0], inner[1], False)
            return (-inner[0], -inner[1], False)
        if isinstance(p, Fraction):
            return (Fraction(0), p, False)
        if p == "x":
            return (Fraction(1), Fraction(0), False)
        if p == "(":
            inner = self.expr()
            if self.next() != ")":
                raise AlgebraError("missing )")
            return (inner[0], inner[1], True)
        raise AlgebraError("unexpected token")

    def _mul(self, l: Lin, r: Lin) -> Lin:
        if l[0] != 0 and r[0] != 0:
            raise AlgebraError("not linear")
        if l[0] == 0:
            c, other = l[1], r
            if self.bug and not l[2] and r[2]:
                return (c * other[0], other[1], False)  # constant times bracket, forgets second term
        else:
            c, other = r[1], l
        return (c * other[0], c * other[1], False)

    def _div(self, l: Lin, r: Lin) -> Lin:
        if r[0] != 0 or r[1] == 0:
            raise AlgebraError("bad division")
        return (l[0] / r[1], l[1] / r[1], False)


@dataclass(frozen=True)
class Equation:
    a1: Fraction
    b1: Fraction
    a2: Fraction
    b2: Fraction

    @property
    def A(self) -> Fraction:
        return self.a1 - self.a2

    @property
    def B(self) -> Fraction:
        return self.b2 - self.b1

    @property
    def solution(self) -> Solution:
        if self.A == 0:
            return "all" if self.B == 0 else "none"
        return self.B / self.A

    @property
    def is_solved_form(self) -> bool:
        return self.a1 == 1 and self.b1 == 0 and self.a2 == 0


def parse_equation(text: str, dist_bug: bool = False) -> Equation:
    if not isinstance(text, str) or len(text) > MAX_LEN:
        raise AlgebraError("too long")
    s = _normalize(text)
    if not s or not _ALLOWED.match(s) or s.count("=") != 1:
        raise AlgebraError("not an equation")
    left, right = s.split("=")
    if not left or not right:
        raise AlgebraError("empty side")
    l = _Parser(_tokenize(left), dist_bug).parse()
    r = _Parser(_tokenize(right), dist_bug).parse()
    return Equation(l[0], l[1], r[0], r[1])


def parse_number(text: str) -> Fraction:
    """Parse a student's final answer such as 'x = 4', '4', '-3/2' or '2.5'."""
    if not isinstance(text, str) or len(text) > 30:
        raise AlgebraError("bad answer")
    s = _normalize(text)
    if s.startswith("x="):
        s = s[2:]
    if not s or not re.fullmatch(r"[0-9+\-*/().]+", s):
        raise AlgebraError("bad answer")
    a, b, _ = _Parser(_tokenize(s)).parse()
    if a != 0:
        raise AlgebraError("bad answer")
    return b


def fmt_fraction(f: Fraction) -> str:
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"


# ---- misconceptions: id -> (title, tip, skill tag) ---------------------------------------------

MISCONCEPTIONS = {
    "sign_error_constant": (
        "Sign slip when moving a number",
        "When a number crosses the equals sign, it changes sign. +3 on one side becomes -3 on the other.",
        "moving_terms",
    ),
    "sign_error_variable": (
        "Sign slip when moving x",
        "When an x-term crosses the equals sign, it changes sign too. Check which side you move it from.",
        "variables_both_sides",
    ),
    "sign_error_both": (
        "Sign slips on both moves",
        "Every term that crosses the equals sign flips its sign, numbers and x-terms alike.",
        "moving_terms",
    ),
    "division_skipped": (
        "Skipped the division",
        "If 4x = 20, divide both sides by 4 to get x = 5. The number in front of x has to go.",
        "division_step",
    ),
    "division_flipped": (
        "Divided the wrong way round",
        "To undo 4x, divide the other side by 4 (20 / 4), not 4 by 20.",
        "division_step",
    ),
    "distribution_error": (
        "Brackets: not every term was multiplied",
        "A number outside a bracket multiplies everything inside it: 3(x + 2) = 3x + 6, not 3x + 2.",
        "brackets",
    ),
    "arithmetic_slip": (
        "Small arithmetic slip",
        "The method is right but one calculation is off. Redo the adding or subtracting on this line.",
        "arithmetic",
    ),
    "unclear_error": (
        "This line does not follow from the one above",
        "The cause is not clear, so this one is best checked with your teacher.",
        "general",
    ),
}


def _hypothesis_solutions(prev: Equation, prev_text: str) -> list[tuple[str, Optional[Fraction]]]:
    """What solution would each known mistake produce if applied to the previous line?"""
    a1, b1, a2, b2 = prev.a1, prev.b1, prev.a2, prev.b2
    a0, b0 = prev.A, prev.B

    def solve(a: Fraction, b: Fraction) -> Optional[Fraction]:
        return b / a if a != 0 else None

    hyps: list[tuple[str, Optional[Fraction]]] = [
        ("sign_error_constant", solve(a1 - a2, b2 + b1)),
        ("sign_error_variable", solve(a1 + a2, b2 - b1)),
        ("sign_error_both", solve(a1 + a2, b2 + b1)),
    ]
    if a0 not in (0, 1):
        hyps.append(("division_skipped", b0))
        hyps.append(("division_flipped", a0 / b0 if b0 != 0 else None))
    if "(" in prev_text:
        try:
            sol = parse_equation(prev_text, dist_bug=True).solution
            hyps.append(("distribution_error", sol if isinstance(sol, Fraction) else None))
        except AlgebraError:
            pass
    return hyps


def classify(prev_text: str, prev: Equation, new: Equation) -> tuple[str, float]:
    """Return (misconception_id, confidence) for a step that changed the solution."""
    new_sol = new.solution
    if isinstance(new_sol, Fraction):
        for mid, sol in _hypothesis_solutions(prev, prev_text):
            if sol is not None and sol == new_sol:
                return mid, 0.9
    # A legitimate move (keep the line, flip it, or divide through to isolate x) with one wrong number.
    if prev.A != 0:
        ks = [Fraction(1), Fraction(-1)]
        if prev.b1 == 0 and prev.a2 == 0:  # previous line is already "Ax = B", so one division finishes it
            ks.append(1 / prev.A)
        for k in ks:
            if new.A == k * prev.A and new.B != k * prev.B:
                return "arithmetic_slip", 0.75
    if new.B == prev.B and new.A != prev.A:
        return "arithmetic_slip", 0.75
    return "unclear_error", 0.5


def check_steps(question: str, lines: list[str]) -> dict:
    """Walk through a student's lines and find the first one that breaks the solution."""
    try:
        prev_text, prev = question, parse_equation(question)
    except AlgebraError:
        return {"status": "unreadable", "reason": "question"}
    base = prev.solution
    if not isinstance(base, Fraction):
        return {"status": "unreadable", "reason": "question_not_unique"}

    review: list[dict] = []
    last_eq = prev
    error: Optional[tuple[int, str, float]] = None
    for idx, line in enumerate(lines, start=1):
        if error is not None:  # lines after the first mistake are shown but not judged
            review.append({"step": idx, "text": line.strip(), "ok": None})
            continue
        try:
            eq = parse_equation(line)
        except AlgebraError:
            return {"status": "unreadable", "reason": f"step_{idx}", "review": review}
        if eq.solution == base:
            review.append({"step": idx, "text": line.strip(), "ok": True})
            prev_text, prev, last_eq = line, eq, eq
        else:
            review.append({"step": idx, "text": line.strip(), "ok": False})
            mid, conf = classify(prev_text, prev, eq)
            error = (idx, mid, conf)

    if error is not None:
        idx, mid, conf = error
        title, tip, skill = MISCONCEPTIONS[mid]
        return {
            "status": "ok", "is_correct": False, "complete": False, "first_error_step": idx,
            "misconception": {"id": mid, "title": title, "tip": tip}, "skill_tag": skill,
            "confidence": conf, "review": review, "expected": fmt_fraction(base),
            "prev_line": prev_text,
        }
    return {
        "status": "ok", "is_correct": True, "complete": bool(review) and last_eq.is_solved_form,
        "first_error_step": None, "misconception": None, "skill_tag": "overall",
        "confidence": 0.95, "review": review, "expected": fmt_fraction(base),
    }
