#!/usr/bin/env bash
# 起 Streamlit 前端：http://localhost:8501
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec uv run streamlit run vaccinepath/ui/app.py --server.headless true --server.port "${PORT:-8501}" "$@"
