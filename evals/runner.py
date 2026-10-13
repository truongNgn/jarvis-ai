"""Live developer corpus. No keyword routing, no real desktop operations."""
import asyncio
import json
import time
from pathlib import Path

from jarvis.brain.graph import TaskAgent
from jarvis.config import Settings
from jarvis.contracts import TaskRequest
from jarvis.llm.llama_cpp import LlamaCppAdapter
from jarvis.security.policy import demo_grant
from jarvis.tools.registry import ToolRegistry


async def main():
    settings = Settings.environment()
    adapter = LlamaCppAdapter(settings)
    results = []
    try:
        health = await adapter.wait_ready()
        for line in Path("evals/cases/core.jsonl").read_text().splitlines():
            case = json.loads(line)
            started = time.monotonic()
            result = await TaskAgent(adapter, ToolRegistry(), settings).run(TaskRequest(text=case["text"]), demo_grant())
            results.append({"id": case["id"], "seconds": round(time.monotonic()-started, 3), **result.model_dump()})
            print(json.dumps({"id": case["id"], "status": result.status, "calls": result.tool_attempts}), flush=True)
        # Failure evidence from real inference, not just a unit fixture.
        failed = await TaskAgent(adapter, ToolRegistry(failures=frozenset({"project_open"})), settings).run(
            TaskRequest(text="Check performance, open jarvis-ai, and report its branch."), demo_grant())
        report = {"health": health, "cases": results, "failure_case": failed.model_dump(),
                  "passed": sum(r["status"] == "succeeded" for r in results), "total": len(results)}
        print("REPORT_JSON=" + json.dumps(report))
        return 0 if report["passed"] == 10 and failed.status != "succeeded" else 1
    finally:
        await adapter.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
