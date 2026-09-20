# VaccinePath Family SG

NTU CA6117 *Agentic AI in Healthcare* 课程原型：一个**长期运行、有状态、自触发**的 agent，帮新加坡家长管理孩子的疫苗接种计划并做接种后的结构化监测。范围与设计以 [`docs/proposal_v2.md`](docs/proposal_v2.md) 为准，开发约定见 [`CLAUDE.md`](CLAUDE.md)。

## 架构

| 层 | 是什么 | 在哪 |
|---|---|---|
| 后端 | [DeerFlow](https://github.com/bytedance/deer-flow) gateway：线程持久状态、定时任务、工具挂载。**不改它的源码** | `deer-flow/`（不进 git，`scripts/setup.sh` 自动 clone） |
| 规则引擎 | 纯确定性 Python：排程、查重、接种前筛查、接种后升级判定。**不经过 LLM**，可单元测试 | `vaccinepath/rules/` |
| 前端 | Streamlit | `vaccinepath/`（Phase 3 起） |
| 数据 | 全部 mock（JSON/SQLite）+ NCIS 日程结构化表 | `vaccinepath/`、`docs/` |

## 安装

前置：macOS/Linux，`git`，[`uv`](https://docs.astral.sh/uv/)（`brew install uv`）。不需要 Docker、Node、Redis。

```bash
git clone git@github.com:syzhang622/vaccinepath.git && cd vaccinepath
scripts/setup.sh          # clone DeerFlow → uv sync → 生成 deer-flow/config.yaml 与 deer-flow/.env
```

然后在 `deer-flow/.env` 填 `DEEPSEEK_API_KEY=sk-...`（向组长要）。`config.yaml`、`.env`、`logs/` 都在 `.gitignore` 里，不会被提交。

## 起 gateway

```bash
scripts/gateway.sh start    # 后台起 DeerFlow gateway，监听 http://localhost:8001（鉴权已关：DEER_FLOW_AUTH_DISABLED=1）
scripts/gateway.sh status   # up / down
scripts/gateway.sh log      # tail 日志（deer-flow/logs/gateway.log）
scripts/gateway.sh stop
```

验证环境（建线程 → 跑一轮 → 建 `reuse_thread` 定时任务 → 手动 trigger → 确认第二轮带着第一轮的记忆）：

```bash
scripts/phase0_smoke.sh     # 末尾打印 PHASE 0 PASS
```

常用接口（都在 `http://localhost:8001/api/...`，完整说明见 `CLAUDE.md`）：

- `POST /api/threads` 建线程；`GET /api/threads/{id}/state` 读状态
- `POST /api/threads/{id}/runs/wait` 同步跑一轮，body `{"input":{"messages":[{"role":"user","content":"..."}]}}`
- `POST /api/scheduled-tasks`（`context_mode: "reuse_thread"` + `thread_id` + `title` 必填）；`POST /api/scheduled-tasks/{id}/trigger` 手动触发；`GET /api/scheduled-tasks/{id}/runs` 看历史

## 跑 agent（Phase 2）

```bash
scripts/agent_setup.sh --reset   # 重置 mock 家庭 → 建线程 + 持续目标 + reuse_thread 定时任务（cron 每天 09:00 SGT），id 存 data/agent.json
scripts/agent_wake.sh            # 手动触发一次唤醒（= 前端"快进到下一次检查"），打印本轮工具调用与 agent 摘要
scripts/phase2_demo.sh           # 一键：重置 → 唤醒#1 → 模拟家长动作 → 唤醒#2 → 打印 db.json 证据
```

每次唤醒 agent 只通过 `vp_*` 工具（`vaccinepath/tools.py`，经 `config.yaml` 的 `tools:` 段挂进 DeerFlow）读状态、调规则引擎、建任务、发提醒、转人工审核、记日志。判定全部在规则引擎；LLM 只做流程编排和文案。唤醒 prompt 与目标在 `vaccinepath/agent/prompts.py`。数据在 `data/db.json`（gitignored，种子 `vaccinepath/data/mock_family.json`）。

## 跑测试

规则引擎的测试在 `tests/`，规则说明与判定表在 [`docs/rule_engine.md`](docs/rule_engine.md)。所有函数入参出参用 Pydantic 定义（`vaccinepath/models.py`），测试直接对着模型写：

```bash
uv sync                     # 仓库根目录，安装 vaccinepath 自身依赖（pytest 等）
uv run pytest               # 全部（含工具层，用临时目录隔离）
uv run pytest tests/test_compute_schedule.py -v
```

## 目录

```
.
├── CLAUDE.md              开发约定 / 启动 prompt（含已验证的 DeerFlow 接口清单）
├── README.md
├── docs/
│   ├── proposal_v2.md     课程 proposal
│   ├── ncis_moh_2026-04.pdf  MOH 官方 NCIS 表（2026-04-01）
│   ├── rule_engine.md     规则引擎说明：总原则、约定、四函数判定表
│   └── sources/           KKH / HealthHub 官方页面原文摘录（接种后升级判据）
├── scripts/
│   ├── setup.sh           一键准备环境
│   ├── gateway.sh         起停 DeerFlow gateway
│   ├── phase0_smoke.sh    Phase 0 验收脚本
│   ├── agent_setup.sh     建 agent（线程 + goal + 定时任务）
│   ├── agent_wake.sh      手动触发一次唤醒
│   ├── simulate_parent.py 模拟家长动作（demo）
│   └── phase2_demo.sh     Phase 2 验收脚本
├── deer-flow/             DeerFlow 上游源码（gitignored）
├── vaccinepath/
│   ├── models.py          全部 Pydantic 模型（档案、记录、四函数入参出参）
│   ├── ncis.py            NCIS 结构化表加载
│   ├── data/ncis_2026_04.json  逐格转录的 NCIS 表
│   ├── data/mock_family.json   演示家庭种子（3 孩：准时 / 漏针 / 海外记录）
│   ├── rules/             compute_schedule / detect_conflicts / pre_vaccination_screen / post_vaccination_escalate
│   ├── store.py           mock 数据层（data/db.json + 文件锁）
│   ├── tools.py           挂到 DeerFlow 的 13 个 vp_* 工具
│   ├── deerflow_tools.yaml  config.yaml 的 tools: 片段（setup.sh 自动追加）
│   └── agent/prompts.py   持续目标 + 唤醒 prompt
└── tests/                 每函数 ≥3 正例 ≥3 反例 + 表格逐格钉死
```
