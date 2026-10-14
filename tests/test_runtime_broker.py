import time

import pytest
from fastapi.testclient import TestClient

from jarvis.runtime.protocol import Rejected, manifest, result, validate_call
from jarvis.runtime.server import Broker, create_app

CREDS = {"admin_token": "a"*64, "runtime_token": "b"*64, "signing_key": "c"*64}


@pytest.fixture
def broker(tmp_path):
    instance = Broker(tmp_path / "broker.sqlite", CREDS)
    yield instance
    instance.db.close()


def test_manifest_and_signed_roundtrip(broker):
    broker.register(manifest())
    ident = broker.submit({"tool": "git.branch", "args": {"project_id": "jarvis-ai"}})["call_id"]
    job = broker.lease()["job"]
    call = job["call"]
    validate_call(call, CREDS["signing_key"], list(manifest()["tools"]))
    output = result(call, "succeeded", {"project_id": "jarvis-ai", "state": "branch", "branch": "main", "commit": "a"*40}, verification="verified")
    broker.complete({"lease_id": job["lease_id"], "result": output})
    assert broker.state(ident)["result"] == output


def test_broker_refuses_unknown_or_disabled_tools(broker):
    broker.register(manifest({"git.branch"}))
    for tool, args in [("exec_shell", {}), ("project.open", {"project_id": "jarvis-ai"}),
                       ("git.branch", {"project_id": "other"})]:
        with pytest.raises(Rejected):
            broker.submit({"tool": tool, "args": args})


def test_changed_manifest_rejected(broker):
    value = manifest()
    value["tools"]["git.branch"]["schema_hash"] = "tampered"
    with pytest.raises(Rejected):
        broker.register(value)
    value = manifest()
    value["version"] = True
    with pytest.raises(Rejected):
        broker.register(value)


def test_duplicate_call_and_collision(broker):
    broker.register(manifest())
    value = {"call_id": "fixed", "task_id": "task", "tool": "system.metrics", "args": {}}
    assert broker.submit(value) == broker.submit(value)
    with pytest.raises(Rejected):
        broker.submit({**value, "tool": "git.branch", "args": {"project_id": "jarvis-ai"}})
    implicit_task = {"call_id": "implicit-task", "tool": "system.metrics"}
    assert broker.submit(implicit_task) == broker.submit(implicit_task)


def test_cancelled_queue_does_not_dispatch(broker):
    broker.register(manifest())
    ident = broker.submit({"tool": "system.metrics"})["call_id"]
    assert broker.cancel(ident)["result"]["status"] == "cancelled"
    assert broker.lease()["job"] is None


def test_stale_lease_rejected(broker):
    broker.register(manifest())
    broker.submit({"tool": "system.metrics"})
    job = broker.lease()["job"]
    with pytest.raises(Rejected):
        broker.complete({"lease_id": "wrong", "result": result(job["call"], "failed", error="x")})


def test_http_auth_role_origin_host_and_schema(broker):
    client = TestClient(create_app(broker), base_url="http://127.0.0.1:18765")
    admin = {"Authorization": "Bearer " + CREDS["admin_token"]}
    runtime = {"Authorization": "Bearer " + CREDS["runtime_token"]}
    assert client.get("/v1/capabilities").status_code == 403
    assert client.get("/v1/runtime/calls", headers=admin).status_code == 403
    assert client.get("/v1/capabilities", headers=runtime).status_code == 403
    assert client.get("/v1/capabilities", headers={**admin, "Origin": "https://evil"}).status_code == 403
    assert client.get("/v1/capabilities", headers={**admin, "Host": "evil"}).status_code == 403
    assert client.post("/v1/runtime/register", json=manifest(), headers=runtime).status_code == 200
    assert client.post("/v1/calls", json={"tool": "system.metrics", "approved": True}, headers=admin).status_code == 400
    assert client.post("/v1/calls", json={"tool": "system.metrics", "args": {"shell": True}}, headers=admin).status_code == 400
    assert client.post("/v1/calls", json={"tool": "system.metrics"}, headers=admin).status_code == 200
