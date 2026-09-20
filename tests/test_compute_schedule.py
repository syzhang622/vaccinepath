from datetime import date

import pytest

from vaccinepath.models import Child, ScheduleInput, ScheduleStatus, Sex, VaccineCode
from vaccinepath.rules import compute_schedule

from .conftest import SIX_IN_ONE, on_schedule_records_to_6m, rec


def item(res, vaccine: VaccineCode, dose: int):
    return next(i for i in res.items if i.vaccine == vaccine and i.dose_number == dose)


# ---------------- 正例 ----------------


def test_newborn_all_upcoming_except_birth_doses(child):
    res = compute_schedule(ScheduleInput(child=child, records=[], as_of=date(2025, 1, 15)))
    assert res.age_months == 0
    assert item(res, VaccineCode.BCG, 1).status == ScheduleStatus.due
    assert item(res, VaccineCode.HepB, 1).status == ScheduleStatus.due
    d1 = item(res, VaccineCode.DTaP, 1)
    assert d1.status == ScheduleStatus.upcoming and d1.due_date == date(2025, 3, 15) and d1.overdue_date == date(2025, 4, 14)
    assert not res.requires_clinician_review


def test_on_schedule_child_at_7_months_has_completed_and_upcoming(child):
    res = compute_schedule(ScheduleInput(child=child, records=on_schedule_records_to_6m(), as_of=date(2025, 8, 20)))
    assert item(res, VaccineCode.DTaP, 3).status == ScheduleStatus.completed
    assert item(res, VaccineCode.PCV13, 2).matched_record_id == "r4"
    b1 = item(res, VaccineCode.PCV13, 3)
    assert b1.status == ScheduleStatus.upcoming and b1.due_date == date(2026, 1, 15)
    mmr = item(res, VaccineCode.MMR, 1)
    assert mmr.due_date == date(2026, 1, 15) and mmr.product_hint == "separate MMR"
    assert not res.requires_clinician_review


def test_overdue_uses_30_day_grace_and_requires_clinician_confirmation(child):
    # 2 月龄针（2025-03-15）到 2025-04-14 前算 due，之后 overdue
    res_due = compute_schedule(ScheduleInput(child=child, records=[], as_of=date(2025, 4, 14)))
    assert item(res_due, VaccineCode.DTaP, 1).status == ScheduleStatus.due
    res_over = compute_schedule(ScheduleInput(child=child, records=[], as_of=date(2025, 4, 15)))
    d1 = item(res_over, VaccineCode.DTaP, 1)
    assert d1.status == ScheduleStatus.overdue and d1.clinician_confirmation_required
    assert res_over.requires_clinician_review


def test_mmr_catch_up_interval_4_weeks_after_late_dose1(child):
    # D1 拖到 17 个月才打，D2 原定 15 个月已过 → 按 p3 顺延到 D1+4 周
    late = rec("m1", date(2026, 6, 20), [VaccineCode.MMR])
    res = compute_schedule(ScheduleInput(child=child, records=[late], as_of=date(2026, 6, 25)))
    d2 = item(res, VaccineCode.MMR, 2)
    assert d2.status == ScheduleStatus.upcoming and d2.due_date == date(2026, 7, 18)
    assert "p3" in d2.source_ref


def test_varicella_catch_up_3_months_under_13(child):
    late = rec("v1", date(2026, 6, 20), [VaccineCode.VAR])
    res = compute_schedule(ScheduleInput(child=child, records=[late], as_of=date(2026, 6, 25)))
    assert item(res, VaccineCode.VAR, 2).due_date == date(2026, 9, 20)


def test_range_column_overdue_at_end_of_range():
    girl = Child(id="g", family_id="f", name="G", date_of_birth=date(2014, 3, 1), sex=Sex.female)
    res = compute_schedule(ScheduleInput(child=girl, records=[], as_of=date(2026, 9, 20)))
    hpv1 = item(res, VaccineCode.HPV2, 1)  # 12-13y → 满 12 岁到期，满 14 岁逾期
    assert hpv1.due_date == date(2026, 3, 1) and hpv1.overdue_date == date(2028, 3, 1)
    assert hpv1.status == ScheduleStatus.due


def test_influenza_first_time_two_doses_then_annual(child):
    res = compute_schedule(ScheduleInput(child=child, records=[], as_of=date(2025, 8, 1)))
    inf = item(res, VaccineCode.INF, 1)
    assert inf.due_date == date(2025, 7, 15) and inf.status == ScheduleStatus.due
    first = rec("i1", date(2025, 8, 1), [VaccineCode.INF])
    res2 = compute_schedule(ScheduleInput(child=child, records=[first], as_of=date(2025, 8, 5)))
    assert item(res2, VaccineCode.INF, 2).due_date == date(2025, 8, 29)  # +4 周
    second = rec("i2", date(2025, 8, 29), [VaccineCode.INF])
    res3 = compute_schedule(ScheduleInput(child=child, records=[first, second], as_of=date(2025, 9, 1)))
    assert item(res3, VaccineCode.INF, 3).due_date == date(2026, 8, 29)  # 上次 +12 月


# ---------------- 反例 / 边界 ----------------


def test_no_catch_up_rule_in_pdf_means_needs_clinician(child):
    # 6-in-1 第 1 剂拖到 5 个月才打（晚于 D2 的 4 月龄推荐）→ D2 无法按 PDF 排 → needs_clinician
    late = rec("l1", date(2025, 6, 20), SIX_IN_ONE, product="6-in-1")
    res = compute_schedule(ScheduleInput(child=child, records=[late], as_of=date(2025, 7, 1)))
    for v in (VaccineCode.DTaP, VaccineCode.IPV, VaccineCode.Hib):
        d2 = item(res, v, 2)
        assert d2.status == ScheduleStatus.needs_clinician and d2.due_date is None
        assert "原则" in d2.source_ref
    assert res.requires_clinician_review


def test_boy_gets_no_hpv(boy):
    res = compute_schedule(ScheduleInput(child=boy, records=[], as_of=date(2026, 9, 20)))
    assert all(i.vaccine != VaccineCode.HPV2 for i in res.items)


def test_over_17_not_applicable():
    adult = Child(id="a", family_id="f", name="A", date_of_birth=date(2008, 1, 1), sex=Sex.male)
    res = compute_schedule(ScheduleInput(child=adult, records=[], as_of=date(2026, 9, 20)))
    assert len(res.items) == 1 and res.items[0].status == ScheduleStatus.not_applicable


def test_as_of_before_birth_rejected(child):
    with pytest.raises(ValueError):
        compute_schedule(ScheduleInput(child=child, records=[], as_of=date(2024, 12, 31)))


def test_high_risk_child_routes_to_clinician_not_dates():
    hr = Child(id="h", family_id="f", name="H", date_of_birth=date(2020, 1, 1), sex=Sex.male, high_risk_condition=True)
    res = compute_schedule(ScheduleInput(child=hr, records=[], as_of=date(2026, 9, 20)))
    ppsv = next(i for i in res.items if i.vaccine == VaccineCode.PPSV23)
    inf = next(i for i in res.items if i.vaccine == VaccineCode.INF)
    assert ppsv.status == inf.status == ScheduleStatus.needs_clinician and ppsv.due_date is None


def test_influenza_not_listed_for_healthy_6_year_old():
    kid = Child(id="k", family_id="f", name="K", date_of_birth=date(2020, 1, 1), sex=Sex.male)
    res = compute_schedule(ScheduleInput(child=kid, records=[], as_of=date(2026, 9, 20)))
    assert all(i.vaccine != VaccineCode.INF for i in res.items)


def test_records_of_other_child_ignored(child):
    other = rec("x", date(2025, 1, 15), [VaccineCode.BCG], child_id="someone-else")
    res = compute_schedule(ScheduleInput(child=child, records=[other], as_of=date(2025, 1, 20)))
    assert item(res, VaccineCode.BCG, 1).status == ScheduleStatus.due


def test_hpv_outside_school_before_age_9_is_upcoming():
    girl = Child(id="p", family_id="f", name="P", date_of_birth=date(2024, 6, 1), sex=Sex.female, attends_local_school=False)
    res = compute_schedule(ScheduleInput(child=girl, records=[], as_of=date(2026, 9, 20)))
    d1 = item(res, VaccineCode.HPV2, 1)
    assert d1.status == ScheduleStatus.upcoming and d1.due_date == date(2033, 6, 1) and d1.overdue_date == date(2039, 6, 1)


def test_hpv_outside_school_15_to_17_three_doses():
    girl = Child(id="p", family_id="f", name="P", date_of_birth=date(2011, 1, 1), sex=Sex.female, attends_local_school=False)
    res = compute_schedule(ScheduleInput(child=girl, records=[], as_of=date(2026, 9, 20)))  # 15 岁 8 个月
    hpv = [i for i in res.items if i.vaccine == VaccineCode.HPV2]
    assert [i.dose_number for i in hpv] == [1, 2, 3] and "3-dose" in hpv[0].reason
