"""Text CLI with explicit outcome goals and synthetic-mode disclosure."""
import argparse
import asyncio
import json
import signal
from pathlib import Path

from jarvis.brain.graph import TaskAgent
from jarvis.config import Settings
from jarvis.contracts import TaskRequest
from jarvis.llm.llama_cpp import LlamaCppAdapter
from jarvis.security.policy import demo_grant
from jarvis.tools.registry import ToolRegistry


async def run(args):
    settings = Settings.environment()
    adapter = LlamaCppAdapter(settings)
    cancel = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, cancel.set)
    try:
        await adapter.wait_ready(cancel)
        outcome = await TaskAgent(adapter, ToolRegistry(failures=frozenset(args.fail_tool)), settings).run(
            TaskRequest(text=args.text, required_tools=args.expect), demo_grant(), cancel)
        data = outcome.model_dump()
        print(json.dumps(data, indent=2) if args.json else outcome.summary)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return 0 if outcome.status == "succeeded" else 2
    except asyncio.CancelledError:
        print(json.dumps({"status": "cancelled", "synthetic": True}))
        return 2
    except Exception as exc:
        print(json.dumps({"status": "unavailable", "error_type": type(exc).__name__,
                          "synthetic": True}))
        return 2
    finally:
        await adapter.close()


def main():
    parser = argparse.ArgumentParser(description="JARVIS Phase 1: all tools are synthetic")
    parser.add_argument("text")
    parser.add_argument("--expect", nargs="+", choices=["system_metrics", "project_open", "git_branch"],
                        default=["system_metrics", "project_open", "git_branch"],
                        help="Trusted task goals; default is the three-action demo, not keyword intent matching")
    parser.add_argument("--fail-tool", action="append", default=[],
                        choices=["system_metrics", "project_open", "git_branch"])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
