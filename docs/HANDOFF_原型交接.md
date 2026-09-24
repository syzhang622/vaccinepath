# VaccinePath Family SG — 原型交接文档（给报告 / PPT / 评测）

代码冻结日期：2026-09-22。仓库：https://github.com/syzhang622/vaccinepath
录屏母带：`录屏2026-09-22_22_24_33.mov`（5 分 52 秒，未剪，按 `docs/demo_script.md` 八步录的）
截图：`docs/screenshots/` 9 张，按步骤编号，可直接进报告第 4 节和 PPT

下面按老师 project brief 的要求组织，每一条都标了「证据在哪」。

---

## 0. 一句话与三个数字

**是什么**：一个长期运行、有状态、自触发的疫苗管理 agent。帮新加坡家长管理孩子的 NCIS 接种计划，做接种前筛查与接种后监测；所有需要临床判断的事一律转人工审核。

**三个数字**：88 条自动化测试全绿 · 14 个 agent 工具 · 每次唤醒 15–20 次有序工具调用

**分工**：
- 原型与录屏：张诗瑶（已完成）
- 测试用例、评测报告（报告第 4 节评测部分）：田依凡 —— 从 `docs/rule_engine.md` + `tests/` 接手
- 报告第 1、2、3、5 节 + PPT：其余组员 —— 本文 §2–§5 是你们的原材料

---

## 1. 架构（报告第 2 节、PPT 架构页）

```
┌──────────────────────────────────────────────────────────┐
│  Streamlit 前端（自写，6 页）                               │
│  档案 · 接种时间线 · 待办与提醒 · 接种后打卡 · 人工审核 · 日志  │
└──────────────┬───────────────────────────┬───────────────┘
               │ 直接 import              │ HTTP /api/scheduled-tasks/{id}/trigger
               ▼                           ▼
┌────────────────────────┐   ┌──────────────────────────────┐
│ 规则引擎 rules/（确定性）│   │ DeerFlow gateway（agent 运行时）│
│ compute_schedule        │   │  · 线程状态 reuse_thread        │
│ detect_conflicts        │◄──│  · 定时任务 cron 每日 09:00 SGT  │
│ pre_vaccination_screen  │   │  · 14 个 vp_* 工具（config.yaml）│
│ post_vaccination_escalate│  │  · LLM: DeepSeek（可换）        │
└───────────┬────────────┘   └──────────────┬───────────────┘
            │                               │
            ▼                               ▼
┌──────────────────────────────────────────────────────────┐
│  data/db.json（唯一状态源）+ 审计日志                       │
│  知识：vaccinepath/data/ncis_2026_04.json（MOH 表逐格转录）  │
│        docs/sources/*.md（KKH / HealthHub 原文摘录，RAG 语料）│
└──────────────────────────────────────────────────────────┘
```

**分层原则（答辩时的核心叙事）**：
- **规则引擎**做所有判断：排程、查重、筛查、升级。纯 Python，不经 LLM，可单元测试。
- **LLM** 只做三件事：编排（决定先看谁、调哪个工具）、写给人看的文案（提醒、审核摘要）、引用官方原句。
- **前端和 agent 共用同一套工具函数**，家长/医生在页面上做的事和 agent 醒来做的事进同一份日志、同一个审核队列。

**关键设计决定与理由**（报告第 2 节要写）：

| 决定 | 理由 |
|---|---|
| 用 DeerFlow 而非自研 LangGraph | 定时任务、线程状态持久、工具挂载开箱即用；底层就是 LangGraph；不改源码，只通过 config.yaml 挂工具 |
| 关闭 DeerFlow 跨会话长期记忆 | agent 状态必须只来自 db.json，否则新线程会"记得"旧会话，破坏可审计性（实测发现后关闭） |
| 判断权收进工具层 | 实测 DeepSeek 会对"未回应的提醒该重发"自行推理跳过；改为工具直接返回「必须重发清单 / 必须升级清单」，LLM 照单执行 |
| 每孩每轮合并 1 审核单 + 1 提醒 | 第一版海外孩子 16 剂逾期跑出 16 任务 + 15 审核单 + 100 次调用；在工具层强制合并，不靠 prompt 劝 |
| RAG 只在 WARN/URGENT 时引用 | 语料（KKH/HealthHub）只讲接种后反应，不讲排程；第一版对逾期提醒硬引了一句，按"没有就不引"改掉 |
| 全系统统一 Asia/Singapore 时区 | UI 本机时间 vs agent UTC 时间曾导致晚间录入被判成"明天" |

---

## 2. 停止条件与目标（报告第 3 节，老师要求第一条）

**人类设定的目标（thread goal）**：每次唤醒的完成条件 = 对每个孩子：记录已校验、日程已计算、到期/逾期任务已存在、需人工的事项已进审核队列、提醒已发或已重发、日志已写。达成即停，不做"永远保持在轨"式的无限循环。

**明确的停止 / 边界条件**：
1. 任何筛查回答非"否" → 不判断适宜性，直接转人工审核，agent 不再对该任务做任何动作
2. 接种后打卡判 URGENT → 只做两件事：发"立即急诊"提醒、并入审核单；不给任何医疗建议
3. 提醒未回应 → 重发，最多 3 次；第 4 次升级为"家长多次未响应"转人工，不再重发
4. NCIS 表未规定的（补种间隔、逾期阈值以外的临床问题）→ 一律标"需医生确认"，不猜
5. 高危人群、HBsAg 阳性母亲变体 → 不排程，整条转人工评估
6. DeerFlow goal 评估最多续跑 8 轮；单次唤醒有完成条件，不会空转

**人机分工**：家长（录入、筛查、打卡、标记已接种）→ agent（巡检、建任务、提醒、转审）→ 医生（批准 / 修改后批准 / 退回、核实海外记录、给补种日期）。医生的每个决定写进日志 `human_decision` 列，agent 下次唤醒会引用。

---

## 3. 四类风险的对应设计（报告第 3 节，老师按此清单打分）

| 风险 | 我们的对应 | 证据 |
|---|---|---|
| **幻觉** | 所有临床判断在确定性规则引擎；LLM 只写文案；引用只允许来自 `docs/sources/` 检索到的原句，语料未覆盖则明确指示"不要引用" | `vaccinepath/guidance.py`；日志 `retrieve_guidance` 行；升级阈值全部对齐 KKH/HealthHub 官方页面（`docs/rule_engine.md` §2.4） |
| **提示注入** | 家长自由文本（打卡补充描述、筛查补充说明）只作为记录和分类输入，从不作为指令执行；工具入参出参 Pydantic 强类型 | `vaccinepath/models.py`；`vp_evaluate_checkin` 只读结构化字段 |
| **过度授权** | agent 只有 14 个 `vp_*` 工具，全部只读写本地 `db.json`；无联网、无外部 API、无删除权限；DeerFlow 的 web/文件工具组未启用给本 agent | `deer-flow/config.yaml` tools 段；`vaccinepath/tools.py` |
| **警报疲劳** | 每孩每轮最多 1 张审核单（合并所有理由）+ 1 条提醒（合并所有剂次）；审核单按严重程度排序 URGENT 置顶；重复筛查合并成一条；"没事就不打扰"（Kai 全程零动作） | 录屏第 2、6 步；`vp_request_review` / `vp_send_reminder` 合并逻辑 |

---

## 4. Demo 七条期望 → 片中证据（报告第 4 节、PPT demo 页）

| 老师要求 | 录屏时间点（母带） | 截图 | 说明 |
|---|---|---|---|
| User input（委托目标 / 启动工作流） | 0:00–0:40 | 01 | 档案页录入接种记录；侧栏"快进"= 手动触发同一条 cron 路径 |
| Agent workflow（可见规划、状态变化、工具调用） | 0:40–1:30、5:00–5:50 | 02、09 | 唤醒摘要 + 日志页每轮 15–20 次有序工具调用清单 |
| Grounding（从文档/数据库检索） | 2:40–3:00 | 04 | URGENT 红框下引用 HealthHub 原句「Has a fit (seizure or convulsion)」；日志 `retrieved: healthhub_fever_in_children.md` |
| Human checkpoint（批准/拒绝/编辑/升级） | 3:20–4:20 | 05、06 | 医生批准 Priya、勾核实 7 条海外记录、写补种日期 2026-10-05 |
| Safety response（安全停止/警告/升级/拒绝） | 2:10–3:00 | 03、04 | 筛查非"否"→转审不判断；41.5°C+抽搐→URGENT 红框"立即前往儿童急诊" |
| Audit log（输入/动作/来源/时间/输出/人工决定） | 5:20–5:52 | 08 | 31 条，四类 actor：rule_engine / agent / parent / clinician |
| Evaluation artefacts（测试、截图、结果表、错误例） | — | `docs/screenshots/` | 88 条 pytest；田依凡补用例；本文 §6 的错误例 |

**第二次唤醒（4:40–5:10，截图 07）是全片最关键的镜头**：agent 说出这期间发生的事——Mei 流感已完成、新增 URGENT 打卡、Priya 审核已批准并引用医生给的 2026-10-05、未回应提醒已重发第 2 次、没有重复建任务。这一屏同时证明"记忆/状态"和"目标驱动"。

---

## 5. 演示家庭与剧情（报告第 4 节、PPT 场景页）

Lim 家三个孩子，全部虚构：
- **Mei** 20 个月：本地出生、按时打到 15 个月，18 个月加强针（5-in-1）漏了，年度流感到期 → 展示逾期提醒 + 筛查 + 打卡 URGENT
- **Kai** 3 岁 3 个月：全部按时 → 展示"没事就不打扰"（agent 每轮对他零动作）
- **Priya** 2 岁 3 个月：2026-08 从印度迁入，接种卡大部分已打（含 9 个月的 MR，早于 NCIS 的 12 个月），缺 18 个月加强针，7 条记录待核实 → 展示海外记录对照 NCIS + 人工审核

知识来源（报告要引用）：
- MOH《National Childhood Immunisation Schedule》2026-04-01 版（`docs/ncis_moh_2026-04.pdf`，逐格转录为 `vaccinepath/data/ncis_2026_04.json`，已独立核对无误）
- KKH《Post Vaccination Advice》→ WARN 判据（`docs/sources/kkh_post_vaccination_advice.md`）
- HealthHub《Fever in Children》2026-06-17 复审 → URGENT 判据（`docs/sources/healthhub_fever_in_children.md`）

---

## 6. 开发中抓到的真问题（报告第 5 节"讨论/局限"的素材，也是评测报告的错误例）

这些都是实测发现、已修复并有测试锁住的，写进报告比"一切顺利"更有说服力：

1. **LLM 不执行工具给的事实**：DeepSeek 看到"任务未回应"后自行推理"时间窗口未到"跳过重发 → 判断权收进工具层
2. **框架默认记忆破坏可审计性**：DeerFlow 跨会话记忆让全新 agent 第一次就"与上次相比" → 关闭
3. **警报风暴**：极端案例 16 剂逾期 → 16 任务 + 15 审核单 + 100 次调用 → 工具层强制合并
4. **RAG 硬引**：语料不覆盖的话题也引了一句 → 改为不覆盖就不引
5. **单选默认值**：重构后筛查单选默认"是"，不动就提交=六项全"是" → 修复 + 测试锁默认"否"
6. **时区**：UI 本机 vs agent UTC → 统一 SGT
7. **前端重跑重复提交**：Streamlit 每次交互重跑整页，表单被反复提交 → 幂等保护

**已知局限（报告第 5 节）**：
- NCIS 未给出 DTaP/IPV/Hib/HepB/PCV13 的补种间隔，系统只判"缺哪几剂"，时间一律转医生 —— 这是有意为之的边界，不是没做完
- 接种后升级阈值来自 KKH/HealthHub 公开指引，非临床验证
- 全部 mock 数据，无真实 EHR/NEHR 接入；单家庭单线程，未做多租户
- 提醒是 mock 收件箱，未接真实短信/推送
- 前端为课程原型级，未做无障碍与移动端

---

## 7. 报告五节 → 从哪取材

| 报告节 | 内容 | 取材 |
|---|---|---|
| 1 问题与背景 | 新加坡儿童疫苗管理痛点、海外迁入家庭、家长负担 | `docs/proposal_v2.md` Q1–Q2 |
| 2 系统设计 | 架构、平台、模型、记忆、工具 | 本文 §1；`README.md` 架构表；`deer-flow/config.yaml` 的 tools 段 |
| 3 工作流·安全·治理 | 监督、升级流、边界、停止条件、审计 | 本文 §2、§3；`docs/rule_engine.md` §0 总原则 |
| 4 原型·demo·评测 | 截图、trace、测试用例与结果 | 本文 §4；`docs/screenshots/`；`tests/`（88 条）；田依凡的用例与评测 |
| 5 讨论与未来 | 反思、可扩展性、局限 | 本文 §6 |

**PPT 建议 8 页（共 10 分钟含答辩，讲 5 分钟 + 录屏 3 分钟 + 答辩 2 分钟）**：
1. 问题（1 页）
2. 为什么是 agent 不是 chatbot：自触发、有状态、跨等待（1 页）
3. 架构图（本文 §1 那张）（1 页）
4. 安全设计：判断在规则引擎、LLM 只写文案、四类风险对应表（1 页）
5. 停止条件与人机分工（1 页）
6. Demo（放剪好的录屏，或用 9 张截图走一遍）（1–2 页）
7. 评测：88 条测试 + 用例结果表 + 错误例（1 页，田依凡）
8. 局限与未来（1 页）

---

## 8. 仓库文件索引

```
CLAUDE.md                     开发指令与已验证的接口约定
README.md                     环境说明（组员从零跑通，已验证）
docs/proposal_v2.md           提案定稿
docs/rule_engine.md           规则引擎说明：§0 总原则、约定→代码对照、判定表、来源表
docs/demo_script.md           八步录屏剧本 + 七条验收要素对照
docs/ncis_moh_2026-04.pdf     MOH 官方表
docs/sources/                 KKH / HealthHub 原文摘录（RAG 语料）
docs/screenshots/             demo 截图 9 张（按录屏八步编号）
docs/HANDOFF_原型交接.md      本文件
vaccinepath/data/ncis_2026_04.json  NCIS 结构化表（已独立核对）
vaccinepath/rules/            规则引擎四函数
vaccinepath/models.py         Pydantic 入参出参
vaccinepath/tools.py          14 个 agent 工具
vaccinepath/guidance.py       官方指引检索（RAG 的 R）
vaccinepath/agent/prompts.py  thread goal 与唤醒 prompt
vaccinepath/ui/               Streamlit 六页
vaccinepath/data/mock_family.json  演示家庭
tests/                        88 条测试
scripts/                      setup / gateway / ui / agent_setup / agent_wake / simulate_parent / phase0_smoke / phase2_demo
```
