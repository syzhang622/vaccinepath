from datetime import date, datetime

import pytest

from vaccinepath.models import Child, RecordSource, Sex, VaccinationRecord, VaccineCode

SIX_IN_ONE = [VaccineCode.DTaP, VaccineCode.IPV, VaccineCode.Hib, VaccineCode.HepB]
FIVE_IN_ONE = [VaccineCode.DTaP, VaccineCode.IPV, VaccineCode.Hib]


@pytest.fixture
def child() -> Child:
    """2025-01-15 出生的女孩。"""
    return Child(id="c1", family_id="f1", name="Mei", date_of_birth=date(2025, 1, 15), sex=Sex.female)


@pytest.fixture
def boy() -> Child:
    return Child(id="c2", family_id="f1", name="Kai", date_of_birth=date(2025, 1, 15), sex=Sex.male)


def rec(id: str, d: date, vaccines: list[VaccineCode], *, product: str | None = None, label: str | None = None, source: RecordSource = RecordSource.polyclinic, child_id: str = "c1", **kw) -> VaccinationRecord:
    return VaccinationRecord(id=id, child_id=child_id, date=d, vaccines=vaccines, product=product, dose_label=label, source=source, **kw)


def on_schedule_records_to_6m() -> list[VaccinationRecord]:
    """按 NCIS 准时打到 6 个月的记录（出生 2025-01-15）。"""
    return [
        rec("r0", date(2025, 1, 15), [VaccineCode.BCG], label="D1"),
        rec("r1", date(2025, 1, 15), [VaccineCode.HepB], product="monovalent HepB", label="D1"),
        rec("r2", date(2025, 3, 15), SIX_IN_ONE, product="6-in-1"),
        rec("r3", date(2025, 5, 15), FIVE_IN_ONE + [VaccineCode.PCV13], product="5-in-1 + PCV13"),
        rec("r4", date(2025, 7, 15), SIX_IN_ONE + [VaccineCode.PCV13], product="6-in-1 + PCV13"),
    ]


NOW = datetime(2026, 9, 20, 10, 0)
