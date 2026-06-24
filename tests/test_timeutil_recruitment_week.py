from datetime import date

from app.timeutil import (
    recruitment_plan_end_date,
    recruitment_plan_weeks_from_end_date,
    recruitment_week_bounds,
    recruitment_week_no,
    recruitment_week_range_label,
)

START = date(2026, 6, 20)


def test_recruitment_week_no_partial_first_week():
    assert recruitment_week_no(START, date(2026, 6, 19)) is None
    assert recruitment_week_no(START, START) == 1
    assert recruitment_week_no(START, date(2026, 6, 21)) == 2
    assert recruitment_week_no(START, date(2026, 6, 27)) == 2
    assert recruitment_week_no(START, date(2026, 6, 28)) == 3


def test_recruitment_week_bounds_partial_first_week():
    assert recruitment_week_bounds(START, 1) == (date(2026, 6, 20), date(2026, 6, 20))
    assert recruitment_week_bounds(START, 2) == (date(2026, 6, 21), date(2026, 6, 27))
    assert recruitment_week_bounds(START, 3) == (date(2026, 6, 28), date(2026, 7, 4))


def test_recruitment_week_range_label_matches_bounds():
    assert recruitment_week_range_label(START, 1) == "6/20–6/20"
    assert recruitment_week_range_label(START, 2) == "6/21–6/27"


def test_recruitment_plan_end_date_matches_last_plan_week():
    assert recruitment_plan_end_date(START, 20) == recruitment_week_bounds(START, 20)[1]


def test_recruitment_plan_weeks_from_end_date():
    assert recruitment_plan_weeks_from_end_date(START, START) == 1
    assert recruitment_plan_weeks_from_end_date(START, date(2026, 6, 27)) == 2
    assert recruitment_plan_weeks_from_end_date(START, recruitment_plan_end_date(START, 20)) == 20
