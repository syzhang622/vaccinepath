"""post_vaccination_escalate：接种后打卡 → CONTINUE / WARN / URGENT。

判据来源（原文摘录在 docs/sources/）：
- WARN  = KKH《Post Vaccination Advice》"When to consult a doctor" + 其发热定义
- URGENT = HealthHub《Fever in Children》"Go to the Children's Emergency immediately"（reviewed 2026-06-17）
判定顺序：URGENT → WARN → CONTINUE。阈值全部在 EscalationCriteria（models.py），LLM 不参与。
"""

from __future__ import annotations

from vaccinepath.models import (
    CheckIn,
    EscalationCriteria,
    EscalationInput,
    EscalationOutcome,
    EscalationResult,
    EscalationTrigger,
    TemperatureSite,
)
from vaccinepath.rules.dates import age_in_months

DISCLAIMER = "本结果由预设规则生成，不构成诊断，不替代医生判断。如对孩子状况有任何担心，请立即联系医生或前往急诊。"
SRC_KKH = "KKH Post Vaccination Advice (docs/sources/kkh_post_vaccination_advice.md)"
SRC_HH = "HealthHub Fever in Children, reviewed 2026-06-17 (docs/sources/healthhub_fever_in_children.md)"
CONTINUE_INTERVAL_HOURS = 24


def has_fever(ck: CheckIn, c: EscalationCriteria) -> bool:
    """KKH 发热定义：腋温 >37.6°C 或耳温 >37.8°C。"""
    if ck.temperature_c is None:
        return False
    limit = c.fever_axillary_gt_c if ck.temperature_site == TemperatureSite.axillary else c.fever_tympanic_gt_c
    return ck.temperature_c > limit


def post_vaccination_escalate(inp: EscalationInput) -> EscalationResult:
    c, ck, child = inp.criteria, inp.checkin, inp.child
    urgent: list[EscalationTrigger] = []
    warn: list[EscalationTrigger] = []

    # ---- URGENT（HealthHub）----
    for s in ck.symptoms:
        if s in c.urgent_symptoms:
            urgent.append(EscalationTrigger(rule="urgent_symptom", detail=s.value))
    if ck.temperature_c is not None:
        if ck.temperature_c > c.urgent_temperature_gt_c:
            urgent.append(EscalationTrigger(rule="urgent_temperature", detail=f"{ck.temperature_c}°C > {c.urgent_temperature_gt_c}°C"))
        age = age_in_months(child.date_of_birth, ck.submitted_at.date())
        if age < c.infant_age_months_lt and ck.temperature_c >= c.infant_fever_gte_c:
            urgent.append(EscalationTrigger(rule="infant_fever", detail=f"{age} 月龄（<{c.infant_age_months_lt} 月）体温 {ck.temperature_c}°C ≥ {c.infant_fever_gte_c}°C"))

    # ---- WARN（KKH）----
    fever = has_fever(ck, c)
    if fever and ck.fever_after_antipyretic:
        warn.append(EscalationTrigger(rule="warn_fever_not_reduced_by_medication", detail=f"服退烧药后仍 {ck.temperature_c}°C（{ck.temperature_site.value}）"))
    if fever and ck.fever_duration_hours is not None and ck.fever_duration_hours > c.warn_fever_duration_hours_gt:
        warn.append(EscalationTrigger(rule="warn_fever_duration", detail=f"发热已持续 {ck.fever_duration_hours}h > {c.warn_fever_duration_hours_gt}h"))
    for s in ck.symptoms:
        if s in c.warn_symptoms:
            warn.append(EscalationTrigger(rule="warn_symptom", detail=s.value))
    if ck.parent_very_worried:
        warn.append(EscalationTrigger(rule="warn_parent_concern", detail="家长担心或觉得孩子在变差（HealthHub: seek medical attention）"))

    if urgent:
        outcome, triggers, nxt, src = EscalationOutcome.URGENT, urgent + warn, None, SRC_HH
    elif warn:
        outcome, triggers, nxt, src = EscalationOutcome.WARN, warn, None, SRC_KKH + ("; " + SRC_HH if any(t.rule == "warn_parent_concern" for t in warn) else "")
    else:
        outcome, triggers, nxt, src = EscalationOutcome.CONTINUE, [], CONTINUE_INTERVAL_HOURS, SRC_KKH

    return EscalationResult(
        child_id=child.id,
        checkin_id=ck.id,
        outcome=outcome,
        triggers=triggers,
        next_checkin_in_hours=nxt,
        disclaimer=DISCLAIMER,
        source_ref=src,
    )
