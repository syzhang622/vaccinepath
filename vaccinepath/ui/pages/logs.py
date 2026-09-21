"""页 6：日志。审计日志 + agent 唤醒记录，全程可追溯。"""

from __future__ import annotations

import streamlit as st

from vaccinepath.ui import gateway
from vaccinepath.ui.common import store


def render():
    st.header("日志")
    s = store()
    kids = {c.id: c.name for c in s.children()}
    tab_audit, tab_runs = st.tabs(["审计日志", "agent 唤醒记录"])

    with tab_audit:
        a, b = st.columns(2)
        actor = a.multiselect("actor", ["agent", "rule_engine", "parent", "clinician", "system"], default=[])
        child = b.selectbox("孩子", ["全部"] + list(kids), format_func=lambda x: kids.get(x, x))
        entries = s.audit_log(None if child == "全部" else child, limit=1000)
        if actor:
            entries = [e for e in entries if e["actor"] in actor]
        st.caption(f"{len(entries)} 条（输入 / 动作 / 来源 / 时间 / 输出 / 人工决定）")
        st.dataframe(
            [{"时间": e["timestamp"][:19].replace("T", " "), "actor": e["actor"], "动作": e["action"], "孩子": kids.get(e.get("child_id"), e.get("child_id") or ""), "输入": e["input_summary"], "输出": e["output_summary"], "来源": e.get("source") or "", "人工决定": e.get("human_decision") or ""} for e in reversed(entries)],
            hide_index=True,
            width="stretch",
            height=600,
        )

    with tab_runs:
        st.markdown(f"agent 状态：{s.agent_state() or '（还没唤醒过）'}")
        if not gateway.agent_config():
            st.info("还没建 agent：`scripts/agent_setup.sh --reset`")
            return
        if not gateway.gateway_up():
            st.error("gateway 未运行：`scripts/gateway.sh start`")
            return
        runs = gateway.list_runs(20)
        st.dataframe([{"触发": r["trigger"], "状态": r["status"], "开始": (r.get("started_at") or "")[:19].replace("T", " "), "结束": (r.get("finished_at") or "")[:19].replace("T", " "), "run_id": r["run_id"], "错误": r.get("error") or ""} for r in runs], hide_index=True, width="stretch")
        ok = [r for r in runs if r["status"] == "success"]
        if ok:
            pick = st.selectbox("查看某次唤醒", [r["run_id"] for r in ok], format_func=lambda x: f"{x[:8]}  {next(r['started_at'][:16] for r in ok if r['run_id'] == x)}")
            calls, reply = gateway.run_reply(pick)
            st.markdown(f"**工具调用 {len(calls)} 次**")
            st.code("\n".join(calls) or "（无）")
            st.markdown("**agent 摘要**")
            st.markdown(reply or "（无）")
