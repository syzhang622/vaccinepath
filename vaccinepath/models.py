"""全部领域数据模型（Pydantic）。规则引擎四个函数的入参/出参也在这里，队友基于它写测试。"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------


class VaccineCode(StrEnum):
    """NCIS 2026-04 表中出现的疫苗（抗原）代码，与 data/ncis_2026_04.json 的 code 字段一致。"""

    BCG = "BCG"
    HepB = "HepB"
    DTaP = "DTaP"
    Tdap = "Tdap"
    IPV = "IPV"
    Hib = "Hib"
    PCV13 = "PCV13"
    PPSV23 = "PPSV23"
    MMR = "MMR"
    VAR = "VAR"
    HPV2 = "HPV2"
    INF = "INF"


class Sex(StrEnum):
    female = "female"
    male = "male"


class RecordSource(StrEnum):
    polyclinic = "polyclinic"
    private_clinic = "private_clinic"
    school_programme = "school_programme"
    overseas = "overseas"
    parent_reported = "parent_reported"


class ScheduleStatus(StrEnum):
    completed = "completed"
    upcoming = "upcoming"  # as_of < due_date
    due = "due"  # due_date <= as_of <= overdue_date
    overdue = "overdue"  # as_of > overdue_date；补种时间需医生确认
    needs_clinician = "needs_clinician"  # PDF 未给规则，无法确定性排程
    not_applicable = "not_applicable"


class Severity(StrEnum):
    error = "error"  # 数据本身不可能成立（早于出生、未来日期、同日重复）
    warning = "warning"  # 可疑但不阻断
    review = "review"  # 需医生/人工确认


class TriState(StrEnum):
    yes = "yes"
    no = "no"
    unsure = "unsure"


class ScreenOutcome(StrEnum):
    CLEAR = "CLEAR"
    PROFESSIONAL_REVIEW_REQUIRED = "PROFESSIONAL_REVIEW_REQUIRED"


class EscalationOutcome(StrEnum):
    CONTINUE = "CONTINUE"  # 继续按计划打卡
    WARN = "WARN"  # 转人工审核（Professional Review Required）
    URGENT = "URGENT"  # Urgent Assessment Required：立即就医


class TaskType(StrEnum):
    vaccination_due = "vaccination_due"
    reminder = "reminder"
    post_vaccination_checkin = "post_vaccination_checkin"
    professional_review = "professional_review"
    clarification = "clarification"


class TaskStatus(StrEnum):
    open = "open"
    awaiting_parent = "awaiting_parent"
    awaiting_review = "awaiting_review"
    done = "done"
    cancelled = "cancelled"


class Actor(StrEnum):
    agent = "agent"
    rule_engine = "rule_engine"
    parent = "parent"
    clinician = "clinician"
    system = "system"


# ---------------------------------------------------------------------------
# 档案 / 记录
# ---------------------------------------------------------------------------


class Family(BaseModel):
    id: str
    guardian_name: str
    contact: str | None = None
    timezone: str = "Asia/Singapore"


class Child(BaseModel):
    id: str
    family_id: str
    name: str
    date_of_birth: date
    sex: Sex
    attends_local_school: bool = Field(default=True, description="False 时 HPV2 走校外规则（p3）")
    high_risk_condition: bool = Field(default=False, description="有 NCIS 列出的高危状况；True 时相关项一律转医生评估")
    high_risk_notes: str | None = None
    notes: str | None = None


class VaccinationRecord(BaseModel):
    """一次接种事件。联合疫苗（如 6-in-1）在 vaccines 里列出全部抗原。"""

    id: str
    child_id: str
    date: date
    vaccines: list[VaccineCode] = Field(min_length=1)
    product: str | None = Field(default=None, description="如 '6-in-1', 'MMRV', 'Tdap-IPV'；海外记录可填原名")
    dose_label: str | None = Field(default=None, description="记录上写的剂次标签，如 'D1'/'B1'；仅用于交叉核对")
    source: RecordSource
    country: str | None = None
    verified: bool = Field(default=False, description="海外/家长自报记录是否已由人工核实")
    notes: str | None = None

    @model_validator(mode="after")
    def _no_duplicate_antigen(self) -> VaccinationRecord:
        if len(set(self.vaccines)) != len(self.vaccines):
            raise ValueError("vaccines 内不能重复列同一抗原")
        return self


class Task(BaseModel):
    id: str
    child_id: str
    type: TaskType
    title: str
    status: TaskStatus = TaskStatus.open
    due_date: date | None = None
    vaccine: VaccineCode | None = None
    dose_number: int | None = None
    reminder_count: int = 0
    last_reminded_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    notes: str | None = None


class AuditLogEntry(BaseModel):
    """全程日志：输入、动作、来源、时间、输出、人工决定。"""

    id: str
    timestamp: datetime
    actor: Actor
    action: str
    child_id: str | None = None
    input_summary: str
    output_summary: str
    source: str | None = Field(default=None, description="依据来源，如 'NCIS 2026-04 p3'")
    human_decision: str | None = None


# ---------------------------------------------------------------------------
# compute_schedule
# ---------------------------------------------------------------------------


class ScheduleInput(BaseModel):
    child: Child
    records: list[VaccinationRecord] = Field(default_factory=list)
    as_of: date


class ScheduleItem(BaseModel):
    vaccine: VaccineCode
    dose_number: int
    label: str = Field(description="NCIS 表上的标签：D1/D2/D3/B1/B2；INF 为 'annual'")
    status: ScheduleStatus
    due_date: date | None = None
    overdue_date: date | None = None
    given_date: date | None = None
    matched_record_id: str | None = None
    product_hint: str | None = None
    clinician_confirmation_required: bool = Field(
        default=False, description="True：剂次本身确定，但补种时间/剂型需医生确认（PDF 未给规则）"
    )
    reason: str = Field(description="人类可读的判定依据")
    source_ref: str = Field(description="NCIS 2026-04 页码或原则编号")


class ScheduleResult(BaseModel):
    child_id: str
    as_of: date
    age_months: int
    items: list[ScheduleItem]
    counts: dict[str, int]
    requires_clinician_review: bool


# ---------------------------------------------------------------------------
# detect_conflicts
# ---------------------------------------------------------------------------


class ConflictInput(BaseModel):
    child: Child
    records: list[VaccinationRecord] = Field(default_factory=list)
    as_of: date


class ConflictIssue(BaseModel):
    code: Literal[
        "before_birth",
        "future_date",
        "duplicate_same_day",
        "duplicate_dose_label",
        "dose_order",
        "extra_doses",
        "earlier_than_schedule",
        "overseas_unverified",
        "mmrv_dose1_under_48m",
        "mmrv_over_max_age",
        "hpv_not_indicated",
    ]
    severity: Severity
    vaccine: VaccineCode | None = None
    record_ids: list[str]
    message: str
    source_ref: str


class ConflictReport(BaseModel):
    child_id: str
    issues: list[ConflictIssue]
    has_blocking_errors: bool
    requires_clinician_review: bool
    clean: bool


# ---------------------------------------------------------------------------
# pre_vaccination_screen
# ---------------------------------------------------------------------------


class ScreeningAnswers(BaseModel):
    """接种前安全筛查问卷（proposal 四类 + 当前发热）。任何 yes/unsure 都不由本系统判定是否可打。"""

    previous_serious_reaction: TriState
    previous_reaction_details: str | None = None
    known_allergy: TriState
    allergy_details: str | None = None
    current_illness: TriState
    current_fever: TriState
    immune_condition: TriState
    immunosuppressive_medication: TriState


class ScreenInput(BaseModel):
    child_id: str
    planned_vaccines: list[VaccineCode] = Field(min_length=1)
    answers: ScreeningAnswers
    answered_by: Actor = Actor.parent
    answered_at: datetime


class ScreenFlag(BaseModel):
    field: str
    answer: TriState
    reason: str


class ScreenResult(BaseModel):
    child_id: str
    outcome: ScreenOutcome
    flags: list[ScreenFlag]
    incomplete: bool = Field(description="有 unsure 答案")
    disclaimer: str
    source_ref: str


# ---------------------------------------------------------------------------
# post_vaccination_escalate
# ---------------------------------------------------------------------------


class Symptom(StrEnum):
    difficulty_breathing = "difficulty_breathing"
    seizure = "seizure"
    unresponsive_or_very_drowsy = "unresponsive_or_very_drowsy"
    swelling_face_lips_tongue = "swelling_face_lips_tongue"
    widespread_hives = "widespread_hives"
    persistent_crying = "persistent_crying"
    vomiting = "vomiting"
    reduced_feeding = "reduced_feeding"
    localised_rash = "localised_rash"
    injection_site_large_swelling = "injection_site_large_swelling"
    injection_site_mild = "injection_site_mild"
    irritability = "irritability"


class CheckIn(BaseModel):
    """接种后结构化打卡。"""

    id: str
    child_id: str
    record_id: str
    submitted_at: datetime
    days_since_vaccination: int = Field(ge=0)
    temperature_c: float | None = Field(default=None, ge=30, le=45)
    fever_duration_hours: int | None = Field(default=None, ge=0)
    symptoms: list[Symptom] = Field(default_factory=list)
    persistent_crying_hours: float | None = Field(default=None, ge=0)
    vomiting_episodes_24h: int | None = Field(default=None, ge=0)
    symptoms_worsening: bool = False
    parent_very_worried: bool = False
    free_text: str | None = None


class EscalationCriteria(BaseModel):
    """升级阈值。**团队自定，非 MOH 来源**，上线前须医生签字；放在模型里以便审核与测试固定。"""

    urgent_symptoms: set[Symptom] = Field(
        default_factory=lambda: {
            Symptom.difficulty_breathing,
            Symptom.seizure,
            Symptom.unresponsive_or_very_drowsy,
            Symptom.swelling_face_lips_tongue,
            Symptom.widespread_hives,
        }
    )
    urgent_temperature_c: float = 40.0
    infant_fever_age_months_lt: int = 3
    infant_fever_temperature_c: float = 38.0
    warn_temperature_c: float = 38.5
    warn_fever_duration_hours: int = 48
    warn_persistent_crying_hours: float = 3.0
    warn_vomiting_episodes_24h: int = 3
    warn_symptoms: set[Symptom] = Field(
        default_factory=lambda: {
            Symptom.injection_site_large_swelling,
            Symptom.reduced_feeding,
            Symptom.localised_rash,
        }
    )
    warn_symptom_persist_days: int = 7


class EscalationInput(BaseModel):
    child: Child
    checkin: CheckIn
    criteria: EscalationCriteria = Field(default_factory=EscalationCriteria)


class EscalationTrigger(BaseModel):
    rule: str
    detail: str


class EscalationResult(BaseModel):
    child_id: str
    checkin_id: str
    outcome: EscalationOutcome
    triggers: list[EscalationTrigger]
    next_checkin_in_hours: int | None = Field(description="CONTINUE 时下一次打卡间隔；其他为 None")
    disclaimer: str
    source_ref: str
