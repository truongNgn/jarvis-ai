# Phase 2 — Windows Desktop Runtime

Implemented 2026-10-13–14 (Asia/Saigon). Scope: authenticated native capabilities and a Docker-hosted broker. Natural-language integration remains Phase 3; the Phase 1 agent still uses fixtures.

## Delivered

| Capability | Result and verification |
|---|---|
| `system.metrics` | Native CPU sample, physical RAM, project-drive capacity and optional NVML GPU memory, with timestamp/units and explicit unavailable counters |
| `git.branch` | Fixed read-only Git argv; reports branch, detached HEAD, unborn branch or non-repository; repository root must match configured alias |
| `project.open` | Configured Code.exe and project alias only; launch receipt and matching-window count; always `verification=unverified` because titles cannot prove the exact workspace |
| `window.list` | Only configured VS Code executable; bounded titles/PIDs and signed, expiring HWND/PID/process-creation references |
| `window.activate` | Requires a fresh signed reference and interactive desktop; rechecks process identity and actual foreground HWND; respects OS refusal |

The native process uses the Windows Python standard library. Win32 APIs and ctypes NVML were selected over host psutil/pywinauto dependencies for this small milestone; richer UIA is deferred. Pydantic validates broker submission envelopes in Docker, while both ends use the same closed, primitive schema definitions for arguments and executable result checks. No caller-supplied schemas or arbitrary tools are registered.

## Communication and authority

FastAPI/Uvicorn run in the Docker broker service, published only on Windows/WSL loopback port 18765. Windows exposes no executor listener. Runtime registers an exact versioned capability manifest, polls leased jobs, checks cancellation and posts validated results. Broker administrative and Runtime tokens are separate. Browser Origin requests, unexpected Host values, unauthenticated requests, cross-role credentials, redirects, oversized bodies, unknown fields and unregistered capabilities are rejected.

Each accepted request has a stable call/task ID, canonical argument scope, tool schema hash, policy version, deadline and HMAC signature. Model text cannot mint authority. Runtime rechecks signature, configured tools, project scope, argument types and deadline before dispatch; worker rechecks them again. Read-only tools are default. `--allow-desktop` is an explicit operator grant for the two reversible GUI capabilities, and each administrative call is a concrete user request.

The Windows singleton mutex prevents concurrent Runtime instances competing for focus. Blocking tools run in isolated owned Python workers with monotonic deadlines. Cancellation or transport loss stops further work; only owned workers are terminated. If a mutation may already have happened, the result is `unknown` rather than a rollback claim.

SQLite records intent before execution and completed results afterward. Repeated IDs with identical payloads return cached results, altered payloads are rejected, and unfinished entries return `unknown` without replaying side effects. Runtime journal is in private Windows LocalAppData; broker queue/results use a JARVIS-owned Linux volume. This is minimal persistence, not Phase 4's full recovery/checkpoint system.

## Credential handling

Setup generates random 256-bit tokens/signing key. Native credentials use user-scoped DPAPI and private user/SYSTEM/Administrators ACLs. A setup-only stdin pipe provisions the broker's private Docker secrets volume; no plaintext secrets are written in the repository or passed on a command line. The service mounts secrets read-only. Workers receive only signing/window-reference material they need, not the administrative token. `.local/`, `.env*`, keys, DPAPI blobs and runtime databases remain excluded from Git and Docker build contexts.

These boundaries limit model authority and accidental execution. They do not provide a sandbox against malicious code already running with the same Windows user or Docker administrator privileges.

## Validation

- **61 Docker tests passed, 2 skipped**. The skipped Git fixture cases require a Git executable, which is intentionally absent from the Linux AI image.
- **21 native Windows tests passed**, including those Git fixtures. Covered unborn/main/detached/worktree/non-repository states and UTF-8 branch names; auth/Origin/Host rejection; stale references and PID reuse; unknown/disabled tools; extra/duplicate arguments; signature/version/schema mismatch; call-ID collision; cached replay; persisted journal restart; unfinished intent; pre-dispatch cancellation; owned-worker termination; and explicit unavailable-GPU output.
- **Actual Windows-to-Docker calls passed** for metrics, current `main` branch, VS Code launch receipt, window enumeration and foreground activation. Duplicate results were identical. Three unsafe requests were rejected before execution: arbitrary shell, unknown project and an extra `approved` argument. Public smoke results omit credentials, titles and signed window references: `phase2-windows.json`.
- Foreground activation was initially refused by Windows and correctly returned `foreground_denied`. A subsequent permitted attempt succeeded and its foreground postcondition was verified. No focus-policy bypass was introduced.
- Starting a second Runtime was rejected as `runtime_already_running`.
- **70 pinned Python packages audited; zero known vulnerabilities** in the advisory lookup. Evidence: `phase2-audit.json`. `pip check` passed during image builds. pip 26.2.1 remains explicitly pinned; the lock generator uses `freeze --all` so the installer pin cannot disappear silently.
- One short idle snapshot: Runtime working set **21.63 MiB**, **0.0156 CPU seconds over five seconds**; broker container memory **48.5 MiB**. These are observations under existing workloads, not peak/sustained benchmarks or whole-machine CPU percentages.

An initial cold start reached the broker before Runtime registration; readiness polling and startup retries now bound that wait. The native WSL engine also stopped when no foreground Linux client remained; the Compose wrapper now maintains a tagged, project-owned keepalive helper. The stop script verifies helper/worker process identity before stopping them and does not stop unrelated WSL workloads or editor instances.

## Run and completion boundary

See README.md for setup, broker startup, native Runtime, explicit calls, tests and cleanup. No Windows Python packages or host venv were installed. All new backend libraries were installed in Docker images. Credentials, journals and private Linux volumes are preserved for subsequent runs; test services/helpers are stopped after verification.

The five Phase 2 capabilities are implemented. Workspace verification remains explicitly limited to an unverified launch receipt; no success claim that the precise workspace is open is made. No filesystem write/delete capability, keyboard typing, mouse control, shell executor, privilege escalation, screen capture, cloud inference, email or calendar was added. The native tools are not yet attached to LangGraph's natural-language loop. That integration, its task-level goal verification and event UI are Phase 3.

Primary references: [Windows foreground rules](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow), [DPAPI](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata), [Git rev-parse](https://git-scm.com/docs/git-rev-parse).
