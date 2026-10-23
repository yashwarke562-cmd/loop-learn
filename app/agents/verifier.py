"""Verifier agent: independently re-solves every generated practice question before a student sees it."""
from __future__ import annotations

from fractions import Fraction

from ..algebra import AlgebraError, parse_equation


def verify(question: str, expected: Fraction) -> bool:
    try:
        sol = parse_equation(question).solution
    except AlgebraError:
        return False
    return isinstance(sol, Fraction) and sol == expected
