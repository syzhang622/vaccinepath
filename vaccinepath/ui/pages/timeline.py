"""页 2：接种时间线（规则引擎 compute_schedule 的可视化）。"""

from __future__ import annotations

import streamlit as st

from vaccinepath.models import ConflictInput, ScheduleInput, ScheduleStatus
from vaccinepath.rules import compute_schedule, detect_conflicts
from vaccinepath.ui.common import STATUS_LABEL, child_selector, disclaimer, store, today


def render():
    st.header("Vaccination Timeline")
    c = child_selector("timeline_child")
    if c is None:
        return
    s = store()
    records = s.records(c.id)
    conflicts = detect_conflicts(ConflictInput(child=c, records=records, as_of=today()))
    if conflicts.has_blocking_errors:
        st.error("Scheduling is blocked because one or more vaccination records are impossible or duplicated. Correct the records or route them for professional review before using this timeline.")
        st.dataframe(
            [
                {"Severity": i.severity.value.upper(), "Issue": i.code, "Details": i.message, "Source": i.source_ref}
                for i in conflicts.issues
                if i.severity.value == "error"
            ],
            hide_index=True,
            width="stretch",
        )
        disclaimer()
        return
    res = compute_schedule(ScheduleInput(child=c, records=records, as_of=today()))

    cols = st.columns(5)
    for col, key in zip(cols, ["completed", "due", "overdue", "needs_clinician", "upcoming"]):
        col.metric(STATUS_LABEL[ScheduleStatus(key)], res.counts.get(key, 0))
    if res.requires_clinician_review:
        st.warning("Some items require clinician confirmation. The system does not independently schedule overdue catch-up doses or situations not specified by the NCIS; these are routed for professional review.")

    order = {ScheduleStatus.overdue: 0, ScheduleStatus.due: 1, ScheduleStatus.needs_clinician: 2, ScheduleStatus.upcoming: 3, ScheduleStatus.completed: 4, ScheduleStatus.not_applicable: 5}
    rows = sorted(res.items, key=lambda i: (order[i.status], i.due_date or i.given_date or today()))
    st.dataframe(
        [
            {
                "Status": STATUS_LABEL[i.status],
                "Vaccine": i.vaccine.value,
                "Dose": i.label,
                "Due date": i.due_date,
                "Overdue after": i.overdue_date,
                "Given date": i.given_date,
                "Product hint": i.product_hint or "",
                "Clinician confirmation": "✔" if (i.clinician_confirmation_required or i.status == ScheduleStatus.needs_clinician) else "",
                "Reason": i.reason,
                "Source": i.source_ref,
            }
            for i in rows
        ],
        hide_index=True,
        width="stretch",
        height=min(60 + 36 * len(rows), 800),
    )
    st.caption(f"As of {res.as_of} · Age {res.age_months} months · Based on MOH NCIS 2026-04-01 · Overdue threshold = due date + 30 days")
    disclaimer()
