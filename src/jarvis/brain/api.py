"""Task routes share the broker's authenticated local-user boundary."""
from fastapi import Request

from jarvis.contracts import TaskRequest
from jarvis.runtime.protocol import Rejected, loads


def install(app, service):
    @app.post("/v1/tasks")
    async def submit(request: Request):
        try:
            raw = await request.body()
            if len(raw) > 32768:
                raise ValueError("too_large")
            value = loads(raw)
            # A missing native project selection must be clarified, not defaulted.
            task = TaskRequest.model_validate({"project_id": None, **value})
            return service.submit(task)
        except (ValueError, TypeError):
            raise Rejected("invalid_task")

    @app.get("/v1/tasks/{ident}")
    async def state(ident: str):
        try:
            return service.state(ident)
        except KeyError:
            raise Rejected("unknown_task")

    @app.post("/v1/tasks/{ident}/cancel")
    async def cancel(ident: str):
        try:
            return service.cancel(ident)
        except KeyError:
            raise Rejected("unknown_task")
