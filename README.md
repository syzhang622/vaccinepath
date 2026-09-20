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

## 跑测试

规则引擎的测试在 `tests/`，规则说明与判定表在 [`docs/rule_engine.md`](docs/rule_engine.md)。所有函数入参出参用 Pydantic 定义（`vaccinepath/models.py`），测试直接对着模型写：

```bash
uv sync                     # 仓库根目录，安装 vaccinepath 自身依赖（pytest 等）
uv run pytest               # 全部
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
│   └── phase0_smoke.sh    Phase 0 验收脚本
├── deer-flow/             DeerFlow 上游源码（gitignored）
├── vaccinepath/
│   ├── models.py          全部 Pydantic 模型（档案、记录、四函数入参出参）
│   ├── ncis.py            NCIS 结构化表加载
│   ├── data/ncis_2026_04.json  逐格转录的 NCIS 表
│   └── rules/             compute_schedule / detect_conflicts / pre_vaccination_screen / post_vaccination_escalate
└── tests/                 每函数 ≥3 正例 ≥3 反例 + 表格逐格钉死
```
