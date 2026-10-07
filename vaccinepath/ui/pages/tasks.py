"""页 3：待办与提醒（家长视角）+ 接种前安全筛查。"""

from __future__ import annotations

import json
from datetime import datetime

import streamlit as st

from vaccinepath import tools
from vaccinepath.labels import OUTCOME_LABEL, SCREEN_FIELD_LABEL, TRI_LABEL
from vaccinepath.models import Actor, ScreeningAnswers, TaskStatus, TaskType, TriState, VaccinationRecord
from vaccinepath.store import new_id, now
from vaccinepath.ui.common import TASK_STATUS_LABEL, age_text, disclaimer, flash, store, today

ICON = {"vaccination_due": "💉", "professional_review": "🩺", "post_vaccination_checkin": "📋", "reminder": "🔔", "clarification": "❓"}


def _screening_for(task_id: str) -> dict | None:
    """该任务最新一次筛查（用于：已筛查过就不再显示表单，并展示结果）。"""
    scrs = [x for x in store().read()["screenings"].values() if x.get("task_id") == task_id and x.get("result")]
    return max(scrs, key=lambda x: x["answered_at"]) if scrs else None


def _screening_block(task, child):
    done = _screening_for(task.id)
    if done:
        r = done["result"]
        label = OUTCOME_LABEL[r["outcome"]]
        if r["outcome"] == "CLEAR":
            st.success(f"Screened on {done['answered_at'][:16].replace('T', ' ')}: {label}. An appointment may be arranged; a clinician will reassess on the vaccination day.")
        else:
            st.warning(f"Screened on {done['answered_at'][:16].replace('T', ' ')}: {label}. Routed for professional review. Flags: " + "; ".join(f"{SCREEN_FIELD_LABEL[f['field']]} = {TRI_LABEL[TriState(f['answer'])]}" for f in r["flags"]))
        return
    st.markdown("**Pre-vaccination safety screening** (the rule engine evaluates the form; any answer other than 'No' is routed for professional review. The system does not decide fitness for vaccination.)")
    with st.form(f"screen_{task.id}"):
        q = {}
        for field, label in SCREEN_FIELD_LABEL.items():
            q[field] = st.radio(label + "?", list(TRI_LABEL), format_func=TRI_LABEL.get, horizontal=True, key=f"{task.id}_{field}")
        details = st.text_input("Additional details (optional)", key=f"{task.id}_details")
        submitted = st.form_submit_button("Submit screening")
    if submitted:
        # 幂等保护：同一任务已有筛查结果就不再写第二份（防止页面重跑重复提交）
        if _screening_for(task.id):
            st.rerun()
        s = store()
        answers = ScreeningAnswers(**{k: TriState(v) for k, v in q.items()}, previous_reaction_details=details or None)
        sid = new_id("scr")
        s.put_doc("screenings", {"id": sid, "child_id": child.id, "task_id": task.id, "planned_vaccines": [task.vaccine.value] if task.vaccine else [], "answers": answers.model_dump(mode="json"), "answered_at": now().isoformat()})
        s.log(Actor.parent, "screening_submitted", sid, f"Caregiver submitted pre-vaccination screening for task {task.id}", child_id=child.id)
        r = json.loads(tools.vp_evaluate_screening.invoke({"screening_id": sid}))
        if r["result"]["outcome"] == "CLEAR":
            s.update_task(task.id, notes=((task.notes + "\n") if task.notes else "") + f"[{today()}] Pre-vaccination screening: no flags")
            flash("success", f"✅ {child.name}'s screening has no flags. An appointment may be arranged; a clinician will reassess on the vaccination day.")
        else:
            tools.vp_request_review.invoke({"child_id": child.id, "reasons": [r["review_reason"]], "related_task_ids": [task.id]})
            flash("warning", f"⚠️ {child.name}'s screening has one or more flags and has been routed for professional review. Wait for the review before arranging vaccination.")
        st.rerun()


def _done_block(task, child):
    with st.form(f"done_{task.id}"):
        st.markdown("**Mark as vaccinated** (also creates a vaccination record)")
        a, b = st.columns(2)
        d = a.date_input("Vaccination date", value=today(), min_value=child.date_of_birth, max_value=today())
        product = b.text_input("Product name (optional)")
        submitted = st.form_submit_button("Confirm")
    if submitted:
        s = store()
        if task.vaccine:
            r = VaccinationRecord(id=new_id("rec"), child_id=child.id, date=d, vaccines=[task.vaccine], product=product or None, source="parent_reported", notes=f"Created from task {task.id}")
            s.put("records", r)
        s.update_task(task.id, status=TaskStatus.done, notes=((task.notes + "\n") if task.notes else "") + f"[{today()}] Caregiver marked vaccination as completed ({d})")
        s.log(Actor.parent, "task_done", task.id, f"Caregiver marked vaccination as completed on {d}", child_id=child.id)
        flash("success", f"✅ Recorded {child.name}'s {task.vaccine.value if task.vaccine else ''} vaccination on {d}. Use Post-vaccination Check-in to report observations.")
        st.rerun()


def render():
    st.header("Tasks & Reminders")
    s = store()
    kids = {c.id: c for c in s.children()}
    tab_tasks, tab_inbox = st.tabs(["Tasks", "Reminder inbox (mock notifications)"])

    with tab_tasks:
        f1, f2 = st.columns([2, 1])
        pick = f1.selectbox("Child", ["all"] + list(kids), format_func=lambda x: "All children" if x == "all" else f"{kids[x].name} ({age_text(kids[x].date_of_birth)})", key="tasks_child")
        show_done = f2.checkbox("Show completed/cancelled", value=False)
        tasks = [t for t in s.tasks() if show_done or t.status not in (TaskStatus.done, TaskStatus.cancelled)]
        if pick != "all":
            tasks = [t for t in tasks if t.child_id == pick]
        if not tasks:
            st.info("No tasks. Use 'Run next check now' in the sidebar to trigger an agent wake-up.")
        # 按孩子分组，组内按到期日
        for cid in ([pick] if pick != "all" else list(kids)):
            group = [t for t in tasks if t.child_id == cid]
            if not group:
                continue
            c = kids[cid]
            st.subheader(f"{c.name} ({age_text(c.date_of_birth)}) · {len(group)} items")
            for t in group:
                with st.container(border=True):
                    head = st.columns([3, 1, 1, 1])
                    head[0].markdown(f"{ICON[t.type.value]} **{t.title}**")
                    head[1].markdown(f"Due {t.due_date}" if t.due_date else "")
                    head[2].markdown(TASK_STATUS_LABEL[t.status.value])
                    head[3].markdown(f"Reminded {t.reminder_count} times" if t.reminder_count else "")
                    if t.notes and t.type != TaskType.professional_review:
                        st.caption(t.notes.replace("\n", "  \n"))
                    if t.type == TaskType.professional_review:
                        st.caption("See Clinical Review for details.")
                    if t.type == TaskType.vaccination_due and t.status != TaskStatus.done:
                        x, y = st.columns(2)
                        with x, st.expander("Pre-vaccination safety screening", expanded=bool(_screening_for(t.id))):
                            _screening_block(t, c)
                        with y, st.expander("Mark as vaccinated"):
                            _done_block(t, c)

    with tab_inbox:
        ns = list(reversed(s.notifications()))
        if not ns:
            st.info("No reminders yet.")
        for n in ns:
            c = kids.get(n["child_id"])
            with st.container(border=True):
                st.markdown(f"**{c.name if c else n['child_id']}**  ·  {n['timestamp'][:16].replace('T', ' ')}  ·  {n['channel']}")
                st.markdown(n["message"].replace("\n", "  \n"))
    disclaimer()
