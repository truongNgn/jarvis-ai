from typing import TypedDict


class TaskState(TypedDict):
    task_id: str
    messages: list[dict]
    pending: list[dict]
    observations: list[dict]
    events: list[dict]
    model_turns: int
    tool_attempts: int
    repairs: int
    terminal: str
    seen_ids: dict[str, dict]
