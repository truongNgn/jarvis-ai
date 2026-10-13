# JARVIS AI — Phase 1

A local LangGraph task agent running in Docker on WSL2. **Every tool is currently synthetic.** It does not measure your PC, open Windows applications, inspect your real Git branch, or execute a shell. The model chooses structured tools and sees their observations; execution permission and completion reporting are enforced by application code.

## Implemented

- Strict Pydantic tool contracts and default-deny local session grants.
- Streamed llama.cpp tool-call assembly with complete-call validation and byte bounds.
- One LangGraph loop: model → validate/execute → observe → model, with eight call attempts, twelve model turns, one argument repair and a 120-second task ceiling.
- Cancellation, per-model/tool deadlines, call-ID deduplication and evidence-based synthetic summaries.
- Three fixtures: `system_metrics`, `project_open`, `git_branch`.
- Clean, non-root Brain and test images, fully pinned transitive Python dependencies, private container network and independent model volume.

## Prerequisites

Windows 11 + Ubuntu WSL2 and the existing native Docker Engine on `/run/persona-docker.sock`. Backend packages are installed in images; no Windows/backend venv is needed. Administrative commands use root in Ubuntu to access the socket; the Brain runs as UID 10001 with no Docker socket or Windows filesystem access.

The pinned primary model is already provisioned in `jarvis-ai_models` on this machine. Fresh setups must provision the artifact identified in `config/models.example.toml` into that volume before startup. `scripts/provision_model.py` can copy and verify an existing local model with `/source` read-only and `/target` mounted to the JARVIS volume; never mount the Persona volume into a released JARVIS service. There is no automatic model download.

## Build and run from PowerShell

```powershell
./scripts/wsl-compose.ps1 --profile test build brain tests
./scripts/wsl-compose.ps1 up -d inference
./scripts/wsl-compose.ps1 --profile cli run --rm brain "Check my PC performance, open jarvis-ai in VS Code, and tell me the current Git branch."
```

The default CLI task requires all three demo capabilities. This is an explicit trusted goal set, not keyword matching. For a one-goal task:

```powershell
./scripts/wsl-compose.ps1 --profile cli run --rm brain "Inspect CPU and RAM." --expect system_metrics
```

`--json` prints observations/events, and Ctrl+C cancels the task. `--fail-tool project_open` injects a fixture failure to demonstrate partial completion. A result exit code of 0 means all required synthetic goals were observed successfully; 2 means partial/failure/cancellation/unavailable. The final displayed facts are built from validated results, so the model cannot claim an editor was opened by merely saying it was.

The native WSL engine may stop with the Ubuntu session on machines configured for idle shutdown. Keep an Ubuntu terminal active while using the stack if necessary. Startup health checks wait within a bounded deadline, and missing inference fails clearly.

## CPU fallback

```powershell
./scripts/wsl-compose.ps1 -f compose.yaml -f compose.cpu.yaml up -d inference
./scripts/wsl-compose.ps1 -f compose.yaml -f compose.cpu.yaml --profile cli run --rm brain "Check performance, open jarvis-ai, and tell me the branch."
```

This override removes the GPU reservation and uses zero offloaded layers. The same verified model and CUDA server image can run CPU-only. Return to GPU mode with `./scripts/wsl-compose.ps1 up -d inference`.

## Tests and live evaluation

```powershell
./scripts/wsl-compose.ps1 --profile test run --rm --no-deps tests -p no:cacheprovider tests
./scripts/wsl-compose.ps1 --profile test run --rm --no-deps --entrypoint python tests evals/runner.py
```

Unit/protocol/security tests require no inference service. Live evaluation requires `inference` running; it exercises ten developer paraphrases plus a tool-failure scenario. `REPORT_JSON=` contains the full machine-readable report. The ten developer cases are a smoke corpus, not the future held-out acceptance set.

To audit the core lock, use the test image with an explicitly network-enabled temporary audit container:

```powershell
wsl -d Ubuntu -u root -- docker -H unix:///run/persona-docker.sock run --rm --entrypoint pip-audit jarvis-ai-tests:phase1 --disable-pip --no-deps -r /app/requirements.lock
```

Locks are specific to Python 3.12/Linux amd64, pin all resolved versions, and currently do not include wheel hashes. Base/inference image digests and GGUF/template hashes are pinned. Regenerate locks in a clean container after changing direct requirements; run `pip check`, audits and tests before accepting changes. LangSmith tracing is disabled and the application network has no external route.

## Stop

```powershell
./scripts/wsl-compose.ps1 stop inference
```

This preserves the verified model volume. Do not run global prune or remove unrelated containers. The implementation report is in `docs/benchmarks/phase1.md`. Phase 2's Windows runtime and Phase 3's integrated desktop tasks remain future work.
