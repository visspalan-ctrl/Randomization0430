from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HK = ZoneInfo("Asia/Hong_Kong")
DEFAULT_RECRUITMENT_START_DATE = date(2026, 6, 20)
DEFAULT_WEEKLY_PLAN_WEEKS = 20
DEFAULT_WEEKLY_PLAN_PER_WEEK = 60


def _aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def hk_calendar_date(dt: datetime) -> datetime.date:
    return _aware_utc(dt).astimezone(HK).date()


def assert_same_hk_calendar_day(window_start: datetime, window_end: datetime) -> None:
    if hk_calendar_date(window_start) != hk_calendar_date(window_end):
        raise ValueError("password_window_must_be_same_hk_calendar_day")


def format_hk_datetime(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return _aware_utc(dt).astimezone(HK).strftime("%Y-%m-%d %H:%M:%S HKT")


def hk_date_stamp(dt: datetime | None = None) -> str:
    target = _aware_utc(dt) if dt is not None else datetime.now(HK)
    return target.astimezone(HK).strftime("%Y%m%d")


def hk_datetime_stamp(dt: datetime | None = None) -> str:
    target = _aware_utc(dt) if dt is not None else datetime.now(HK)
    return target.astimezone(HK).strftime("%Y%m%d_%H%M%S")


def hk_today_password_window() -> tuple[datetime, datetime]:
    now_hk = datetime.now(HK)
    start = now_hk.replace(hour=0, minute=0, second=0, microsecond=0)
    end = now_hk.replace(hour=23, minute=59, second=59, microsecond=0)
    return start, end


def recruitment_week_no(start_date: date, event_date: date) -> int | None:
    if event_date < start_date:
        return None
    if event_date == start_date:
        return 1
    return ((event_date - start_date).days - 1) // 7 + 2


def recruitment_week_bounds(start_date: date, week_no: int) -> tuple[date, date]:
    if week_no <= 1:
        return start_date, start_date
    week_start = start_date + timedelta(days=1 + (week_no - 2) * 7)
    week_end = start_date + timedelta(days=(week_no - 1) * 7)
    return week_start, week_end


def recruitment_week_range_label(start_date: date, week_no: int) -> str:
    week_start, week_end = recruitment_week_bounds(start_date, week_no)
    return f"{week_start.month}/{week_start.day}–{week_end.month}/{week_end.day}"


def recruitment_plan_end_date(start_date: date, plan_weeks: int) -> date:
    """計劃跟踪最後一週的結束日（含當日）。"""
    if plan_weeks < 1:
        return start_date
    return recruitment_week_bounds(start_date, plan_weeks)[1]


def recruitment_plan_weeks_from_end_date(start_date: date, end_date: date) -> int | None:
    """由招募結束日反推計劃跟踪週數（與 recruitment_week_no 規則一致）。"""
    return recruitment_week_no(start_date, end_date)
