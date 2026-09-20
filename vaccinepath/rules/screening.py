"""pre_vaccination_screen：接种前安全筛查。本系统**不判定**孩子是否适合接种；
任何非 "no" 的答案都转医生审核（proposal §3：flagged or uncertain cases enter a mandatory
healthcare-professional review state）。
"""

from __future__ import annotations

from vaccinepath.models import ScreenFlag, ScreenInput, ScreenOutcome, ScreenResult, TriState

DISCLAIMER = "本结果仅为信息整理，不构成诊断，不替代医生判断；是否适合接种由医疗专业人员决定。"

_REASONS = {
    "previous_serious_reaction": "既往疫苗严重反应",
    "known_allergy": "已知过敏（含疫苗成分）",
    "current_illness": "当前患病",
    "current_fever": "当前发热",
    "immune_condition": "免疫相关疾病",
    "immunosuppressive_medication": "正在使用免疫抑制药物",
}


def pre_vaccination_screen(inp: ScreenInput) -> ScreenResult:
    flags: list[ScreenFlag] = []
    for field, label in _REASONS.items():
        ans: TriState = getattr(inp.answers, field)
        if ans == TriState.no:
            continue
        flags.append(ScreenFlag(field=field, answer=ans, reason=f"{label}：回答为 {ans.value}，需医生评估"))
    incomplete = any(f.answer == TriState.unsure for f in flags)
    outcome = ScreenOutcome.CLEAR if not flags else ScreenOutcome.PROFESSIONAL_REVIEW_REQUIRED
    return ScreenResult(
        child_id=inp.child_id,
        outcome=outcome,
        flags=flags,
        incomplete=incomplete,
        disclaimer=DISCLAIMER,
        source_ref="proposal §3/§4；原则 §0",
    )
