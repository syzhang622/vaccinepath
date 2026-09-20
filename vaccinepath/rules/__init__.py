"""确定性规则引擎。四个函数都是纯函数：Pydantic 入参 → Pydantic 出参，不访问网络/LLM/数据库。"""

from vaccinepath.rules.conflicts import detect_conflicts
from vaccinepath.rules.escalation import post_vaccination_escalate
from vaccinepath.rules.schedule import compute_schedule
from vaccinepath.rules.screening import pre_vaccination_screen

__all__ = ["compute_schedule", "detect_conflicts", "pre_vaccination_screen", "post_vaccination_escalate"]
