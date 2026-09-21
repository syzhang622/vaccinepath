"""页 5：人工审核队列（医护视角）。理由按严重程度排序、同类合并；批准 / 修改 / 退回，并可核实海外记录。"""

from __future__ import annotations

import re
from collections import Counter

import streamlit as st

from vaccinepath.models import Actor, TaskStatus, TaskType
from vaccinepath.ui.common import flash, store, today

_SCREEN_RE = re.compile(r"^接种前筛查有标记项：(.*?)(?: \[.*\])?$")


def _classify(reason: str) -> tuple[int, str]:
    """(排序权重, 显示样式)。0 = URGENT 红，1 = 需尽快处理（WARN / 筛查 / 数据错误），2 = 常规。"""
    if "URGENT" in reason:
        return 0, "error"
    if "WARN" in reason or reason.startswith("接种前筛查") or "error" in reason.lower() or "未响应" in reason:
        return 1, "warning"
    return 2, "plain"


def _render_reasons(reasons: list[str]) -> int:
    """按严重程度排序、合并重复的筛查条目；返回条目数。"""
    reasons = [r for r in reasons if r.strip()]
    screen = [r for r in reasons if _SCREEN_RE.match(r)]
    others = [r for r in reasons if not _SCREEN_RE.match(r)]
    merged = list(dict.fromkeys(others))
    if screen:
        c = Counter(_SCREEN_RE.match(r).group(1) for r in screen)
        merged += [f"接种前筛查有标记项：{k}" + (f"（提交 {n} 次）" if n > 1 else "") for k, n in c.items()]
    merged.sort(key=lambda r: _classify(r)[0])
    for r in merged:
        w, style = _classify(r)
        if style == "error":
            st.error(f"🚨 {r}")
        elif style == "warning":
            st.warning(r)
        else:
            st.markdown(f"- {r}")
    return len(merged)


def render():
    st.header("人工审核队列")
    st.caption("模拟医护控制台。规则引擎把「需医生确认」的事项按孩子汇总到这里；这里的决定会写进日志的 human_decision。")
    s = store()
    kids = {c.id: c for c in s.children()}
    queue = [t for t in s.tasks(status=TaskStatus.awaiting_review) if t.type == TaskType.professional_review]
    queue.sort(key=lambda t: min((_classify(r)[0] for r in (t.notes or "").split("\n")), default=9))
    st.metric("待审核", len(queue))

    for t in queue:
        c = kids.get(t.child_id)
        reasons = (t.notes or "").split("\n")
        urgent = any(_classify(r)[0] == 0 for r in reasons)
        with st.container(border=True):
            st.markdown(f"### {'🚨' if urgent else '🩺'} {c.name if c else t.child_id}  ·  {len([r for r in reasons if r.strip()])} 项待确认" + ("  ·  :red[有 URGENT 打卡]" if urgent else ""))
            st.caption(f"创建 {t.created_at:%Y-%m-%d %H:%M}")
            _render_reasons(reasons)

            unverified = [r for r in s.records(t.child_id) if not r.verified and r.source.value in ("overseas", "parent_reported")]
            verify_ids = []
            if unverified:
                st.markdown(f"**待核实记录（{len(unverified)} 条）**")
                verify_ids = st.multiselect("勾选已核实的记录", [r.id for r in unverified], format_func=lambda rid: next(f"{r.date} {r.product or ', '.join(r.vaccines)}（{r.country or r.source.value}）" for r in unverified if r.id == rid), key=f"verify_{t.id}")

            note = st.text_area("审核意见（会记入日志）", key=f"note_{t.id}", placeholder="例：海外记录已核对接种卡，抗原与 NCIS 对应；DTaP/IPV/Hib 补种安排在 2026-10-05")
            a, b, cc = st.columns(3)
            related = [x for x in s.tasks(t.child_id) if x.type == TaskType.vaccination_due and x.status == TaskStatus.awaiting_review]
            if a.button("✅ 批准", key=f"ok_{t.id}"):
                _decide(s, t, c, "approved", note, verify_ids, unverified, related, TaskStatus.open)
            if b.button("✏️ 修改后批准", key=f"edit_{t.id}"):
                if not note:
                    st.error("修改后批准必须填写审核意见")
                else:
                    _decide(s, t, c, "approved_with_changes", note, verify_ids, unverified, related, TaskStatus.open)
            if cc.button("⛔ 退回 / 暂缓", key=f"no_{t.id}"):
                _decide(s, t, c, "rejected", note, verify_ids, unverified, related, TaskStatus.awaiting_review)

    st.subheader("已处理")
    done = [t for t in s.tasks(status=TaskStatus.done) if t.type == TaskType.professional_review]
    if done:
        st.dataframe([{"孩子": kids[t.child_id].name if t.child_id in kids else t.child_id, "处理时间": t.updated_at.strftime("%Y-%m-%d %H:%M"), "意见": (t.notes or "").split("\n")[-1]} for t in done], hide_index=True, width="stretch")


def _decide(s, t, c, decision, note, verify_ids, unverified, related, related_status):
    for rid in verify_ids:
        s.update_doc("records", rid, verified=True)
        s.log(Actor.clinician, "verify_record", rid, "记录已人工核实", child_id=t.child_id, human_decision=decision)
    for x in related:
        s.update_task(x.id, status=related_status, notes=((x.notes or "") + f"\n[{today()}] 审核 {decision}：{note}").strip())
    new_status = TaskStatus.done if decision != "rejected" else TaskStatus.awaiting_review
    s.update_task(t.id, status=new_status, notes=((t.notes or "") + f"\n[{today()}] 审核 {decision}：{note or '（无意见）'}").strip())
    s.log(Actor.clinician, "review_decision", t.id, note or "", child_id=t.child_id, human_decision=decision)
    name = c.name if c else t.child_id
    left = len(unverified) - len(verify_ids)
    word = {"approved": "已批准", "approved_with_changes": "已修改后批准", "rejected": "已退回 / 暂缓"}[decision]
    msg = f"✅ {name} 的审核单{word}" + (f"，核实了 {len(verify_ids)} 条记录" if verify_ids else "")
    if left > 0:
        msg += f"；**仍有 {left} 条记录未核实**，agent 下次唤醒会继续提示"
    flash("success" if decision != "rejected" else "warning", msg + "。")
    st.rerun()
