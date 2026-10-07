"""VaccinePath Family SG — Streamlit 前端入口。启动：scripts/ui.sh 或 uv run streamlit run vaccinepath/ui/app.py"""

from __future__ import annotations

import streamlit as st

from vaccinepath.agent.setup import setup_agent
from vaccinepath.store import Store
from vaccinepath.ui import gateway
from vaccinepath.ui.common import show_flash
from vaccinepath.ui.pages import checkin, logs, profiles, review, tasks, timeline

st.set_page_config(page_title="VaccinePath Family SG", page_icon="💉", layout="wide")


def sidebar():
    st.sidebar.title("💉 VaccinePath")
    st.sidebar.caption("Long-running · stateful · self-triggering vaccination agent (course prototype; synthetic data only)")
    up = gateway.gateway_up()
    cfg = gateway.agent_config()
    st.sidebar.markdown(("🟢 Gateway online" if up else "🔴 Gateway offline") + ("  ·  Agent ready" if cfg else "  ·  Agent not set up"))
    state = Store().agent_state()
    if state.get("wake_ups"):
        st.sidebar.markdown(f"**{state['wake_ups']}** wake-ups · Last {str(state.get('last_wake_up', ''))[:16].replace('T', ' ')}")

    if st.sidebar.button("⏩ Run next check now", type="primary", disabled=not (up and cfg), width="stretch", help="Manually triggers the same scheduled workflow without waiting for cron"):
        with st.sidebar.status("The agent is checking the family…", expanded=True) as box:
            try:
                r = gateway.trigger_wake_up()
                box.update(label=f"Completed: {r['status']} · {r['seconds']}s · {len(r['calls'])} tool calls", state="complete" if r["status"] == "success" else "error")
                st.session_state["last_wake"] = r
            except Exception as e:  # noqa: BLE001
                box.update(label=f"Failed: {e}", state="error")
        st.rerun()
    if "last_wake" in st.session_state:
        r = st.session_state["last_wake"]
        with st.sidebar.expander(f"Latest wake-up summary ({r['seconds']}s / {len(r['calls'])} calls)", expanded=True):
            st.markdown(r["reply"] or "(No response)")

    with st.sidebar.expander("Demo tools"):
        st.caption("Reset restores the synthetic family and rebuilds the agent with a fresh thread.")
        if st.button("Reset demo data and agent", width="stretch", disabled=not up):
            try:
                setup_agent(reset_data=True)
                st.session_state.pop("last_wake", None)
                st.session_state["_flash"] = ("success", "Reset complete: synthetic data restored and a fresh agent created (0 wake-ups).")
            except Exception as e:  # noqa: BLE001
                st.session_state["_flash"] = ("error", f"Reset failed: {e}")
            st.rerun()


def _page(fn):
    """每页自己渲染侧栏（不放在 st.navigation().run() 之前），避免公共元素在页面重跑时重复渲染。"""

    def run():
        sidebar()
        show_flash()
        fn()

    run.__name__ = fn.__module__.rsplit(".", 1)[-1]
    return run


def main():
    pages = [
        st.Page(_page(profiles.render), title="Profiles", icon="👪", default=True),
        st.Page(_page(timeline.render), title="Vaccination Timeline", icon="📅", url_path="timeline"),
        st.Page(_page(tasks.render), title="Tasks & Reminders", icon="✅", url_path="tasks"),
        st.Page(_page(checkin.render), title="Post-vaccination Check-in", icon="🌡️", url_path="checkin"),
        st.Page(_page(review.render), title="Clinical Review", icon="🩺", url_path="review"),
        st.Page(_page(logs.render), title="Audit & Runs", icon="📜", url_path="logs"),
    ]
    st.navigation(pages).run()


main()
