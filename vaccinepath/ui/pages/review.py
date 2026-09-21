"""页 5：人工审核队列（医护视角）。批准 / 退回 / 修改，并可核实海外记录。"""

from __future__ import annotations

import streamlit as st

from vaccinepath.models import Actor, TaskStatus, TaskType
from vaccinepath.ui.common import store, today


def render():
    st.header("人工审核队列")
    st.caption("模拟医护控制台。规则引擎把「需医生确认」的事项汇总到这里；这里的决定会写进日志的 human_decision。")
    s = store()
    kids = {c.id: c for c in s.children()}
    queue = [t for t in s.tasks(status=TaskStatus.awaiting_review) if t.type == TaskType.professional_review]
    st.metric("待审核", len(queue))

    for t in queue:
        c = kids.get(t.child_id)
        with st.container(border=True):
            st.markdown(f"### 🩺 {c.name if c else t.child_id}  ·  {t.title}")
            st.caption(f"创建 {t.created_at:%Y-%m-%d %H:%M}")
            reasons = (t.notes or "").split("\n")
            for r in reasons:
                st.markdown(f"- {r}")

            unverified = [r for r in s.records(t.child_id) if not r.verified and r.source.value in ("overseas", "parent_reported")]
            verify_ids = []
            if unverified:
                st.markdown("**待核实记录**")
                verify_ids = st.multiselect("勾选已核实的记录", [r.id for r in unverified], format_func=lambda rid: next(f"{r.date} {r.product or ', '.join(r.vaccines)}（{r.country or r.source.value}）" for r in unverified if r.id == rid), key=f"verify_{t.id}")

            note = st.text_area("审核意见（会记入日志）", key=f"note_{t.id}", placeholder="例：海外记录已核对接种卡，抗原与 NCIS 对应；DTaP/IPV/Hib 补种安排在 2026-10-05")
            a, b, cc = st.columns(3)
            related = [x for x in s.tasks(t.child_id) if x.type == TaskType.vaccination_due and x.status == TaskStatus.awaiting_review]
            if a.button("✅ 批准", key=f"ok_{t.id}"):
                _decide(s, t, "approved", note, verify_ids, related, TaskStatus.open)
            if b.button("✏️ 修改后批准", key=f"edit_{t.id}"):
                if not note:
                    st.error("修改后批准必须填写审核意见")
                else:
                    _decide(s, t, "approved_with_changes", note, verify_ids, related, TaskStatus.open)
            if cc.button("⛔ 退回 / 暂缓", key=f"no_{t.id}"):
                _decide(s, t, "rejected", note, verify_ids, related, TaskStatus.awaiting_review)

    st.subheader("已处理")
    done = [t for t in s.tasks(status=TaskStatus.done) if t.type == TaskType.professional_review]
    if done:
        st.dataframe([{"孩子": kids[t.child_id].name if t.child_id in kids else t.child_id, "标题": t.title, "处理时间": t.updated_at, "意见": (t.notes or "").split("\n")[-1]} for t in done], hide_index=True, width="stretch")


def _decide(s, t, decision, note, verify_ids, related, related_status):
    for rid in verify_ids:
        s.update_doc("records", rid, verified=True)
        s.log(Actor.clinician, "verify_record", rid, "记录已人工核实", child_id=t.child_id, human_decision=decision)
    for x in related:
        s.update_task(x.id, status=related_status, notes=((x.notes or "") + f"\n审核 {decision}：{note}").strip())
    new_status = TaskStatus.done if decision != "rejected" else TaskStatus.awaiting_review
    s.update_task(t.id, status=new_status, notes=((t.notes or "") + f"\n[{today()}] 审核 {decision}：{note or '（无意见）'}").strip())
    s.log(Actor.clinician, "review_decision", t.id, note or "", child_id=t.child_id, human_decision=decision)
    st.success(f"已记录：{decision}")
    st.rerun()
