"""日期约定（2026-09-20 与组长确认）：月龄按日历月；逾期 = 到期 + 30 天，不分年龄。"""

from __future__ import annotations

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

OVERDUE_GRACE_DAYS = 30


def add_months(d: date, months: int) -> date:
    return d + relativedelta(months=months)


def age_in_months(dob: date, on: date) -> int:
    rd = relativedelta(on, dob)
    return rd.years * 12 + rd.months


def overdue_after(due: date) -> date:
    return due + timedelta(days=OVERDUE_GRACE_DAYS)
