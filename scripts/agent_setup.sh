#!/usr/bin/env bash
# 建 / 重建 VaccinePath agent：线程 + 持续目标 + reuse_thread 定时任务。id 存到 data/agent.json。
# 用法：scripts/agent_setup.sh [--reset]   （--reset 同时把 data/db.json 重置为 mock 家庭种子）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[ "${1:-}" = "--reset" ] && echo "db.json 已重置为 mock 家庭"
exec uv run --quiet python -m vaccinepath.agent.setup "$@"
