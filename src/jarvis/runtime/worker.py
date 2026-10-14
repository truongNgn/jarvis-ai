import sys

from jarvis.runtime.protocol import Rejected, canonical, loads, result, validate_call, validate_result


def run(payload):
    from jarvis.runtime.tools import git, metrics, projects, windows
    call, config, credentials = payload["call"], payload["config"], payload["credentials"]
    validate_call(call, credentials["signing_key"], config["allowed_tools"])
    key = credentials["runtime_token"]
    tool, args = call["tool"], call["args"]
    if tool == "system.metrics":
        data = metrics.collect(config)
    elif tool == "git.branch":
        data = git.branch(config, args["project_id"])
    elif tool == "project.open":
        data = projects.open_project(config, args["project_id"], key)
    elif tool == "window.list":
        data = windows.list_windows(config, key)
    elif tool == "window.activate":
        data = windows.activate(config, key, args["window_ref"])
    else:
        raise Rejected("unknown_tool")
    output = result(call, "succeeded", data, verification="unverified" if tool == "project.open" else "verified")
    return validate_result(output, call)


if __name__ == "__main__":
    payload = loads(sys.stdin.read(65537))
    try:
        output = run(payload)
    except (Rejected, OSError, ValueError) as exc:
        code = str(exc) if isinstance(exc, Rejected) else type(exc).__name__
        output = result(payload["call"], "failed", error=code[:128])
    print(canonical(output))
