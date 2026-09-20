"""判据来源：WARN = KKH Post Vaccination Advice；URGENT = HealthHub Fever in Children（2026-06-17）。"""

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from vaccinepath.models import CheckIn, Child, EscalationCriteria, EscalationInput, EscalationOutcome, Sex, Symptom, TemperatureSite
from vaccinepath.rules import post_vaccination_escalate
from vaccinepath.rules.escalation import has_fever

from .conftest import NOW

AX, EAR = TemperatureSite.axillary, TemperatureSite.tympanic


def checkin(**kw) -> CheckIn:
    base = dict(id="ck1", child_id="c1", record_id="r1", submitted_at=NOW, days_since_vaccination=1)
    base.update(kw)
    return CheckIn(**base)


def run(child: Child, ck: CheckIn, criteria: EscalationCriteria | None = None):
    return post_vaccination_escalate(EscalationInput(child=child, checkin=ck, criteria=criteria or EscalationCriteria()))


def rules(r):
    return {t.rule for t in r.triggers}


# ---------------- 发热定义（KKH：腋温 >37.6 / 耳温 >37.8） ----------------


def test_fever_definition_by_site():
    c = EscalationCriteria()
    assert not has_fever(checkin(temperature_c=37.6, temperature_site=AX), c)
    assert has_fever(checkin(temperature_c=37.7, temperature_site=AX), c)
    assert not has_fever(checkin(temperature_c=37.8, temperature_site=EAR), c)
    assert has_fever(checkin(temperature_c=37.9, temperature_site=EAR), c)


def test_temperature_requires_site():
    with pytest.raises(ValidationError):
        checkin(temperature_c=38.0)


# ---------------- 正例（CONTINUE） ----------------


def test_expected_mild_reaction_continues(child):
    r = run(child, checkin(temperature_c=38.3, temperature_site=EAR, fever_duration_hours=12, fever_after_antipyretic=False, symptoms=[Symptom.injection_site_redness_swelling_pain, Symptom.irritability]))
    assert r.outcome == EscalationOutcome.CONTINUE and r.triggers == [] and r.next_checkin_in_hours == 24
    assert "KKH" in r.source_ref


def test_no_symptoms_continues(child):
    assert run(child, checkin()).outcome == EscalationOutcome.CONTINUE


def test_fever_exactly_2_days_not_more_continues(child):
    assert run(child, checkin(temperature_c=38.0, temperature_site=AX, fever_duration_hours=48)).outcome == EscalationOutcome.CONTINUE


def test_antipyretic_not_reducing_but_no_fever_by_definition_continues(child):
    # 腋温 37.5 不算发热，"退烧药无效"不成立
    assert run(child, checkin(temperature_c=37.5, temperature_site=AX, fever_after_antipyretic=True)).outcome == EscalationOutcome.CONTINUE


# ---------------- WARN（KKH "When to consult a doctor"） ----------------


def test_fever_not_reduced_by_medication_warns(child):
    r = run(child, checkin(temperature_c=38.2, temperature_site=AX, fever_after_antipyretic=True))
    assert r.outcome == EscalationOutcome.WARN and rules(r) == {"warn_fever_not_reduced_by_medication"} and r.next_checkin_in_hours is None


def test_fever_more_than_2_days_warns(child):
    r = run(child, checkin(temperature_c=38.0, temperature_site=EAR, fever_duration_hours=49))
    assert r.outcome == EscalationOutcome.WARN and rules(r) == {"warn_fever_duration"}


def test_less_active_warns(child):
    assert rules(run(child, checkin(symptoms=[Symptom.less_active_than_usual]))) == {"warn_symptom"}


def test_persistent_but_consolable_crying_warns(child):
    r = run(child, checkin(symptoms=[Symptom.crying_persistent_consolable]))
    assert r.outcome == EscalationOutcome.WARN


def test_parent_concern_warns_with_healthhub_source(child):
    r = run(child, checkin(parent_very_worried=True))
    assert r.outcome == EscalationOutcome.WARN and "HealthHub" in r.source_ref


# ---------------- URGENT（HealthHub "Go to the Children's Emergency immediately"） ----------------


@pytest.mark.parametrize("symptom", sorted(EscalationCriteria().urgent_symptoms, key=str))
def test_each_healthhub_emergency_symptom_is_urgent(child, symptom):
    r = run(child, checkin(symptoms=[symptom]))
    assert r.outcome == EscalationOutcome.URGENT and r.triggers[0].detail == symptom.value and "HealthHub" in r.source_ref


def test_inconsolable_crying_is_urgent_consolable_is_warn(child):
    assert run(child, checkin(symptoms=[Symptom.crying_inconsolable])).outcome == EscalationOutcome.URGENT
    assert run(child, checkin(symptoms=[Symptom.crying_persistent_consolable])).outcome == EscalationOutcome.WARN


def test_temperature_over_41_is_urgent_but_41_exactly_is_not(child):
    assert run(child, checkin(temperature_c=41.1, temperature_site=EAR)).outcome == EscalationOutcome.URGENT
    assert run(child, checkin(temperature_c=41.0, temperature_site=EAR)).outcome == EscalationOutcome.CONTINUE


def test_infant_under_3_months_38_is_urgent():
    infant = Child(id="i", family_id="f", name="I", date_of_birth=date(2026, 8, 1), sex=Sex.male)
    r = run(infant, checkin(child_id="i", temperature_c=38.0, temperature_site=AX, submitted_at=datetime(2026, 9, 20, 9, 0)))
    assert r.outcome == EscalationOutcome.URGENT and rules(r) == {"infant_fever"}


def test_same_38_not_urgent_for_older_child(child):
    assert run(child, checkin(temperature_c=38.0, temperature_site=AX)).outcome == EscalationOutcome.CONTINUE


def test_urgent_also_lists_warn_triggers(child):
    r = run(child, checkin(temperature_c=41.5, temperature_site=EAR, fever_after_antipyretic=True, symptoms=[Symptom.seizure]))
    assert r.outcome == EscalationOutcome.URGENT
    assert rules(r) == {"urgent_symptom", "urgent_temperature", "warn_fever_not_reduced_by_medication"}


def test_criteria_overridable(child):
    strict = EscalationCriteria(warn_fever_duration_hours_gt=24)
    assert run(child, checkin(temperature_c=38.0, temperature_site=AX, fever_duration_hours=30), strict).outcome == EscalationOutcome.WARN
