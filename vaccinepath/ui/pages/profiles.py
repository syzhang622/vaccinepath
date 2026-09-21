"""页 1：家庭 / 孩子档案 + 接种记录录入 + 校验/查重。"""

from __future__ import annotations

from datetime import date

import streamlit as st

from vaccinepath.models import Actor, Child, ConflictInput, Family, RecordSource, Sex, VaccinationRecord
from vaccinepath.rules import detect_conflicts
from vaccinepath.store import new_id
from vaccinepath.ui.common import SEVERITY_LABEL, age_text, store, today, vaccine_options


def render():
    st.header("家庭 / 孩子档案")
    s = store()
    fams = s.families()

    with st.expander("➕ 新增孩子", expanded=not fams):
        with st.form("add_child", clear_on_submit=True):
            fam_labels = {f.id: f.guardian_name for f in fams}
            c1, c2 = st.columns(2)
            fam_id = c1.selectbox("家庭", list(fam_labels) + ["__new__"], format_func=lambda x: fam_labels.get(x, "＋ 新家庭"))
            guardian = c2.text_input("新家庭：监护人姓名（选新家庭时填）")
            name = c1.text_input("孩子姓名")
            dob = c2.date_input("出生日期", value=date(2025, 1, 1), min_value=date(2008, 1, 1), max_value=today())
            sex = c1.selectbox("性别", [Sex.female, Sex.male], format_func=lambda x: {"female": "女", "male": "男"}[x])
            local_school = c2.checkbox("在新加坡本地学校就读（影响 HPV2 走校内/校外规则）", value=True)
            high_risk = st.checkbox("有 NCIS 列出的高危状况（勾选后相关项一律转医生评估）")
            notes = st.text_input("备注")
            if st.form_submit_button("保存"):
                if fam_id == "__new__":
                    if not guardian:
                        st.error("请填监护人姓名")
                        st.stop()
                    f = Family(id=new_id("fam"), guardian_name=guardian)
                    s.put("families", f)
                    fam_id = f.id
                if not name:
                    st.error("请填孩子姓名")
                    st.stop()
                c = Child(id=new_id("child"), family_id=fam_id, name=name, date_of_birth=dob, sex=sex, attends_local_school=local_school, high_risk_condition=high_risk, notes=notes or None)
                s.put("children", c)
                s.log(Actor.parent, "create_child", name, c.id, child_id=c.id)
                st.success(f"已添加 {name}")
                st.rerun()

    for f in fams:
        st.subheader(f"👪 {f.guardian_name} 家")
        for c in s.children(f.id):
            with st.container(border=True):
                top = st.columns([2, 1, 1, 1])
                top[0].markdown(f"**{c.name}**  ·  {age_text(c.date_of_birth)}  ·  {'女' if c.sex == Sex.female else '男'}  ·  生于 {c.date_of_birth}")
                top[1].markdown("本地学校 ✅" if c.attends_local_school else "非本地学校")
                top[2].markdown("⚠️ 高危状况" if c.high_risk_condition else "无高危标记")
                top[3].markdown(f"记录 {len(s.records(c.id))} 条")
                if c.notes:
                    st.caption(c.notes)

                recs = s.records(c.id)
                if recs:
                    st.dataframe(
                        [{"日期": r.date, "抗原": ", ".join(r.vaccines), "产品": r.product or "", "来源": r.source.value, "国家": r.country or "", "已核实": "✅" if r.verified else "", "备注": r.notes or ""} for r in sorted(recs, key=lambda r: r.date)],
                        hide_index=True,
                        width="stretch",
                    )
                rep = detect_conflicts(ConflictInput(child=c, records=recs, as_of=today()))
                if rep.clean:
                    st.caption("✅ 记录校验通过：无重复、无冲突、无待核实项")
                else:
                    for i in rep.issues:
                        st.markdown(f"- {SEVERITY_LABEL[i.severity.value]} `{i.code}` {i.message}  ·  _{i.source_ref}_")

                with st.expander(f"➕ 给 {c.name} 录入一次接种"):
                    with st.form(f"add_rec_{c.id}", clear_on_submit=True):
                        a, b = st.columns(2)
                        d = a.date_input("接种日期", value=today(), min_value=c.date_of_birth, max_value=today())
                        vax = b.multiselect("抗原（联合疫苗请全选，如 6-in-1 = DTaP+IPV+Hib+HepB）", vaccine_options())
                        product = a.text_input("产品名（可选，如 6-in-1 / MMRV / Hexaxim）")
                        src = b.selectbox("来源", list(RecordSource), format_func=lambda x: x.value)
                        country = a.text_input("国家（海外记录填）")
                        label = b.text_input("记录上的剂次标签（可选，如 D1/B1）")
                        rnotes = st.text_input("备注（可选）")
                        if st.form_submit_button("保存记录"):
                            if not vax:
                                st.error("至少选一个抗原")
                                st.stop()
                            r = VaccinationRecord(id=new_id("rec"), child_id=c.id, date=d, vaccines=vax, product=product or None, dose_label=label or None, source=src, country=country or None, notes=rnotes or None)
                            s.put("records", r)
                            s.log(Actor.parent, "add_record", f"{d} {vax} {product}", r.id, child_id=c.id)
                            st.success("已保存，校验结果已刷新")
                            st.rerun()
