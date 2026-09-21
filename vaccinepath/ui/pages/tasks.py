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
            st.success(f"已筛查（{done['answered_at'][:16].replace('T', ' ')}）：{label}。可以预约接种；接种当天医生仍会再次评估。")
        else:
            st.warning(f"已筛查（{done['answered_at'][:16].replace('T', ' ')}）：{label}，已转医生审核。标记项：" + "；".join(f"{SCREEN_FIELD_LABEL[f['field']]}＝{TRI_LABEL[TriState(f['answer'])]}" for f in r["flags"]))
        return
    st.markdown("**接种前安全筛查**（提交后由规则引擎判定；任何非“否”的回答都转医生审核，系统不判断是否适合接种）")
    with st.form(f"screen_{task.id}"):
        q = {}
        for field, label in SCREEN_FIELD_LABEL.items():
            q[field] = st.radio(label + "？", list(TRI_LABEL), format_func=TRI_LABEL.get, horizontal=True, key=f"{task.id}_{field}")
        details = st.text_input("补充说明（可选）", key=f"{task.id}_details")
        submitted = st.form_submit_button("提交筛查")
    if submitted:
        # 幂等保护：同一任务已有筛查结果就不再写第二份（防止页面重跑重复提交）
        if _screening_for(task.id):
            st.rerun()
        s = store()
        answers = ScreeningAnswers(**{k: TriState(v) for k, v in q.items()}, previous_reaction_details=details or None)
        sid = new_id("scr")
        s.put_doc("screenings", {"id": sid, "child_id": child.id, "task_id": task.id, "planned_vaccines": [task.vaccine.value] if task.vaccine else [], "answers": answers.model_dump(mode="json"), "answered_at": now().isoformat()})
        s.log(Actor.parent, "screening_submitted", sid, f"家长提交接种前筛查（任务 {task.id}）", child_id=child.id)
        r = json.loads(tools.vp_evaluate_screening.invoke({"screening_id": sid}))
        if r["result"]["outcome"] == "CLEAR":
            s.update_task(task.id, notes=((task.notes + "\n") if task.notes else "") + f"[{today()}] 接种前筛查：无标记项")
            flash("success", f"✅ {child.name} 的接种前筛查已提交：无标记项，可以预约接种（接种当天医生仍会再次评估）。")
        else:
            tools.vp_request_review.invoke({"child_id": child.id, "reasons": [r["review_reason"]], "related_task_ids": [task.id]})
            flash("warning", f"⚠️ {child.name} 的接种前筛查已提交：有标记项，已转医生审核，请等待审核结果再预约。")
        st.rerun()


def _done_block(task, child):
    with st.form(f"done_{task.id}"):
        st.markdown("**标记已接种**（会同时写入接种记录）")
        a, b = st.columns(2)
        d = a.date_input("接种日期", value=today(), min_value=child.date_of_birth, max_value=today())
        product = b.text_input("产品名（可选）")
        submitted = st.form_submit_button("确认")
    if submitted:
        s = store()
        if task.vaccine:
            r = VaccinationRecord(id=new_id("rec"), child_id=child.id, date=d, vaccines=[task.vaccine], product=product or None, source="parent_reported", notes=f"来自任务 {task.id}")
            s.put("records", r)
        s.update_task(task.id, status=TaskStatus.done, notes=((task.notes + "\n") if task.notes else "") + f"[{today()}] 家长标记已接种（{d}）")
        s.log(Actor.parent, "task_done", task.id, f"家长标记已接种 {d}", child_id=child.id)
        flash("success", f"✅ 已记录 {child.name} 于 {d} 接种 {task.vaccine.value if task.vaccine else ''}。接种后请到「接种后打卡」页填写观察情况。")
        st.rerun()


def render():
    st.header("待办与提醒")
    s = store()
    kids = {c.id: c for c in s.children()}
    tab_tasks, tab_inbox = st.tabs(["待办", "提醒收件箱（mock 推送）"])

    with tab_tasks:
        f1, f2 = st.columns([2, 1])
        pick = f1.selectbox("孩子", ["全部"] + list(kids), format_func=lambda x: "全部孩子" if x == "全部" else f"{kids[x].name}（{age_text(kids[x].date_of_birth)}）", key="tasks_child")
        show_done = f2.checkbox("显示已完成/已取消", value=False)
        tasks = [t for t in s.tasks() if show_done or t.status not in (TaskStatus.done, TaskStatus.cancelled)]
        if pick != "全部":
            tasks = [t for t in tasks if t.child_id == pick]
        if not tasks:
            st.info("没有待办。点侧栏「快进到下一次检查」让 agent 跑一轮。")
        # 按孩子分组，组内按到期日
        for cid in ([pick] if pick != "全部" else list(kids)):
            group = [t for t in tasks if t.child_id == cid]
            if not group:
                continue
            c = kids[cid]
            st.subheader(f"{c.name}（{age_text(c.date_of_birth)}）· {len(group)} 项")
            for t in group:
                with st.container(border=True):
                    head = st.columns([3, 1, 1, 1])
                    head[0].markdown(f"{ICON[t.type.value]} **{t.title}**")
                    head[1].markdown(f"到期 {t.due_date}" if t.due_date else "")
                    head[2].markdown(TASK_STATUS_LABEL[t.status.value])
                    head[3].markdown(f"已提醒 {t.reminder_count} 次" if t.reminder_count else "")
                    if t.notes and t.type != TaskType.professional_review:
                        st.caption(t.notes.replace("\n", "  \n"))
                    if t.type == TaskType.professional_review:
                        st.caption("详情见「人工审核」页")
                    if t.type == TaskType.vaccination_due and t.status != TaskStatus.done:
                        x, y = st.columns(2)
                        with x, st.expander("接种前安全筛查", expanded=bool(_screening_for(t.id))):
                            _screening_block(t, c)
                        with y, st.expander("标记已接种"):
                            _done_block(t, c)

    with tab_inbox:
        ns = list(reversed(s.notifications()))
        if not ns:
            st.info("还没有提醒。")
        for n in ns:
            c = kids.get(n["child_id"])
            with st.container(border=True):
                st.markdown(f"**{c.name if c else n['child_id']}**  ·  {n['timestamp'][:16].replace('T', ' ')}  ·  {n['channel']}")
                st.markdown(n["message"].replace("\n", "  \n"))
    disclaimer()
