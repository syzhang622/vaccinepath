#!/usr/bin/env bash
# Phase 2 验收：重置数据 → 建 agent → 唤醒 #1 → 模拟家长动作 → 唤醒 #2 → 打印状态证据
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
scripts/gateway.sh status | grep -q up || scripts/gateway.sh start
echo "================ setup"; scripts/agent_setup.sh --reset
echo; echo "================ wake-up #1"; scripts/agent_wake.sh
echo; echo "================ parent acts between wake-ups"; uv run --quiet python scripts/simulate_parent.py
echo; echo "================ wake-up #2"; scripts/agent_wake.sh
echo; echo "================ evidence from data/db.json"
uv run --quiet python - <<'PY'
from collections import Counter
from vaccinepath.models import TaskType
from vaccinepath.store import Store
s = Store(); d = s.read(); tasks = s.tasks()
print("agent state       :", {k: v for k, v in d["agent"].items() if k != "last_summary"})
print("tasks (type,status):", dict(Counter((t.type.value, t.status.value) for t in tasks)))
print("reminder_count     :", dict(Counter(t.reminder_count for t in tasks if t.type == TaskType.vaccination_due)))
for t in tasks:
    if t.type == TaskType.professional_review:
        print(f"review {t.child_id:12}: {len((t.notes or '').splitlines())} reasons")
for ck in d["checkins"].values():
    ev = ck.get("evaluation") or {}
    print("checkin evaluation :", ev.get("outcome"), [t["rule"] for t in ev.get("triggers", [])])
print("notifications      :", len(d["notifications"]))
print("audit_log          :", len(d["audit_log"]), dict(Counter(e["actor"] for e in d["audit_log"])))
PY
echo; echo "PHASE 2 PASS"
