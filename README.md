# VaccinePath Family SG

NTU CA6117 *Agentic AI in Healthcare* 课程原型：一个**长期运行、有状态、自触发**的 agent，帮新加坡家长管理孩子的疫苗接种计划并做接种后的结构化监测。范围与设计以 [`docs/proposal_v2.md`](docs/proposal_v2.md) 为准，开发约定见 [`CLAUDE.md`](CLAUDE.md)。

## 本地环境说明（组员必读）

### 一、所有人先装这三样

1. git
2. uv（Python 包管理器）：macOS/Linux 终端里跑 `curl -LsSf https://astral.sh/uv/install.sh | sh`（或 `brew install uv`），装完重开终端
3. Python 3.12 不用单独装，uv 会自动拉

### 二、只想跑规则引擎、写/看测试用例（不需要任何 key）

```bash
git clone https://github.com/syzhang622/vaccinepath.git
cd vaccinepath
uv sync
uv run pytest            # 期望：82 passed
```

看到全部 passed 就说明环境对了。规则说明在 `docs/rule_engine.md`，四个函数在 `vaccinepath/rules/`，测试在 `tests/`。改 `vaccinepath/` 下任何东西先跑它。

### 三、要跑完整 agent 的，在二的基础上再做三步

4. 运行 `scripts/setup.sh`
   会自动下载 DeerFlow（后端框架，已锁定到 commit `1e3bfa0`，放在 `deer-flow/`，整个目录 gitignored，**不要往里写代码**）、装依赖、生成 `deer-flow/config.yaml`（开 scheduler、启用 deepseek-chat、挂上我们的 `vp_*` 工具）和 `deer-flow/.env`。第一次要几分钟，依赖比较多，别以为卡死了。重复执行安全。
5. 准备一个 DeepSeek 的 API key
   platform.deepseek.com 注册，充几块钱够用几周。填进 `deer-flow/.env` 里的 `DEEPSEEK_API_KEY=`。（也可以在第 4 步直接 `DEEPSEEK_API_KEY=sk-xxx scripts/setup.sh`，脚本会替你写进去。）
6. 启动并验证
   ```bash
   scripts/gateway.sh start      # 起后端，http://localhost:8001，鉴权已关
   scripts/phase0_smoke.sh       # 7 步自检，末尾 PHASE 0 PASS 即通
   ```
   其他命令：`scripts/gateway.sh status|log|stop`，日志在 `deer-flow/logs/gateway.log`。

想看完整闭环：`scripts/phase2_demo.sh`（重置 mock 家庭 → 建 agent → 唤醒#1 → 模拟家长动作 → 唤醒#2 → 打印 `data/db.json` 证据）。分步是 `scripts/agent_setup.sh --reset` 和 `scripts/agent_wake.sh`（手动触发一次唤醒 = 前端"快进到下一次检查"）。

### 四、注意

- Windows：脚本是 bash 写的，**推荐 WSL**；Git Bash 未验证（DeerFlow 后端在原生 Windows 上能否起来我们没测过），PowerShell 不行。
- `deer-flow/.env` 和 `deer-flow/config.yaml` 不要提交到 git，里面有 key；`deer-flow/`、`data/`、`logs/` 也都已在 `.gitignore` 里。推之前 `git status` 看一眼。
- 前端：`scripts/ui.sh` 起 Streamlit，浏览器开 http://localhost:8501（六页：档案 / 接种时间线 / 待办与提醒 / 接种后打卡 / 人工审核 / 日志；侧栏「⏩ 快进到下一次检查」= 手动触发 agent 唤醒，需要 gateway 在线且已跑过 `scripts/agent_setup.sh`）。

有卡住的直接把报错贴群里。

### 排错

| 现象 | 原因 / 处理 |
|---|---|
| `setup.sh` 报 `缺 uv` | 装 uv 后重开终端 |
| `gateway.sh start` 说 `already up on :8001` | 别的 gateway 占着端口：`scripts/gateway.sh stop` 或 `lsof -i :8001` |
| `phase0_smoke.sh` 第 2 步失败，日志 `No chat models are configured` | `deer-flow/.env` 里 `DEEPSEEK_API_KEY` 为空；填好后 `scripts/gateway.sh stop && scripts/gateway.sh start` |
| 第 2 步 401 / `Authentication Fails` | key 错了或余额为 0 |
| `ModuleNotFoundError: vaccinepath`（gateway 日志） | 没用 `scripts/gateway.sh` 起的 gateway（它负责设 `PYTHONPATH`） |
| 想换回干净的 mock 数据 | `scripts/agent_setup.sh --reset` 或 `cp vaccinepath/data/mock_family.json data/db.json` |
| 想升级 DeerFlow | 改 `scripts/setup.sh` 里的 `DEERFLOW_COMMIT`，重跑 `phase0_smoke.sh` 确认接口没变 |

## 架构

| 层 | 是什么 | 在哪 |
|---|---|---|
| 后端 | [DeerFlow](https://github.com/bytedance/deer-flow) gateway：线程持久状态、定时任务、工具挂载。**不改它的源码** | `deer-flow/`（不进 git，`scripts/setup.sh` 自动 clone） |
| 规则引擎 | 纯确定性 Python：排程、查重、接种前筛查、接种后升级判定。**不经过 LLM**，可单元测试 | `vaccinepath/rules/` |
| 前端 | Streamlit 六页，直接调规则引擎与工具函数，只有 trigger/运行记录走 gateway HTTP | `vaccinepath/ui/` |
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
│   ├── phase2_demo.sh     Phase 2 验收脚本
│   └── ui.sh              起 Streamlit 前端 :8501
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
│   ├── agent/prompts.py   持续目标 + 唤醒 prompt
│   └── ui/                Streamlit：app.py 入口 + pages/ 六页 + gateway.py HTTP 客户端
└── tests/                 规则引擎 / 工具层 / 前端（AppTest 无头渲染）
```
