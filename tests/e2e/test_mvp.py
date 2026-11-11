"""Graph + native broker protocol integration without personal desktop effects."""
import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from jarvis.brain.graph import TaskAgent
from jarvis.brain.service import TaskService
from jarvis.config import Settings
from jarvis.contracts import ModelReply, TaskRequest, ToolCall
from jarvis.runtime.protocol import manifest, result
from jarvis.runtime.server import Broker, create_app
from jarvis.security.policy import demo_grant
from jarvis.tools.native import NAMES, NativeRegistry

CREDS = {"admin_token": "a"*64, "runtime_token": "b"*64, "signing_key": "c"*64}


class Model:
    def __init__(self, order):
        self.order = iter(order)
        self.messages = []
        self.schemas = []

    async def complete(self, messages, tools):
        self.messages.append(list(messages))
        self.schemas = tools
        name = next(self.order, None)
        if not name:
            return ModelReply(content="All actions completed!")
        return ModelReply(calls=[ToolCall(id=str(len(self.messages)), name=name,
            arguments=json.dumps({} if name == "system_metrics" else {"project_id": "jarvis-ai"}))])

    async def close(self):
        pass


@pytest.fixture
def broker(tmp_path):
    value = Broker(tmp_path / "bridge.sqlite", CREDS)
    value.register(manifest())
    yield value
    value.db.close()


def observation(call, failure=None, verified=True, nonrepo=False):
    if call["tool"] == failure:
        return result(call, "failed", error="editor_absent")
    data = {
        "system.metrics": {"cpu_percent": 7.0, "ram_used_bytes": 10, "ram_total_bytes": 20,
            "disk_free_bytes": 10, "disk_total_bytes": 20, "sample_time": time.time(), "sample_seconds": 0.1,
            "gpu": {"available": False, "reason": "unavailable"}},
        "git.branch": {"project_id": "jarvis-ai", "state": "not_a_repository" if nonrepo else "branch",
                       "branch": "" if nonrepo else "main", "commit": "" if nonrepo else "a"*40},
        "project.open": {"project_id": "jarvis-ai", "launch_requested": True, "matching_window_count": 1}}
    if verified:
        data["project.open"]["workspace_evidence"] = {"method": "vscode_workspace_api",
            "request_id": "d"*32, "verified_at": time.time()}
    return result(call, "succeeded", data[call["tool"]],
                  verification="unverified" if call["tool"] == "project.open" and not verified else "verified")


async def worker(broker, **options):
    while True:
        job = broker.lease()["job"]
        if job:
            broker.complete({"lease_id": job["lease_id"], "result": observation(job["call"], **options)})
        await asyncio.sleep(0.005)


async def run(broker, order, **options):
    model = Model(order)
    runtime = asyncio.create_task(worker(broker, **options))
    try:
        registry = NativeRegistry(broker, "task", "jarvis-ai", broker.enabled)
        outcome = await TaskAgent(model, registry, Settings(tool_timeout=1.0)).run(
            TaskRequest(text="Check PC, open jarvis-ai and read the branch."), demo_grant())
        return outcome, model
    finally:
        runtime.cancel()
        await asyncio.gather(runtime, return_exceptions=True)


@pytest.mark.parametrize("order", [list(NAMES), list(reversed(NAMES)),
                                  ["project_open", "git_branch", "system_metrics"]])
async def test_real_protocol_observations_and_changed_order(broker, order):
    outcome, model = await run(broker, order)
    assert outcome.status == "succeeded" and not outcome.synthetic
    assert all(not r.synthetic for r in outcome.observations)
    assert [r.tool for r in outcome.observations] == order
    assert json.loads(model.messages[1][-1]["content"])["synthetic"] is False
    assert {s["function"]["name"] for s in model.schemas} == set(NAMES)


@pytest.mark.parametrize("options", [{"failure": "project.open"}, {"verified": False}, {"nonrepo": True}])
async def test_partial_outcomes_not_hidden_by_model_prose(broker, options):
    outcome, _ = await run(broker, list(NAMES), **options)
    assert outcome.status == "partial" and "Unfulfilled goals:" in outcome.summary
    assert "All actions completed!" not in outcome.summary


async def test_model_stops_early(broker):
    outcome, _ = await run(broker, ["system_metrics"])
    assert outcome.status == "partial" and "project_open" in outcome.summary


async def test_missing_tool_hidden_and_denied(broker):
    broker.register(manifest({"system.metrics", "git.branch"}))
    outcome, model = await run(broker, list(NAMES))
    assert outcome.status == "partial"
    assert "project_open" not in {s["function"]["name"] for s in model.schemas}
    assert outcome.observations[-1].status == "denied"
    assert broker.db.execute("SELECT count(*) FROM calls WHERE json_extract(body,'$.tool')='project.open'").fetchone()[0] == 0


async def test_runtime_disconnect_timeout_cancels_queued_call(broker):
    registry = NativeRegistry(broker, "task", "jarvis-ai", broker.enabled)
    outcome = await TaskAgent(Model(["system_metrics"]), registry, Settings(tool_timeout=0.05)).run(
        TaskRequest(text="Read metrics", required_tools=["system_metrics"]), demo_grant())
    assert outcome.status == "failed"
    assert broker.lease()["job"] is None


async def test_tasks_serialize_and_cancel_without_more_dispatch(broker):
    class Slow(Model):
        active = 0
        peak = 0
        async def complete(self, messages, tools):
            self.active += 1
            self.peak = max(self.active, self.peak)
            try:
                await asyncio.sleep(0.02)
                return ModelReply()
            finally:
                self.active -= 1
    model = Slow([])
    service = TaskService(broker, model)
    ids = [service.submit(TaskRequest(text="metrics", required_tools=["system_metrics"]))["task_id"] for _ in range(2)]
    service.cancel(ids[1])
    await asyncio.gather(*(r["runner"] for r in service.tasks.values()))
    assert model.peak == 1 and service.state(ids[1])["status"] == "cancelled"
    await service.close()


def test_task_api_auth_project_clarification_and_unknown_id(broker):
    service = TaskService(broker, Model([]))
    client = TestClient(create_app(broker, service), base_url="http://127.0.0.1:18765")
    auth = {"Authorization": "Bearer " + CREDS["admin_token"]}
    assert client.post("/v1/tasks", json={"text": "open my project"}).status_code == 403
    response = client.post("/v1/tasks", json={"text": "open my project"}, headers=auth)
    assert response.json()["status"] == "clarification_required" and not service.tasks
    response = client.post("/v1/tasks", json={"text": "open other", "project_id": "other"}, headers=auth)
    assert response.json()["status"] == "clarification_required"
    assert client.get("/v1/tasks/unknown", headers=auth).status_code == 400
    assert client.post("/v1/tasks", json={"text": "x", "approved": True}, headers=auth).status_code == 400
