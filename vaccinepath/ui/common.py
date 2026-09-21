"""各页面共用：store、常量、小组件。"""

from __future__ import annotations

from datetime import date

import streamlit as st

from vaccinepath.models import ScheduleStatus, VaccineCode
from vaccinepath.rules.dates import age_in_months
from vaccinepath.store import Store

DISCLAIMER = "本信息不构成诊断，不替代医生建议；如有疑问请咨询医生。"
STATUS_LABEL = {
    ScheduleStatus.completed: "✅ 已完成",
    ScheduleStatus.upcoming: "🗓 未到期",
    ScheduleStatus.due: "🟡 应接种",
    ScheduleStatus.overdue: "🔴 已逾期",
    ScheduleStatus.needs_clinician: "🩺 需医生确认",
    ScheduleStatus.not_applicable: "— 不适用",
}
TASK_STATUS_LABEL = {"open": "待处理", "awaiting_parent": "等家长回应", "awaiting_review": "等人工审核", "done": "已完成", "cancelled": "已取消"}
SEVERITY_LABEL = {"error": "❌ 错误", "warning": "⚠️ 提示", "review": "🩺 需人工确认"}


def store() -> Store:
    return Store()


def today() -> date:
    return date.today()


def age_text(dob: date) -> str:
    m = age_in_months(dob, today())
    return f"{m // 12} 岁 {m % 12} 个月" if m >= 24 else f"{m} 个月"


def child_selector(key: str = "child"):
    s = store()
    kids = s.children()
    if not kids:
        st.info("还没有孩子档案，先去「档案」页添加。")
        return None
    labels = {c.id: f"{c.name}（{age_text(c.date_of_birth)}）" for c in kids}
    cid = st.selectbox("孩子", list(labels), format_func=labels.get, key=key)
    return s.child(cid)


def vaccine_options() -> list[str]:
    return [v.value for v in VaccineCode]


def disclaimer():
    st.caption(DISCLAIMER)
