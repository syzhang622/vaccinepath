"""建 / 重建 VaccinePath agent：线程 + 持续目标 + reuse_thread 定时任务。脚本 agent_setup.sh 和 UI 的"重置"按钮都调这里。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from vaccinepath.agent.prompts import GOAL_OBJECTIVE, WAKE_UP_PROMPT
from vaccinepath.store import SEED_PATH, Store, data_dir

DEFAULT_BASE = "http://localhost:8001"


def agent_json() -> Path:
    return data_dir() / "agent.json"


def setup_agent(base: str = DEFAULT_BASE, *, reset_data: bool = False) -> dict[str, Any]:
    """返回 {thread_id, scheduled_task_id, base}。会删除旧的定时任务；旧线程留在 DeerFlow 里但不再使用。"""
    if reset_data:
        Store().reset_from_seed(SEED_PATH)
    old = json.loads(agent_json().read_text()) if agent_json().exists() else None
    if old and old.get("scheduled_task_id"):
        try:
            requests.delete(f"{base}/api/scheduled-tasks/{old['scheduled_task_id']}", timeout=10)
        except requests.RequestException:
            pass
    h = {"content-type": "application/json"}
    tid = requests.post(f"{base}/api/threads", json={"metadata": {"app": "vaccinepath"}}, headers=h, timeout=10).json()["thread_id"]
    requests.put(f"{base}/api/threads/{tid}/goal", json={"objective": GOAL_OBJECTIVE, "max_continuations": 3}, headers=h, timeout=10).raise_for_status()
    r = requests.post(
        f"{base}/api/scheduled-tasks",
        json={"thread_id": tid, "context_mode": "reuse_thread", "title": "VaccinePath daily wake-up", "prompt": WAKE_UP_PROMPT, "schedule_type": "cron", "schedule_spec": {"cron": "0 9 * * *"}, "timezone": "Asia/Singapore"},
        headers=h,
        timeout=10,
    )
    r.raise_for_status()
    cfg = {"thread_id": tid, "scheduled_task_id": r.json()["id"], "base": base}
    agent_json().parent.mkdir(parents=True, exist_ok=True)
    agent_json().write_text(json.dumps(cfg, indent=2))
    return cfg


if __name__ == "__main__":
    import sys

    cfg = setup_agent(reset_data="--reset" in sys.argv)
    print(f"thread: {cfg['thread_id']}\nscheduled task: {cfg['scheduled_task_id']} (cron 每天 09:00 SGT；demo 用 trigger)\nsaved → {agent_json()}")
