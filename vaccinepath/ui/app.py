"""VaccinePath Family SG — Streamlit 前端入口。启动：scripts/ui.sh 或 uv run streamlit run vaccinepath/ui/app.py"""

from __future__ import annotations

import streamlit as st

from vaccinepath.store import SEED_PATH, Store
from vaccinepath.ui import gateway
from vaccinepath.ui.pages import checkin, logs, profiles, review, tasks, timeline

st.set_page_config(page_title="VaccinePath Family SG", page_icon="💉", layout="wide")


def sidebar():
    st.sidebar.title("💉 VaccinePath")
    st.sidebar.caption("长期运行 · 有状态 · 自触发的疫苗计划 agent（课程原型，全部 mock 数据）")
    up = gateway.gateway_up()
    cfg = gateway.agent_config()
    st.sidebar.markdown(("🟢 gateway 在线" if up else "🔴 gateway 离线") + ("  ·  agent 已建" if cfg else "  ·  agent 未建"))
    state = Store().agent_state()
    if state:
        st.sidebar.markdown(f"已唤醒 **{state.get('wake_ups', 0)}** 次 · 上次 {str(state.get('last_wake_up', ''))[:16].replace('T', ' ')}")

    if st.sidebar.button("⏩ 快进到下一次检查", type="primary", disabled=not (up and cfg), width="stretch", help="= POST /api/scheduled-tasks/{id}/trigger，不等 cron"):
        with st.sidebar.status("agent 醒来了，正在检查…", expanded=True) as box:
            try:
                r = gateway.trigger_wake_up()
                box.update(label=f"完成：{r['status']}，{r['seconds']}s，{len(r['calls'])} 次工具调用", state="complete" if r["status"] == "success" else "error")
                st.session_state["last_wake"] = r
            except Exception as e:  # noqa: BLE001
                box.update(label=f"失败：{e}", state="error")
        st.rerun()
    if "last_wake" in st.session_state:
        r = st.session_state["last_wake"]
        with st.sidebar.expander(f"上次唤醒摘要（{r['seconds']}s / {len(r['calls'])} 次调用）", expanded=True):
            st.markdown(r["reply"] or "（无回复）")

    with st.sidebar.expander("演示工具"):
        if st.button("重置为 mock 家庭数据", width="stretch"):
            Store().reset_from_seed(SEED_PATH)
            st.session_state.pop("last_wake", None)
            st.rerun()
        st.caption("重置后需要重新建 agent：`scripts/agent_setup.sh`（线程里的记忆不会自动清）")


def main():
    sidebar()
    pages = [
        st.Page(profiles.render, title="档案", icon="👪", url_path="profiles", default=True),
        st.Page(timeline.render, title="接种时间线", icon="📅", url_path="timeline"),
        st.Page(tasks.render, title="待办与提醒", icon="✅", url_path="tasks"),
        st.Page(checkin.render, title="接种后打卡", icon="🌡️", url_path="checkin"),
        st.Page(review.render, title="人工审核", icon="🩺", url_path="review"),
        st.Page(logs.render, title="日志", icon="📜", url_path="logs"),
    ]
    st.navigation(pages).run()


main()
