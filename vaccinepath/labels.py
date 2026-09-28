"""代码 → 人话。规则引擎输出的枚举/规则名在这里统一翻译，UI、工具、agent 都用它。"""

from __future__ import annotations

from vaccinepath.models import EscalationTrigger, ScreenFlag, Symptom, TriState

SYMPTOM_LABEL: dict[Symptom, str] = {
    Symptom.difficult_to_awaken: "Difficult to awaken",
    Symptom.confused_or_delirious: "Confused or delirious",
    Symptom.crying_inconsolable: "Persistent crying that cannot be consoled",
    Symptom.difficulty_breathing: "Difficulty breathing",
    Symptom.very_lethargic: "Very lethargic",
    Symptom.skin_pale_or_grey: "Pale or grey skin",
    Symptom.bruising_spots: "Bruising or purple spots",
    Symptom.seizure: "Seizure or fit",
    Symptom.drinking_less_and_less_urine: "Drinking much less or passing much less urine",
    Symptom.less_active_than_usual: "Much less active than usual",
    Symptom.crying_persistent_consolable: "Persistent crying that can be consoled",
    Symptom.injection_site_redness_swelling_pain: "Injection-site redness, swelling, or pain",
    Symptom.irritability: "Irritability",
    Symptom.mild_rash: "Mild rash",
    Symptom.vomiting: "Vomiting",
}

RULE_LABEL: dict[str, str] = {
    "urgent_symptom": "Emergency warning sign",
    "urgent_temperature": "Temperature above the emergency threshold",
    "infant_fever": "Fever in an infant under 3 months",
    "warn_fever_not_reduced_by_medication": "Fever persists after medication",
    "warn_fever_duration": "Fever lasting more than 2 days",
    "warn_symptom": "Medical-review warning sign",
    "warn_parent_concern": "Caregiver is worried or thinks the child is worsening",
}

SCREEN_FIELD_LABEL: dict[str, str] = {
    "previous_serious_reaction": "Previous serious reaction after vaccination",
    "known_allergy": "Known allergy, including vaccine components",
    "current_illness": "Currently unwell",
    "current_fever": "Current fever",
    "immune_condition": "Immune-related condition",
    "immunosuppressive_medication": "Currently taking immunosuppressive medication",
}

TRI_LABEL: dict[TriState, str] = {TriState.no: "No", TriState.yes: "Yes", TriState.unsure: "Unsure"}  # Order determines the default: No.

OUTCOME_LABEL = {"CONTINUE": "Continue monitoring", "WARN": "Consult a doctor", "URGENT": "Go to the Children's Emergency immediately", "CLEAR": "No flags", "PROFESSIONAL_REVIEW_REQUIRED": "Professional review required"}


def trigger_text(t: EscalationTrigger) -> str:
    detail = t.detail
    try:
        detail = SYMPTOM_LABEL[Symptom(t.detail)]
    except ValueError:
        pass
    return f"{RULE_LABEL.get(t.rule, t.rule)}: {detail}"


def screen_flag_text(f: ScreenFlag) -> str:
    return f"{SCREEN_FIELD_LABEL.get(f.field, f.field)} = {TRI_LABEL[f.answer]}"
