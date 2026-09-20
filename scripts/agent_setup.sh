#!/usr/bin/env bash
# 建 VaccinePath agent：线程 + 持续目标 + reuse_thread 定时任务。id 存到 data/agent.json，供前端"快进"按钮使用。
# 用法：scripts/agent_setup.sh [--reset]   （--reset 先把 data/db.json 重置为 mock 家庭种子）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="${BASE:-http://localhost:8001}"
H='content-type: application/json'
mkdir -p "$ROOT/data"
[ "${1:-}" = "--reset" ] && cp "$ROOT/vaccinepath/data/mock_family.json" "$ROOT/data/db.json" && echo "db.json 已重置为 mock 家庭"
[ -f "$ROOT/data/db.json" ] || cp "$ROOT/vaccinepath/data/mock_family.json" "$ROOT/data/db.json"

TMP=$(mktemp -d)
(cd "$ROOT" && uv run --quiet python - "$TMP" <<'PY'
import json, sys
from vaccinepath.agent.prompts import GOAL_OBJECTIVE, WAKE_UP_PROMPT
d = sys.argv[1]
json.dump({"objective": GOAL_OBJECTIVE, "max_continuations": 3}, open(f"{d}/goal.json", "w"))
json.dump({"context_mode": "reuse_thread", "title": "VaccinePath daily wake-up", "prompt": WAKE_UP_PROMPT,
           "schedule_type": "cron", "schedule_spec": {"cron": "0 9 * * *"}, "timezone": "Asia/Singapore"}, open(f"{d}/task.json", "w"))
PY
)

TID=$(curl -sf -X POST "$BASE/api/threads" -H "$H" -d '{"metadata":{"app":"vaccinepath"}}' | python3 -c "import sys,json;print(json.load(sys.stdin)['thread_id'])")
echo "thread: $TID"
curl -sf -X PUT "$BASE/api/threads/$TID/goal" -H "$H" -d @"$TMP/goal.json" > /dev/null && echo "goal set"
python3 -c "import json,sys; d=json.load(open('$TMP/task.json')); d['thread_id']='$TID'; json.dump(d, open('$TMP/task.json','w'))"
TASK=$(curl -sf -X POST "$BASE/api/scheduled-tasks" -H "$H" -d @"$TMP/task.json" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "scheduled task: $TASK (cron 每天 09:00 SGT；demo 用 trigger)"
python3 -c "import json; json.dump({'thread_id':'$TID','scheduled_task_id':'$TASK','base':'$BASE'}, open('$ROOT/data/agent.json','w'), indent=2)"
echo "saved → data/agent.json"
