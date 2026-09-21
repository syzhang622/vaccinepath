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
    st.sidebar.caption("长期运行 · 有状态 · 自触发的疫苗计划 agent（课程原型，全部 mock 数据）")
    up = gateway.gateway_up()
    cfg = gateway.agent_config()
    st.sidebar.markdown(("🟢 gateway 在线" if up else "🔴 gateway 离线") + ("  ·  agent 已建" if cfg else "  ·  agent 未建"))
    state = Store().agent_state()
    if state.get("wake_ups"):
        st.sidebar.markdown(f"已唤醒 **{state['wake_ups']}** 次 · 上次 {str(state.get('last_wake_up', ''))[:16].replace('T', ' ')}")

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
        st.caption("重置 = 数据回到 mock 家庭 + 重建 agent（新线程，记忆清零）")
        if st.button("重置演示（数据 + agent）", width="stretch", disabled=not up):
            try:
                setup_agent(reset_data=True)
                st.session_state.pop("last_wake", None)
                st.session_state["_flash"] = ("success", "已重置：数据回到 mock 家庭，agent 已重建（唤醒计数 0）。")
            except Exception as e:  # noqa: BLE001
                st.session_state["_flash"] = ("error", f"重置失败：{e}")
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
        st.Page(_page(profiles.render), title="档案", icon="👪", default=True),
        st.Page(_page(timeline.render), title="接种时间线", icon="📅", url_path="timeline"),
        st.Page(_page(tasks.render), title="待办与提醒", icon="✅", url_path="tasks"),
        st.Page(_page(checkin.render), title="接种后打卡", icon="🌡️", url_path="checkin"),
        st.Page(_page(review.render), title="人工审核", icon="🩺", url_path="review"),
        st.Page(_page(logs.render), title="日志", icon="📜", url_path="logs"),
    ]
    st.navigation(pages).run()


main()
