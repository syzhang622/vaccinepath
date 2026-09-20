# 规则引擎（rule engine）说明

## §0 总原则：PDF 没写的一律不猜

规则引擎的唯一医学依据是 **MOH《National Childhood Immunisation Schedule》2026-04-01 版**（`docs/ncis_moh_2026-04.pdf`，结构化为 `vaccinepath/data/ncis_2026_04.json`）。

- PDF 明确写出的：进规则，输出里带 `source_ref`（页码）。
- PDF 没写的（各系列的补种最小间隔、逾期后的补种时点、高危人群的具体剂次与间隔、接种前是否适合接种、接种后症状是否需要就医）：**不猜、不从记忆补、不从其他来源补**。统一标「需医生确认」（`needs_clinician` / `clinician_confirmation_required` / `PROFESSIONAL_REVIEW_REQUIRED` / `review`），走人工审核队列。
- 所有对家长的输出附固定免责语：不诊断、不替代医生。
- 四个函数都是**纯函数**：Pydantic 入参 → Pydantic 出参，不调 LLM、不访问网络和数据库。LLM 只负责解释结果和生成文案，**不参与任何判定**。

与组长确认的约定（2026-09-20）：

| # | 约定 | 落点 |
|---|---|---|
| 1 | 除 MMR/VAR/HPV/INF 外 PDF 无 catch-up 间隔 → 只判缺哪几剂，补种时间标需医生确认 | `schedule.py` |
| 2 | 逾期 = 到期 + 30 天，不分年龄 | `dates.py: OVERDUE_GRACE_DAYS` |
| 3 | 年龄段列：段起点 = 到期，段终点+1 月龄 = 逾期线（10-11y → 满 10 岁到期，满 12 岁逾期） | `schedule.py: _window` |
| 4 | "N months" 按日历月（`relativedelta`） | `dates.py` |
| 5 | VAR catch-up 的 <13 / 13-17 岁按**第 1 剂时**的年龄判定 | `schedule.py: _catch_up_interval` |
| 6 | HPV2 女性默认走学校计划（Sec1/Sec2）；`attends_local_school=False` 走校外规则 | `schedule.py: _hpv` |
| 7 | 高危人群：档案只记 `high_risk_condition` 布尔值，为 True 时 PPSV23/PCV13/INF(5-17y) 整条标需医生评估，不排日期 | `schedule.py: _high_risk`, `_influenza` |
| 8 | HBsAg 阳性母亲的 HepB 变体：**不进 core，stretch** | JSON 里保留原文，引擎不用 |
| 9 | 流感 "annually or per season"：上次接种 +12 个月到期 | `schedule.py: _influenza` |

## §1 数据模型

全部在 `vaccinepath/models.py`。档案类：`Family`、`Child`、`VaccinationRecord`、`Task`、`CheckIn`、`AuditLogEntry`。

`VaccinationRecord.vaccines` 是**抗原列表**：一针 6-in-1 记为 `[DTaP, IPV, Hib, HepB]`，`product="6-in-1"`。这样海外的 Hexaxim/Infanrix hexa 只要家长/审核员填对抗原，就能对上 NCIS；对不上的走 `overseas_unverified`。

## §2 四个函数

### 2.1 `compute_schedule(ScheduleInput) -> ScheduleResult`

**入参** `ScheduleInput{child: Child, records: list[VaccinationRecord], as_of: date}`
**出参** `ScheduleResult{child_id, as_of, age_months, items: list[ScheduleItem], counts, requires_clinician_review}`

每个 `ScheduleItem`：`vaccine, dose_number, label, status, due_date, overdue_date, given_date, matched_record_id, product_hint, clinician_confirmation_required, reason, source_ref`。

`status` 的判定：

```
有记录对上该剂                        → completed
as_of < due                           → upcoming
due ≤ as_of ≤ overdue                 → due
as_of > overdue                       → overdue（clinician_confirmation_required=True，约定 1）
上一剂日期 ≥ 本剂推荐到期日 且 PDF 无该系列 catch-up 间隔 → needs_clinician（§0）
PDF 只说"视情况而定"（高危、5-17 岁流感）  → needs_clinician
年龄 > 17 岁                          → not_applicable
```

系列定义（`ncis.routine_series()`）：BCG(1)、HepB(3)、DTaP(5，第 5 剂为 Tdap B2)、IPV(5)、Hib(4)、PCV13(3)、MMR(2)、VAR(2)、HPV2(2，仅女性)。记录按日期升序依次对到第 1、2、3… 剂；同一天多条只算一次（重复交给 `detect_conflicts`）。

Catch-up（只有 PDF p3/p4 写了的）：

| 疫苗 | 规则 | 来源 |
|---|---|---|
| MMR | 2 剂至少间隔 4 周 → D2 到期 = max(15 月龄, D1+4 周) | p3 |
| VAR | D1 时 <13 岁：间隔 3 个月；13-17 岁：4-8 周（到期 D1+4 周，逾期 D1+8 周） | p3 |
| HPV2 校外 | 9-14 岁：0/6 月两剂；15-17 岁：0/1/6 月三剂；按第 1 剂（无则当前）年龄选方案 | p3 |
| INF | 6-59 月龄全体每年；6 月-8 岁首次接种 2 剂间隔 4 周；之后上次+12 月 | p1, p4 |

### 2.2 `detect_conflicts(ConflictInput) -> ConflictReport`

**入参** `ConflictInput{child, records, as_of}`
**出参** `ConflictReport{child_id, issues: list[ConflictIssue], has_blocking_errors, requires_clinician_review, clean}`

| code | severity | 判定 | 来源 |
|---|---|---|---|
| `before_birth` | error | 接种日 < 出生日 | 数据校验 |
| `future_date` | error | 接种日 > as_of | 数据校验 |
| `duplicate_same_day` | error | 同一抗原同一天 ≥2 条 | 数据校验 |
| `duplicate_dose_label` | warning | 同一抗原两条不同日期都标 D1 | p1 |
| `dose_order` | warning | 标签顺序与日期顺序矛盾（D2 早于 D1） | p1 |
| `extra_doses` | review | 抗原剂数 > NCIS 系列长度 | p1-2 |
| `earlier_than_schedule` | review | 第 k 剂早于 NCIS 第 k 剂推荐月龄 | p1 |
| `overseas_unverified` | review | 海外/家长自报记录且 `verified=False` | proposal §4 |
| `mmrv_dose1_under_48m` | review | MMRV 用作第 1 剂且 12-47 月龄 | p3 |
| `mmrv_over_max_age` | review | MMRV 超过 12 岁 | p3 |
| `hpv_not_indicated` | review | 男性有 HPV2 记录 | p1, p3 |

**明确不做**：两剂之间的最小间隔检查（PDF 没有）。`error` 阻断排程；`review` 进人工审核队列；`warning` 只提示。

### 2.3 `pre_vaccination_screen(ScreenInput) -> ScreenResult`

**入参** `ScreenInput{child_id, planned_vaccines, answers: ScreeningAnswers, answered_by, answered_at}`；`ScreeningAnswers` 六项三态（yes/no/unsure）：既往严重反应、已知过敏、当前患病、当前发热、免疫相关疾病、免疫抑制药物。
**出参** `ScreenResult{child_id, outcome, flags, incomplete, disclaimer, source_ref}`

判定只有一条：**六项全部 `no` → CLEAR；否则 → PROFESSIONAL_REVIEW_REQUIRED**，`unsure` 额外置 `incomplete=True`。本系统不判"能不能打"，这是 proposal §3 的硬约束。

### 2.4 `post_vaccination_escalate(EscalationInput) -> EscalationResult`

**入参** `EscalationInput{child, checkin: CheckIn, criteria: EscalationCriteria}`
**出参** `EscalationResult{child_id, checkin_id, outcome: CONTINUE|WARN|URGENT, triggers, next_checkin_in_hours, disclaimer, source_ref}`

> ⚠️ **阈值不是 MOH 来源。** NCIS 不涉及接种后监测。`EscalationCriteria` 的默认值是团队为原型自定的，放在 Pydantic 模型里以便审核、覆盖和测试固定；真实使用前须医生签字。

| 级别 | 默认触发条件 |
|---|---|
| **URGENT**（Urgent Assessment Required） | 呼吸困难 / 抽搐 / 无反应或极度嗜睡 / 面唇舌肿胀 / 全身荨麻疹；体温 ≥ 40.0°C；<3 月龄且 ≥ 38.0°C |
| **WARN**（→ Professional Review Required） | 体温 ≥ 38.5°C；发热 > 48h；持续哭闹 ≥ 3h；24h 呕吐 ≥ 3 次；注射部位大范围肿胀 / 进食减少 / 局部皮疹；症状加重；接种后 > 7 天仍有症状；家长非常担心 |
| **CONTINUE** | 以上都没有 → 24h 后再打卡 |

URGENT 优先于 WARN；URGENT 结果里也列出同时命中的 WARN 触发项，便于审核。

## §3 测试

`tests/` 下每个函数 ≥3 正例 ≥3 反例，另有 `test_ncis_data.py` 把第 1 页表格逐格钉死（改 JSON 会红）。

```bash
uv run pytest            # 48 passed
uv run pytest -k schedule -v
```

给队友的接手建议：先加 `docs/proposal_v2.md` 里三类家庭（多孩、跨机构、海外迁入）的端到端用例；`EscalationCriteria` 每个阈值加一对边界值测试。
