"""Explicit native tool smoke; requires running broker/runtime and DPAPI setup.

Public evidence omits credentials, window titles and ephemeral window references.
Use --desktop only when editor launch/window activation is authorized.
"""
import argparse
import http.client
import json
import time
import urllib.error
import uuid
from pathlib import Path

from jarvis.runtime.client import Client
from jarvis.security.credentials import load_credentials


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--desktop", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("docs/benchmarks/phase2-windows.json"))
    args = parser.parse_args()
    credentials = load_credentials()
    client = Client("http://127.0.0.1:18765", credentials["admin_token"])
    report = {"synthetic": False, "checks": []}
    ready_until = time.monotonic()+20
    while True:
        try:
            capabilities = client.request("/v1/capabilities")
            if "system.metrics" in capabilities.get("tools", {}):
                break
        except (urllib.error.URLError, http.client.HTTPException, OSError):
            pass
        if time.monotonic() >= ready_until:
            raise RuntimeError("Runtime did not complete capability registration")
        time.sleep(0.25)

    def execute(tool, inputs, ident=None):
        ident = ident or str(uuid.uuid4())
        started = time.monotonic()
        client.request("/v1/calls", {"tool": tool, "args": inputs, "call_id": ident, "task_id": ident})
        until = started+30
        while time.monotonic() < until:
            state = client.request("/v1/calls/"+ident)
            if state["result"]:
                value = state["result"]
                report["checks"].append({"tool": tool, "status": value["status"], "error": value["error"],
                    "verification": value["verification"], "seconds": round(time.monotonic()-started, 3),
                    "data": value["data"] if tool not in {"window.list", "window.activate"} else
                            {"window_count": len(value["data"].get("windows", []))} if tool == "window.list" else value["data"]})
                return value
            time.sleep(0.2)
        raise RuntimeError("Call did not settle before smoke deadline")

    metrics = execute("system.metrics", {})
    git = execute("git.branch", {"project_id": "jarvis-ai"})
    repeated = str(uuid.uuid4())
    first = execute("git.branch", {"project_id": "jarvis-ai"}, repeated)
    second = execute("git.branch", {"project_id": "jarvis-ai"}, repeated)
    report["duplicate_result_identical"] = first == second
    if args.desktop:
        execute("project.open", {"project_id": "jarvis-ai"})
    windows = execute("window.list", {"app_id": "vscode"})
    if args.desktop and windows["data"].get("windows"):
        execute("window.activate", {"window_ref": windows["data"]["windows"][0]["window_ref"]})
    for request in ({"tool": "exec_shell", "args": {"command": "whoami"}},
                    {"tool": "project.open", "args": {"project_id": "other"}},
                    {"tool": "system.metrics", "args": {"approved": True}}):
        try:
            client.request("/v1/calls", request)
            raise RuntimeError("Forbidden request accepted")
        except urllib.error.HTTPError as exc:
            if exc.code != 400:
                raise
    report["unsafe_requests_rejected"] = 3
    # Queue cancellation is tested while Runtime is idle; no new side effect is required.
    report["core_passed"] = metrics["status"] == git["status"] == "succeeded" and first == second
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"core_passed": report["core_passed"], "checks": [
        {"tool": c["tool"], "status": c["status"], "verification": c["verification"]} for c in report["checks"]]}))


if __name__ == "__main__":
    main()
