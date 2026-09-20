"""模拟两次唤醒之间家长的动作（demo 用）：把 Mei 的流感任务标完成，并提交一份会触发 URGENT 的接种后打卡。
用法：uv run python scripts/simulate_parent.py
"""

from datetime import UTC, datetime

from vaccinepath.models import Actor, CheckIn, Symptom, TaskStatus, TemperatureSite, VaccineCode
from vaccinepath.store import Store, new_id

s = Store()
inf = next((t for t in s.tasks("child-mei") if t.vaccine == VaccineCode.INF and t.status != TaskStatus.done), None)
if inf:
    s.update_task(inf.id, status=TaskStatus.done, notes="家长：已于今日在 polyclinic 接种")
    s.log(Actor.parent, "task_done", inf.id, "家长标记流感疫苗已接种", child_id="child-mei")
    print("task done:", inf.id)
ck = CheckIn(
    id=new_id("ck"), child_id="child-mei", record_id="rec-mei-10", submitted_at=datetime.now(UTC), days_since_vaccination=1,
    temperature_c=41.3, temperature_site=TemperatureSite.tympanic, fever_duration_hours=6, fever_after_antipyretic=True,
    symptoms=[Symptom.seizure], parent_very_worried=True, free_text="打完流感针第二天高烧，刚才抽了一下",
)
s.put("checkins", ck)
s.log(Actor.parent, "checkin_submitted", ck.id, "家长提交接种后打卡", child_id="child-mei")
print("checkin submitted:", ck.id)
