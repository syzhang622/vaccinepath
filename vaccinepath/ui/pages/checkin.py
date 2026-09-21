"""页 4：接种后结构化打卡。提交即由规则引擎判定（CONTINUE / WARN / URGENT），LLM 不参与。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import streamlit as st

from vaccinepath import tools
from vaccinepath.models import Actor, CheckIn, Symptom, TemperatureSite
from vaccinepath.store import new_id
from vaccinepath.ui.common import child_selector, store, today

URGENT_SYMPTOMS = [
    (Symptom.difficult_to_awaken, "叫不醒 / 很难唤醒"),
    (Symptom.confused_or_delirious, "意识混乱 / 说胡话"),
    (Symptom.crying_inconsolable, "持续哭闹，怎么都安抚不了"),
    (Symptom.difficulty_breathing, "呼吸困难"),
    (Symptom.very_lethargic, "极度嗜睡 / 没精神"),
    (Symptom.skin_pale_or_grey, "肤色苍白或发灰"),
    (Symptom.bruising_spots, "皮肤出现瘀点 / 瘀斑"),
    (Symptom.seizure, "抽搐"),
    (Symptom.drinking_less_and_less_urine, "喝得明显少、尿量明显少"),
]
WARN_SYMPTOMS = [
    (Symptom.less_active_than_usual, "比平时明显不活跃"),
    (Symptom.crying_persistent_consolable, "持续哭闹，但能安抚"),
]
MILD_SYMPTOMS = [
    (Symptom.injection_site_redness_swelling_pain, "注射部位红肿痛"),
    (Symptom.irritability, "烦躁"),
    (Symptom.mild_rash, "轻微皮疹"),
    (Symptom.vomiting, "呕吐"),
]
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
    recs = sorted(s.records(c.id), key=lambda r: r.date, reverse=True)
    if not recs:
        st.info("这个孩子还没有接种记录。")
        return
    rec_labels = {r.id: f"{r.date}  {r.product or ', '.join(r.vaccines)}" for r in recs}

    with st.form("checkin_form"):
        rid = st.selectbox("这次打卡针对哪次接种", list(rec_labels), format_func=rec_labels.get)
        days = (today() - next(r for r in recs if r.id == rid).date).days
        st.caption(f"接种后第 {days} 天")
        a, b, cc = st.columns(3)
        has_temp = a.checkbox("量了体温")
        temp = b.number_input("体温 °C", min_value=34.0, max_value=43.0, value=37.0, step=0.1)
        site = cc.selectbox("测量部位", [TemperatureSite.axillary, TemperatureSite.tympanic], format_func=lambda x: {"axillary": "腋温", "tympanic": "耳温"}[x])
        d, e = st.columns(2)
        fever_h = d.number_input("这次发热已持续（小时）", min_value=0, max_value=240, value=0)
        anti = e.selectbox("吃过退烧药后还发热吗？", ["未吃退烧药", "吃了，退了", "吃了，仍发热"])
        st.markdown("**有没有以下情况**（勾选所有符合的）")
        u = st.multiselect("急诊指征（HealthHub）", [k for k, _ in URGENT_SYMPTOMS], format_func=dict(URGENT_SYMPTOMS).get)
        w = st.multiselect("建议就医指征（KKH）", [k for k, _ in WARN_SYMPTOMS], format_func=dict(WARN_SYMPTOMS).get)
        m = st.multiselect("常见轻微反应（仅记录）", [k for k, _ in MILD_SYMPTOMS], format_func=dict(MILD_SYMPTOMS).get)
        worried = st.checkbox("我很担心 / 觉得孩子在变差")
        free = st.text_area("补充描述（可选）")
        if st.form_submit_button("提交打卡"):
            ck = CheckIn(
                id=new_id("ck"), child_id=c.id, record_id=rid, submitted_at=datetime.now(timezone.utc), days_since_vaccination=max(days, 0),
                temperature_c=float(temp) if has_temp else None, temperature_site=site if has_temp else None,
                fever_duration_hours=int(fever_h) if fever_h else None, fever_after_antipyretic={"未吃退烧药": None, "吃了，退了": False, "吃了，仍发热": True}[anti],
                symptoms=u + w + m, parent_very_worried=worried, free_text=free or None,
            )
            s.put("checkins", ck)
            s.log(Actor.parent, "checkin_submitted", ck.id, "家长提交接种后打卡", child_id=c.id)
            r = json.loads(tools.vp_evaluate_checkin.invoke({"checkin_id": ck.id}))["result"]
            kind, title, text = OUTCOME_UI[r["outcome"]]
            getattr(st, kind)(f"**{title}**  \n{text}")
            if r["triggers"]:
                st.markdown("触发项：" + "；".join(f"`{t['rule']}` {t['detail']}" for t in r["triggers"]))
            if r["outcome"] != "CONTINUE":
                tools.vp_request_review.invoke({"child_id": c.id, "reasons": [f"接种后打卡 {ck.id}（第 {ck.days_since_vaccination} 天）判定 {r['outcome']}：" + "；".join(f"{t['rule']}={t['detail']}" for t in r["triggers"]) + f" [{r['source_ref']}]"]})
            st.caption(f"依据：{r['source_ref']}")
            st.caption(r["disclaimer"])

    st.subheader("历史打卡")
    hist = [ck for ck in s.read()["checkins"].values() if ck["child_id"] == c.id]
    if hist:
        st.dataframe(
            [{"时间": ck["submitted_at"][:16].replace("T", " "), "第几天": ck["days_since_vaccination"], "体温": ck.get("temperature_c"), "症状": ", ".join(ck.get("symptoms", [])), "判定": (ck.get("evaluation") or {}).get("outcome", "未评估"), "触发": ", ".join(t["rule"] for t in (ck.get("evaluation") or {}).get("triggers", []))} for ck in sorted(hist, key=lambda x: x["submitted_at"], reverse=True)],
            hide_index=True,
            width="stretch",
        )
