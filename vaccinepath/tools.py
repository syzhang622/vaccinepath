"""挂到 DeerFlow 的工具（LangChain @tool）。每个工具：读 store → 调规则引擎/写 store → 记日志 → 返回 JSON 字符串。

硬性护栏：这里没有任何判定逻辑，判定全部在 vaccinepath.rules；LLM 只能通过这些工具读结果、写任务、发提醒、转人工。
config.yaml 挂法见 vaccinepath/deerflow_tools.yaml。
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from langchain_core.tools import tool

from vaccinepath.models import (
    Actor,
    CheckIn,
    ConflictInput,
    EscalationInput,
    EscalationOutcome,
    ScheduleInput,
    ScheduleStatus,
    ScreeningAnswers,
    ScreenInput,
    ScreenOutcome,
    Task,
    TaskStatus,
    TaskType,
    VaccineCode,
)
from vaccinepath.rules import compute_schedule, detect_conflicts, post_vaccination_escalate, pre_vaccination_screen
from vaccinepath.store import Store, new_id, now, today as _today

DISCLAIMER = "本信息不构成诊断，不替代医生建议；如有疑问请咨询医生。"


def _store() -> Store:
    return Store()


def _default(o: Any) -> Any:
    from pydantic import BaseModel

    if isinstance(o, BaseModel):
        return o.model_dump(mode="json")
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if isinstance(o, set):
        return sorted(o)
    return str(o)


def _j(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=_default)


# ---------------------------------------------------------------------------
# 读
# ---------------------------------------------------------------------------


@tool("vp_list_children", parse_docstring=True)
def vp_list_children() -> str:
    """List every family and child under management, with their age and open task count. Call this first on every wake-up.

    Returns:
        JSON: {today, families: [{id, guardian_name, children: [{id, name, age_months, sex, attends_local_school, high_risk_condition, open_tasks}]}]}
    """
    s = _store()
    s.set_agent_state(current_run_started_at=now().isoformat())
    out = []
    for f in s.families():
        kids = []
        for c in s.children(f.id):
            from vaccinepath.rules.dates import age_in_months

            open_tasks = [t for t in s.tasks(c.id) if t.status not in (TaskStatus.done, TaskStatus.cancelled)]
            kids.append({"id": c.id, "name": c.name, "age_months": age_in_months(c.date_of_birth, _today()), "sex": c.sex, "attends_local_school": c.attends_local_school, "high_risk_condition": c.high_risk_condition, "open_tasks": len(open_tasks)})
        out.append({"id": f.id, "guardian_name": f.guardian_name, "children": kids})
    return _j({"today": _today(), "families": out})


@tool("vp_get_child", parse_docstring=True)
def vp_get_child(child_id: str) -> str:
    """Get one child's profile, vaccination records, tasks, and post-vaccination check-ins that have not been evaluated yet.

    Args:
        child_id: The child's id from vp_list_children.
    """
    s = _store()
    c = s.child(child_id)
    pending = [ck for ck in s.read()["checkins"].values() if ck["child_id"] == child_id and not ck.get("evaluation")]
    return _j({"child": c, "records": s.records(child_id), "tasks": s.tasks(child_id), "pending_checkins": pending})


@tool("vp_check_schedule", parse_docstring=True)
def vp_check_schedule(child_id: str) -> str:
    """Run the deterministic NCIS rule engine for a child and return every dose that is NOT completed (due / overdue / upcoming / needs_clinician). The engine, not you, decides status and dates.

    Args:
        child_id: The child's id.
    """
    s = _store()
    c = s.child(child_id)
    res = compute_schedule(ScheduleInput(child=c, records=s.records(child_id), as_of=_today()))
    items = [i for i in res.items if i.status != ScheduleStatus.completed]
    s.log(Actor.rule_engine, "compute_schedule", f"child={child_id} as_of={res.as_of}", _j(res.counts), child_id=child_id, source="NCIS 2026-04")
    return _j({"child_id": child_id, "as_of": res.as_of, "age_months": res.age_months, "counts": res.counts, "requires_clinician_review": res.requires_clinician_review, "items": items})


@tool("vp_check_records", parse_docstring=True)
def vp_check_records(child_id: str) -> str:
    """Run the deterministic record validation (duplicates, conflicts, unverified overseas records) for a child. Issues with severity 'review' must be routed to professional review via vp_request_review; 'error' blocks scheduling.

    Args:
        child_id: The child's id.
    """
    s = _store()
    c = s.child(child_id)
    rep = detect_conflicts(ConflictInput(child=c, records=s.records(child_id), as_of=_today()))
    s.log(Actor.rule_engine, "detect_conflicts", f"child={child_id}", f"{len(rep.issues)} issues, blocking={rep.has_blocking_errors}", child_id=child_id, source="NCIS 2026-04")
    return _j(rep)


@tool("vp_list_tasks", parse_docstring=True)
def vp_list_tasks(status: str = "") -> str:
    """List tasks across all children, plus two ready-made decisions computed by the rules (do NOT re-derive them): 'repeat_reminders_required' = per child, the awaiting_parent tasks whose last reminder has gone unanswered past the repeat window and are under max_reminders — send ONE repeat vp_send_reminder per child covering them; 'escalations_required' = per child, tasks unanswered at max_reminders — include them in that child's vp_request_review as related_task_ids with reason '家长多次提醒未响应'.

    Args:
        status: Optional filter: open | awaiting_parent | awaiting_review | done | cancelled. Empty = all except done/cancelled.
    """
    s = _store()
    cfg = s.settings()
    repeat_h, max_r = cfg.get("reminder_repeat_hours", 24), cfg.get("max_reminders", 3)
    tasks = s.tasks(status=TaskStatus(status) if status else None)
    if not status:
        tasks = [t for t in tasks if t.status not in (TaskStatus.done, TaskStatus.cancelled)]
    run_started = datetime.fromisoformat(s.agent_state().get("current_run_started_at", now().isoformat()))
    out, repeat, escalate = [], {}, {}
    for t in tasks:
        d = t.model_dump(mode="json")
        # 未响应 = 任务还没完成、提醒是在本轮唤醒开始之前发的（不是本轮刚发的）、且已超过重复窗口。与审核状态无关。
        d["unanswered"] = bool(t.status not in (TaskStatus.done, TaskStatus.cancelled) and t.last_reminded_at and t.last_reminded_at < run_started and now() - t.last_reminded_at >= timedelta(hours=repeat_h))
        if d["unanswered"]:
            (repeat if t.reminder_count < max_r else escalate).setdefault(t.child_id, []).append(t.id)
        out.append(d)
    return _j({"max_reminders": max_r, "reminder_repeat_hours": repeat_h, "repeat_reminders_required": repeat, "escalations_required": escalate, "tasks": out})


# ---------------------------------------------------------------------------
# 写
# ---------------------------------------------------------------------------


@tool("vp_create_task", parse_docstring=True)
def vp_create_task(child_id: str, type: str, title: str, due_date: str = "", vaccine: str = "", dose_number: int = 0, notes: str = "") -> str:
    """Create a task for a child. Idempotent: if an open task of the same type/vaccine/dose already exists, it is returned instead of creating a duplicate.

    Args:
        child_id: The child's id.
        type: vaccination_due | reminder | post_vaccination_checkin | professional_review | clarification.
        title: Short human-readable title (Chinese or English, for the parent).
        due_date: ISO date (YYYY-MM-DD) from the schedule item, or empty.
        vaccine: Vaccine code from the schedule item (e.g. DTaP), or empty.
        dose_number: Dose number from the schedule item, or 0.
        notes: Optional notes.
    """
    s = _store()
    s.child(child_id)
    ttype = TaskType(type)
    vcode = VaccineCode(vaccine) if vaccine else None
    dn = dose_number or None
    existing = s.find_open_task(child_id, ttype, vcode.value if vcode else None, dn)
    if existing:
        return _j({"created": False, "task": existing})
    t = Task(id=new_id("task"), child_id=child_id, type=ttype, title=title, due_date=date.fromisoformat(due_date) if due_date else None, vaccine=vcode, dose_number=dn, created_at=now(), updated_at=now(), notes=notes or None)
    s.put("tasks", t)
    s.log(Actor.agent, "create_task", f"{ttype} {vcode or ''} d{dn or ''}", f"{t.id}: {title}", child_id=child_id)
    return _j({"created": True, "task": t})


@tool("vp_create_tasks", parse_docstring=True)
def vp_create_tasks(child_id: str, items: list[dict]) -> str:
    """Create several vaccination_due tasks for one child in one call (one per schedule item). Idempotent per vaccine+dose.

    Args:
        child_id: The child's id.
        items: List of {"vaccine": "DTaP", "dose_number": 4, "label": "B1", "due_date": "YYYY-MM-DD", "status": "overdue"} taken from vp_check_schedule items.
    """
    s = _store()
    s.child(child_id)
    created, existing = [], []
    for it in items:
        vcode = VaccineCode(it["vaccine"])
        dn = int(it.get("dose_number") or 0) or None
        old = s.find_open_task(child_id, TaskType.vaccination_due, vcode.value, dn)
        if old:
            existing.append(old.id)
            continue
        status_word = {"overdue": "逾期补种", "due": "应接种"}.get(it.get("status", ""), "待接种")
        title = f"{s.child(child_id).name} {vcode.value} {it.get('label', '')} {status_word}".strip()
        t = Task(id=new_id("task"), child_id=child_id, type=TaskType.vaccination_due, title=title, due_date=date.fromisoformat(it["due_date"]) if it.get("due_date") else None, vaccine=vcode, dose_number=dn, created_at=now(), updated_at=now())
        s.put("tasks", t)
        created.append(t)
    s.log(Actor.agent, "create_tasks", f"child={child_id} n={len(items)}", f"created={[t.id for t in created]} existing={existing}", child_id=child_id)
    return _j({"created": created, "existing": existing})


@tool("vp_update_task", parse_docstring=True)
def vp_update_task(task_id: str, status: str, notes: str = "") -> str:
    """Change a task's status (open | awaiting_parent | awaiting_review | done | cancelled) and optionally append notes.

    Args:
        task_id: The task id.
        status: New status.
        notes: Optional note to append.
    """
    s = _store()
    old = Task(**s.get("tasks", task_id))  # type: ignore[arg-type]
    fields: dict[str, Any] = {"status": TaskStatus(status)}
    if notes:
        fields["notes"] = ((old.notes + "\n") if old.notes else "") + notes
    t = s.update_task(task_id, **fields)
    s.log(Actor.agent, "update_task", f"{task_id} {old.status}->{status}", notes or "", child_id=t.child_id)
    return _j({"task": t})


@tool("vp_send_reminder", parse_docstring=True)
def vp_send_reminder(child_id: str, task_ids: list[str], message: str) -> str:
    """Send ONE (mock) notification to the parent covering all listed tasks of a child, and mark those tasks awaiting_parent. Send at most one reminder per child per wake-up. The fixed disclaimer is appended automatically if missing. Tasks already at max_reminders are skipped and returned in 'exhausted' — route those via vp_request_review.

    Args:
        child_id: The child's id.
        task_ids: The vaccination_due tasks this reminder covers.
        message: The reminder text for the parent: which child, which doses, by when / that a doctor must confirm the catch-up date.
    """
    s = _store()
    max_r = s.settings().get("max_reminders", 3)
    covered, exhausted = [], []
    for tid in task_ids:
        raw = s.get("tasks", tid)
        if raw is None or raw["child_id"] != child_id:
            continue
        t = Task(**raw)
        (exhausted if t.reminder_count >= max_r else covered).append(t)
    if not covered:
        return _j({"sent": False, "reason": "没有可提醒的任务", "exhausted": [t.id for t in exhausted]})
    if DISCLAIMER not in message:
        message = f"{message}\n\n{DISCLAIMER}"
    n = s.notify(child_id, None, "mock_push", message)
    for t in covered:
        # 只有"待处理"变"等家长回应"；"等人工审核"保持不变（审核与提醒是两条独立的线）
        s.update_task(t.id, status=TaskStatus.awaiting_parent if t.status == TaskStatus.open else t.status, reminder_count=t.reminder_count + 1, last_reminded_at=now())
    s.log(Actor.agent, "send_reminder", f"child={child_id} tasks={[t.id for t in covered]}", message, child_id=child_id)
    return _j({"sent": True, "notification_id": n["id"], "covered": [t.id for t in covered], "exhausted": [t.id for t in exhausted]})


@tool("vp_request_review", parse_docstring=True)
def vp_request_review(child_id: str, reasons: list[str], related_task_ids: list[str] = []) -> str:
    """Route a child to the human (healthcare professional) review queue with ALL reasons for this wake-up in one call. One open review task per child: if one already exists, new reasons are appended and duplicates ignored. Use for: schedule items with needs_clinician or clinician_confirmation_required, record issues with severity 'review'/'error', screening outcome PROFESSIONAL_REVIEW_REQUIRED, check-in outcome WARN/URGENT, parents unresponsive after max reminders.

    Args:
        child_id: The child's id.
        reasons: One string per reason, each citing the rule-engine reason and source_ref.
        related_task_ids: Optional tasks this review is about; they are moved to awaiting_review.
    """
    s = _store()
    s.child(child_id)
    reasons = [r.strip() for r in reasons if r and r.strip()]
    existing = next((t for t in s.tasks(child_id, TaskStatus.awaiting_review) if t.type == TaskType.professional_review), None)
    if existing:
        have = set((existing.notes or "").split("\n"))
        new = [r for r in reasons if r not in have]
        t = s.update_task(existing.id, notes="\n".join([*(existing.notes.split("\n") if existing.notes else []), *new])) if new else existing
        created = False
    else:
        t = Task(id=new_id("task"), child_id=child_id, type=TaskType.professional_review, title=f"人工审核：{s.child(child_id).name}（{len(reasons)} 项）", status=TaskStatus.awaiting_review, created_at=now(), updated_at=now(), notes="\n".join(reasons))
        s.put("tasks", t)
        new, created = reasons, True
    for tid in related_task_ids:
        if s.get("tasks", tid):
            s.update_task(tid, status=TaskStatus.awaiting_review)
    s.log(Actor.agent, "request_review", f"child={child_id} +{len(new)} reasons", t.id, child_id=child_id)
    return _j({"created": created, "review_task_id": t.id, "new_reasons": len(new), "total_reasons": len((t.notes or "").split("\n"))})


@tool("vp_evaluate_checkin", parse_docstring=True)
def vp_evaluate_checkin(checkin_id: str) -> str:
    """Run the deterministic post-vaccination escalation rules on a parent check-in and persist the outcome (CONTINUE / WARN / URGENT). You must NOT decide escalation yourself; only explain the result to the parent and, for WARN/URGENT, call vp_request_review.

    Args:
        checkin_id: The check-in id from vp_get_child pending_checkins.
    """
    s = _store()
    raw = s.get("checkins", checkin_id)
    if raw is None:
        return _j({"error": f"checkin {checkin_id} not found"})
    ck = CheckIn(**{k: v for k, v in raw.items() if k != "evaluation"})
    res = post_vaccination_escalate(EscalationInput(child=s.child(ck.child_id), checkin=ck))
    s.update_doc("checkins", checkin_id, evaluation=res)
    s.log(Actor.rule_engine, "post_vaccination_escalate", f"checkin={checkin_id}", f"{res.outcome}: {[t.rule for t in res.triggers]}", child_id=ck.child_id, source=res.source_ref)
    from vaccinepath.labels import trigger_text

    return _j({"result": res, "triggers_text": [trigger_text(t) for t in res.triggers], "must_request_review": res.outcome != EscalationOutcome.CONTINUE,
               "review_reason": f"接种后打卡判定 {res.outcome.value}（接种后第 {ck.days_since_vaccination} 天）：" + "；".join(trigger_text(t) for t in res.triggers) + f" [{res.source_ref}]" if res.outcome != EscalationOutcome.CONTINUE else None})


@tool("vp_evaluate_screening", parse_docstring=True)
def vp_evaluate_screening(screening_id: str) -> str:
    """Run the deterministic pre-vaccination screening rules on a submitted questionnaire and persist the outcome (CLEAR / PROFESSIONAL_REVIEW_REQUIRED). The system never decides suitability; anything not CLEAR goes to vp_request_review.

    Args:
        screening_id: The screening id.
    """
    s = _store()
    raw = s.get("screenings", screening_id)
    if raw is None:
        return _j({"error": f"screening {screening_id} not found"})
    inp = ScreenInput(child_id=raw["child_id"], planned_vaccines=[VaccineCode(v) for v in raw["planned_vaccines"]], answers=ScreeningAnswers(**raw["answers"]), answered_at=datetime.fromisoformat(raw["answered_at"]))
    res = pre_vaccination_screen(inp)
    s.update_doc("screenings", screening_id, result=res)
    s.log(Actor.rule_engine, "pre_vaccination_screen", f"screening={screening_id}", f"{res.outcome} flags={[f.field for f in res.flags]}", child_id=raw["child_id"], source=res.source_ref)
    from vaccinepath.labels import screen_flag_text

    return _j({"result": res, "must_request_review": res.outcome != ScreenOutcome.CLEAR,
               "review_reason": ("接种前筛查有标记项：" + "；".join(screen_flag_text(f) for f in res.flags) + f" [{res.source_ref}]") if res.outcome != ScreenOutcome.CLEAR else None})


@tool("vp_get_guidance", parse_docstring=True)
def vp_get_guidance(query: str, limit: int = 3) -> str:
    """Retrieve verbatim sentences from the official Singapore guidance stored in docs/sources/. The corpus covers ONLY post-vaccination reactions and fever in children (KKH Post Vaccination Advice, HealthHub Fever in Children) — it says nothing about scheduling, catch-up timing or record verification. Call it before writing a parent message or review reason about a WARN/URGENT check-in or a reaction, then quote ONE returned sentence verbatim and name its source. If it returns no excerpts, write your message WITHOUT any quote — never stretch an unrelated sentence to fit, and never turn a quote into a medical conclusion of your own.

    Args:
        query: What you are writing about — a symptom, a rule name, or a short description (Chinese or English), e.g. "抽搐 急诊" or "fever medication persistent".
        limit: How many sentences to return (default 3).
    """
    from vaccinepath.guidance import search, source_files

    hits = search(query, limit=max(1, min(limit, 5)))
    s = _store()
    s.log(Actor.agent, "retrieve_guidance", query, f"retrieved: {source_files(hits)}（{len(hits)} 条原句）", source=source_files(hits))
    if not hits:
        return _j({"query": query, "retrieved": "（无匹配）", "excerpts": [], "instruction": "本语料只覆盖接种后反应与儿童发热；这个话题没有官方原句可引用，请不要引用任何句子。"})
    return _j({"query": query, "retrieved": source_files(hits), "excerpts": [{"quote": e.quote, "source": e.source_title, "section": e.section, "url": e.source_url, "file": e.source_file, "cite": e.cite()} for e in hits]})


@tool("vp_log", parse_docstring=True)
def vp_log(action: str, summary: str, child_id: str = "") -> str:
    """Append an entry to the audit log. Call once at the END of every wake-up with action='wake_up_summary' and a summary of what you checked, decided and did (counts per child).

    Args:
        action: Short action name, e.g. wake_up_summary.
        summary: What happened.
        child_id: Optional child id.
    """
    s = _store()
    e = s.log(Actor.agent, action, "", summary, child_id=child_id or None)
    if action == "wake_up_summary":
        st = s.agent_state()
        s.set_agent_state(wake_ups=st.get("wake_ups", 0) + 1, last_wake_up=now().isoformat(), last_summary=summary[:500])
    return _j({"logged": e.id, "wake_ups_so_far": s.agent_state().get("wake_ups", 0)})


ALL_TOOLS = [vp_list_children, vp_get_child, vp_check_schedule, vp_check_records, vp_list_tasks, vp_create_task, vp_create_tasks, vp_update_task, vp_send_reminder, vp_request_review, vp_evaluate_checkin, vp_evaluate_screening, vp_get_guidance, vp_log]
