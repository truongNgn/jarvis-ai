"""Deterministic native goal verification; prose is never completion evidence."""
import json

from jarvis.contracts import TaskOutcome, ToolResult


def finalize(state, request):
    observations = [ToolResult.model_validate(r) for r in state["observations"]]
    evidence = {}
    for r in observations:
        if r.synthetic or r.status != "succeeded" or r.verification != "verified":
            continue
        if r.tool == "git_branch" and (r.data.get("project_id") != request.project_id
                or r.data.get("state") == "not_a_repository"):
            continue
        if r.tool == "project_open" and r.data.get("project_id") != request.project_id:
            continue
        evidence[r.tool] = r
    missing = sorted(set(request.required_tools) - evidence.keys())
    terminal = state["terminal"]
    status = terminal if terminal in {"cancelled", "timeout"} else (
        "succeeded" if not missing and terminal == "model_finished" else
        "partial" if observations and any(r.status == "succeeded" for r in observations) else "failed")
    lines = [f"{r.tool}: {json.dumps(r.data, sort_keys=True)} ({r.verification})"
             if r.status == "succeeded" else f"{r.tool}: {r.status} ({r.error})" for r in observations]
    if not lines:
        lines.append("No verified Runtime result.")
    if missing:
        lines.append("Unfulfilled goals: " + ", ".join(missing))
    if terminal != "model_finished":
        lines.append("Stopped: " + terminal)
    return TaskOutcome(task_id=state["task_id"], status=status, summary="\n".join(lines),
        observations=observations, events=state["events"], model_turns=state["model_turns"],
        tool_attempts=state["tool_attempts"], synthetic=False)
