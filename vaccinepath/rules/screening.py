"""pre_vaccination_screen：接种前安全筛查。本系统**不判定**孩子是否适合接种；
任何非 "no" 的答案都转医生审核（proposal §3：flagged or uncertain cases enter a mandatory
healthcare-professional review state）。
"""

from __future__ import annotations

from vaccinepath.models import ScreenFlag, ScreenInput, ScreenOutcome, ScreenResult, TriState

DISCLAIMER = "This result organises the information provided. It is not a diagnosis and does not replace clinical judgement; fitness for vaccination must be decided by a healthcare professional."

_REASONS = {
    "previous_serious_reaction": "Previous serious vaccine reaction",
    "known_allergy": "Known allergy, including vaccine components",
    "current_illness": "Current illness",
    "current_fever": "Current fever",
    "immune_condition": "Immune-related condition",
    "immunosuppressive_medication": "Current immunosuppressive medication",
}


def pre_vaccination_screen(inp: ScreenInput) -> ScreenResult:
    flags: list[ScreenFlag] = []
    for field, label in _REASONS.items():
        ans: TriState = getattr(inp.answers, field)
        if ans == TriState.no:
            continue
        flags.append(ScreenFlag(field=field, answer=ans, reason=f"{label}: answer is {ans.value}; clinician assessment is required"))
    incomplete = any(f.answer == TriState.unsure for f in flags)
    outcome = ScreenOutcome.CLEAR if not flags else ScreenOutcome.PROFESSIONAL_REVIEW_REQUIRED
    return ScreenResult(
        child_id=inp.child_id,
        outcome=outcome,
        flags=flags,
        incomplete=incomplete,
        disclaimer=DISCLAIMER,
        source_ref="Proposal §3/§4; safety principle §0",
    )
