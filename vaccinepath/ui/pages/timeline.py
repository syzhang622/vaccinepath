"""页 2：接种时间线（规则引擎 compute_schedule 的可视化）。"""

from __future__ import annotations

import streamlit as st

from vaccinepath.models import ScheduleInput, ScheduleStatus
from vaccinepath.rules import compute_schedule
from vaccinepath.ui.common import STATUS_LABEL, child_selector, disclaimer, store, today


def render():
    st.header("接种时间线")
    c = child_selector("timeline_child")
    if c is None:
        return
    s = store()
    res = compute_schedule(ScheduleInput(child=c, records=s.records(c.id), as_of=today()))

    cols = st.columns(5)
    for col, key in zip(cols, ["completed", "due", "overdue", "needs_clinician", "upcoming"]):
        col.metric(STATUS_LABEL[ScheduleStatus(key)], res.counts.get(key, 0))
    if res.requires_clinician_review:
        st.warning("有需要医生确认的项目。已逾期剂次的补种时间、以及 NCIS 未给出规则的情形，本系统不自行安排，统一进入人工审核。")

    order = {ScheduleStatus.overdue: 0, ScheduleStatus.due: 1, ScheduleStatus.needs_clinician: 2, ScheduleStatus.upcoming: 3, ScheduleStatus.completed: 4, ScheduleStatus.not_applicable: 5}
    rows = sorted(res.items, key=lambda i: (order[i.status], i.due_date or i.given_date or today()))
    st.dataframe(
        [
            {
                "状态": STATUS_LABEL[i.status],
                "疫苗": i.vaccine.value,
                "剂次": i.label,
                "到期": i.due_date,
                "逾期线": i.overdue_date,
                "已接种": i.given_date,
                "剂型提示": i.product_hint or "",
                "需医生确认": "✔" if (i.clinician_confirmation_required or i.status == ScheduleStatus.needs_clinician) else "",
                "依据": i.reason,
                "来源": i.source_ref,
            }
            for i in rows
        ],
        hide_index=True,
        width="stretch",
        height=min(60 + 36 * len(rows), 800),
    )
    st.caption(f"as_of {res.as_of} · 月龄 {res.age_months} · 依据 MOH NCIS 2026-04-01；逾期 = 到期 + 30 天")
    disclaimer()
