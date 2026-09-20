from datetime import date, datetime

from vaccinepath.models import CheckIn, Child, EscalationCriteria, EscalationInput, EscalationOutcome, Sex, Symptom
from vaccinepath.rules import post_vaccination_escalate

from .conftest import NOW


def checkin(**kw) -> CheckIn:
    base = dict(id="ck1", child_id="c1", record_id="r1", submitted_at=NOW, days_since_vaccination=1)
    base.update(kw)
    return CheckIn(**base)


def run(child: Child, ck: CheckIn, criteria: EscalationCriteria | None = None):
    return post_vaccination_escalate(EscalationInput(child=child, checkin=ck, criteria=criteria or EscalationCriteria()))


# ---------------- 正例（CONTINUE） ----------------


def test_mild_expected_reaction_continues(child):
    r = run(child, checkin(temperature_c=37.8, symptoms=[Symptom.injection_site_mild, Symptom.irritability]))
    assert r.outcome == EscalationOutcome.CONTINUE and r.triggers == [] and r.next_checkin_in_hours == 24


def test_no_symptoms_continues(child):
    r = run(child, checkin())
    assert r.outcome == EscalationOutcome.CONTINUE


def test_low_fever_short_duration_continues(child):
    r = run(child, checkin(temperature_c=38.2, fever_duration_hours=12))
    assert r.outcome == EscalationOutcome.CONTINUE


# ---------------- WARN ----------------


def test_fever_over_38_5_warns(child):
    r = run(child, checkin(temperature_c=38.6))
    assert r.outcome == EscalationOutcome.WARN and r.triggers[0].rule == "warn_temperature" and r.next_checkin_in_hours is None


def test_fever_longer_than_48h_warns(child):
    r = run(child, checkin(temperature_c=38.0, fever_duration_hours=49))
    assert r.outcome == EscalationOutcome.WARN


def test_persisting_symptoms_after_7_days_warns(child):
    r = run(child, checkin(days_since_vaccination=8, symptoms=[Symptom.irritability]))
    assert r.outcome == EscalationOutcome.WARN and r.triggers[0].rule == "warn_persisting"


def test_parent_very_worried_warns(child):
    assert run(child, checkin(parent_very_worried=True)).outcome == EscalationOutcome.WARN


# ---------------- URGENT ----------------


def test_breathing_difficulty_is_urgent(child):
    r = run(child, checkin(symptoms=[Symptom.difficulty_breathing]))
    assert r.outcome == EscalationOutcome.URGENT and r.triggers[0].rule == "urgent_symptom"


def test_temperature_40_is_urgent_and_also_lists_warn_triggers(child):
    r = run(child, checkin(temperature_c=40.1))
    assert r.outcome == EscalationOutcome.URGENT
    assert {t.rule for t in r.triggers} == {"urgent_temperature", "warn_temperature"}


def test_infant_under_3_months_fever_is_urgent():
    infant = Child(id="i", family_id="f", name="I", date_of_birth=date(2026, 8, 1), sex=Sex.male)
    r = run(infant, checkin(child_id="i", temperature_c=38.1, submitted_at=datetime(2026, 9, 20, 9, 0)))
    assert r.outcome == EscalationOutcome.URGENT and r.triggers[0].rule == "infant_fever"


def test_same_temperature_not_urgent_for_older_child(child):
    assert run(child, checkin(temperature_c=38.1)).outcome == EscalationOutcome.CONTINUE


def test_criteria_are_overridable(child):
    strict = EscalationCriteria(warn_temperature_c=38.0)
    assert run(child, checkin(temperature_c=38.1), strict).outcome == EscalationOutcome.WARN
