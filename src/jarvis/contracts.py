"""Versioned, strict boundary types. Authority never comes from the model."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ToolCall(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=64)
    arguments: str = Field(max_length=2048)

    def wire(self) -> dict:
        return {"id": self.id, "type": "function", "function": {
            "name": self.name, "arguments": self.arguments}}


class ModelReply(StrictModel):
    content: str = Field(default="", max_length=4000)
    calls: list[ToolCall] = Field(default_factory=list, max_length=8)


class ToolResult(StrictModel):
    version: Literal[1] = 1
    call_id: str
    tool: str
    status: Literal["succeeded", "failed", "denied", "invalid", "cancelled"]
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    synthetic: Literal[True] = True


class TaskRequest(StrictModel):
    version: Literal[1] = 1
    text: str = Field(min_length=1, max_length=1500)
    project_id: Literal["jarvis-ai"] = "jarvis-ai"
    required_tools: list[Literal["system_metrics", "project_open", "git_branch"]] = Field(
        default_factory=lambda: ["system_metrics", "project_open", "git_branch"], max_length=3)


class TaskOutcome(StrictModel):
    version: Literal[1] = 1
    task_id: str
    status: Literal["succeeded", "partial", "failed", "cancelled", "timeout"]
    summary: str
    observations: list[ToolResult]
    events: list[dict[str, Any]]
    model_turns: int
    tool_attempts: int
    synthetic: Literal[True] = True
