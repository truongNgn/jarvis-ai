"""Opt-in live native-model development corpus; opens the selected project."""
import argparse
import json
import time
from pathlib import Path

from jarvis.runtime.client import Client
from jarvis.security.credentials import load_credentials


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("docs/benchmarks/phase3-live.json"))
    args = parser.parse_args()
    client = Client("http://127.0.0.1:18765", load_credentials()["admin_token"])
    ready_until = time.monotonic()+20
    while not client.request("/v1/capabilities").get("tools"):
        if time.monotonic() >= ready_until:
            raise RuntimeError("runtime_not_registered")
        time.sleep(0.2)
    rows = []
    for line in Path("evals/cases/mvp.jsonl").read_text(encoding="utf-8").splitlines()[:args.limit]:
        case = json.loads(line)
        start = time.monotonic()
        submitted = client.request("/v1/tasks", {"text": case["text"], "project_id": "jarvis-ai"})
        ident = submitted["task_id"]
        try:
            until = start+150
            while time.monotonic() < until:
                state = client.request("/v1/tasks/"+ident)
                if state["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.2)
            else:
                raise RuntimeError("task_deadline_exceeded")
        except BaseException:
            client.request("/v1/tasks/"+ident+"/cancel", {})
            raise
        rows.append({"id": case["id"], "seconds": round(time.monotonic()-start, 3), **state})
        print(json.dumps({"id": case["id"], "status": state["status"], "seconds": rows[-1]["seconds"]}), flush=True)
        report = {"synthetic": False, "corpus": "mvp development smoke, not held-out acceptance",
                  "passed": sum(r["status"] == "succeeded" for r in rows), "total": len(rows), "cases": rows}
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if rows and all(r["status"] == "succeeded" for r in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
