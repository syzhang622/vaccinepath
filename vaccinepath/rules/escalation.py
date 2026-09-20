"""post_vaccination_escalate：接种后打卡 → CONTINUE / WARN / URGENT。

阈值在 EscalationCriteria（models.py）里，**团队自定，非 MOH 来源**，须医生签字后才能用于真实场景。
判定顺序：URGENT 规则 → WARN 规则 → CONTINUE。LLM 不参与。
"""

from __future__ import annotations

from vaccinepath.models import EscalationInput, EscalationOutcome, EscalationResult, EscalationTrigger
from vaccinepath.rules.dates import age_in_months

DISCLAIMER = "本结果由预设规则生成，不构成诊断，不替代医生判断。如对孩子状况有任何担心，请立即联系医生或前往急诊。"
SOURCE = "EscalationCriteria（团队自定阈值，待医生审核）"
CONTINUE_INTERVAL_HOURS = 24


def post_vaccination_escalate(inp: EscalationInput) -> EscalationResult:
    c, ck, child = inp.criteria, inp.checkin, inp.child
    urgent: list[EscalationTrigger] = []
    warn: list[EscalationTrigger] = []

    # ---- URGENT ----
    for s in ck.symptoms:
        if s in c.urgent_symptoms:
            urgent.append(EscalationTrigger(rule="urgent_symptom", detail=s.value))
    if ck.temperature_c is not None:
        if ck.temperature_c >= c.urgent_temperature_c:
            urgent.append(EscalationTrigger(rule="urgent_temperature", detail=f"{ck.temperature_c}°C ≥ {c.urgent_temperature_c}°C"))
        age = age_in_months(child.date_of_birth, ck.submitted_at.date())
        if age < c.infant_fever_age_months_lt and ck.temperature_c >= c.infant_fever_temperature_c:
            urgent.append(EscalationTrigger(rule="infant_fever", detail=f"{age} 月龄婴儿体温 {ck.temperature_c}°C ≥ {c.infant_fever_temperature_c}°C"))

    # ---- WARN ----
    if ck.temperature_c is not None and ck.temperature_c >= c.warn_temperature_c:
        warn.append(EscalationTrigger(rule="warn_temperature", detail=f"{ck.temperature_c}°C ≥ {c.warn_temperature_c}°C"))
    if ck.fever_duration_hours is not None and ck.fever_duration_hours > c.warn_fever_duration_hours:
        warn.append(EscalationTrigger(rule="warn_fever_duration", detail=f"发热 {ck.fever_duration_hours}h > {c.warn_fever_duration_hours}h"))
    if ck.persistent_crying_hours is not None and ck.persistent_crying_hours >= c.warn_persistent_crying_hours:
        warn.append(EscalationTrigger(rule="warn_persistent_crying", detail=f"持续哭闹 {ck.persistent_crying_hours}h ≥ {c.warn_persistent_crying_hours}h"))
    if ck.vomiting_episodes_24h is not None and ck.vomiting_episodes_24h >= c.warn_vomiting_episodes_24h:
        warn.append(EscalationTrigger(rule="warn_vomiting", detail=f"24h 内呕吐 {ck.vomiting_episodes_24h} 次 ≥ {c.warn_vomiting_episodes_24h}"))
    for s in ck.symptoms:
        if s in c.warn_symptoms:
            warn.append(EscalationTrigger(rule="warn_symptom", detail=s.value))
    if ck.symptoms_worsening:
        warn.append(EscalationTrigger(rule="warn_worsening", detail="家长报告症状加重"))
    if ck.symptoms and ck.days_since_vaccination > c.warn_symptom_persist_days:
        warn.append(EscalationTrigger(rule="warn_persisting", detail=f"接种后 {ck.days_since_vaccination} 天仍有症状 > {c.warn_symptom_persist_days} 天"))
    if ck.parent_very_worried:
        warn.append(EscalationTrigger(rule="warn_parent_concern", detail="家长表示非常担心"))

    if urgent:
        outcome, triggers, nxt = EscalationOutcome.URGENT, urgent + warn, None
    elif warn:
        outcome, triggers, nxt = EscalationOutcome.WARN, warn, None
    else:
        outcome, triggers, nxt = EscalationOutcome.CONTINUE, [], CONTINUE_INTERVAL_HOURS

    return EscalationResult(
        child_id=child.id,
        checkin_id=ck.id,
        outcome=outcome,
        triggers=triggers,
        next_checkin_in_hours=nxt,
        disclaimer=DISCLAIMER,
        source_ref=SOURCE,
    )
