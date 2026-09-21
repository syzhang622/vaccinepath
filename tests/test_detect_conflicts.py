from datetime import date

from vaccinepath.models import ConflictInput, RecordSource, Severity, VaccineCode
from vaccinepath.rules import detect_conflicts

from .conftest import SIX_IN_ONE, on_schedule_records_to_6m, rec

AS_OF = date(2026, 9, 20)


def codes(report):
    return sorted(i.code for i in report.issues)


# ---------------- 正例（干净数据不报） ----------------


def test_on_schedule_records_are_clean(child):
    r = detect_conflicts(ConflictInput(child=child, records=on_schedule_records_to_6m(), as_of=AS_OF))
    assert r.clean and not r.has_blocking_errors and not r.requires_clinician_review


def test_verified_overseas_record_not_flagged(child):
    recs = [rec("o1", date(2025, 3, 15), SIX_IN_ONE, product="Hexaxim", source=RecordSource.overseas, country="MY", verified=True)]
    assert detect_conflicts(ConflictInput(child=child, records=recs, as_of=AS_OF)).clean


def test_mmrv_as_dose2_at_15_months_is_fine(child):
    recs = [
        rec("m1", date(2026, 1, 15), [VaccineCode.MMR, VaccineCode.VAR]),
        rec("m2", date(2026, 4, 15), [VaccineCode.MMR, VaccineCode.VAR], product="MMRV"),
    ]
    assert detect_conflicts(ConflictInput(child=child, records=recs, as_of=AS_OF)).clean


# ---------------- 反例（必须报） ----------------


def test_before_birth_and_future_are_blocking_errors(child):
    recs = [rec("a", date(2024, 12, 1), [VaccineCode.BCG]), rec("b", date(2027, 1, 1), [VaccineCode.BCG])]
    r = detect_conflicts(ConflictInput(child=child, records=recs, as_of=AS_OF))
    assert codes(r) == ["before_birth", "future_date"] and r.has_blocking_errors


def test_same_day_duplicate(child):
    recs = [rec("a", date(2025, 3, 15), SIX_IN_ONE), rec("b", date(2025, 3, 15), SIX_IN_ONE)]
    r = detect_conflicts(ConflictInput(child=child, records=recs, as_of=AS_OF))
    dup = [i for i in r.issues if i.code == "duplicate_same_day"]
    assert len(dup) == 4 and all(i.severity == Severity.error for i in dup)  # 4 个抗原各报一次
    assert set(dup[0].record_ids) == {"a", "b"}


def test_extra_doses_beyond_series(child):
    recs = [rec(f"p{i}", date(2025, 4 + i, 15), [VaccineCode.PCV13]) for i in range(4)]  # PCV13 系列只有 3 剂
    r = detect_conflicts(ConflictInput(child=child, records=recs, as_of=AS_OF))
    assert "extra_doses" in codes(r) and r.requires_clinician_review


def test_earlier_than_schedule(child):
    r = detect_conflicts(ConflictInput(child=child, records=[rec("m", date(2025, 10, 15), [VaccineCode.MMR])], as_of=AS_OF))  # 9 月龄打 MMR
    issue = next(i for i in r.issues if i.code == "earlier_than_schedule")
    assert issue.severity == Severity.review and "9 月龄" in issue.message


def test_unverified_overseas_record_needs_review(child):
    recs = [rec("o1", date(2025, 3, 15), SIX_IN_ONE, product="Hexaxim", source=RecordSource.overseas, country="MY")]
    r = detect_conflicts(ConflictInput(child=child, records=recs, as_of=AS_OF))
    assert codes(r) == ["overseas_unverified"] and r.requires_clinician_review and not r.has_blocking_errors


def test_dose_label_order_and_duplicate_label(child):
    recs = [
        rec("a", date(2025, 3, 15), [VaccineCode.HepB], label="D2"),
        rec("b", date(2025, 5, 15), [VaccineCode.HepB], label="D1"),
        rec("c", date(2025, 7, 15), [VaccineCode.HepB], label="D1"),
    ]
    r = detect_conflicts(ConflictInput(child=child, records=recs, as_of=AS_OF))
    assert {"dose_order", "duplicate_dose_label"} <= set(codes(r))


def test_mmrv_dose1_under_48m_flagged(child):
    r = detect_conflicts(ConflictInput(child=child, records=[rec("m", date(2026, 1, 15), [VaccineCode.MMR, VaccineCode.VAR], product="MMRV")], as_of=AS_OF))
    assert codes(r) == ["mmrv_dose1_under_48m"]


def test_hpv_on_boy_flagged(boy):
    r = detect_conflicts(ConflictInput(child=boy, records=[rec("h", date(2026, 9, 1), [VaccineCode.HPV2], child_id="c2")], as_of=AS_OF))
    assert "hpv_not_indicated" in codes(r) and r.requires_clinician_review


def test_parent_reported_record_is_warning_not_review(child):
    recs = [rec("p1", date(2026, 9, 1), [VaccineCode.INF], source=RecordSource.parent_reported)]
    r = detect_conflicts(ConflictInput(child=child, records=recs, as_of=AS_OF))
    assert codes(r) == ["overseas_unverified"] and r.issues[0].severity == Severity.warning and not r.requires_clinician_review
