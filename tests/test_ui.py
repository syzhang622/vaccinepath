"""前端六页用 streamlit AppTest 无头渲染：不抛异常 + 关键交互能走通。用临时目录隔离数据。"""

import pytest
from streamlit.testing.v1 import AppTest

from vaccinepath.store import SEED_PATH, Store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("VACCINEPATH_DATA_DIR", str(tmp_path))
    Store().reset_from_seed(SEED_PATH)


def page(module: str) -> AppTest:
    at = AppTest.from_string(f"from vaccinepath.ui.pages import {module}\n{module}.render()\n", default_timeout=30)
    return at.run()


@pytest.mark.parametrize("module", ["profiles", "timeline", "tasks", "checkin", "review", "logs"])
def test_every_page_renders_without_exception(module):
    at = page(module)
    assert not at.exception, at.exception


def test_profiles_shows_seed_children_and_conflicts():
    at = page("profiles")
    text = " ".join(m.value for m in at.markdown)
    assert "Mei" in text and "Kai" in text and "Priya" in text
    assert "overseas_unverified" in text  # Priya 的海外记录校验提示


def test_timeline_counts_for_priya():
    at = page("timeline")
    at.selectbox[0].select("child-priya").run()
    assert not at.exception
    labels = {m.label: m.value for m in at.metric}
    assert labels["🔴 已逾期"] == "16" and labels["🩺 需医生确认"] == "1"


def test_checkin_urgent_routes_to_review():
    at = page("checkin")
    at.selectbox[0].select("child-mei").run()
    at.checkbox[0].check()  # 量了体温
    at.number_input[0].set_value(41.5)
    at.selectbox[2].select("tympanic")
    at.multiselect[0].select("seizure")
    at.button[0].click().run()
    assert not at.exception
    assert any("立即前往儿童急诊" in e.value for e in at.error)
    s = Store()
    assert any(t.type.value == "professional_review" for t in s.tasks("child-mei"))
    ck = list(s.read()["checkins"].values())[0]
    assert ck["evaluation"]["outcome"] == "URGENT"


def test_review_queue_approve_marks_done_and_verifies_record():
    from vaccinepath import tools

    tools.vp_request_review.invoke({"child_id": "child-priya", "reasons": ["海外记录未核实"]})
    at = page("review")
    assert at.metric[0].value == "1"
    at.multiselect[0].select("rec-priya-01")
    at.text_area[0].set_value("已核对接种卡")
    at.button[0].click().run()  # 批准
    assert not at.exception
    s = Store()
    assert s.get("records", "rec-priya-01")["verified"] is True
    assert all(t.status.value == "done" for t in s.tasks("child-priya") if t.type.value == "professional_review")
    assert any(e["human_decision"] == "approved" for e in s.audit_log("child-priya"))


def test_tasks_page_screening_with_flag_routes_to_review():
    from vaccinepath import tools

    tools.vp_create_tasks.invoke({"child_id": "child-mei", "items": [{"vaccine": "DTaP", "dose_number": 4, "label": "B1", "due_date": "2026-07-15", "status": "overdue"}]})
    at = page("tasks")
    assert not at.exception
    at.radio[0].set_value("yes")  # 既往严重反应
    at.button[0].click().run()  # 提交筛查（第一个 form 的按钮）
    assert not at.exception
    s = Store()
    assert any(t.type.value == "professional_review" and "接种前筛查" in (t.notes or "") for t in s.tasks("child-mei"))
