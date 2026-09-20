"""Mock 数据层：单文件 JSON（data/db.json）+ 文件锁。gateway 里的工具和 Streamlit 都读写它。

不是数据库，是原型用的最小持久化。VACCINEPATH_DATA_DIR 指定目录（默认仓库根 data/，gitignored）。
"""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel

from vaccinepath.models import Actor, AuditLogEntry, CheckIn, Child, Family, Task, TaskStatus, TaskType, VaccinationRecord

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = Path(__file__).parent / "data" / "mock_family.json"
COLLECTIONS = ("families", "children", "records", "tasks", "screenings", "checkins")


def data_dir() -> Path:
    return Path(os.environ.get("VACCINEPATH_DATA_DIR", REPO_ROOT / "data"))


def db_path() -> Path:
    return data_dir() / "db.json"


def now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _empty() -> dict[str, Any]:
    return {**{c: {} for c in COLLECTIONS}, "notifications": [], "audit_log": [], "settings": {"reminder_repeat_hours": 24, "max_reminders": 3}, "agent": {}}


def _dump(obj: Any) -> Any:
    return obj.model_dump(mode="json") if isinstance(obj, BaseModel) else obj


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps(_empty(), ensure_ascii=False, indent=2))

    # ---- 底层读写 ----
    @contextmanager
    def _locked(self) -> Iterator[dict[str, Any]]:
        lock = self.path.with_suffix(".lock")
        with open(lock, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                data = json.loads(self.path.read_text())
                yield data
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))
                tmp.replace(self.path)
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)

    def read(self) -> dict[str, Any]:
        return json.loads(self.path.read_text())

    def reset_from_seed(self, seed: Path = SEED_PATH) -> None:
        shutil.copy(seed, self.path)

    # ---- 通用 ----
    def put(self, collection: str, obj: BaseModel) -> None:
        with self._locked() as d:
            d[collection][obj.id] = _dump(obj)  # type: ignore[attr-defined]

    def get(self, collection: str, id: str) -> dict[str, Any] | None:
        return self.read()[collection].get(id)

    def list(self, collection: str, **where: Any) -> list[dict[str, Any]]:
        return [v for v in self.read()[collection].values() if all(v.get(k) == val for k, val in where.items())]

    # ---- 类型化访问 ----
    def families(self) -> list[Family]:
        return [Family(**f) for f in self.list("families")]

    def child(self, child_id: str) -> Child:
        raw = self.get("children", child_id)
        if raw is None:
            raise KeyError(f"child {child_id} not found")
        return Child(**raw)

    def children(self, family_id: str | None = None) -> list[Child]:
        return [Child(**c) for c in (self.list("children", family_id=family_id) if family_id else self.list("children"))]

    def records(self, child_id: str) -> list[VaccinationRecord]:
        return [VaccinationRecord(**r) for r in self.list("records", child_id=child_id)]

    def tasks(self, child_id: str | None = None, status: TaskStatus | None = None) -> list[Task]:
        where: dict[str, Any] = {}
        if child_id:
            where["child_id"] = child_id
        if status:
            where["status"] = status.value
        return sorted((Task(**t) for t in self.list("tasks", **where)), key=lambda t: (t.due_date or datetime.max.date(), t.created_at))

    def checkins(self, child_id: str | None = None) -> list[CheckIn]:
        return [CheckIn(**c) for c in (self.list("checkins", child_id=child_id) if child_id else self.list("checkins"))]

    def settings(self) -> dict[str, Any]:
        return self.read()["settings"]

    def agent_state(self) -> dict[str, Any]:
        return self.read().get("agent", {})

    def set_agent_state(self, **kv: Any) -> None:
        with self._locked() as d:
            d.setdefault("agent", {}).update(kv)

    # ---- 任务 ----
    def find_open_task(self, child_id: str, type: TaskType, vaccine: str | None, dose_number: int | None) -> Task | None:
        for t in self.tasks(child_id):
            if t.type == type and t.status not in (TaskStatus.done, TaskStatus.cancelled) and (t.vaccine or None) == (vaccine or None) and t.dose_number == dose_number:
                return t
        return None

    def update_task(self, task_id: str, **fields: Any) -> Task:
        with self._locked() as d:
            raw = d["tasks"].get(task_id)
            if raw is None:
                raise KeyError(f"task {task_id} not found")
            raw.update({k: _dump(v) for k, v in fields.items()})
            raw["updated_at"] = now().isoformat()
            return Task(**raw)

    def update_doc(self, collection: str, id: str, **fields: Any) -> dict[str, Any]:
        with self._locked() as d:
            raw = d[collection].get(id)
            if raw is None:
                raise KeyError(f"{collection}/{id} not found")
            raw.update({k: _dump(v) for k, v in fields.items()})
            return raw

    # ---- 通知（mock）与日志 ----
    def notify(self, child_id: str, task_id: str | None, channel: str, message: str) -> dict[str, Any]:
        n = {"id": new_id("ntf"), "timestamp": now().isoformat(), "child_id": child_id, "task_id": task_id, "channel": channel, "message": message, "delivered": True}
        with self._locked() as d:
            d["notifications"].append(n)
        return n

    def log(self, actor: Actor, action: str, input_summary: str, output_summary: str, *, child_id: str | None = None, source: str | None = None, human_decision: str | None = None) -> AuditLogEntry:
        e = AuditLogEntry(id=new_id("log"), timestamp=now(), actor=actor, action=action, child_id=child_id, input_summary=input_summary[:500], output_summary=output_summary[:1000], source=source, human_decision=human_decision)
        with self._locked() as d:
            d["audit_log"].append(_dump(e))
        return e

    def audit_log(self, child_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        entries = self.read()["audit_log"]
        if child_id:
            entries = [e for e in entries if e.get("child_id") == child_id]
        return entries[-limit:]

    def notifications(self, child_id: str | None = None) -> list[dict[str, Any]]:
        ns = self.read()["notifications"]
        return [n for n in ns if n["child_id"] == child_id] if child_id else ns
