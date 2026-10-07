"""页 1：家庭 / 孩子档案 + 接种记录录入 + 校验/查重。"""

from __future__ import annotations

from datetime import date

import streamlit as st

from vaccinepath.models import Actor, Child, ConflictInput, Family, RecordSource, Sex, VaccinationRecord
from vaccinepath.rules import detect_conflicts
from vaccinepath.store import new_id
from vaccinepath.ui.common import SEVERITY_LABEL, age_text, flash, store, today, vaccine_options


def render():
    st.header("Family & Child Profiles")
    s = store()
    fams = s.families()

    with st.expander("➕ Add a child", expanded=not fams):
        with st.form("add_child", clear_on_submit=True):
            fam_labels = {f.id: f.guardian_name for f in fams}
            c1, c2 = st.columns(2)
            fam_id = c1.selectbox("Family", list(fam_labels) + ["__new__"], format_func=lambda x: fam_labels.get(x, "＋ New family"))
            guardian = c2.text_input("Guardian name (required for a new family)")
            name = c1.text_input("Child's name")
            dob = c2.date_input("Date of birth", value=date(2025, 1, 1), min_value=date(2008, 1, 1), max_value=today())
            sex = c1.selectbox("Sex", [Sex.female, Sex.male], format_func=lambda x: {"female": "Female", "male": "Male"}[x])
            local_school = c2.checkbox("Attends a local Singapore school (affects school/out-of-school HPV2 rules)", value=True)
            high_risk = st.checkbox("Has an NCIS-listed high-risk condition (relevant items require clinician review)")
            notes = st.text_input("Notes")
            if st.form_submit_button("Save"):
                if fam_id == "__new__":
                    if not guardian:
                        st.error("Please enter the guardian's name.")
                        st.stop()
                    f = Family(id=new_id("fam"), guardian_name=guardian)
                    s.put("families", f)
                    fam_id = f.id
                if not name:
                    st.error("Please enter the child's name.")
                    st.stop()
                c = Child(id=new_id("child"), family_id=fam_id, name=name, date_of_birth=dob, sex=sex, attends_local_school=local_school, high_risk_condition=high_risk, notes=notes or None)
                s.put("children", c)
                s.log(Actor.parent, "create_child", name, c.id, child_id=c.id)
                flash("success", f"✅ {name} has been added. View the NCIS plan on Vaccination Timeline or enter existing records below.")
                st.rerun()

    for f in fams:
        st.subheader(f"👪 {f.guardian_name}'s family")
        for c in s.children(f.id):
            with st.container(border=True):
                top = st.columns([2, 1, 1, 1])
                top[0].markdown(f"**{c.name}**  ·  {age_text(c.date_of_birth)}  ·  {'Female' if c.sex == Sex.female else 'Male'}  ·  Born {c.date_of_birth}")
                top[1].markdown("Local school ✅" if c.attends_local_school else "Not in a local school")
                top[2].markdown("⚠️ High-risk condition" if c.high_risk_condition else "No high-risk flag")
                top[3].markdown(f"{len(s.records(c.id))} records")
                if c.notes:
                    st.caption(c.notes)

                recs = s.records(c.id)
                if recs:
                    st.dataframe(
                        [{"Date": r.date, "Antigens": ", ".join(r.vaccines), "Product": r.product or "", "Source": r.source.value, "Country": r.country or "", "Verified": "✅" if r.verified else "", "Notes": r.notes or ""} for r in sorted(recs, key=lambda r: r.date)],
                        hide_index=True,
                        width="stretch",
                    )
                rep = detect_conflicts(ConflictInput(child=c, records=recs, as_of=today()))
                if rep.clean:
                    st.caption("✅ Record validation passed: no duplicates, conflicts, or unverified items.")
                else:
                    for i in rep.issues:
                        st.markdown(f"- {SEVERITY_LABEL[i.severity.value]} `{i.code}` {i.message}  ·  _{i.source_ref}_")

                with st.expander(f"➕ Add a vaccination record for {c.name}"):
                    with st.form(f"add_rec_{c.id}", clear_on_submit=True):
                        a, b = st.columns(2)
                        d = a.date_input("Vaccination date", value=today(), min_value=c.date_of_birth, max_value=today())
                        vax = b.multiselect("Antigens (select all components of combination vaccines, e.g. 6-in-1 = DTaP+IPV+Hib+HepB)", vaccine_options())
                        product = a.text_input("Product name (optional, e.g. 6-in-1 / MMRV / Hexaxim)")
                        src = b.selectbox("Source", list(RecordSource), format_func=lambda x: x.value)
                        country = a.text_input("Country (for overseas records)")
                        label = b.text_input("Dose label shown on the record (optional, e.g. D1/B1)")
                        rnotes = st.text_input("Notes (optional)")
                        if st.form_submit_button("Save record"):
                            if not vax:
                                st.error("Select at least one antigen.")
                                st.stop()
                            r = VaccinationRecord(id=new_id("rec"), child_id=c.id, date=d, vaccines=vax, product=product or None, dose_label=label or None, source=src, country=country or None, notes=rnotes or None)
                            s.put("records", r)
                            s.log(Actor.parent, "add_record", f"{d} {vax} {product}", r.id, child_id=c.id)
                            flash("success", f"✅ Saved {c.name}'s {d} vaccination record ({', '.join(vax)}). Validation has been refreshed.")
                            st.rerun()
