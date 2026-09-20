"""compute_schedule：对照 NCIS 2026-04 计算某个孩子每一剂的到期/逾期/状态。

原则（docs/rule_engine.md §0）：PDF 没写的一律不猜。凡 PDF 未给出补种间隔的系列，
一旦排程被已接种记录"追过"，该剂标 needs_clinician；一旦逾期，标 overdue 且
clinician_confirmation_required=True（只判缺哪剂，补种时间由医生定）。
"""

from __future__ import annotations

from datetime import date, timedelta

from vaccinepath import ncis
from vaccinepath.models import (
    Child,
    ScheduleInput,
    ScheduleItem,
    ScheduleResult,
    ScheduleStatus,
    Sex,
    VaccinationRecord,
    VaccineCode,
)
from vaccinepath.ncis import DoseSpec, SeriesSpec
from vaccinepath.rules.dates import add_months, age_in_months, overdue_after

P = ncis.SOURCE


def _records_for(antigens: set[VaccineCode], records: list[VaccinationRecord]) -> list[VaccinationRecord]:
    """该系列的记录，按日期升序；同一天多条只取第一条（重复由 detect_conflicts 报）。"""
    seen: set[date] = set()
    out: list[VaccinationRecord] = []
    for r in sorted((r for r in records if antigens & set(r.vaccines)), key=lambda r: (r.date, r.id)):
        if r.date in seen:
            continue
        seen.add(r.date)
        out.append(r)
    return out


def _status(as_of: date, due: date, overdue: date) -> ScheduleStatus:
    if as_of < due:
        return ScheduleStatus.upcoming
    if as_of <= overdue:
        return ScheduleStatus.due
    return ScheduleStatus.overdue


def _window(dob: date, spec: DoseSpec) -> tuple[date, date]:
    """到期日 = 列的起点月龄；逾期线：点列 = 到期+30 天，段列 = 段终点的下一个月龄（如 10-11y → 满 12 岁）。"""
    due = add_months(dob, spec.column.min_months)
    if spec.column.is_range:
        return due, add_months(dob, spec.column.max_months + 1)
    return due, overdue_after(due)


def _completed(spec_vaccine: VaccineCode, dose_number: int, label: str, rec: VaccinationRecord, hint: str | None) -> ScheduleItem:
    return ScheduleItem(
        vaccine=spec_vaccine,
        dose_number=dose_number,
        label=label,
        status=ScheduleStatus.completed,
        given_date=rec.date,
        matched_record_id=rec.id,
        product_hint=hint,
        reason=f"记录 {rec.id} 于 {rec.date} 接种",
        source_ref=f"{P} p1",
    )


# ---------------------------------------------------------------------------
# 固定剂次系列
# ---------------------------------------------------------------------------


def _catch_up_interval(series: SeriesSpec, prev: VaccinationRecord, dob: date) -> tuple[timedelta | None, timedelta | None, str] | None:
    """PDF 第 3 页给出的 catch-up 间隔 → (最小间隔, 最大间隔或 None, 依据)。没有则 None。"""
    if series.key == "MMR":
        return timedelta(weeks=4), None, f"{P} p3 Catch-up MMR：2 剂至少间隔 4 周"
    if series.key == "VAR":
        if age_in_months(dob, prev.date) < 13 * 12:
            return add_months(prev.date, 3) - prev.date, None, f"{P} p3 Catch-up Varicella <13 岁：2 剂间隔 3 个月"
        return timedelta(weeks=4), timedelta(weeks=8), f"{P} p3 Catch-up Varicella 13-17 岁：2 剂间隔 4-8 周"
    return None


def _routine_series(series: SeriesSpec, child: Child, records: list[VaccinationRecord], as_of: date) -> list[ScheduleItem]:
    dob = child.date_of_birth
    recs = _records_for(series.antigens, records)
    items: list[ScheduleItem] = []
    for i, spec in enumerate(series.doses):
        prev = recs[i - 1] if 0 < i <= len(recs) else None
        if i < len(recs):
            items.append(_completed(spec.vaccine, spec.dose_number, spec.label, recs[i], spec.product))
            continue

        due, overdue = _window(dob, spec)
        reason = f"NCIS 推荐月龄 {spec.column.label}"
        src = f"{P} p1"

        if prev is not None:
            cu = _catch_up_interval(series, prev, dob)
            if cu is not None:
                min_iv, max_iv, cu_src = cu
                earliest = prev.date + min_iv
                if earliest > due:
                    due = earliest
                    overdue = prev.date + max_iv if max_iv else overdue_after(due)
                    reason = f"上一剂 {prev.date} 较晚，按 catch-up 间隔顺延"
                    src = cu_src
            elif prev.date >= due:
                # 排程已被追过，而 PDF 没有这个系列的补种间隔 → 不猜
                items.append(
                    ScheduleItem(
                        vaccine=spec.vaccine,
                        dose_number=spec.dose_number,
                        label=spec.label,
                        status=ScheduleStatus.needs_clinician,
                        product_hint=spec.product,
                        reason=f"上一剂于 {prev.date} 接种，已晚于本剂推荐月龄 {spec.column.label}；NCIS 未给出 {series.key} 补种间隔",
                        source_ref="原则 §0（PDF 未写不猜）",
                    )
                )
                continue

        status = _status(as_of, due, overdue)
        items.append(
            ScheduleItem(
                vaccine=spec.vaccine,
                dose_number=spec.dose_number,
                label=spec.label,
                status=status,
                due_date=due,
                overdue_date=overdue,
                product_hint=spec.product,
                clinician_confirmation_required=status == ScheduleStatus.overdue,
                reason=reason + ("；已逾期，补种时间需医生确认" if status == ScheduleStatus.overdue else ""),
                source_ref=src,
            )
        )
    return items


# ---------------------------------------------------------------------------
# HPV2（仅女性；校内 vs 校外）
# ---------------------------------------------------------------------------


def _hpv(child: Child, records: list[VaccinationRecord], as_of: date) -> list[ScheduleItem]:
    if child.sex != Sex.female:
        return []
    series = ncis.series_for(VaccineCode.HPV2)
    assert series is not None
    if child.attends_local_school:
        return _routine_series(series, child, records, as_of)

    # 校外规则（p3）：按第 1 剂时的年龄（无记录则按当前年龄）选 2 剂或 3 剂方案
    dob = child.date_of_birth
    recs = _records_for(series.antigens, records)
    ref_age = age_in_months(dob, recs[0].date if recs else as_of)
    plan = None
    for rule in ncis.hpv_outside_school():
        lo, hi = rule["age_months_range"]
        if lo <= ref_age <= hi:
            plan = rule
            break
    if plan is None:
        return [
            ScheduleItem(
                vaccine=VaccineCode.HPV2,
                dose_number=1,
                label="D1",
                status=ScheduleStatus.needs_clinician if ref_age < 9 * 12 else ScheduleStatus.not_applicable,
                reason=f"校外 HPV2 规则仅覆盖 9-17 岁，当前参考年龄 {ref_age} 个月",
                source_ref=f"{P} p3",
            )
        ]
    offsets = plan["schedule_months"]
    lo_months = plan["age_months_range"][0]
    d1 = recs[0].date if recs else max(add_months(dob, lo_months), as_of)
    items: list[ScheduleItem] = []
    for n, off in enumerate(offsets, start=1):
        if n - 1 < len(recs):
            items.append(_completed(VaccineCode.HPV2, n, f"D{n}", recs[n - 1], None))
            continue
        due = add_months(d1, off) if recs else (add_months(dob, lo_months) if n == 1 else add_months(d1, off))
        overdue = add_months(dob, plan["age_months_range"][1] + 1) if n == 1 else overdue_after(due)
        status = _status(as_of, due, overdue)
        items.append(
            ScheduleItem(
                vaccine=VaccineCode.HPV2,
                dose_number=n,
                label=f"D{n}",
                status=status,
                due_date=due,
                overdue_date=overdue,
                clinician_confirmation_required=status == ScheduleStatus.overdue,
                reason=f"校外 HPV2 {plan['series']}（0/{'/'.join(str(o) for o in offsets[1:])} 月），参考年龄 {ref_age} 个月",
                source_ref=f"{P} p3",
            )
        )
    return items


# ---------------------------------------------------------------------------
# 流感（每年；上次 +12 个月）
# ---------------------------------------------------------------------------


def _influenza(child: Child, records: list[VaccinationRecord], as_of: date) -> list[ScheduleItem]:
    inf = ncis.influenza()
    dob = child.date_of_birth
    age = age_in_months(dob, as_of)
    recs = _records_for({VaccineCode.INF}, records)
    items = [_completed(VaccineCode.INF, n, "annual", r, None) for n, r in enumerate(recs, start=1)]
    n = len(recs) + 1

    lo, hi = inf["all_children_age_months"]
    hr_lo, hr_hi = inf["high_risk_age_months"]
    if lo <= age <= hi:
        first = inf["first_time_series"]
        if not recs:
            due = add_months(dob, lo)
            reason = "6-59 月龄所有儿童每年接种；首次"
        elif len(recs) == 1 and first["age_months_range"][0] <= age_in_months(dob, recs[0].date) <= first["age_months_range"][1]:
            due = recs[0].date + timedelta(weeks=first["interval_weeks"])
            reason = f"首次接种 2 剂系列，第 2 剂距第 1 剂 {first['interval_weeks']} 周"
        else:
            due = add_months(recs[-1].date, 12)
            reason = "每年一剂：上次接种 +12 个月（与组长约定，SG 无固定流感季）"
        overdue = overdue_after(due)
        status = _status(as_of, due, overdue)
        items.append(
            ScheduleItem(
                vaccine=VaccineCode.INF,
                dose_number=n,
                label="annual",
                status=status,
                due_date=due,
                overdue_date=overdue,
                reason=reason,
                source_ref=f"{P} p1, p4",
            )
        )
    elif hr_lo <= age <= hr_hi and child.high_risk_condition:
        items.append(
            ScheduleItem(
                vaccine=VaccineCode.INF,
                dose_number=n,
                label="annual",
                status=ScheduleStatus.needs_clinician,
                reason="5-17 岁仅高危人群推荐，是否属于高危及剂次由医生评估",
                source_ref=f"{P} p4",
            )
        )
    return items


# ---------------------------------------------------------------------------
# 高危：PPSV23 / PCV13 补种
# ---------------------------------------------------------------------------


def _high_risk(child: Child, as_of: date) -> list[ScheduleItem]:
    if not child.high_risk_condition:
        return []
    age = age_in_months(child.date_of_birth, as_of)
    items = []
    for code in ("PPSV23", "PCV13"):
        hr = ncis.high_risk(code)
        lo, hi = hr["age_range_months"]
        if lo <= age <= hi:
            items.append(
                ScheduleItem(
                    vaccine=VaccineCode(code),
                    dose_number=0,
                    label="high-risk",
                    status=ScheduleStatus.needs_clinician,
                    reason=f"档案标记高危状况；{code} 的剂次与间隔 NCIS 写明视具体情况而定，需医生评估",
                    source_ref=f"{P} p2-3",
                )
            )
    return items


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def compute_schedule(inp: ScheduleInput) -> ScheduleResult:
    child, records, as_of = inp.child, [r for r in inp.records if r.child_id == inp.child.id], inp.as_of
    if as_of < child.date_of_birth:
        raise ValueError("as_of 早于出生日期")
    age = age_in_months(child.date_of_birth, as_of)

    items: list[ScheduleItem] = []
    if age > ncis.max_age_months():
        items.append(
            ScheduleItem(
                vaccine=VaccineCode.BCG,
                dose_number=0,
                label="-",
                status=ScheduleStatus.not_applicable,
                reason=f"年龄 {age} 个月，超出 NCIS 覆盖范围（0-17 岁）",
                source_ref=f"{P} p1",
            )
        )
    else:
        for series in ncis.routine_series():
            if series.key == "HPV2":
                continue
            items += _routine_series(series, child, records, as_of)
        items += _hpv(child, records, as_of)
        items += _influenza(child, records, as_of)
        items += _high_risk(child, as_of)

    counts: dict[str, int] = {}
    for it in items:
        counts[it.status.value] = counts.get(it.status.value, 0) + 1
    return ScheduleResult(
        child_id=child.id,
        as_of=as_of,
        age_months=age,
        items=items,
        counts=counts,
        requires_clinician_review=any(it.status == ScheduleStatus.needs_clinician or it.clinician_confirmation_required for it in items),
    )
