"""页 6：日志。审计日志 + agent 唤醒记录，全程可追溯。"""

from __future__ import annotations

import streamlit as st

from vaccinepath.ui import gateway
from vaccinepath.ui.common import store


def render():
    st.header("Audit & Agent Runs")
    s = store()
    kids = {c.id: c.name for c in s.children()}
    tab_audit, tab_runs = st.tabs(["Audit log", "Agent wake-up runs"])

    with tab_audit:
        a, b = st.columns(2)
        actor = a.multiselect("actor", ["agent", "rule_engine", "parent", "clinician", "system"], default=[])
        st.caption("For retrieve_guidance actions, the Output column records the exact source file used by the agent.")
        child = b.selectbox("Child", ["all"] + list(kids), format_func=lambda x: "All children" if x == "all" else kids.get(x, x))
        entries = s.audit_log(None if child == "all" else child, limit=1000)
        if actor:
            entries = [e for e in entries if e["actor"] in actor]
        st.caption(f"{len(entries)} entries (input / action / source / time / output / human decision)")
        st.dataframe(
            [{"Time": e["timestamp"][:19].replace("T", " "), "Actor": e["actor"], "Action": e["action"], "Child": kids.get(e.get("child_id"), e.get("child_id") or ""), "Input": e["input_summary"], "Output": e["output_summary"], "Source": e.get("source") or "", "Human decision": e.get("human_decision") or ""} for e in reversed(entries)],
            hide_index=True,
            width="stretch",
            height=600,
        )

    with tab_runs:
        st.markdown(f"Agent state: {s.agent_state() or '(No wake-ups yet)'}")
        if not gateway.agent_config():
            st.info("Agent not set up: run `scripts/agent_setup.sh --reset`.")
            return
        if not gateway.gateway_up():
            st.error("Gateway is not running: run `scripts/gateway.sh start`.")
            return
        runs = gateway.list_runs(20)
        st.dataframe([{"Trigger": r["trigger"], "Status": r["status"], "Started": (r.get("started_at") or "")[:19].replace("T", " "), "Finished": (r.get("finished_at") or "")[:19].replace("T", " "), "Run ID": r["run_id"], "Error": r.get("error") or ""} for r in runs], hide_index=True, width="stretch")
        ok = [r for r in runs if r["status"] == "success"]
        if ok:
            pick = st.selectbox("View a wake-up run", [r["run_id"] for r in ok], format_func=lambda x: f"{x[:8]}  {next(r['started_at'][:16] for r in ok if r['run_id'] == x)}")
            calls, reply = gateway.run_reply(pick)
            st.markdown(f"**{len(calls)} tool calls**")
            st.code("\n".join(calls) or "(None)")
            st.markdown("**Agent summary**")
            st.markdown(reply or "(None)")
