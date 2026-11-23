#!/usr/bin/env python3
"""
Monthly Report Date Calculator
Rule: "當月的最後一個星期三當週的星期五 (可能跨月)"
"""
import calendar
import datetime
import sys
from typing import Tuple


def get_last_wednesday(year: int, month: int) -> datetime.date:
    """Return the last Wednesday of the given year and month."""
    cal = calendar.monthcalendar(year, month)
    last_wed_day = max(week[calendar.WEDNESDAY] for week in cal if week[calendar.WEDNESDAY] != 0)
    return datetime.date(year, month, last_wed_day)


def get_report_date(year: int, month: int) -> datetime.date:
    """
    Return the Friday of the week containing the last Wednesday of the month.
    Since Wednesday is day 2 of the week, Friday is Wednesday + 2 days (may cross month boundary).
    """
    wed = get_last_wednesday(year, month)
    return wed + datetime.timedelta(days=2)


def get_previous_month(year: int, month: int) -> Tuple[int, int]:
    """Return (prev_year, prev_month)."""
    if month == 1:
        return year - 1, 12
    return year, month - 1


def get_report_metadata(
    year: int,
    month: int,
    reporter: str = "alston.huang",
    override_date: str | None = None,
) -> dict:
    """Compute current report date (supports explicit override_date YYYY-MM-DD), previous report date and page titles."""
    curr_date = (
        datetime.date.fromisoformat(override_date)
        if override_date
        else get_report_date(year, month)
    )
    prev_y, prev_m = get_previous_month(year, month)
    prev_date = get_report_date(prev_y, prev_m)
    
    # Capitalize reporter name for title if applicable
    # e.g. alston.huang -> Alston
    reporter_display = "Alston"
    if "." in reporter:
        reporter_display = reporter.split(".")[0].capitalize()
    elif reporter:
        reporter_display = reporter.capitalize()
        
    curr_title = f"{curr_date.strftime('%Y-%m-%d')} - Weekly Report of {reporter_display}"
    prev_title = f"{prev_date.strftime('%Y-%m-%d')} - Weekly Report of {reporter_display}"
    
    return {
        "target_year": year,
        "target_month": month,
        "reporter": reporter,
        "reporter_display": reporter_display,
        "report_date": curr_date.strftime("%Y-%m-%d"),
        "report_date_table": curr_date.strftime("%d %b %Y"),
        "page_title": curr_title,
        "previous_year": prev_y,
        "previous_month": prev_m,
        "previous_report_date": prev_date.strftime("%Y-%m-%d"),
        "previous_page_title": prev_title,
    }


if __name__ == "__main__":
    now = datetime.datetime.now()
    y = int(sys.argv[1]) if len(sys.argv) > 1 else now.year
    m = int(sys.argv[2]) if len(sys.argv) > 2 else now.month
    meta = get_report_metadata(y, m)
    import json
    print(json.dumps(meta, indent=2, ensure_ascii=False))
