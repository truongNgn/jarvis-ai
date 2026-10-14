"""Docker-only Phase 2 capability broker; no model-directed actions yet."""
import json
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from jarvis.contracts import StrictModel
from jarvis.runtime.auth import authorize
from jarvis.runtime.protocol import TOOLS, Rejected, canonical, digest, loads, manifest, result, sign, validate, validate_result


class Submit(StrictModel):
    tool: str = Field(min_length=1, max_length=64)
    args: dict = Field(default_factory=dict)
    call_id: str = Field(default_factory=lambda: str(uuid.uuid4()), pattern=r"^[A-Za-z0-9_-]{1,128}$")
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()), pattern=r"^[A-Za-z0-9_-]{1,128}$")
    timeout: float = Field(default=20.0, gt=0, le=30)


class Broker:
    def __init__(self, path, credentials):
        if set(credentials) != {"admin_token", "runtime_token", "signing_key"} or any(
                type(v) is not str or len(v) != 64 for v in credentials.values()):
            raise ValueError("Invalid broker credentials")
        self.credentials = credentials
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY, hash TEXT, body TEXT, state TEXT, lease TEXT, until REAL, result TEXT, cancelled INTEGER DEFAULT 0)")
        self.db.commit()
        self.enabled = set()

    def register(self, value):
        if type(value) is not dict or set(value) != {"version", "runtime_id", "tools"}:
            raise Rejected("manifest_invalid")
        if value["version"] != 1 or value["runtime_id"] != "desktop-main" or type(value["tools"]) is not dict:
            raise Rejected("manifest_invalid")
        enabled = set(value["tools"])
        if not enabled or enabled - TOOLS.keys() or canonical(value) != canonical(manifest(enabled)):
            raise Rejected("manifest_mismatch")
        with self.lock:
            self.enabled = enabled
        return {"version": 1, "manifest_hash": digest(value)}

    def submit(self, value):
        parsed = Submit.model_validate(value)
        if "task_id" not in value:
            parsed.task_id = parsed.call_id
        body = parsed.model_dump()
        name = body["tool"]
        if name not in TOOLS:
            raise Rejected("unknown_tool")
        validate(body["args"], TOOLS[name]["args"])
        with self.lock, self.db:
            if name not in self.enabled:
                raise Rejected("runtime_not_ready_or_tool_disabled")
            old = self.db.execute("SELECT hash FROM calls WHERE id=?", (body["call_id"],)).fetchone()
            if old:
                if old[0] != digest(body):
                    raise Rejected("call_id_collision")
                return {"call_id": body["call_id"]}
            if self.db.execute("SELECT count(*) FROM calls WHERE state!='completed'").fetchone()[0] >= 100:
                raise Rejected("queue_full")
            call = {"version": 1, "policy_version": 1, "call_id": body["call_id"], "task_id": body["task_id"],
                    "tool": name, "args": body["args"], "deadline": time.time()+body["timeout"],
                    "schema_hash": digest(TOOLS[name]["args"]),
                    "grant": {"principal": "local-user", "tools": [name], "projects": ["jarvis-ai"]}}
            call["signature"] = sign(call, self.credentials["signing_key"])
            self.db.execute("INSERT INTO calls(id,hash,body,state) VALUES(?,?,?,'queued')",
                            (call["call_id"], digest(body), canonical(call)))
            return {"call_id": call["call_id"]}

    def lease(self):
        with self.lock, self.db:
            row = self.db.execute("SELECT id,body FROM calls WHERE cancelled=0 AND (state='queued' OR (state='leased' AND until<?)) ORDER BY rowid LIMIT 1", (time.time(),)).fetchone()
            if not row:
                return {"job": None}
            lease = secrets.token_hex(16)
            self.db.execute("UPDATE calls SET state='leased',lease=?,until=? WHERE id=?", (lease, time.time()+5, row[0]))
            return {"job": {"lease_id": lease, "call": json.loads(row[1])}}

    def state(self, ident):
        with self.lock:
            row = self.db.execute("SELECT state,result,cancelled,body FROM calls WHERE id=?", (ident,)).fetchone()
        if not row:
            raise Rejected("unknown_call")
        return {"call_id": ident, "state": row[0], "result": json.loads(row[1]) if row[1] else None,
                "cancelled": bool(row[2]), "deadline": json.loads(row[3])["deadline"]}

    def cancel(self, ident):
        with self.lock, self.db:
            row = self.db.execute("SELECT body,state FROM calls WHERE id=?", (ident,)).fetchone()
            if not row:
                raise Rejected("unknown_call")
            self.db.execute("UPDATE calls SET cancelled=1 WHERE id=? AND state!='completed'", (ident,))
            if row[1] == "queued":
                output = result(json.loads(row[0]), "cancelled", error="cancelled_before_dispatch")
                self.db.execute("UPDATE calls SET state='completed',result=? WHERE id=?", (canonical(output), ident))
        return self.state(ident)

    def complete(self, value):
        if type(value) is not dict or set(value) != {"lease_id", "result"}:
            raise Rejected("invalid_result_envelope")
        output = value["result"]
        if type(output) is not dict:
            raise Rejected("invalid_result")
        with self.lock, self.db:
            row = self.db.execute("SELECT body,lease,state,result FROM calls WHERE id=?", (output.get("call_id"),)).fetchone()
            if not row or value["lease_id"] != row[1]:
                raise Rejected("stale_lease")
            validate_result(output, json.loads(row[0]))
            if row[2] == "completed" and row[3] != canonical(output):
                raise Rejected("result_collision")
            self.db.execute("UPDATE calls SET state='completed',result=? WHERE id=?", (canonical(output), output["call_id"]))
        return {"accepted": True}


def create_app(broker):
    @asynccontextmanager
    async def lifespan(app):
        yield
        broker.db.close()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.middleware("http")
    async def boundary(request, next_handler):
        try:
            role = "runtime_token" if request.url.path.startswith("/v1/runtime/") else "admin_token"
            authorize(request.headers, broker.credentials[role])
            if request.headers.get("transfer-encoding"):
                raise Rejected("chunked_request_forbidden")
            if request.method == "POST":
                if request.headers.get("content-type", "").split(";")[0] != "application/json":
                    raise Rejected("json_required")
                if not 0 < int(request.headers.get("content-length", "0")) <= 32768:
                    raise Rejected("request_size_invalid")
            return await next_handler(request)
        except (Rejected, ValueError):
            return JSONResponse({"error": "request_rejected"}, status_code=403)

    async def body(request):
        try:
            raw = await request.body()
            if len(raw) > 32768:
                raise Rejected("request_too_large")
            return loads(raw)
        except ValueError:
            raise Rejected("invalid_json")

    @app.exception_handler(Rejected)
    async def rejected(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=400)

    @app.get("/v1/capabilities")
    async def capabilities():
        return manifest(broker.enabled)

    @app.post("/v1/runtime/register")
    async def register(request: Request):
        return broker.register(await body(request))

    @app.get("/v1/runtime/calls")
    async def lease():
        return broker.lease()

    @app.get("/v1/runtime/calls/{ident}/status")
    async def status(ident: str):
        value = broker.state(ident)
        return {"cancelled": value["cancelled"], "deadline": value["deadline"]}

    @app.post("/v1/runtime/results")
    async def complete(request: Request):
        return broker.complete(await body(request))

    @app.post("/v1/calls")
    async def submit(request: Request):
        from pydantic import ValidationError
        try:
            return broker.submit(await body(request))
        except ValidationError:
            raise Rejected("invalid_call")

    @app.get("/v1/calls/{ident}")
    async def state(ident: str):
        return broker.state(ident)

    @app.post("/v1/calls/{ident}/cancel")
    async def cancel(ident: str):
        return broker.cancel(ident)

    return app


def main():
    import uvicorn
    secrets_file = Path("/secrets/bridge.json")
    Path("/state").mkdir(exist_ok=True)
    broker = Broker("/state/bridge.sqlite", json.loads(secrets_file.read_text()))
    uvicorn.run(create_app(broker), host="0.0.0.0", port=18765, access_log=False,
                timeout_keep_alive=2, limit_concurrency=16)


if __name__ == "__main__":
    main()
