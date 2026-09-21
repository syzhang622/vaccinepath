"""代码 → 人话。规则引擎输出的枚举/规则名在这里统一翻译，UI、工具、agent 都用它。"""

from __future__ import annotations

from vaccinepath.models import EscalationTrigger, ScreenFlag, Symptom, TriState

SYMPTOM_LABEL: dict[Symptom, str] = {
    Symptom.difficult_to_awaken: "叫不醒 / 很难唤醒",
    Symptom.confused_or_delirious: "意识混乱 / 说胡话",
    Symptom.crying_inconsolable: "持续哭闹，怎么都安抚不了",
    Symptom.difficulty_breathing: "呼吸困难",
    Symptom.very_lethargic: "极度嗜睡 / 没精神",
    Symptom.skin_pale_or_grey: "肤色苍白或发灰",
    Symptom.bruising_spots: "皮肤出现瘀点 / 瘀斑",
    Symptom.seizure: "抽搐",
    Symptom.drinking_less_and_less_urine: "喝得明显少、尿量明显少",
    Symptom.less_active_than_usual: "比平时明显不活跃",
    Symptom.crying_persistent_consolable: "持续哭闹，但能安抚",
    Symptom.injection_site_redness_swelling_pain: "注射部位红肿痛",
    Symptom.irritability: "烦躁",
    Symptom.mild_rash: "轻微皮疹",
    Symptom.vomiting: "呕吐",
}

RULE_LABEL: dict[str, str] = {
    "urgent_symptom": "急诊指征",
    "urgent_temperature": "体温超过急诊阈值",
    "infant_fever": "3 个月以下婴儿发热",
    "warn_fever_not_reduced_by_medication": "退烧药后仍发热",
    "warn_fever_duration": "发热持续超过 2 天",
    "warn_symptom": "建议就医指征",
    "warn_parent_concern": "家长担心 / 觉得在变差",
}

SCREEN_FIELD_LABEL: dict[str, str] = {
    "previous_serious_reaction": "既往接种后出现过严重反应",
    "known_allergy": "已知过敏（含疫苗成分）",
    "current_illness": "当前正在生病",
    "current_fever": "当前发热",
    "immune_condition": "有免疫相关疾病",
    "immunosuppressive_medication": "正在使用免疫抑制药物",
}

TRI_LABEL: dict[TriState, str] = {TriState.yes: "是", TriState.no: "否", TriState.unsure: "不确定"}

OUTCOME_LABEL = {"CONTINUE": "继续观察", "WARN": "建议看医生", "URGENT": "请立即前往儿童急诊", "CLEAR": "无标记项", "PROFESSIONAL_REVIEW_REQUIRED": "需医生审核"}


def trigger_text(t: EscalationTrigger) -> str:
    detail = t.detail
    try:
        detail = SYMPTOM_LABEL[Symptom(t.detail)]
    except ValueError:
        pass
    return f"{RULE_LABEL.get(t.rule, t.rule)}：{detail}"


def screen_flag_text(f: ScreenFlag) -> str:
    return f"{SCREEN_FIELD_LABEL.get(f.field, f.field)}＝{TRI_LABEL[f.answer]}"
