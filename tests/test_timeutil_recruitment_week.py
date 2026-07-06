from datetime import date

from app.timeutil import (
    recruitment_plan_end_date,
    recruitment_plan_weeks_from_end_date,
    record_recruitment_week_for_stats,
    recruitment_week_bounds,
    recruitment_week_no,
    recruitment_week_range_label,
)

START = date(2026, 6, 15)


def test_recruitment_week_no_seven_day_weeks():
    assert recruitment_week_no(START, date(2026, 6, 14)) is None
    assert recruitment_week_no(START, START) == 1
    assert recruitment_week_no(START, date(2026, 6, 21)) == 1
    assert recruitment_week_no(START, date(2026, 6, 22)) == 2
    assert recruitment_week_no(START, date(2026, 6, 28)) == 2
    assert recruitment_week_no(START, date(2026, 6, 29)) == 3


def test_recruitment_week_bounds_seven_day_weeks():
    assert recruitment_week_bounds(START, 1) == (date(2026, 6, 15), date(2026, 6, 21))
    assert recruitment_week_bounds(START, 2) == (date(2026, 6, 22), date(2026, 6, 28))
    assert recruitment_week_bounds(START, 3) == (date(2026, 6, 29), date(2026, 7, 5))


def test_recruitment_week_range_label_matches_bounds():
    assert recruitment_week_range_label(START, 1) == "6/15–6/21"
    assert recruitment_week_range_label(START, 2) == "6/22–6/28"


def test_recruitment_plan_end_date_matches_last_plan_week():
    assert recruitment_plan_end_date(START, 20) == recruitment_week_bounds(START, 20)[1]


def test_recruitment_plan_weeks_from_end_date():
    assert recruitment_plan_weeks_from_end_date(START, START) == 1
    assert recruitment_plan_weeks_from_end_date(START, date(2026, 6, 28)) == 2
    assert recruitment_plan_weeks_from_end_date(START, recruitment_plan_end_date(START, 20)) == 20


def test_record_recruitment_week_for_stats_prefers_site_assignment():
    assert record_recruitment_week_for_stats(START, date(2026, 6, 18), 2) == 2
    assert record_recruitment_week_for_stats(START, date(2026, 6, 25), None) == 2
    assert record_recruitment_week_for_stats(START, date(2026, 6, 14), 1) == 1
    assert record_recruitment_week_for_stats(START, date(2026, 6, 14), None) is None


def test_record_recruitment_week_for_stats_prefers_record_assignment():
    assert record_recruitment_week_for_stats(START, date(2026, 6, 18), 2, 5) == 5
    assert record_recruitment_week_for_stats(START, date(2026, 6, 25), None, 3) == 3
