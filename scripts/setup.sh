#!/usr/bin/env bash
# 一键准备本地环境：clone DeerFlow → uv sync → 生成 config.yaml/.env
# 用法：scripts/setup.sh   （重复执行安全，已存在的步骤会跳过）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DF="$ROOT/deer-flow"
# 与 Phase 0 验证时一致的上游 commit；升级前先跑 scripts/phase0_smoke.sh 确认接口没变
DEERFLOW_COMMIT="${DEERFLOW_COMMIT:-1e3bfa0}"

command -v uv >/dev/null || { echo "缺 uv：brew install uv（或 https://docs.astral.sh/uv/）"; exit 1; }
command -v git >/dev/null || { echo "缺 git"; exit 1; }

# 1. DeerFlow 源码
if [ ! -d "$DF/.git" ]; then
  echo "==> clone DeerFlow"
  git clone https://github.com/bytedance/deer-flow.git "$DF"
  (cd "$DF" && git checkout -q "$DEERFLOW_COMMIT" 2>/dev/null || echo "   (commit $DEERFLOW_COMMIT 不在浅历史里，使用当前 HEAD)")
else
  echo "==> deer-flow 已存在，跳过 clone（当前 $(cd "$DF" && git rev-parse --short HEAD)）"
fi

# 2. 后端依赖（DeerFlow 要求 Python >= 3.12，uv 会自动下载）
echo "==> uv sync（DeerFlow backend）"
(cd "$DF/backend" && uv sync)

# 3. config.yaml：开 scheduler，启用 deepseek-chat
if [ ! -f "$DF/config.yaml" ]; then
  echo "==> 生成 config.yaml"
  python3 - "$DF" <<'PY'
import sys, pathlib
df = pathlib.Path(sys.argv[1]); root = df.parent
s = (df / "config.example.yaml").read_text()
s = s.replace("scheduler:\n  enabled: false", "scheduler:\n  enabled: true", 1)
s = s.replace("tool_groups:\n", "tool_groups:\n  - name: vaccinepath\n", 1)
# 把 vaccinepath 工具追加到 tools: 段末尾（下一个顶层键之前）
tools_snippet = (root / "vaccinepath" / "deerflow_tools.yaml").read_text()
i = s.index("\ntools:\n") + 1
j = s.index("\n", i)
import re
m = re.search(r"^\S", s[j:], re.M)  # tools: 之后第一个顶层键
k = j + m.start()
s = s[:k] + tools_snippet + "\n" + s[k:]
s = s.replace("models:\n", """models:
  - name: deepseek-chat
    display_name: DeepSeek Chat
    use: langchain_openai:ChatOpenAI
    model: deepseek-chat
    api_key: $DEEPSEEK_API_KEY
    base_url: https://api.deepseek.com/v1
    max_tokens: 4096
    max_retries: 3
    temperature: 0.3
""", 1)
(df / "config.yaml").write_text(s)
PY
else
  echo "==> config.yaml 已存在，跳过"
fi

# 4. .env：只需要 DEEPSEEK_API_KEY
if [ ! -f "$DF/.env" ]; then
  echo "==> 生成 .env"
  cp "$DF/.env.example" "$DF/.env"
  printf '\n# VaccinePath：向组长要 key\nDEEPSEEK_API_KEY=\n' >> "$DF/.env"
fi
if ! grep -qE '^DEEPSEEK_API_KEY=.+' "$DF/.env"; then
  echo
  echo "!! 请在 $DF/.env 里填 DEEPSEEK_API_KEY=sk-...  然后："
else
  echo "==> .env 已有 DEEPSEEK_API_KEY"
fi

# 5. 我们自己的 Python 依赖（Phase 1 起有 vaccinepath/ 后启用）
if [ -f "$ROOT/pyproject.toml" ]; then
  echo "==> uv sync（vaccinepath）"
  (cd "$ROOT" && uv sync)
fi

echo
echo "完成。下一步："
echo "  scripts/gateway.sh start      # 起 DeerFlow gateway :8001"
echo "  scripts/phase0_smoke.sh       # 验证线程 / 跑一轮 / 定时任务 / 手动触发"
