"""各页面共用：store、常量、flash 提示、小组件。"""

from __future__ import annotations

from datetime import date

import streamlit as st

from vaccinepath.models import ScheduleStatus, VaccineCode
from vaccinepath.rules.dates import age_in_months
from vaccinepath.store import Store, today

DISCLAIMER = "This information is not a diagnosis and does not replace medical advice. Please consult a healthcare professional if you have concerns."
STATUS_LABEL = {
    ScheduleStatus.completed: "✅ Completed",
    ScheduleStatus.upcoming: "🗓 Upcoming",
    ScheduleStatus.due: "🟡 Due",
    ScheduleStatus.overdue: "🔴 Overdue",
    ScheduleStatus.needs_clinician: "🩺 Clinician confirmation",
    ScheduleStatus.not_applicable: "— Not applicable",
}
TASK_STATUS_LABEL = {"open": "Open", "awaiting_parent": "Awaiting caregiver", "awaiting_review": "Awaiting review", "done": "Completed", "cancelled": "Cancelled"}
SEVERITY_LABEL = {"error": "❌ Error", "warning": "⚠️ Warning", "review": "🩺 Review required"}

__all__ = ["today"]


def store() -> Store:
    return Store()


def age_text(dob: date) -> str:
    m = age_in_months(dob, today())
    return f"{m // 12}y {m % 12}m" if m >= 24 else f"{m} months"


def child_selector(key: str = "child"):
    s = store()
    kids = s.children()
    if not kids:
        st.info("No child profiles yet. Add one on the Profiles page.")
        return None
    labels = {c.id: f"{c.name} ({age_text(c.date_of_birth)})" for c in kids}
    cid = st.selectbox("Child", list(labels), format_func=labels.get, key=key)
    return s.child(cid)


def vaccine_options() -> list[str]:
    return [v.value for v in VaccineCode]


def disclaimer():
    st.caption(DISCLAIMER)


# ---- flash：跨 rerun 保留一条成功/警告提示（st.rerun 会清掉当次的 st.success） ----


def flash(kind: str, text: str) -> None:
    st.session_state["_flash"] = (kind, text)


def show_flash() -> None:
    f = st.session_state.pop("_flash", None)
    if f:
        getattr(st, f[0])(f[1])
