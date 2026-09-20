# VaccinePath Family SG

NTU CA6117 *Agentic AI in Healthcare* 课程原型：一个**长期运行、有状态、自触发**的 agent，帮新加坡家长管理孩子的疫苗接种计划并做接种后的结构化监测。范围与设计以 [`docs/proposal_v2.md`](docs/proposal_v2.md) 为准，开发约定见 [`CLAUDE.md`](CLAUDE.md)。

## 本地环境说明（组员必读）

目标：从零到 `pytest` 全绿 + `phase0_smoke.sh` 通过，约 10 分钟。所有步骤在仓库根目录执行。

### 0. 前置

| 需要 | 版本 | 装法 |
|---|---|---|
| macOS / Linux | — | Windows 请用 WSL2 |
| git | 任意 | — |
| [uv](https://docs.astral.sh/uv/) | ≥ 0.5 | `brew install uv` 或 `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Python | 3.12+ | **不用自己装**，uv 会按 `pyproject.toml` 自动下载 |
| DeepSeek API key | — | 向组长要，形如 `sk-...` |

不需要 Docker、Node、Redis、nginx。

### 1. clone + 一键准备

```bash
git clone git@github.com:syzhang622/vaccinepath.git
cd vaccinepath
DEEPSEEK_API_KEY=sk-你的key scripts/setup.sh
```

`setup.sh` 做四件事，重复执行安全：
1. 把 DeerFlow 源码 clone 到 `deer-flow/`（锁定到 commit `1e3bfa0`，这个目录整个 gitignored，**不要往里写代码**）
2. `uv sync` 装 DeerFlow 后端依赖（首次约 2–3 分钟）和本仓库依赖
3. 生成 `deer-flow/config.yaml`：开 scheduler、启用 `deepseek-chat`、挂上我们的 `vp_*` 工具
4. 生成 `deer-flow/.env` 并写入 `DEEPSEEK_API_KEY`（没传环境变量就留空，之后手动填）

### 2. 跑测试（不需要 gateway、不需要 key）

```bash
uv run pytest            # 期望：71 passed
```

规则引擎、数据模型、工具层全在这里，改 `vaccinepath/` 下任何东西先跑它。

### 3. 起 gateway + 端到端验证

```bash
scripts/gateway.sh start       # 后台起 DeerFlow gateway，http://localhost:8001，鉴权已关
scripts/phase0_smoke.sh        # 建线程 → 跑一轮 → 定时任务 → 手动触发 → 验证状态延续；末尾打印 PHASE 0 PASS
```

其他命令：`scripts/gateway.sh status|log|stop`。日志在 `deer-flow/logs/gateway.log`。

### 4. 跑 agent（可选，看完整闭环）

```bash
scripts/phase2_demo.sh         # 重置 mock 家庭 → 建 agent → 唤醒#1 → 模拟家长动作 → 唤醒#2 → 打印 data/db.json 证据
```

或分步：`scripts/agent_setup.sh --reset` 建 agent，`scripts/agent_wake.sh` 手动触发一次唤醒（= 前端"快进到下一次检查"）。

### 5. 哪些文件不能提交

`deer-flow/`、`deer-flow/.env`、`deer-flow/config.yaml`、`data/`、`logs/` 都在 `.gitignore` 里。推之前 `git status` 看一眼，**API key 绝不能进 git**。

### 排错

| 现象 | 原因 / 处理 |
|---|---|
| `setup.sh` 报 `缺 uv` | 装 uv 后重开终端 |
| `gateway.sh start` 说 `already up on :8001` | 别人的 gateway 占着端口：`scripts/gateway.sh stop` 或 `lsof -i :8001` |
| `phase0_smoke.sh` 第 2 步失败，日志 `No chat models are configured` | `deer-flow/.env` 里 `DEEPSEEK_API_KEY` 为空；填好后 `scripts/gateway.sh stop && scripts/gateway.sh start` |
| 第 2 步 401 / `Authentication Fails` | key 错了 |
| `ModuleNotFoundError: vaccinepath`（gateway 日志） | 没用 `scripts/gateway.sh` 起的 gateway（它负责设 `PYTHONPATH`） |
| 想换回干净的 mock 数据 | `scripts/agent_setup.sh --reset` 或 `cp vaccinepath/data/mock_family.json data/db.json` |
| 想升级 DeerFlow | 改 `scripts/setup.sh` 里的 `DEERFLOW_COMMIT`，重跑 `phase0_smoke.sh` 确认接口没变 |

## 架构

| 层 | 是什么 | 在哪 |
|---|---|---|
| 后端 | [DeerFlow](https://github.com/bytedance/deer-flow) gateway：线程持久状态、定时任务、工具挂载。**不改它的源码** | `deer-flow/`（不进 git，`scripts/setup.sh` 自动 clone） |
| 规则引擎 | 纯确定性 Python：排程、查重、接种前筛查、接种后升级判定。**不经过 LLM**，可单元测试 | `vaccinepath/rules/` |
| 前端 | Streamlit | `vaccinepath/`（Phase 3 起） |
| 数据 | 全部 mock（JSON/SQLite）+ NCIS 日程结构化表 | `vaccinepath/`、`docs/` |

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
