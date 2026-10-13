"""Phase 0 infrastructure probe; never executes model-proposed tools.

Uses an existing WSL Docker engine/image and a read-only reference model only
for validation. Release deployments must use JARVIS-owned artifacts.
"""
import argparse
import hashlib
import http.client
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

IMAGE = "ghcr.io/ggml-org/llama.cpp@sha256:b2aae63c399341c37187872d6c60b727b8f1e48b7dc15916f7aea956ac329229"
MODEL = "qwen2.5-1.5b-instruct-q4_k_m.gguf"


def docker(*args):
    result = subprocess.run(
        ["wsl", "-d", "Ubuntu", "-u", "root", "--", "docker", "-H",
         "unix:///run/persona-docker.sock", *args],
        capture_output=True, text=True, timeout=45,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return (result.stdout + result.stderr).strip() if args[0] == "logs" else result.stdout.strip()


def request(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:18080" + path, data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.load(response)


def probe(mode):
    name = "jarvis-phase0-" + mode
    # No arbitrary name deletion: refuse if an earlier container occupies it.
    if docker("ps", "-a", "--filter", "name=^/" + name + "$", "-q"):
        raise RuntimeError("Probe container already exists: " + name)
    args = ["run", "-d", "--name", name, "--label", "jarvis.phase=0",
            "--pull", "never", "--memory", "4g", "--cpus", "4",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "-p", "127.0.0.1:18080:8080",
            "-v", "persona-graph-ai_llama_models:/models:ro"]
    if mode == "gpu":
        args += ["--gpus", "all"]
    args += [IMAGE, "--model", "/models/" + MODEL, "--alias", "jarvis-probe",
             "--host", "0.0.0.0", "--port", "8080", "--ctx-size", "2048",
             "--parallel", "1", "--threads", "4", "--batch-size", "256",
             "--ubatch-size", "128", "--n-gpu-layers", "20" if mode == "gpu" else "0",
             "--jinja"]
    started = time.monotonic()
    container_id = docker(*args)
    result = {"mode": mode, "container_id": container_id, "image": IMAGE,
              "context_tokens": 2048, "gpu_layers": 20 if mode == "gpu" else 0}
    try:
        deadline = started + 90
        while True:
            try:
                request("/health")
                break
            except (urllib.error.URLError, TimeoutError, http.client.RemoteDisconnected, ConnectionResetError):
                if time.monotonic() > deadline:
                    raise RuntimeError("Readiness deadline exceeded")
                time.sleep(1)
        result["startup_seconds"] = round(time.monotonic() - started, 3)
        props = request("/props")
        template = props.get("chat_template", "")
        result["template_sha256"] = hashlib.sha256(template.encode()).hexdigest()
        result["server_props"] = props
        result["trials"] = []
        for text in ["Check my PC performance using system_metrics.",
                     "Please retrieve current CPU and RAM information with system_metrics.",
                     "Use system_metrics to inspect computer performance now."]:
            before = time.monotonic()
            response = request("/v1/chat/completions", {
                "model": "jarvis-probe", "temperature": 0, "max_tokens": 128,
                "messages": [{"role": "system", "content":
                              "Call the provided tool to obtain live metrics. Do not invent results."},
                             {"role": "user", "content": text}],
                "tools": [{"type": "function", "function": {
                    "name": "system_metrics", "description": "Get current PC CPU and RAM metrics",
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}}],
                "tool_choice": "auto", "parallel_tool_calls": False,
            })
            calls = response["choices"][0]["message"].get("tool_calls", [])
            valid = len(calls) == 1 and calls[0]["function"]["name"] == "system_metrics"
            if valid:
                valid = json.loads(calls[0]["function"]["arguments"]) == {}
            result["trials"].append({"seconds": round(time.monotonic() - before, 3),
                                     "valid_call": valid, "response": response})
        result["stats"] = docker("stats", "--no-stream", "--format", "{{json .}}", name)
        result["logs"] = docker("logs", name)
        result["passed"] = all(t["valid_call"] for t in result["trials"])
    except Exception as exc:
        result["passed"] = False
        result["error"] = str(exc)
        try:
            result["logs"] = docker("logs", name)
        except Exception:
            pass
    finally:
        docker("rm", "-f", container_id)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    results = []
    for mode in ("cpu", "gpu"):
        result = probe(mode)
        results.append(result)
        print(json.dumps({k: result.get(k) for k in
                          ("mode", "passed", "startup_seconds", "error", "stats")}))
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    raise SystemExit(0 if all(r["passed"] for r in results) else 1)
