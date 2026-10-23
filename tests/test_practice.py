import random
from fractions import Fraction

import pytest

from app.agents.practice import PRACTICE_SKILLS, generate
from app.agents.verifier import verify
from app.algebra import parse_equation


@pytest.mark.parametrize("skill", PRACTICE_SKILLS)
@pytest.mark.parametrize("level", ["easy", "medium", "hard"])
def test_every_generated_question_is_verified(skill, level):
    rng = random.Random(7)
    for _ in range(60):
        q, a = generate(skill, level, rng)
        assert verify(q, Fraction(a)), (q, a)
        assert parse_equation(q).solution == Fraction(a)
        assert a != "0"


def test_verifier_rejects_wrong_answer():
    assert verify("2x + 3 = 11", Fraction(4))
    assert not verify("2x + 3 = 11", Fraction(5))
    assert not verify("x + 1 = x + 2", Fraction(1))
    assert not verify("x + 1 = x + 1", Fraction(1))
    assert not verify("not an equation", Fraction(1))
    assert not verify("", Fraction(0))

