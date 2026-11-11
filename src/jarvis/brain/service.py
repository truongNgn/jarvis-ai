"""Bounded in-memory task lifecycle. Durable recovery belongs to Phase 4."""
import asyncio
import uuid

from jarvis.brain.graph import TaskAgent
from jarvis.config import Settings
from jarvis.security.policy import Grant
from jarvis.storage.memory import Preferences
from jarvis.tools.native import NAMES, NativeRegistry


class TaskService:
    def __init__(self, broker, adapter, settings=None):
        self.broker, self.adapter = broker, adapter
        self.settings = settings or Settings(tool_timeout=25.0)
        self.preferences = Preferences()
        self.tasks = {}
        self.serial = asyncio.Lock()

    def submit(self, request):
        if len(self.tasks) >= 100:
            raise ValueError("task_capacity_reached_restart_or_clear_completed_tasks")
        project = self.preferences.resolve(request.project_id)
        if any(t != "system_metrics" for t in request.required_tools) and not project:
            return {"status": "clarification_required", "error": "select_configured_project",
                    "projects": self.preferences.choices()}
        ident = str(uuid.uuid4())
        record = {"task_id": ident, "status": "queued", "events": [], "outcome": None,
                  "cancel": asyncio.Event(), "runner": None}
        self.tasks[ident] = record
        record["runner"] = asyncio.create_task(self._run(record, request, project))
        return {"task_id": ident, "status": "queued"}

    async def _run(self, record, request, project):
        try:
            async with self.serial:
                record["status"] = "running"
                enabled = set(self.broker.enabled)
                registry = NativeRegistry(self.broker, record["task_id"], project, enabled)
                grant = Grant("local-user", frozenset(request.required_tools),
                              frozenset({project}) if project else frozenset())
                result = await TaskAgent(self.adapter, registry, self.settings).run(request, grant,
                    record["cancel"], task_id=record["task_id"], on_event=record["events"].append)
                record["outcome"], record["status"] = result.model_dump(), result.status
        except asyncio.CancelledError:
            record["status"] = "cancelled"
        except Exception:
            record["status"] = "failed"
            record["events"].append({"type": "task_error", "error": "task_unavailable"})

    def state(self, ident):
        record = self.tasks[ident]
        return {k: record[k] for k in ("task_id", "status", "events", "outcome")}

    def cancel(self, ident):
        record = self.tasks[ident]
        record["cancel"].set()
        return {"task_id": ident, "stop_requested": True}

    async def close(self):
        for record in self.tasks.values():
            record["cancel"].set()
            record["runner"].cancel()
        await asyncio.gather(*(r["runner"] for r in self.tasks.values()), return_exceptions=True)
        await self.adapter.close()
