from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

HK = ZoneInfo("Asia/Hong_Kong")


def hk_calendar_date(dt: datetime) -> datetime.date:
    if dt.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return dt.astimezone(HK).date()


def assert_same_hk_calendar_day(window_start: datetime, window_end: datetime) -> None:
    if hk_calendar_date(window_start) != hk_calendar_date(window_end):
        raise ValueError("password_window_must_be_same_hk_calendar_day")
