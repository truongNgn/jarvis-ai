# JARVIS AI — Phases 1–2

A local LangGraph task agent running in Docker on WSL2, with a separate native Windows capability runtime. **Phase 1's natural-language CLI still uses synthetic tools.** Phase 2 adds explicit authenticated native tool calls; connecting them to natural-language multi-step tasks is Phase 3. No unrestricted shell is exposed.

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

The Compose wrapper maintains a tagged JARVIS WSL keepalive helper when starting services or running containers, preventing idle shutdown of the native engine. `scripts/stop-phase2.ps1` releases that helper when stopping the desktop stack. Startup checks have bounded deadlines.

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

This preserves the verified model volume. Do not run global prune or remove unrelated containers. The Phase 1 implementation report is in `docs/benchmarks/phase1.md`.

## Phase 2: native Windows tools

The runtime needs only the existing Windows Python 3.10+ standard library. Backend FastAPI/Uvicorn libraries are installed in Docker; there is no host venv or new host library installation. Native Win32 monitoring/window APIs and ctypes NVML avoid shipping psutil/pywinauto at this milestone. Rich UIA remains a future capability.

Initialize once, build the broker image, and start its loopback-only endpoint:

```powershell
./scripts/windows-runtime.ps1 -Action init
./scripts/wsl-compose.ps1 --profile desktop build broker
./scripts/wsl-compose.ps1 --profile desktop up -d broker
./scripts/windows-runtime.ps1 -Action serve
```

The last command runs the runtime in the signed-in Windows session. It polls authenticated leased calls from the Docker broker; Windows exposes no execution listener. Credentials are generated randomly, DPAPI-protected under your private LocalAppData, and provisioned into a dedicated read-only Docker secrets volume. They are not environment variables or repository files. The runtime's SQLite journal and broker's own SQLite volume preserve call IDs and results.

From a second PowerShell terminal:

```powershell
./scripts/windows-runtime.ps1 -Action call -Tool system.metrics
./scripts/windows-runtime.ps1 -Action call -Tool git.branch -Arguments '{"project_id":"jarvis-ai"}'
./scripts/windows-runtime.ps1 -Action call -Tool window.list -Arguments '{"app_id":"vscode"}'
```

Read-only tools are enabled by default. To explicitly enable reversible desktop operations, start the runtime with `-AllowDesktop`, then call:

```powershell
./scripts/windows-runtime.ps1 -Action serve -AllowDesktop
./scripts/windows-runtime.ps1 -Action call -Tool project.open -Arguments '{"project_id":"jarvis-ai"}'
```

Edit `config/runtime.example.json` for a different trusted installation path before running it. Windows references returned by `window.list` are signed, expire after 30 seconds, and bind HWND/PID/process creation time; `window.activate` accepts only such references. Foreground activation may be refused by Windows and returns `foreground_denied`, rather than bypassing that restriction. `project.open` reports `launch_requested` and `verification=unverified`; window titles alone do not prove the exact workspace opened.

Each administrative call is explicit user authorization, separate from model output. The broker signs a bounded request; the native runtime independently rechecks tool, arguments, local scope, grant, version, deadline and signature. A duplicate call ID returns its recorded result, altered arguments are rejected, and unfinished journal entries return `unknown` without replaying a side effect.

Native tests and optional desktop smoke:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -m unittest discover -s tests -p test_runtime_native.py
python scripts/phase2_validate.py               # metrics, Git, scoped windows and denials
python scripts/phase2_validate.py --desktop     # additionally requests launch and activation
```

Use `scripts/stop-phase2.ps1` to stop recorded JARVIS helpers/broker; Ctrl+C in the runtime terminal is the normal foreground stop. Force-stopping during a mutation can leave an unknown outcome; the durable journal prevents blind replay. The implementation report and known verification limits are in `docs/benchmarks/phase2.md`. Natural-language integration remains Phase 3.
