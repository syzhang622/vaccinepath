from vaccinepath.models import ScreenInput, ScreenOutcome, ScreeningAnswers, TriState, VaccineCode
from vaccinepath.rules import pre_vaccination_screen

from .conftest import NOW


def answers(**over) -> ScreeningAnswers:
    base = dict(previous_serious_reaction="no", known_allergy="no", current_illness="no", current_fever="no", immune_condition="no", immunosuppressive_medication="no")
    base.update(over)
    return ScreeningAnswers(**base)


def screen(a: ScreeningAnswers):
    return pre_vaccination_screen(ScreenInput(child_id="c1", planned_vaccines=[VaccineCode.MMR], answers=a, answered_at=NOW))


# ---------------- 正例 ----------------


def test_all_no_is_clear():
    r = screen(answers())
    assert r.outcome == ScreenOutcome.CLEAR and r.flags == [] and not r.incomplete
    assert "不构成诊断" in r.disclaimer


def test_clear_result_still_carries_disclaimer_and_source():
    r = screen(answers())
    assert r.disclaimer and r.source_ref


def test_details_text_does_not_change_outcome():
    r = screen(answers(allergy_details="none really"))
    assert r.outcome == ScreenOutcome.CLEAR


# ---------------- 反例 ----------------


def test_previous_serious_reaction_requires_review():
    r = screen(answers(previous_serious_reaction="yes", previous_reaction_details="anaphylaxis 2024"))
    assert r.outcome == ScreenOutcome.PROFESSIONAL_REVIEW_REQUIRED
    assert [f.field for f in r.flags] == ["previous_serious_reaction"]


def test_unsure_is_never_clear():
    r = screen(answers(immune_condition="unsure"))
    assert r.outcome == ScreenOutcome.PROFESSIONAL_REVIEW_REQUIRED and r.incomplete


def test_current_fever_requires_review():
    r = screen(answers(current_fever="yes"))
    assert r.outcome == ScreenOutcome.PROFESSIONAL_REVIEW_REQUIRED


def test_multiple_flags_all_listed():
    r = screen(answers(known_allergy="yes", immunosuppressive_medication="unsure", current_illness="yes"))
    assert {f.field for f in r.flags} == {"known_allergy", "immunosuppressive_medication", "current_illness"}
    assert all(f.answer in (TriState.yes, TriState.unsure) for f in r.flags)
