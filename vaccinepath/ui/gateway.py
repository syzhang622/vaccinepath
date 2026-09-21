"""前端 → DeerFlow gateway 的最小 HTTP 客户端。只做：探活、手动触发唤醒、读运行记录与 agent 回复。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

from vaccinepath.store import data_dir

DEFAULT_BASE = "http://localhost:8001"


def agent_config() -> dict[str, Any] | None:
    p = data_dir() / "agent.json"
    return json.loads(p.read_text()) if p.exists() else None


def base_url() -> str:
    cfg = agent_config()
    return (cfg or {}).get("base", DEFAULT_BASE)


def gateway_up() -> bool:
    try:
        return requests.get(f"{base_url()}/api/scheduled-tasks", timeout=2).status_code == 200
    except requests.RequestException:
        return False


def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    cfg = agent_config()
    if not cfg:
        return []
    r = requests.get(f"{base_url()}/api/scheduled-tasks/{cfg['scheduled_task_id']}/runs", params={"limit": limit}, timeout=10)
    r.raise_for_status()
    return r.json()


def run_reply(run_id: str) -> tuple[list[str], str]:
    """返回 (本轮工具调用列表, agent 最终回复)。"""
    cfg = agent_config()
    r = requests.get(f"{base_url()}/api/threads/{cfg['thread_id']}/runs/{run_id}/messages", params={"limit": 200}, timeout=20)
    r.raise_for_status()
    calls, final = [], ""
    for m in r.json().get("data", []):
        c = m.get("content") or {}
        if m.get("event_type") == "llm.ai.response":
            for t in c.get("tool_calls") or []:
                calls.append(f"{t['name']}({json.dumps(t.get('args', {}), ensure_ascii=False)[:80]})")
            if c.get("content"):
                final = c["content"]
    return calls, final


def trigger_wake_up(timeout_s: int = 300) -> dict[str, Any]:
    """手动触发一次唤醒并等它结束。返回 {status, run_id, seconds, calls, reply}。"""
    cfg = agent_config()
    if not cfg:
        raise RuntimeError("还没建 agent：先跑 scripts/agent_setup.sh")
    before = len(list_runs(200))
    r = requests.post(f"{base_url()}/api/scheduled-tasks/{cfg['scheduled_task_id']}/trigger", timeout=10)
    if r.status_code == 409:
        raise RuntimeError("上一次唤醒还在跑，稍等再点")
    r.raise_for_status()
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        runs = list_runs(200)
        if len(runs) > before and runs[0]["status"] in ("success", "failed"):
            run = runs[0]
            calls, reply = run_reply(run["run_id"]) if run["status"] == "success" else ([], run.get("error") or "")
            return {"status": run["status"], "run_id": run["run_id"], "seconds": round(time.time() - t0), "calls": calls, "reply": reply}
        time.sleep(2)
    raise TimeoutError("唤醒超时")
