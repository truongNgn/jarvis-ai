"""Isolated bounded tool workers; terminate only the worker, never unrelated apps."""
import os
import subprocess
import sys
import time

from jarvis.runtime.protocol import TOOLS, canonical, loads, result


def execute(call, config, credentials, cancelled):
    process = subprocess.Popen([sys.executable, "-m", "jarvis.runtime.worker"], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    payload = canonical({"call": call, "config": config, "credentials": {
        "signing_key": credentials["signing_key"], "runtime_token": credentials["runtime_token"]}})
    deadline = time.monotonic() + max(0, min(call["deadline"]-time.time(), TOOLS[call["tool"]]["timeout"]))
    first = True
    try:
        while True:
            try:
                output, error = process.communicate(payload if first else None, timeout=0.2)
                if process.returncode != 0 or len(output.encode()) > 32768:
                    return result(call, "unknown" if TOOLS[call["tool"]]["mutation"] else "failed", error="worker_failed")
                return loads(output)
            except subprocess.TimeoutExpired:
                first = False
                if cancelled() or time.monotonic() >= deadline:
                    process.kill()
                    process.communicate(timeout=2)
                    return result(call, "unknown" if TOOLS[call["tool"]]["mutation"] else "cancelled",
                                  error="cancelled_or_timed_out")
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=2)
