"""页 4：接种后结构化打卡。提交即由规则引擎判定（CONTINUE / WARN / URGENT），LLM 不参与。"""

from __future__ import annotations

import json

import streamlit as st

from vaccinepath import tools
from vaccinepath.labels import RULE_LABEL, SYMPTOM_LABEL
from vaccinepath.models import Actor, CheckIn, Symptom, TemperatureSite
from vaccinepath.store import new_id, now
from vaccinepath.ui.common import child_selector, store, today

URGENT = [Symptom.difficult_to_awaken, Symptom.confused_or_delirious, Symptom.crying_inconsolable, Symptom.difficulty_breathing, Symptom.very_lethargic, Symptom.skin_pale_or_grey, Symptom.bruising_spots, Symptom.seizure, Symptom.drinking_less_and_less_urine]
WARN = [Symptom.less_active_than_usual, Symptom.crying_persistent_consolable]
MILD = [Symptom.injection_site_redness_swelling_pain, Symptom.irritability, Symptom.mild_rash, Symptom.vomiting]
OUTCOME_UI = {
    "CONTINUE": ("success", "继续观察", "目前没有需要就医的迹象。24 小时后再打卡一次；情况有变化随时重新填写。"),
    "WARN": ("warning", "建议看医生", "按 KKH 接种后指引，出现了建议就医的情况。已转人工审核，请尽快联系诊所。"),
    "URGENT": ("error", "请立即前往儿童急诊", "按 HealthHub 儿童发热指引，出现了需要立即急诊的情况。请立即前往 KKH 儿童急诊或拨打 995。"),
}


def render():
    st.header("接种后打卡")
    c = child_selector("checkin_child")
    if c is None:
        return
    s = store()
    recs = sorted(s.records(c.id), key=lambda r: (r.date, r.id), reverse=True)
    if not recs:
        st.info("这个孩子还没有接种记录。")
        return
    rec_labels = {r.id: f"{r.date}  {r.product or ', '.join(r.vaccines)}（{(today() - r.date).days} 天前）" for r in recs}
    # 选针在 form 外面：切换时立即重算"第几天"
    rid = st.selectbox("这次打卡针对哪次接种（默认最近一针）", list(rec_labels), format_func=rec_labels.get, key="checkin_rec")
    days = (today() - next(r for r in recs if r.id == rid).date).days
    st.caption(f"接种后第 {days} 天")

    if "checkin_result" in st.session_state and st.session_state["checkin_result"]["child_id"] == c.id:
        _show_result(st.session_state["checkin_result"])

    with st.form("checkin_form", clear_on_submit=True):
        a, b, cc = st.columns(3)
        has_temp = a.checkbox("量了体温")
        temp = b.number_input("体温 °C", min_value=34.0, max_value=43.0, value=37.0, step=0.1)
        site = cc.selectbox("测量部位", [TemperatureSite.axillary, TemperatureSite.tympanic], format_func=lambda x: {"axillary": "腋温", "tympanic": "耳温"}[x])
        d, e = st.columns(2)
        fever_h = d.number_input("这次发热已持续（小时）", min_value=0, max_value=240, value=0)
        anti = e.selectbox("吃过退烧药后还发热吗？", ["未吃退烧药", "吃了，退了", "吃了，仍发热"])
        st.markdown("**有没有以下情况**（勾选所有符合的）")
        u = st.multiselect("急诊指征（HealthHub）", URGENT, format_func=SYMPTOM_LABEL.get)
        w = st.multiselect("建议就医指征（KKH）", WARN, format_func=SYMPTOM_LABEL.get)
        m = st.multiselect("常见轻微反应（仅记录）", MILD, format_func=SYMPTOM_LABEL.get)
        worried = st.checkbox("我很担心 / 觉得孩子在变差")
        free = st.text_area("补充描述（可选）")
        submitted = st.form_submit_button("提交打卡", type="primary")
    if submitted:
        ck = CheckIn(
            id=new_id("ck"), child_id=c.id, record_id=rid, submitted_at=now(), days_since_vaccination=max(days, 0),
            temperature_c=float(temp) if has_temp else None, temperature_site=site if has_temp else None,
            fever_duration_hours=int(fever_h) if fever_h else None, fever_after_antipyretic={"未吃退烧药": None, "吃了，退了": False, "吃了，仍发热": True}[anti],
            symptoms=u + w + m, parent_very_worried=worried, free_text=free or None,
        )
        s.put("checkins", ck)
        s.log(Actor.parent, "checkin_submitted", ck.id, "家长提交接种后打卡", child_id=c.id)
        r = json.loads(tools.vp_evaluate_checkin.invoke({"checkin_id": ck.id}))
        if r["review_reason"]:
            tools.vp_request_review.invoke({"child_id": c.id, "reasons": [r["review_reason"]]})
        st.session_state["checkin_result"] = {"child_id": c.id, "outcome": r["result"]["outcome"], "triggers_text": r["triggers_text"], "source_ref": r["result"]["source_ref"], "disclaimer": r["result"]["disclaimer"], "days": ck.days_since_vaccination}
        st.rerun()

    st.subheader("历史打卡")
    hist = [ck for ck in s.read()["checkins"].values() if ck["child_id"] == c.id]
    if hist:
        st.dataframe(
            [{"时间": ck["submitted_at"][:16].replace("T", " "), "第几天": ck["days_since_vaccination"], "体温": ck.get("temperature_c"), "症状": "、".join(SYMPTOM_LABEL.get(Symptom(x), x) for x in ck.get("symptoms", [])), "判定": {"CONTINUE": "继续观察", "WARN": "建议看医生", "URGENT": "立即急诊"}.get((ck.get("evaluation") or {}).get("outcome"), "未评估"), "触发": "；".join(f"{RULE_LABEL.get(t['rule'], t['rule'])}" for t in (ck.get("evaluation") or {}).get("triggers", []))} for ck in sorted(hist, key=lambda x: x["submitted_at"], reverse=True)],
            hide_index=True,
            width="stretch",
        )


def _show_result(r):
    kind, title, text = OUTCOME_UI[r["outcome"]]
    getattr(st, kind)(f"**{title}**（接种后第 {r['days']} 天的打卡已提交）  \n{text}")
    if r["triggers_text"]:
        st.markdown("触发项：" + "；".join(r["triggers_text"]))
    if r["outcome"] != "CONTINUE":
        st.markdown("已自动转入「人工审核」队列。")
    st.caption(f"依据：{r['source_ref']}")
    st.caption(r["disclaimer"])
