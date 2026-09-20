#!/usr/bin/env bash
# Phase 0 验收：建线程 → 跑一轮 → 读状态 → 建 reuse_thread 定时任务 → 手动 trigger → 看运行记录 → 证明写进同一线程
# 前置：scripts/gateway.sh start；deer-flow/config.yaml 至少配置一个 model
set -euo pipefail
BASE="${BASE:-http://localhost:8001}"
H='content-type: application/json'
step() { echo; echo "=== $1"; }
need() { # need <json> <python-expr> <说明>
  python3 -c "import sys,json; d=json.loads(sys.argv[1]); assert ($2), '$3'; print('    ✓ $3')" "$1" || { echo "    ✗ $3"; exit 1; }
}

step "1. POST /api/threads 建线程"
R=$(curl -sf -X POST "$BASE/api/threads" -H "$H" -d '{}'); echo "$R"
need "$R" "d['thread_id']" "返回 thread_id"
TID=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin)['thread_id'])")

step "2. POST /api/threads/$TID/runs/wait 同步跑一轮"
R=$(curl -sf -X POST "$BASE/api/threads/$TID/runs/wait" -H "$H" \
  -d '{"input":{"messages":[{"role":"user","content":"Reply with exactly the word PONG and nothing else."}]}}')
echo "$R" | head -c 600; echo
need "$R" "any(m.get('type')=='ai' and m.get('content') for m in d.get('messages',[]))" "messages 里有 AI 回复"

step "3. GET /api/threads/$TID/state 读状态"
R=$(curl -sf "$BASE/api/threads/$TID/state"); echo "$R" | head -c 400; echo
N1=$(echo "$R" | python3 -c "import sys,json; print(len([m for m in json.load(sys.stdin)['values'].get('messages',[]) if m.get('type') in ('human','ai')]))")
echo "    消息数 = $N1"; [ "$N1" -ge 2 ] && echo "    ✓ 状态持久化了第 2 步的对话" || { echo "    ✗ 状态里没消息"; exit 1; }

step "4. POST /api/scheduled-tasks 建 reuse_thread 定时任务（interval 1h，不等它自己触发）"
R=$(curl -sf -X POST "$BASE/api/scheduled-tasks" -H "$H" -d "{
  \"thread_id\": \"$TID\", \"context_mode\": \"reuse_thread\",
  \"title\": \"phase0 smoke\",
  \"prompt\": \"This is a scheduled wake-up. Reply with exactly: WAKE and the word you replied with last time.\",
  \"schedule_type\": \"interval\", \"schedule_spec\": {\"every_seconds\": 3600},
  \"timezone\": \"Asia/Singapore\"}"); echo "$R"
need "$R" "d['context_mode']=='reuse_thread' and d['status']=='enabled'" "context_mode=reuse_thread 且 status=enabled"
TASK=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

step "5. POST /api/scheduled-tasks/$TASK/trigger 手动触发"
R=$(curl -sf -X POST "$BASE/api/scheduled-tasks/$TASK/trigger"); echo "$R"
need "$R" "d['triggered'] is True" "triggered=true"

step "6. GET /api/scheduled-tasks/$TASK/runs 等运行完成"
for i in $(seq 1 60); do
  R=$(curl -sf "$BASE/api/scheduled-tasks/$TASK/runs")
  ST=$(echo "$R" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r[0]['status'] if r else 'none')")
  [ "$ST" = "success" ] && break; [ "$ST" = "failed" ] && break; sleep 2
done
echo "$R" | head -c 800; echo
[ "$ST" = "success" ] && echo "    ✓ 运行记录 status=success (trigger=manual)" || { echo "    ✗ 运行状态=$ST"; exit 1; }

step "7. GET /api/threads/$TID/messages 证明定时任务写进了同一线程（返回的是事件日志，每条有 event_type）"
R=$(curl -sf "$BASE/api/threads/$TID/messages")
N2=$(echo "$R" | python3 -c "import sys,json; print(len([e for e in json.load(sys.stdin) if e['category']=='message']))")
echo "    对话消息数 第2步后=$N1 → trigger 后=$N2"
[ "$N2" -gt "$N1" ] && echo "    ✓ 同一线程消息增加，定时任务带着历史状态运行" || { echo "    ✗ 消息数没增加"; exit 1; }
echo; echo "线程完整对话："; echo "$R" | python3 -c "
import sys,json
for e in json.load(sys.stdin):
    if e['category']=='message': print('   ', e['event_type'].split('.')[1].upper()+':', str(e['content'].get('content'))[:120].replace(chr(10),' '))"

step "清理：删除定时任务 $TASK"
curl -sf -X DELETE "$BASE/api/scheduled-tasks/$TASK"; echo
echo; echo "PHASE 0 PASS  thread=$TID"
