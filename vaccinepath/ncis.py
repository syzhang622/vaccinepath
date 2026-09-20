"""NCIS 2026-04 结构化表的加载与类型化访问。数据本身在 data/ncis_2026_04.json，此处不含任何医学规则。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from vaccinepath.models import VaccineCode

DATA_PATH = Path(__file__).parent / "data" / "ncis_2026_04.json"
SOURCE = "NCIS 2026-04"


class AgeColumn(BaseModel):
    id: str
    label: str
    min_months: int
    max_months: int
    school_level: str | None = None

    @property
    def is_range(self) -> bool:
        return self.max_months > self.min_months


class DoseSpec(BaseModel):
    vaccine: VaccineCode
    label: str
    dose_number: int
    column: AgeColumn
    product: str | None = None


class SeriesSpec(BaseModel):
    """一个抗原系列。DTaP 系列包含 Tdap 的 B2（p2 把它们写成 Dose 1-5）。"""

    key: str
    antigens: set[VaccineCode]
    doses: list[DoseSpec]


@lru_cache(maxsize=1)
def raw() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text())


@lru_cache(maxsize=1)
def columns() -> dict[str, AgeColumn]:
    return {c["id"]: AgeColumn(**c) for c in raw()["age_columns"]}


def _vaccine(code: str) -> dict[str, Any]:
    for v in raw()["vaccines"]:
        if v["code"] == code:
            return v
    raise KeyError(code)


def _doses(code: str) -> list[DoseSpec]:
    return [
        DoseSpec(vaccine=VaccineCode(code), label=d["label"], dose_number=d["dose_number"], column=columns()[d["column"]], product=d.get("product"))
        for d in _vaccine(code)["doses"]
    ]


@lru_cache(maxsize=1)
def routine_series() -> list[SeriesSpec]:
    """表上"所有儿童"固定剂次的系列（不含 INF/PPSV23/高危）。HPV2 仅女性，由排程逻辑处理。"""
    return [
        SeriesSpec(key="BCG", antigens={VaccineCode.BCG}, doses=_doses("BCG")),
        SeriesSpec(key="HepB", antigens={VaccineCode.HepB}, doses=_doses("HepB")),
        SeriesSpec(key="DTaP", antigens={VaccineCode.DTaP, VaccineCode.Tdap}, doses=_doses("DTaP") + _doses("Tdap")),
        SeriesSpec(key="IPV", antigens={VaccineCode.IPV}, doses=_doses("IPV")),
        SeriesSpec(key="Hib", antigens={VaccineCode.Hib}, doses=_doses("Hib")),
        SeriesSpec(key="PCV13", antigens={VaccineCode.PCV13}, doses=_doses("PCV13")),
        SeriesSpec(key="MMR", antigens={VaccineCode.MMR}, doses=_doses("MMR")),
        SeriesSpec(key="VAR", antigens={VaccineCode.VAR}, doses=_doses("VAR")),
        SeriesSpec(key="HPV2", antigens={VaccineCode.HPV2}, doses=_doses("HPV2")),
    ]


def series_for(code: VaccineCode) -> SeriesSpec | None:
    for s in routine_series():
        if code in s.antigens:
            return s
    return None


def catch_up(code: str) -> dict[str, Any] | None:
    return _vaccine(code).get("catch_up")


def hpv_outside_school() -> list[dict[str, Any]]:
    return _vaccine("HPV2")["outside_school_programme"]["by_age"]


def influenza() -> dict[str, Any]:
    return _vaccine("INF")["recurring"]


def high_risk(code: str) -> dict[str, Any] | None:
    return _vaccine(code).get("high_risk")


def mmrv_rules() -> dict[str, Any]:
    return raw()["mmrv_rules"]


def combination_products() -> dict[str, list[VaccineCode]]:
    return {k: [VaccineCode(c) for c in v["components"]] for k, v in raw()["combination_products"].items()}


def max_age_months() -> int:
    return max(c.max_months for c in columns().values())
