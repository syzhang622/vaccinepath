"""页 3：待办与提醒（家长视角）+ 接种前安全筛查。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import streamlit as st

from vaccinepath import tools
from vaccinepath.models import Actor, ScreeningAnswers, TaskStatus, TaskType, TriState, VaccinationRecord
from vaccinepath.store import new_id
from vaccinepath.ui.common import TASK_STATUS_LABEL, disclaimer, store, today

TRI = {"no": "否", "yes": "是", "unsure": "不确定"}


def _screening_form(task, child):
    st.markdown("**接种前安全筛查**（提交后由规则引擎判定；任何非“否”的回答都转医生审核，系统不判断是否适合接种）")
    with st.form(f"screen_{task.id}"):
        q = {}
        for field, label in [
            ("previous_serious_reaction", "既往接种后出现过严重反应？"),
            ("known_allergy", "已知过敏（含疫苗成分）？"),
            ("current_illness", "当前正在生病？"),
            ("current_fever", "当前发热？"),
            ("immune_condition", "有免疫相关疾病？"),
            ("immunosuppressive_medication", "正在使用免疫抑制药物？"),
        ]:
            q[field] = st.radio(label, list(TRI), format_func=TRI.get, horizontal=True, key=f"{task.id}_{field}")
        details = st.text_input("补充说明（可选）", key=f"{task.id}_details")
        if st.form_submit_button("提交筛查"):
            s = store()
            answers = ScreeningAnswers(**{k: TriState(v) for k, v in q.items()}, previous_reaction_details=details or None)
            sid = new_id("scr")
            s.put_doc("screenings", {"id": sid, "child_id": child.id, "task_id": task.id, "planned_vaccines": [task.vaccine.value] if task.vaccine else [], "answers": answers.model_dump(mode="json"), "answered_at": datetime.now(timezone.utc).isoformat()})
            r = json.loads(tools.vp_evaluate_screening.invoke({"screening_id": sid}))
            outcome = r["result"]["outcome"]
            if outcome == "CLEAR":
                s.update_task(task.id, notes=((task.notes + "\n") if task.notes else "") + f"筛查 {sid}：CLEAR")
                st.success("筛查无标记项。可以预约接种；接种当天医生仍会再次评估。")
            else:
                flags = "；".join(f["reason"] for f in r["result"]["flags"])
                tools.vp_request_review.invoke({"child_id": child.id, "reasons": [f"接种前筛查 {sid} 有标记项：{flags} [{r['result']['source_ref']}]"], "related_task_ids": [task.id]})
                st.warning("筛查有标记项，已转医生审核；请等待审核结果再预约。")
            st.caption(r["result"]["disclaimer"])
            st.rerun()


def _done_form(task, child):
    with st.form(f"done_{task.id}"):
        st.markdown("**标记已接种**（会同时写入接种记录）")
        a, b = st.columns(2)
        d = a.date_input("接种日期", value=today(), min_value=child.date_of_birth, max_value=today())
        product = b.text_input("产品名（可选）")
        if st.form_submit_button("确认"):
            s = store()
            if task.vaccine:
                r = VaccinationRecord(id=new_id("rec"), child_id=child.id, date=d, vaccines=[task.vaccine], product=product or None, source="parent_reported", notes=f"来自任务 {task.id}")
                s.put("records", r)
            s.update_task(task.id, status=TaskStatus.done, notes=((task.notes + "\n") if task.notes else "") + f"家长 {today()} 标记已接种")
            s.log(Actor.parent, "task_done", task.id, f"家长标记已接种 {d}", child_id=child.id)
            st.success("已记录。接种后请到「接种后打卡」页填写观察情况。")
            st.rerun()


def render():
    st.header("待办与提醒")
    s = store()
    kids = {c.id: c for c in s.children()}
    tab_tasks, tab_inbox = st.tabs(["待办", "提醒收件箱（mock 推送）"])

    with tab_tasks:
        show_done = st.checkbox("显示已完成/已取消", value=False)
        tasks = [t for t in s.tasks() if show_done or t.status not in (TaskStatus.done, TaskStatus.cancelled)]
        if not tasks:
            st.info("没有待办。点侧栏「快进到下一次检查」让 agent 跑一轮。")
        for t in tasks:
            c = kids.get(t.child_id)
            icon = {"vaccination_due": "💉", "professional_review": "🩺", "post_vaccination_checkin": "📋", "reminder": "🔔", "clarification": "❓"}[t.type.value]
            with st.container(border=True):
                head = st.columns([3, 1, 1, 1])
                head[0].markdown(f"{icon} **{t.title}**  ·  {c.name if c else t.child_id}")
                head[1].markdown(f"到期 {t.due_date}" if t.due_date else "")
                head[2].markdown(TASK_STATUS_LABEL[t.status.value])
                head[3].markdown(f"提醒 {t.reminder_count} 次" if t.reminder_count else "")
                if t.notes:
                    st.caption(t.notes.replace("\n", "  \n"))
                if t.type == TaskType.vaccination_due and t.status in (TaskStatus.open, TaskStatus.awaiting_parent, TaskStatus.awaiting_review) and c:
                    x, y = st.columns(2)
                    with x, st.expander("接种前安全筛查"):
                        _screening_form(t, c)
                    with y, st.expander("标记已接种"):
                        _done_form(t, c)

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
