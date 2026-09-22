"""工具层：幂等、合并、上限。用临时目录隔离 data/db.json。"""

import json

import pytest

from vaccinepath import tools
from vaccinepath.models import TaskStatus
from vaccinepath.store import SEED_PATH, Store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("VACCINEPATH_DATA_DIR", str(tmp_path))
    Store().reset_from_seed(SEED_PATH)


def call(t, **kw):
    return json.loads(t.invoke(kw))


def test_list_children_seed():
    d = call(tools.vp_list_children)
    assert [c["name"] for c in d["families"][0]["children"]] == ["Mei", "Kai", "Priya"]


def test_check_schedule_returns_json_not_repr():
    d = call(tools.vp_check_schedule, child_id="child-priya")
    assert isinstance(d["items"], list) and isinstance(d["items"][0], dict) and "status" in d["items"][0]
    assert d["counts"]["overdue"] == 4 and d["requires_clinician_review"]


def test_create_tasks_idempotent():
    items = [{"vaccine": "DTaP", "dose_number": 4, "label": "B1", "due_date": "2026-07-15", "status": "overdue"}]
    a = call(tools.vp_create_tasks, child_id="child-mei", items=items)
    b = call(tools.vp_create_tasks, child_id="child-mei", items=items)
    assert len(a["created"]) == 1 and a["existing"] == []
    assert b["created"] == [] and b["existing"] == [a["created"][0]["id"]]


def test_request_review_bundles_per_child():
    a = call(tools.vp_request_review, child_id="child-priya", reasons=["r1", "r2"])
    b = call(tools.vp_request_review, child_id="child-priya", reasons=["r2", "r3"])
    assert a["created"] and not b["created"] and b["review_task_id"] == a["review_task_id"]
    assert b["new_reasons"] == 1 and b["total_reasons"] == 3
    assert len([t for t in Store().tasks("child-priya") if t.status == TaskStatus.awaiting_review]) == 1


def test_send_reminder_appends_disclaimer_and_respects_max():
    created = call(tools.vp_create_tasks, child_id="child-mei", items=[{"vaccine": "Hib", "dose_number": 4, "label": "B1", "due_date": "2026-07-15", "status": "overdue"}])["created"]
    tid = created[0]["id"]
    for n in range(3):
        r = call(tools.vp_send_reminder, child_id="child-mei", task_ids=[tid], message=f"提醒 {n}")
        assert r["sent"] and r["covered"] == [tid]
    r = call(tools.vp_send_reminder, child_id="child-mei", task_ids=[tid], message="第四次")
    assert not r["sent"] and r["exhausted"] == [tid]
    s = Store()
    assert tools.DISCLAIMER in s.notifications("child-mei")[0]["message"]
    assert s.get("tasks", tid)["status"] == "awaiting_parent" and s.get("tasks", tid)["reminder_count"] == 3


def test_evaluate_checkin_persists_and_flags_review():
    from datetime import UTC, datetime

    from vaccinepath.models import CheckIn, Symptom, TemperatureSite

    s = Store()
    ck = CheckIn(id="ck-t", child_id="child-kai", record_id="rec-kai-12", submitted_at=datetime.now(UTC), days_since_vaccination=2, temperature_c=38.0, temperature_site=TemperatureSite.axillary, symptoms=[Symptom.less_active_than_usual])
    s.put("checkins", ck)
    r = call(tools.vp_evaluate_checkin, checkin_id="ck-t")
    assert r["result"]["outcome"] == "WARN" and r["must_request_review"]
    assert s.get("checkins", "ck-t")["evaluation"]["outcome"] == "WARN"


def test_wake_up_summary_increments_counter():
    call(tools.vp_log, action="wake_up_summary", summary="一")
    r = call(tools.vp_log, action="wake_up_summary", summary="二")
    assert r["wake_ups_so_far"] == 2


def test_list_tasks_precomputes_repeat_and_escalation():
    call(tools.vp_list_children)  # 标记一轮开始；之后发的提醒属于"本轮"
    created = call(tools.vp_create_tasks, child_id="child-mei", items=[{"vaccine": "Hib", "dose_number": 4, "label": "B1", "due_date": "2026-07-15", "status": "overdue"}, {"vaccine": "IPV", "dose_number": 4, "label": "B1", "due_date": "2026-07-15", "status": "overdue"}])["created"]
    a, b = created[0]["id"], created[1]["id"]
    call(tools.vp_send_reminder, child_id="child-mei", task_ids=[a, b], message="1")
    d = call(tools.vp_list_tasks)  # 本轮刚发的提醒不算未响应
    assert d["repeat_reminders_required"] == {} and d["escalations_required"] == {}
    call(tools.vp_list_children)  # 下一轮唤醒开始（seed 的 reminder_repeat_hours=0）
    d = call(tools.vp_list_tasks)
    assert d["repeat_reminders_required"] == {"child-mei": [a, b]} and d["escalations_required"] == {}
    for _ in range(2):
        call(tools.vp_send_reminder, child_id="child-mei", task_ids=[a], message="again")
    call(tools.vp_list_children)
    d = call(tools.vp_list_tasks)
    assert d["escalations_required"] == {"child-mei": [a]} and d["repeat_reminders_required"] == {"child-mei": [b]}


def test_get_guidance_returns_verbatim_quotes_and_logs_retrieved():
    d = call(tools.vp_get_guidance, query="抽搐 急诊")
    assert d["retrieved"] == "healthhub_fever_in_children.md"
    quotes = [e["quote"] for e in d["excerpts"]]
    assert "Has a fit (seizure or convulsion)" in quotes  # 原句，未改写
    assert all(e["url"].startswith("https://") for e in d["excerpts"])
    log = Store().audit_log()[-1]
    assert log["action"] == "retrieve_guidance" and log["output_summary"].startswith("retrieved: healthhub_fever_in_children.md")


def test_get_guidance_picks_kkh_for_consult_topics():
    d = call(tools.vp_get_guidance, query="退烧药 发热 持续")
    assert "kkh_post_vaccination_advice.md" in d["retrieved"]
    assert "Medication does not reduce fever" in [e["quote"] for e in d["excerpts"]]


def test_get_guidance_returns_nothing_for_topics_the_corpus_does_not_cover():
    d = call(tools.vp_get_guidance, query="逾期补种 catch-up schedule")
    assert d["excerpts"] == [] and "不要引用" in d["instruction"]
    assert Store().audit_log()[-1]["output_summary"].startswith("retrieved: （无匹配）")
