# Phase 3 implementation — 2026-10-14 (Asia/Saigon)

The native text MVP candidate is implemented. Full live acceptance remains pending: the current VS Code session did not return a workspace API receipt. No unverified editor launch is counted as successful goal completion.

P3.1–P3.4 connect actual Runtime schemas and observations to the existing LangGraph loop, provide trusted project selection/clarification, stream model/tool events, serialize tasks and desktop dispatch, and generate deterministic partial-failure summaries. The authenticated task API runs inside the existing broker container; inference still runs separately. The original synthetic CLI remains available and disclosed.

The first-party `jarvis-ai.workspace-verifier` extension is installed at version 0.1.3. Its source is in `integrations/vscode-verifier`; its only effect is an expiring nonce-bound local workspace observation. It reads `vscode.workspace.workspaceFolders`, compares the canonical configured folder, and writes a receipt in the private JARVIS directory. Runtime checks the receipt's request ID, project, path, time and method. It does not execute commands, open folders, receive tokens or contact the network. VS Code must activate the installed version after reload. Activation in the current running session is not confirmed; the available session logged earlier verifier versions.

## Validation

- Container Python suite: **80 passed, 2 skipped**, 3.44 seconds. The Linux image has no Git executable for the two platform-dependent Git fixtures.
- Native Windows standard-library suite: **21 passed**; includes real disposable Git repository/worktree tests.
- A separate live metrics-only natural-language task succeeded with a verified current measurement and two genuine model turns (`phase3-readonly.json`). The PowerShell task wrapper also returned project clarification before dispatch when project selection was omitted.
- Node standard-library verifier contract test: **1 passed**; covers exact path/nonce evidence, wrong workspace, expiry and traversal rejection. This is a mocked VS Code API test, not a desktop acceptance result.
- Live local Qwen/llama.cpp development smoke: **0/10 complete, 10/10 partial** in `phase3-live.json`. Metrics and branch observations are native; all editor launch receipts remain unverified. Results preserve that missing goal despite model completion prose. Case 1 was rerun after Runtime registration; the initial startup-race result is retained in `.local/phase3-startup.json`.

The ten-case corpus varies wording and ordering and is a development smoke set, not the held-out release acceptance set. It uses the already provisioned local model and current Compose configuration. No model/dependency downloads or cloud inference were added. The full evidence contains call IDs, task events, native sampling times, units, current Git observations and per-case durations.

Deterministic integration tests cover protocol round trips, changed action order, editor failure, non-repository state, unverified launch, disabled tools, early model exit, disconnect/timeout cancellation, trusted project clarification, authentication and serialization. The backend rebuilt successfully with unchanged dependency locks. No reference repository files were changed; no commits or publication were made.

## Remaining gate and boundaries

Reload VS Code to activate the installed verifier, start the documented broker/native runtime, and rerun `python scripts/phase3_validate.py`. All three goals require actual current receipts before Phase 3 is considered validated. If receipts still do not arrive, diagnose extension activation and editor launch rather than accepting a title or model claim.

Task state is intentionally in memory and bounded to 100 records. The broker/runtime ledgers still preserve external call IDs, but do not make graph tasks restartable. Durable checkpoints, approvals, journal reconciliation, request/receipt retention, hardened cancellation and release benchmarks remain Phase 4 or later. Expired verifier requests are inert. The extension and Runtime are same-user processes, not a hardened sandbox against compromised same-user software.
