#!/usr/bin/env bash
# 手动触发一次唤醒（= 前端的"快进到下一次检查"），等它跑完，打印 agent 的回复与本轮工具调用。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE=$(python3 -c "import json;print(json.load(open('$ROOT/data/agent.json'))['base'])")
TID=$(python3 -c "import json;print(json.load(open('$ROOT/data/agent.json'))['thread_id'])")
TASK=$(python3 -c "import json;print(json.load(open('$ROOT/data/agent.json'))['scheduled_task_id'])")

BEFORE=$(curl -sf "$BASE/api/scheduled-tasks/$TASK/runs" | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
curl -sf -X POST "$BASE/api/scheduled-tasks/$TASK/trigger" > /dev/null
echo "triggered; waiting..."
for i in $(seq 1 150); do
  RUNS=$(curl -sf "$BASE/api/scheduled-tasks/$TASK/runs")
  ST=$(echo "$RUNS" | python3 -c "import sys,json;r=json.load(sys.stdin);print(r[0]['status'] if len(r)>$BEFORE else 'pending')")
  case "$ST" in success|failed) break;; esac
  sleep 2
done
RUN_ID=$(echo "$RUNS" | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['run_id'])")
echo "run $RUN_ID → $ST ($((i*2))s)"
[ "$ST" = "success" ] || { echo "$RUNS" | head -c 600; exit 1; }
curl -sf "$BASE/api/threads/$TID/runs/$RUN_ID/messages?limit=200" | python3 -c "
import sys,json
ms=json.load(sys.stdin)['data']
calls=[]; final=''
for m in ms:
    c=m['content']
    if m['event_type']=='llm.ai.response':
        for t in (c.get('tool_calls') or []): calls.append(t['name']+'('+json.dumps(t.get('args',{}),ensure_ascii=False)[:90]+')')
        if c.get('content'): final=c['content']
print('本轮工具调用 %d 次：' % len(calls))
for c in calls: print('  ', c)
print(); print('agent 回复：'); print(final)"
