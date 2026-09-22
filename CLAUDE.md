# VaccinePath Family SG — 原型开发启动指令

## 你的角色
你是这个课程项目（NTU CA6117 Agentic AI in Healthcare）的原型开发者。我负责验收和决策，你负责规划和实现。遇到需要我拍板的事先停下来问，不要自己猜。

## 项目一句话
一个**长期运行、有状态、自触发**的智能体（agent）：帮新加坡家长管理孩子的疫苗接种计划，并做接种后的结构化监测。核心卖点是「它会自己按日程醒来推进任务」，不是一个问答机器人（chatbot）。

## 架构分层（已定，不要改）
1. **后端：DeerFlow**（github.com/bytedance/deer-flow，源码 clone 在 `6117/deer-flow/`，**它不是我们的源码，不要往里写业务代码**）。**不用 Docker**，直接用 uv 起 gateway：`cd deer-flow/backend && DEER_FLOW_AUTH_DISABLED=1 PYTHONPATH=. uv run uvicorn app.gateway.app:app --port 8001`（stream bridge 默认 `memory`，不需要 Redis/nginx/Next.js 前端）。用它的：线程（thread）持久状态、定时任务（scheduled tasks）、工具（tools）挂载。**不改 DeerFlow 源码**，只通过 `config.yaml` 的 `tools:` 段挂我们自己写的 Python 工具（`use: 模块:函数` 形式，模块通过 `PYTHONPATH` 指向我们自己的目录），以及 HTTP API 调它。
2. **规则引擎（rule engine）：独立 Python 模块**，纯确定性逻辑，不经过 LLM。负责：接种日程计算（对照 NCIS 表）、记录查重/冲突检测、接种前安全筛查判定、接种后症状升级判定。这一层必须可单元测试，队友会对它写全部测试用例。
3. **前端：Streamlit 自写**。页面：家庭/孩子档案、接种时间线、待办与提醒、接种后打卡问卷、人工审核队列、日志。前端通过 HTTP 调 DeerFlow gateway，并直接调规则引擎。
4. **数据：全部 mock**（JSON/SQLite），不接任何真实医疗数据。NCIS 官方日程表整理成一张结构化表作为知识库。

## DeerFlow 已验证可用的接口（2026-09-20 对着 commit 1e3bfa0 查的）
所有路由带 `/api` 前缀（gateway 直连 `http://localhost:8001`）。
- 线程：`POST /api/threads` 建线程（body 可空 `{}`），`GET/POST /api/threads/{id}/state` 读写状态，`PUT /api/threads/{id}/goal` 设持续目标
- 运行：`POST /api/threads/{id}/runs/wait` 同步跑一轮，body 为 `{"input": {"messages": [{"role": "user", "content": "..."}]}}`（`extra="forbid"`，不能加未定义字段）；`GET /api/threads/{id}/messages` 读结果（返回的是**事件日志**，每条有 `event_type` 如 `llm.human.input`/`llm.ai.response`、`category`、`content`，不是 LangChain message 列表；要 message 列表用 `/state` 的 `values.messages`）
- 定时任务：`POST /api/scheduled-tasks`，字段 `thread_id`、`context_mode`、**`title`（必填，之前漏了）**、`prompt`、`schedule_type`（`once|cron|interval`）、`schedule_spec`（interval 用 `{"every_seconds": N}`）、`timezone`；`POST /api/scheduled-tasks/{id}/trigger` **手动触发**（demo 用它，不等 cron；它和 cron 走同一个 `dispatch_task`，是真实路径），`GET /api/scheduled-tasks/{id}/runs` 看历史（终态是 `success`/`failed`/`skipped`，不是 `completed`）
- 定时任务的 `context_mode` 线程复用模式的准确取值是 **`"reuse_thread"`**，必须同时传 `thread_id`（否则 422）。默认值 `fresh_thread_per_run` 不要用
- 调度器默认关闭：`config.yaml` 里 `scheduler.enabled: true`
- 鉴权：**用 `DEER_FLOW_AUTH_DISABLED=1` 关掉**（代码内置的非 production 开关），所有请求免 token。不走 PAT
- 模型：DeepSeek `deepseek-chat`（`langchain_openai:ChatOpenAI` + `base_url: https://api.deepseek.com/v1`），key 在 `deer-flow/.env` 的 `DEEPSEEK_API_KEY`，`config.yaml` 用 `$DEEPSEEK_API_KEY` 引用
- 启停：`scripts/gateway.sh start|stop|status|log`（会显式导出 `.env`，`PYTHONPATH` 含仓库根，`VACCINEPATH_DATA_DIR=data/`）；验收：`scripts/phase0_smoke.sh`、`scripts/phase2_demo.sh`（2026-09-20 均 PASS）
- 工具挂载：`use:` 必须指向 LangChain `BaseTool` 实例（`@tool` 装饰的函数即可）；lead agent 默认加载全部 `tool_groups`。片段在 `vaccinepath/deerflow_tools.yaml`，`setup.sh` 生成 config.yaml 时自动追加
- thread goal（`PUT /api/threads/{id}/goal`，body `{objective, max_continuations}`）的语义是：每轮结束后由评估模型判断 objective 是否达成，未达成就自动续跑（默认最多 8 次）。所以 objective 要写成**单次唤醒的完成条件**，不能写成"永远保持计划在轨"，否则每次唤醒空转
- 定时任务的运行记录 `GET /api/threads/{tid}/runs/{run_id}/messages?limit=200` 返回 `{data: [事件], has_more}`，工具调用在 `llm.ai.response` 事件的 `content.tool_calls` 里

## 范围：只做 core，stretch 明确不做
**core 闭环（必须全部做出来）：**
录入 → 校验/查重（含海外记录对照 NCIS）→ 排程 → 接种前安全筛查 → 人工审核 → 定时提醒（agent 醒来检查到期/逾期/未回应）→ 接种后结构化打卡 → 规则引擎判断是否升级 → 全程日志

**stretch（本阶段一律不做，有人提也先拒）：** OCR 上传接种卡、诊所搜索、症状趋势图。

## 硬性护栏
- **LLM 不做升级判断。** 接种后是否升级只由规则引擎决定；LLM 只负责解释结果、生成追问和提醒文案。
- 任何医疗建议类输出都要有「不诊断、不替代医生」的固定免责语，且高风险情形统一走「转人工审核」。
- 每个阶段结束前跑通一次端到端，不要堆代码到最后再调。
- 跑不通、依赖装不上、DeerFlow 行为跟上面写的不一致：**停下来报给我**，不要绕路自己 mock 掉。
- 所有工具函数入参出参用 Pydantic 定义，队友要基于它写测试。

## 分阶段验收（每阶段完成后停下来给我看）
**Phase 0 — 环境跑通（半天）**
DeerFlow 起来，能通过 API 建线程、跑一轮、建一个定时任务并手动触发。给我一个 curl 脚本证明（`scripts/phase0_smoke.sh`）。

**Phase 1 — 数据模型 + 规则引擎 + 测试骨架（1 天）**
- 家庭/孩子/接种记录/任务/打卡 的数据模型
- NCIS 日程表结构化
- 规则引擎四个函数：`compute_schedule`、`detect_conflicts`、`pre_vaccination_screen`、`post_vaccination_escalate`
- 每个函数至少 3 条正例 3 条反例的测试，给队友接手

**Phase 2 — agent 工具 + 定时循环（1–2 天）**
- 把规则引擎包成 DeerFlow 工具挂上
- 写 agent 的持续目标（goal）和每次醒来的 prompt：检查到期/逾期/未回应 → 决定动作 → 写回状态 → 记日志
- 手动触发两次，证明第二次带着第一次的状态

**Phase 3 — Streamlit 前端（1–2 天）**
- 六个页面按上面列的做，风格朴素即可，功能优先
- 「快进到下一次检查」按钮 = 调 `trigger` 接口

**Phase 4 — demo 脚本（半天）**
- 写一份 5 分钟录屏脚本，覆盖老师要求的 7 条验收要素：目标驱动、多步规划、工具调用、记忆/状态、人工监督、安全响应、日志可追溯
- 准备一套演示用 mock 家庭：多孩 + 一个带海外记录的孩子

## 目录约定
```
6117/
├── CLAUDE.md            ← 本文件，启动 prompt
├── docs/proposal_v2.md  ← 课程 proposal，范围以它为准
├── scripts/             ← 验收/启动脚本
├── deer-flow/           ← DeerFlow 上游源码（只读，config.yaml 和 .env 在这里，均 gitignored）
└── vaccinepath/         ← 我们自己的代码（规则引擎、工具、Streamlit），Phase 1 起建
```

## 现在开始
Phase 0–4 全部完成并经组长实测（2026-09-22）。demo 剧本在 `docs/demo_script.md`；agent 引用官方指引走 `vp_get_guidance`（语料 `docs/sources/`，只覆盖接种后反应与发热，检索不到就不引用）。
