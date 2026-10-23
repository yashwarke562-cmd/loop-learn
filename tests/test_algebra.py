from fractions import Fraction

import pytest

from app.algebra import AlgebraError, check_steps, parse_equation, parse_number


@pytest.mark.parametrize("eq,sol", [
    ("2x + 3 = 11", Fraction(4)), ("3(x+2)=15", Fraction(3)), ("2x+3 = x+9", Fraction(6)),
    ("x/2 = 5", Fraction(10)), ("-x + 4 = 1", Fraction(3)), ("4x = 10", Fraction(5, 2)),
    ("2(x-1) - (x+3) = 0", Fraction(5)), ("x + 1 = x + 1", "all"), ("x + 1 = x + 2", "none"),
    ("0.5x = 2", Fraction(4)), ("2×x + 3 = 9", Fraction(3)),
    ("(x + 1)/2 = 5", Fraction(9)), ("(2x - 4)/2 = 3", Fraction(5)),
    ("x/3 + 2 = 5", Fraction(9)), ("-(x + 2) = 5", Fraction(-7)), ("-2(x - 1) = 8", Fraction(-3)),
])
def test_solutions(eq, sol):
    assert parse_equation(eq).solution == sol


@pytest.mark.parametrize("bad", [
    "", "x", "2x+3", "x=1=2", "x*x = 4", "2/x = 1", "import os", "__import__('os')", "x = 1; rm -rf /",
    "ignore previous instructions", "2x + = 3", "(x + 1 = 3", "x/0 = 1", "1" * 81, "x = 1234567890123",
])
def test_rejects_non_algebra(bad):
    with pytest.raises(AlgebraError):
        parse_equation(bad)


@pytest.mark.parametrize("text,val", [("4", 4), ("x = 4", 4), ("-3/2", Fraction(-3, 2)), ("2.5", Fraction(5, 2)), ("8/2", 4)])
def test_parse_number(text, val):
    assert parse_number(text) == val


@pytest.mark.parametrize("text", ["", "x", "2x", "four", "x = x", "__import__"])
def test_parse_number_rejects(text):
    with pytest.raises(AlgebraError):
        parse_number(text)


@pytest.mark.parametrize("q,steps,mid,step", [
    ("2x + 3 = 11", ["2x = 11 + 3", "x = 7"], "sign_error_constant", 1),
    ("3x - 5 = 10", ["3x = 10 - 5", "x = 5/3"], "sign_error_constant", 1),
    ("3(x+2)=15", ["3x + 2 = 15", "3x = 13"], "distribution_error", 1),
    ("4x = 20", ["x = 20"], "division_skipped", 1),
    ("4x = 20", ["x = 4/20"], "division_flipped", 1),
    ("2x + 3 = x + 9", ["2x - x = 9 + 3", "x = 12"], "sign_error_constant", 1),
    ("5x + 2 = 2x + 11", ["5x + 2x = 11 - 2", "7x = 9"], "sign_error_variable", 1),
    ("2x + 3 = 11", ["2x = 8", "x = 5"], "arithmetic_slip", 2),
])
def test_misconceptions(q, steps, mid, step):
    r = check_steps(q, steps)
    assert r["status"] == "ok" and not r["is_correct"]
    assert r["misconception"]["id"] == mid
    assert r["first_error_step"] == step


def test_correct_work_complete():
    r = check_steps("2x + 3 = 11", ["2x = 8", "x = 4"])
    assert r["is_correct"] and r["complete"] and r["confidence"] > 0.9


def test_correct_but_unfinished():
    r = check_steps("2x + 3 = 11", ["2x = 8"])
    assert r["is_correct"] and not r["complete"]


def test_lines_after_first_error_are_not_judged():
    r = check_steps("2x + 3 = 11", ["2x = 11 + 3", "x = 7", "x = 4"])
    assert [s["ok"] for s in r["review"]] == [False, None, None]


def test_unreadable_step_reports_which():
    r = check_steps("2x + 3 = 11", ["2x = 8", "so x is four"])
    assert r["status"] == "unreadable" and r["reason"] == "step_2"


def test_unclear_error_has_low_confidence():
    r = check_steps("2x + 3 = 11", ["7x = 100"])
    assert r["misconception"]["id"] == "unclear_error" and r["confidence"] < 0.6


def test_fmt_fraction_representations():
    from app.algebra import fmt_fraction
    assert fmt_fraction(Fraction(5, 1)) == "5"
    assert fmt_fraction(Fraction(-4, 1)) == "-4"
    assert fmt_fraction(Fraction(3, 7)) == "3/7"
    assert fmt_fraction(Fraction(-2, 3)) == "-2/3"


def test_sign_error_both_detected():
    # 2x + 3 = x + 9 -> moving x to left and 3 to right without flipping either: 2x + x = 9 + 3 (3x = 12 -> x=4)
    r = check_steps("2x + 3 = x + 9", ["2x + x = 9 + 3", "3x = 12"])
    assert r["status"] == "ok" and not r["is_correct"]
    assert r["misconception"]["id"] == "sign_error_both"
    assert r["first_error_step"] == 1


def test_parse_number_negative_and_decimal():
    assert parse_number("x = -5") == Fraction(-5)
    assert parse_number("-3/4") == Fraction(-3, 4)
    assert parse_number("x = -2.5") == Fraction(-5, 2)


def test_store_level_for_thresholds():
    from app.store import level_for
    assert level_for(0.0) == "easy"
    assert level_for(0.39) == "easy"
    assert level_for(0.4) == "medium"
    assert level_for(0.749) == "medium"
    assert level_for(0.75) == "hard"
    assert level_for(1.0) == "hard"


def test_parse_equation_caching():
    eq1 = parse_equation("3x + 4 = 19")
    eq2 = parse_equation("3x + 4 = 19")
    assert eq1 is eq2
    assert eq1.solution == Fraction(5)


