# Phase 0 architecture decisions

Date: 2026-10-13, Asia/Saigon. Scope: infrastructure research and validation only. Phase 1 is not started.

## Accepted deployment

The user selected Docker on WSL2 instead of a backend host venv. Use two Compose services: Brain (Python 3.12) and inference (pinned llama.cpp). Use the existing native Docker Engine in Ubuntu. Administration currently uses `/run/persona-docker.sock`; the socket name is historical and does not make JARVIS depend on the Persona application. Never mount the socket in the Brain. Do not run two engines for this project.

Docker Desktop startup was probed before discovering the native engine. The CLI initially reported a missing Desktop Linux pipe and startup remained pending. The working, validated engine is native Ubuntu Docker, not Docker Desktop. WSL startup also activated existing services according to their configured restart behavior; no reference compose commands or file changes were made. Do not stop or prune unrelated workloads to free resources implicitly.

JARVIS uses its own Compose project name, network, credentials, model/state volumes, and service lifecycle. Phase 0 temporarily mounted an existing model volume read-only and used an existing backend image for imports; these are research conveniences only. Phase 1 must build a clean Brain image and provision a JARVIS-owned copy of the verified GGUF (or download that exact artifact). No reference database, embedding service, TTS endpoint or backend image is a release dependency.

Brain libraries are installed at image build time. Avoid interactive pip changes and backend host venvs. A Python 3.12.15 Linux image successfully imported FastAPI, Pydantic and LangGraph with the versions recorded in `config/models.example.toml`. This establishes a compatibility baseline only; Phase 1 creates a full dependency lock, audits it, and pins the clean base-image digest. Optional speech/vision dependencies stay out of the core image. Windows-specific Runtime libraries must be distributed separately; a packaged executable is the future preferred delivery, and Linux libraries cannot replace Windows UIA dependencies.

## Native Windows boundary

Windows owns application launch, window/UIA interaction, screen capture, microphone capture and playback. Brain and inference stay in Linux containers. User confirmed project alias `jarvis-ai` for `D:\Coder-IT\AI\jarvis-ai` and English-only product scope. VS Code executable exists at the configured path. The JARVIS workspace is not currently a Git repository; later branch tooling must return `not_a_repository` until the user chooses initialization. No Git initialization was performed.

## Communication choice

For the native-engine deployment, choose outbound HTTP from Runtime to the Brain endpoint forwarded to Windows loopback. Runtime registers its manifest, polls a bounded leased-call queue and posts results. This avoids requiring the container to reach a Windows privileged HTTP listener. Future routes: `POST /v1/runtimes/register`, `GET /v1/runtimes/{id}/calls?wait=20`, `POST /v1/runtimes/{id}/results`, with authenticated runtime identity, lease ID, schema hash, call ID, grant and cancellation epoch. Brain continues exposing task/status/cancel/approval routes to the UI.

Only Brain's required endpoint is published on 127.0.0.1; inference is private on the Compose network. Explicitly test Windows localhost forwarding in Phase 2; Phase 0 successfully used Windows localhost to reach a temporary inference container. Polling lease expiry must not mean permission to repeat a side effect: consult the Runtime journal and reconcile uncertain results. An authenticated duplex WebSocket can replace polling later. Direct Brain-to-Runtime HTTP remains an alternative for topologies with validated host routing, not the selected default. Cross-host/non-loopback communication requires TLS and explicit firewall scope.

## Model selection and evidence

Choose Qwen2.5-1.5B-Instruct Q4_K_M for Phase 1's first model, with 2K context, one slot, four CPU threads and 20 GPU layers. CPU fallback uses the same pinned CUDA image with zero offloaded layers; no cloud fallback. Both profiles produced valid structured tool calls in three synthetic trials. Tool outputs were never executed. Exact model/image/template hashes are in configuration and raw results.

Qwen3-4B Q4_K_M is a disabled challenger. Publisher revision, artifact size/hash and Apache-2.0 metadata were checked through Hugging Face; no challenger weights were downloaded. Benchmark only if Phase 1 quality requires it and resource preflight passes. Basic syntax compatibility is established for the primary, not full multi-step planning or permission behavior.

## Contract and safety freeze

Freeze the v1 envelopes in Sections 8–12 of the full plan: TaskRequest/State, ToolSpec/Call/Result, ApprovalRecord, TaskEvent and CapabilityManifest. Persist serializable values only. Security is enforced by default-deny registry and Runtime policy, strict per-tool arguments, configured project aliases, scoped authenticated grants and bound approvals. Unknown identity/tool/schema versions are rejected. Inference has no direct executor, shell, Docker socket or credentials. Treat repo/mail/screen/tool output as untrusted data. Runtime journal is the side-effect deduplication authority; graph checkpoints do not imply exactly-once execution.

First live capabilities remain deferred to Phase 2. Phase 1 has fake metrics/project/Git tools only. Core budgets are eight calls, twelve model turns, bounded output, one schema repair and one desktop mutation lane once enabled. Frozen evaluation categories: 50 development benign, 50 held-out benign and 50 adversarial/ambiguous/failure cases. Release targets remain Section 24: held-out completion at least 90%, zero prohibited dispatch in negative fixtures, zero false-success claims in failure fixtures, measured resource headroom and documented p95 latency.

## Phase 0 completion and deferred gates

- P0.1 complete for immediate scope: project, English, VS Code and container Python selected. Reference code-copy rights remain unresolved; use new code until verified, so this does not block Phase 1.
- P0.2 complete: primary and challenger identities, checksums, sizes and model licenses recorded; primary template and image pinned. Challenger template is intentionally unvalidated while disabled. Full Brain dependency/base-image lock belongs to its Phase 1 build.
- P0.3 complete: primary CPU and GPU startup/tool-call compatibility and bounded-context allocations checked; temporary containers removed. Small-sample evidence is in baseline/raw results.
- P0.4 complete: contracts, threat boundary, test categories and release targets frozen by this record and the full plan.

Deferred before affected milestones: copied-source/asset rights, full dependency security audit, new Brain image build, JARVIS-owned model provisioning, complete GPU peak/headroom benchmark, graph checkpoint saver selection/install, Windows Runtime packaging and authenticated bridge tests. No complete task success or production readiness is claimed by Phase 0.

Primary documentation: [Docker WSL2](https://docs.docker.com/desktop/features/wsl/), [GPU support](https://docs.docker.com/desktop/features/gpu/), [llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md), [Qwen primary](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF), [Qwen challenger](https://huggingface.co/Qwen/Qwen3-4B-GGUF). Docker Desktop-specific networking names such as `host.docker.internal` are not assumed to exist in native Docker Engine.


## Phase 1 implementation update — 2026-10-13

Phase 1 is implemented; historical Phase 0 statements above remain dated evidence. A clean digest-pinned Python 3.12.15 image now runs LangGraph 1.2.15 and Pydantic 2.14.1 with fully pinned production/development locks. FastAPI was omitted from the CLI-only core to minimize dependencies. The standalone model volume jarvis-ai_models contains its own SHA-256-verified copy; Compose does not reference Persona services or volumes. The local native Docker Engine remains a shared administration facility only.

The graph chooses and executes three fake tools under immutable grants, preserves structured call/response IDs, validates streamed calls, limits execution and reports verified fixture facts. Required outcomes are explicit trusted CLI inputs, defaulting to the three-tool demo; no keyword classifier determines tool order. Durable checkpoints and the Windows Runtime are not enabled. See docs/benchmarks/phase1.md and README.md for tested scope and commands.

## Phase 2 implementation update — 2026-10-14

Phase 2 implements the Docker FastAPI broker and the standard-library Windows Runtime. Fixed primitive schemas are shared between endpoints; Docker submissions additionally use Pydantic. This avoids native AI/library installation while preserving strict argument/result checks. Basic Win32 window APIs and ctypes NVML cover this milestone; richer UIA stays optional for Phase 7.

The selected reverse HTTP bridge now uses /v1/runtime/register, /v1/runtime/calls, /v1/runtime/calls/{id}/status and /v1/runtime/results, plus administrative /v1/calls routes. Admin/runtime credentials are distinct, calls are HMAC-bound and deadlines/scopes rechecked natively. DPAPI and private volumes hold credentials; separate SQLite ledgers hold queue and execution results. Read-only capabilities are default, with an explicit --allow-desktop operator flag for launch/focus. Single-instance execution and owned worker timeouts prevent competing desktop jobs.

Real metrics, main-branch inspection, editor launch, window enumeration and allowed foreground activation were checked. Launch receipt remains unverified for exact workspace identity; OS focus denial is respected. See docs/benchmarks/phase2.md and README.md. The Phase 1 graph still uses fake tools; natural-language native task integration is Phase 3, not silently enabled by these broker endpoints.
