# Phase 1 implementation and validation

Completed 2026-10-13 (Asia/Saigon). Scope: core task agent with synthetic capabilities. Phase 2 was not started.

## Result

JARVIS now has a clean Docker-hosted Python 3.12 Brain, a real llama.cpp model adapter and one LangGraph execution loop. The model chooses among three fake tools and receives their observations. Pydantic schemas, immutable session grants, execution limits and result verification are enforced outside model prompts. The final response is generated from verified fixture facts; model prose cannot manufacture task completion.

No PC measurements, real project launches or Git operations occur. The default task goal set explicitly requires all three demo tools; `--expect` can select a narrower trusted goal set. There is no keyword dispatch or hard-coded execution order. Model batches are executed serially even if the server returns multiple calls despite parallel calling being disabled in the request.

## Implemented components

| Component | Implementation |
|---|---|
| Typed boundaries | Strict TaskRequest, ToolCall, ModelReply, ToolResult and TaskOutcome; unknown fields rejected |
| Model adapter | Local-only endpoint, pinned-template health check, bounded readiness wait, SSE call assembly, complete-stream validation |
| Registry/policy | Explicit tools, input/output schemas, duplicate registration rejection, default-deny tool/project/principal grants |
| Fake tools | CPU/RAM fixture, simulated VS Code project receipt, fixture branch `feature/phase1-demo` |
| LangGraph | Model → validate/execute → observe → model; serializable state and structured call/response IDs |
| Reliability | Call/turn/context budgets, one argument repair, per-model/tool/task deadlines, cancellation and in-task call-ID deduplication |
| Completion | Required-tool evidence gate, partial/failure states and synthetic disclosure |
| Delivery | Digest-pinned Python/inference images, non-root read-only Brain, private internal network, no published inference port |

Durable checkpoints and execution journals belong to later phases. In-memory deduplication does not survive restart and is not an exactly-once execution guarantee. FastAPI was omitted from the CLI-only Phase 1 image; add it when a transport API is needed. Model clients, grants and cancellation events remain outside serialized graph state.

## Validation evidence

- **35 deterministic tests passed** in the Docker test image. Coverage includes malformed/truncated streams, fragment assembly, oversized stream rejection, unknown tools/principals, extra and duplicate arguments, project scopes, tool-schema manifests, injected observation attempting shell authorization, argument repair, premature completion, tool errors, duplicate/colliding call IDs, call/turn budgets, tool/task timeout, cancellation during model/tool execution and readiness/template checks.
- **10/10 live developer cases succeeded** with genuine local inference and three tool attempts each. Final run duration range: **2.668–3.240 seconds**, median **2.900 seconds**. These are small warm smoke cases, not held-out task quality or production p95 measurements.
- **Live failure case returned partial**, with the simulated project-open failure visible and no false success claim. Full responses, observations and event correlation are in `phase1-live.json`.
- **CPU-only CLI scenario succeeded**, with the Compose override removing the GPU reservation. Evidence is in `phase1-cpu.json`; this verifies fallback function, not sustained fallback performance.
- **pip check passed** during both image builds. **64 pinned production/development packages were audited with zero known vulnerabilities** after upgrading pip to 26.2.1. Result is in `phase1-audit.json`. This is Python advisory coverage as of this run, not an OS image or comprehensive security certification.
- Compose GPU/CPU configurations validated. The reference repository's working tree remained clean.

Tests initially failed because the test image omitted the pytest configuration in pyproject.toml; copying that configuration fixed async test collection. A CPU startup check initially raced model readiness; bounded health polling fixed it. The dependency audit identified the base image's pip 25.0.1 advisories; both locks now pin patched pip 26.2.1 and the audit was rerun successfully.

## Reproducibility

- Hardware: the Phase 0 ASUS i5-12450H / RTX 3050 Laptop 4 GiB machine; other configured WSL services were running.
- Python image: `python:3.12.15-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258`.
- Inference image: `ghcr.io/ggml-org/llama.cpp@sha256:b2aae63c399341c37187872d6c60b727b8f1e48b7dc15916f7aea956ac329229`.
- Model/template identities: `src/jarvis/llm/profiles.py` and `config/models.example.toml`.
- Model: Qwen2.5 1.5B Instruct Q4_K_M, 2,048 context tokens, one slot, four threads, 20 GPU layers; CPU fallback zero layers.
- Sampler/output: temperature 0, maximum 256 generated tokens per turn. Character-based preflight caps messages plus tool definitions at 6,500 characters; it is conservative, not an exact tokenizer budget. Server context failures become unavailable/partial results and do not trigger tool dispatch.
- Direct dependencies: LangGraph 1.2.15, Pydantic 2.14.1 and HTTPX 0.28.1. Fully pinned transitive locks are `requirements.lock` and `requirements-dev.lock`; wheel hashes are not yet included.
- Selected application image IDs at validation: Brain `sha256:52d92e2278420729b39a250d4a4ed7c156c5d37a2bd734f0e90232fc7e6d5afc`; tests `sha256:5ce9e757ea308049811e734f43b4e0d1a72d351691eaa1076d5437faa5ee7843`.

JARVIS's own `jarvis-ai_models` volume contains a verified independent copy of the model. Persona's model volume was mounted read-only solely to provision that copy; it is absent from Compose. No dependency is installed into a host venv and no reference image/service is required by JARVIS. Models and images are local reusable artifacts; no new Git repository, commits or pushes were created.

## Handoff

Run commands are in README.md. Inference is stopped after validation to release resources; built images, model volume and evidence are preserved. Phase 2 can now build native Windows tools and the authenticated leased HTTP bridge using these contracts/policy concepts, with actual scopes revalidated in the Runtime. This phase does not establish generalized user-intent coverage, desktop permissions, persistent recovery or full MVP acceptance.
