"""Three synthetic tools. No imports or access to Windows execution."""
import asyncio
import json
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from jarvis.contracts import ToolCall, ToolResult
from jarvis.security.policy import Grant
from jarvis.tools.schemas import (BranchData, MetricsArgs, MetricsData, ProjectArgs, ProjectData)


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate argument key")
        result[key] = value
    return result


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]

    def wire(self):
        return {"type": "function", "function": {"name": self.name,
            "description": self.description, "parameters": self.input_model.model_json_schema()}}


class ToolRegistry:
    def __init__(self, failures: frozenset[str] = frozenset(), delay: float = 0):
        self.specs: dict[str, ToolSpec] = {}
        self.failures = failures
        self.delay = delay
        self.executed: list[str] = []
        for spec in (
            ToolSpec("system_metrics", "Read synthetic PC performance (CPU and RAM).", MetricsArgs, MetricsData),
            ToolSpec("project_open", "Open configured development project in synthetic VS Code.", ProjectArgs, ProjectData),
            ToolSpec("git_branch", "Read the synthetic current Git branch of a configured project.", ProjectArgs, BranchData),
        ):
            self.register(spec)

    def register(self, spec: ToolSpec):
        if spec.name in self.specs:
            raise ValueError("Duplicate tool registration")
        self.specs[spec.name] = spec

    def manifest(self, grant: Grant) -> list[dict]:
        if grant.principal != "local-user":
            return []
        return [s.wire() for s in self.specs.values() if s.name in grant.tools]

    def validate(self, call: ToolCall, grant: Grant) -> tuple[dict | None, ToolResult | None]:
        spec = self.specs.get(call.name)
        if spec is None or call.name not in grant.tools or grant.principal != "local-user":
            return None, ToolResult(call_id=call.id, tool=call.name, status="denied", error="forbidden_tool")
        try:
            args = json.loads(call.arguments, object_pairs_hook=unique_keys)
            if not isinstance(args, dict):
                raise ValueError("Arguments must be an object")
            validated = spec.input_model.model_validate(args).model_dump()
        except (ValueError, ValidationError):
            return None, ToolResult(call_id=call.id, tool=call.name, status="invalid", error="invalid_arguments")
        if not grant.allows(call.name, validated):
            return None, ToolResult(call_id=call.id, tool=call.name, status="denied", error="forbidden_project")
        return validated, None

    async def execute(self, call: ToolCall, grant: Grant) -> ToolResult:
        args, error = self.validate(call, grant)
        if error:
            return error
        await asyncio.sleep(self.delay)
        self.executed.append(call.name)
        if call.name in self.failures:
            return ToolResult(call_id=call.id, tool=call.name, status="failed", error="fixture_unavailable")
        data = {"system_metrics": {"cpu_percent": 12.5, "ram_used_gib": 8.0, "ram_total_gib": 24.0},
                "project_open": {"project_id": "jarvis-ai", "editor": "VS Code", "opened": True},
                "git_branch": {"project_id": "jarvis-ai", "branch": "feature/phase1-demo"}}[call.name]
        validated = self.specs[call.name].output_model.model_validate(data).model_dump()
        return ToolResult(call_id=call.id, tool=call.name, status="succeeded", data=validated)
