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
    "CONTINUE": ("success", "Continue monitoring", "No signs requiring medical review were identified. Check in again after 24 hours, or sooner if the child's condition changes."),
    "WARN": ("warning", "Consult a doctor", "The KKH post-vaccination guidance indicates that medical review is appropriate. This has been routed for professional review; please contact a clinic promptly."),
    "URGENT": ("error", "Go to the Children's Emergency immediately", "The HealthHub fever guidance indicates a need for immediate emergency assessment. Go to the KKH Children's Emergency immediately or call 995."),
}


def render():
    st.header("Post-vaccination Check-in")
    c = child_selector("checkin_child")
    if c is None:
        return
    s = store()
    recs = sorted(s.records(c.id), key=lambda r: (r.date, r.id), reverse=True)
    if not recs:
        st.info("This child has no vaccination records yet.")
        return
    rec_labels = {r.id: f"{r.date}  {r.product or ', '.join(r.vaccines)} ({(today() - r.date).days} days ago)" for r in recs}
    # 选针在 form 外面：切换时立即重算"第几天"
    rid = st.selectbox("Which vaccination is this check-in about? (Most recent by default)", list(rec_labels), format_func=rec_labels.get, key="checkin_rec")
    days = (today() - next(r for r in recs if r.id == rid).date).days
    st.caption(f"Day {days} after vaccination")

    if "checkin_result" in st.session_state and st.session_state["checkin_result"]["child_id"] == c.id:
        _show_result(st.session_state["checkin_result"])

    with st.form("checkin_form", clear_on_submit=True):
        a, b, cc = st.columns(3)
        has_temp = a.checkbox("Temperature measured")
        temp = b.number_input("Temperature °C", min_value=34.0, max_value=43.0, value=37.0, step=0.1)
        site = cc.selectbox("Measurement site", [TemperatureSite.axillary, TemperatureSite.tympanic], format_func=lambda x: {"axillary": "Axillary", "tympanic": "Tympanic (ear)"}[x])
        d, e = st.columns(2)
        fever_h = d.number_input("How long has this fever lasted? (hours)", min_value=0, max_value=240, value=0)
        anti = e.selectbox("Is the child still febrile after fever medication?", ["No medication given", "Medication given; fever reduced", "Medication given; still febrile"])
        st.markdown("**Does the child have any of the following?** (Select all that apply)")
        u = st.multiselect("Emergency warning signs (HealthHub)", URGENT, format_func=SYMPTOM_LABEL.get)
        w = st.multiselect("Signs requiring medical review (KKH)", WARN, format_func=SYMPTOM_LABEL.get)
        m = st.multiselect("Common mild reactions (record only)", MILD, format_func=SYMPTOM_LABEL.get)
        worried = st.checkbox("I am very worried or think the child is getting worse")
        free = st.text_area("Additional description (optional)")
        submitted = st.form_submit_button("Submit check-in", type="primary")
    if submitted:
        ck = CheckIn(
            id=new_id("ck"), child_id=c.id, record_id=rid, submitted_at=now(), days_since_vaccination=max(days, 0),
            temperature_c=float(temp) if has_temp else None, temperature_site=site if has_temp else None,
            fever_duration_hours=int(fever_h) if fever_h else None, fever_after_antipyretic={"No medication given": None, "Medication given; fever reduced": False, "Medication given; still febrile": True}[anti],
            symptoms=u + w + m, parent_very_worried=worried, free_text=free or None,
        )
        s.put("checkins", ck)
        s.log(Actor.parent, "checkin_submitted", ck.id, "Caregiver submitted a post-vaccination check-in", child_id=c.id)
        r = json.loads(tools.vp_evaluate_checkin.invoke({"checkin_id": ck.id}))
        if r["review_reason"]:
            tools.vp_request_review.invoke({"child_id": c.id, "reasons": [r["review_reason"]]})
        quotes = []
        if r["result"]["outcome"] != "CONTINUE":
            from vaccinepath.guidance import search
            q = " ".join(r["triggers_text"]) + (" emergency" if r["result"]["outcome"] == "URGENT" else " doctor")
            quotes = [e.cite() for e in search(q, 2)]
        st.session_state["checkin_result"] = {"child_id": c.id, "outcome": r["result"]["outcome"], "triggers_text": r["triggers_text"], "quotes": quotes, "source_ref": r["result"]["source_ref"], "disclaimer": r["result"]["disclaimer"], "days": ck.days_since_vaccination}
        st.rerun()

    st.subheader("Check-in history")
    hist = [ck for ck in s.read()["checkins"].values() if ck["child_id"] == c.id]
    if hist:
        st.dataframe(
            [{"Time": ck["submitted_at"][:16].replace("T", " "), "Day": ck["days_since_vaccination"], "Temperature": ck.get("temperature_c"), "Symptoms": ", ".join(SYMPTOM_LABEL.get(Symptom(x), x) for x in ck.get("symptoms", [])), "Outcome": {"CONTINUE": "Continue monitoring", "WARN": "Consult a doctor", "URGENT": "Emergency assessment"}.get((ck.get("evaluation") or {}).get("outcome"), "Not evaluated"), "Triggers": "; ".join(f"{RULE_LABEL.get(t['rule'], t['rule'])}" for t in (ck.get("evaluation") or {}).get("triggers", []))} for ck in sorted(hist, key=lambda x: x["submitted_at"], reverse=True)],
            hide_index=True,
            width="stretch",
        )


def _show_result(r):
    kind, title, text = OUTCOME_UI[r["outcome"]]
    getattr(st, kind)(f"**{title}** (check-in submitted on day {r['days']} after vaccination)  \n{text}")
    if r["triggers_text"]:
        st.markdown("Triggers: " + "; ".join(r["triggers_text"]))
    for q in r.get("quotes", []):
        st.markdown(f"> {q}")
    if r["outcome"] != "CONTINUE":
        st.markdown("Automatically routed to the Clinical Review queue.")
    st.caption(f"Source: {r['source_ref']}")
    st.caption(r["disclaimer"])
