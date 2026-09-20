"""结构化表本身与 PDF 第 1 页逐格一致（人工核对过的固定事实）。"""

from vaccinepath import ncis
from vaccinepath.models import VaccineCode


def _cells(key: str) -> list[tuple[str, str]]:
    s = next(s for s in ncis.routine_series() if s.key == key)
    return [(d.label, d.column.id) for d in s.doses]


def test_page1_grid_matches_pdf():
    assert _cells("BCG") == [("D1", "birth")]
    assert _cells("HepB") == [("D1", "birth"), ("D2", "2m"), ("D3", "6m")]
    assert _cells("DTaP") == [("D1", "2m"), ("D2", "4m"), ("D3", "6m"), ("B1", "18m"), ("B2", "10-11y")]
    assert _cells("IPV") == [("D1", "2m"), ("D2", "4m"), ("D3", "6m"), ("B1", "18m"), ("B2", "10-11y")]
    assert _cells("Hib") == [("D1", "2m"), ("D2", "4m"), ("D3", "6m"), ("B1", "18m")]
    assert _cells("PCV13") == [("D1", "4m"), ("D2", "6m"), ("B1", "12m")]
    assert _cells("MMR") == [("D1", "12m"), ("D2", "15m")]
    assert _cells("VAR") == [("D1", "12m"), ("D2", "15m")]
    assert _cells("HPV2") == [("D1", "12-13y"), ("D2", "13-14y")]


def test_tdap_is_dose5_of_dtap_series():
    s = ncis.series_for(VaccineCode.Tdap)
    assert s is not None and s.key == "DTaP"
    assert s.doses[-1].vaccine == VaccineCode.Tdap and s.doses[-1].dose_number == 5


def test_catch_up_rules_present_only_where_pdf_gives_them():
    assert ncis.catch_up("MMR")["min_interval_weeks"] == 4
    assert ncis.catch_up("VAR")["by_age"][0]["interval"] == {"months": 3}
    for code in ("BCG", "HepB", "DTaP", "IPV", "Hib", "PCV13"):
        assert ncis.catch_up(code) is None


def test_combination_products():
    cp = ncis.combination_products()
    assert set(cp["6-in-1"]) == {VaccineCode.DTaP, VaccineCode.IPV, VaccineCode.Hib, VaccineCode.HepB}
    assert set(cp["5-in-1"]) == {VaccineCode.DTaP, VaccineCode.IPV, VaccineCode.Hib}
