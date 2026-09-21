#!/usr/bin/env bash
# 启停 DeerFlow gateway（uv 直跑，不用 Docker）。用法：scripts/gateway.sh start|stop|status|log
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DF="$ROOT/deer-flow"
LOG="$DF/logs/gateway.log"
PORT=8001

case "${1:-status}" in
  start)
    if lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then echo "port :$PORT already in use (gateway already up, or still shutting down)"; exit 0; fi
    mkdir -p "$DF/logs"
    # 显式导出 .env（API key 等），不依赖 load_dotenv 的查找路径
    (cd "$DF/backend" && set -a && [ -f "$DF/.env" ] && . "$DF/.env"; set +a; DEER_FLOW_AUTH_DISABLED=1 PYTHONPATH=".:$ROOT" VACCINEPATH_DATA_DIR="$ROOT/data" \
      nohup uv run --no-sync uvicorn app.gateway.app:app --port $PORT > "$LOG" 2>&1 &)
    for i in $(seq 1 60); do
      curl -sf -o /dev/null "http://localhost:$PORT/api/scheduled-tasks" && { echo "gateway up (${i}s), log: $LOG"; exit 0; }
      sleep 1
    done
    echo "gateway failed to start, see $LOG"; tail -30 "$LOG"; exit 1 ;;
  stop)
    if pkill -f "uvicorn app.gateway.app:app"; then
      for i in $(seq 1 30); do lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1 || break; sleep 1; done
      echo "gateway stopped"
    else
      echo "gateway not running"
    fi ;;
  status)
    curl -sf -o /dev/null "http://localhost:$PORT/docs" && echo "up" || echo "down" ;;
  log)
    tail -f "$LOG" ;;
  *) echo "usage: $0 start|stop|status|log"; exit 1 ;;
esac
