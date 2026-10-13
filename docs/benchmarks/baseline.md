# Phase 0 infrastructure baseline

Measured 2026-10-13 on the ASUS FX517ZC, Intel i5-12450H, 23.63 GiB physical RAM and RTX 3050 Laptop 4096 MiB GPU. Windows + existing background workloads were active. No controlled idle baseline, sustained benchmark or held-out agent evaluation was run.

## Environment

| Item | Evidence |
|---|---|
| WSL | 2.6.3.0; Ubuntu kernel 6.6.87.2-microsoft-standard-WSL2 |
| Native Ubuntu engine | Docker 29.9.0, Compose v5.6.0, `/run/persona-docker.sock` |
| Windows Docker CLI | 29.2.0, Compose v5.0.2; initial Desktop pipe unavailable |
| Python | Windows 3.10.11; Ubuntu 3.12.3; disposable compatibility image 3.12.15 |
| Free physical storage | C: about 45.9 GiB; D: about 19.9 GiB at inspection |
| WSL filesystem | 49 GiB used / 908 GiB logical free; logical VHD capacity is not host free space |
| Pre-probe total GPU allocation | 1850 MiB; separate from peak inference usage |
| VS Code | Configured Code.exe and code.cmd found |
| Git workspace | JARVIS is not yet a Git repository |

The primary GGUF's local SHA-256 matched the publisher LFS hash. Size: 1,117,320,736 bytes. Challenger metadata size: 2,497,280,256 bytes; not acquired. No new image/model download or library installation was needed.

## Inference compatibility smoke

Script: `python scripts/phase0_validate.py --output docs/benchmarks/phase0-inference.json`. It starts only labeled temporary JARVIS containers using an existing pinned image and read-only model mount, polls Windows localhost health, requests one synthetic metrics tool and checks returned name/arguments. No model-proposed tool is executed. Containers are removed afterward.

| Profile | Observed readiness seconds | Three call durations (seconds) | Valid structured calls | Post-trial container memory snapshot |
|---|---:|---|---:|---:|
| CPU, zero offload | 3.562 | 2.484, 1.438, 1.359 | 3/3 | 757.6 MiB |
| GPU, 20 layers | 3.156 | 0.625, 0.422, 0.453 | 3/3 | 377.6 MiB |

Both use 2,048 context, one slot, four threads, 256 batch / 128 microbatch and 128 maximum output tokens. Docker container memory snapshots exclude VRAM and are not peak RSS. Readiness includes process launch and one-second health polling; it is not a precise cold-model-load metric. Later prompts benefit from prompt-cache reuse. The primary template hash is recorded in config/raw results. Full server props/logs and responses are preserved in `phase0-inference.json`.

An initial GPU readiness probe stopped on an early connection-close event. The readiness handler was corrected to retry that transient startup condition within its deadline. The rerun passed both profiles; the table contains the successful rerun. This was a probe robustness correction, not a measured model quality improvement.

## Dependency compatibility smoke

A disposable, network-disabled existing backend image successfully imported FastAPI, Pydantic and LangGraph under Python 3.12.15. Installed versions: FastAPI 0.115.0, Pydantic 2.9.2, LangGraph 1.0.1, langgraph-checkpoint 3.0.1, langchain-core 0.3.86, HTTPX 0.27.2, Uvicorn 0.30.6. LangGraph emitted a serializer allowed_objects deprecation warning; Phase 1 must select explicit safe serializer configuration. Import success is not a full dependency/security audit or proof of SQLite saver availability.

Phase 1 must build a clean minimal Brain image, lock dependencies and verify them independently. Phase 0's use of the reference image is not a deployment dependency.

## Next measurements

Use the main plan's frozen corpus and benchmark procedure. Measure actual multi-step completion, peak whole-machine RAM/VRAM, normal editor load, CPU fallback latency, thermal degradation and authenticated Runtime transport. The 3/3 smoke results do not establish 90% held-out task success, p95 task latency, prompt-injection resistance or model headroom under all workloads.
