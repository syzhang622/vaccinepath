"""detect_conflicts：接种记录的查重与冲突检测（含海外记录对照 NCIS）。

只做 NCIS 2026-04 明确支持的判定。**不做**两剂之间的最小间隔检查——PDF 没有给出，
按原则 §0 不猜；这类问题以 review 交医生。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from vaccinepath import ncis
from vaccinepath.models import (
    ConflictInput,
    ConflictIssue,
    ConflictReport,
    RecordSource,
    Severity,
    Sex,
    VaccinationRecord,
    VaccineCode,
)
from vaccinepath.rules.dates import add_months, age_in_months

P = ncis.SOURCE
_LABEL_ORDER = {"D1": 1, "D2": 2, "D3": 3, "B1": 4, "B2": 5}


def _issue(code: str, sev: Severity, recs: list[VaccinationRecord], msg: str, src: str, vaccine: VaccineCode | None = None) -> ConflictIssue:
    return ConflictIssue(code=code, severity=sev, vaccine=vaccine, record_ids=[r.id for r in recs], message=msg, source_ref=src)


def _date_sanity(records: list[VaccinationRecord], dob: date, as_of: date) -> list[ConflictIssue]:
    out = []
    for r in records:
        if r.date < dob:
            out.append(_issue("before_birth", Severity.error, [r], f"接种日期 {r.date} 早于出生日期 {dob}", "数据校验"))
        elif r.date > as_of:
            out.append(_issue("future_date", Severity.error, [r], f"接种日期 {r.date} 晚于当前日期 {as_of}", "数据校验"))
    return out


def _per_antigen(records: list[VaccinationRecord], child_dob: date) -> list[ConflictIssue]:
    out: list[ConflictIssue] = []
    by_antigen: dict[VaccineCode, list[VaccinationRecord]] = defaultdict(list)
    for r in records:
        for v in r.vaccines:
            by_antigen[v].append(r)

    for antigen, recs in by_antigen.items():
        recs = sorted(recs, key=lambda r: (r.date, r.id))
        series = ncis.series_for(antigen)

        # 同日重复
        by_date: dict[date, list[VaccinationRecord]] = defaultdict(list)
        for r in recs:
            by_date[r.date].append(r)
        for d, same in by_date.items():
            if len(same) > 1:
                out.append(_issue("duplicate_same_day", Severity.error, same, f"{antigen} 在 {d} 有 {len(same)} 条记录", "数据校验", antigen))

        # 剂次标签重复 / 顺序倒置
        labelled = [r for r in recs if r.dose_label]
        by_label: dict[str, list[VaccinationRecord]] = defaultdict(list)
        for r in labelled:
            by_label[r.dose_label.upper()].append(r)
        for lbl, same in by_label.items():
            if len(same) > 1 and len({r.date for r in same}) > 1:
                out.append(_issue("duplicate_dose_label", Severity.warning, same, f"{antigen} 有 {len(same)} 条记录都标为 {lbl}，日期不同", f"{P} p1 剂次标签", antigen))
        ordered = [(r, _LABEL_ORDER.get(r.dose_label.upper())) for r in labelled]
        ordered = [(r, k) for r, k in ordered if k is not None]
        for (r1, k1), (r2, k2) in zip(ordered, ordered[1:]):
            if k2 < k1:
                out.append(_issue("dose_order", Severity.warning, [r1, r2], f"{antigen}：{r2.dose_label}（{r2.date}）晚于 {r1.dose_label}（{r1.date}），标签与日期顺序不一致", f"{P} p1", antigen))

        if series is None:
            continue  # INF / PPSV23 无固定剂次

        # 多于系列剂次
        unique_dates = sorted({r.date for r in recs})
        series_len = len(series.doses)  # DTaP 系列含 Tdap B2，合计 5 剂
        if len(unique_dates) > series_len:
            out.append(_issue("extra_doses", Severity.review, recs, f"{antigen} 共 {len(unique_dates)} 剂，NCIS 系列为 {series_len} 剂", f"{P} p1-2", antigen))

        # 早于推荐月龄：按日期顺序把第 k 剂对上系列第 k 剂
        doses = series.doses
        seen: set[date] = set()
        k = 0
        for r in recs:
            if r.date in seen:
                continue
            seen.add(r.date)
            if k < len(doses):
                spec = doses[k]
                if r.date < add_months(child_dob, spec.column.min_months):
                    out.append(
                        _issue(
                            "earlier_than_schedule",
                            Severity.review,
                            [r],
                            f"{antigen} 第 {k + 1} 剂于 {r.date} 接种（{age_in_months(child_dob, r.date)} 月龄），早于 NCIS 推荐 {spec.column.label}",
                            f"{P} p1",
                            antigen,
                        )
                    )
            k += 1
    return out


def _mmrv(records: list[VaccinationRecord], dob: date) -> list[ConflictIssue]:
    rules = ncis.mmrv_rules()
    out = []
    mmr_dates = sorted({r.date for r in records if VaccineCode.MMR in r.vaccines})
    for r in records:
        if (r.product or "").upper() != "MMRV":
            continue
        age = age_in_months(dob, r.date)
        is_dose1 = bool(mmr_dates) and r.date == mmr_dates[0]
        if is_dose1 and 12 <= age <= 47:
            out.append(_issue("mmrv_dose1_under_48m", Severity.review, [r], f"MMRV 用作第 1 剂（{age} 月龄）：12-47 月龄热性惊厥风险较高，需确认已有临床建议与同意", f"{P} p3"))
        if age > rules["mmrv_max_age_years"] * 12 + 11:
            out.append(_issue("mmrv_over_max_age", Severity.review, [r], f"MMRV 于 {age} 月龄接种，超过最大适用年龄 {rules['mmrv_max_age_years']} 岁", f"{P} p3"))
    return out


def _hpv(records: list[VaccinationRecord], sex: Sex) -> list[ConflictIssue]:
    if sex == Sex.female:
        return []
    recs = [r for r in records if VaccineCode.HPV2 in r.vaccines]
    return [_issue("hpv_not_indicated", Severity.review, recs, "NCIS 仅对女性推荐 HPV2；男性记录需医生确认", f"{P} p1, p3")] if recs else []


def _overseas(records: list[VaccinationRecord]) -> list[ConflictIssue]:
    return [
        _issue("overseas_unverified", Severity.review, [r], f"{'海外' if r.source == RecordSource.overseas else '家长自报'}记录（{r.country or '未填国家'}，{r.product or '/'.join(r.vaccines)}）未核实，对照 NCIS 前需人工确认抗原与剂次", "proposal §4 核心范围 2")
        for r in records
        if r.source in (RecordSource.overseas, RecordSource.parent_reported) and not r.verified
    ]


def detect_conflicts(inp: ConflictInput) -> ConflictReport:
    child = inp.child
    records = [r for r in inp.records if r.child_id == child.id]
    issues = _date_sanity(records, child.date_of_birth, inp.as_of)
    valid = [r for r in records if child.date_of_birth <= r.date <= inp.as_of]
    issues += _per_antigen(valid, child.date_of_birth)
    issues += _mmrv(valid, child.date_of_birth)
    issues += _hpv(valid, child.sex)
    issues += _overseas(records)
    issues.sort(key=lambda i: ({"error": 0, "warning": 1, "review": 2}[i.severity.value], i.code))
    has_err = any(i.severity == Severity.error for i in issues)
    needs_review = any(i.severity == Severity.review for i in issues)
    return ConflictReport(child_id=child.id, issues=issues, has_blocking_errors=has_err, requires_clinician_review=needs_review, clean=not issues)
