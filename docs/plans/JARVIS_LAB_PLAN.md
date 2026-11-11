# JARVIS Agent Engineering Lab Plan

These six labs turn the concepts from *Building AI Agents and Agentic Workflows* into exercises on the existing JARVIS codebase. Each lab identifies where to start, what to build, and what evidence marks it complete. The [architecture discussion](https://chatgpt.com/share/6aefd6d1-5cfc-83ec-a11c-7e8dd7843b6b) proposed the exercises. The [implementation roadmap](JARVIS_FULL_HYBRID_IMPLEMENTATION_PLAN.md) tracks project milestones separately from lab numbers.

JARVIS already uses LangGraph to run a bounded model and tool loop. The authenticated Broker connects that loop to the Windows Runtime, which executes scoped tools and returns structured observations. Start from that path so each lab exercises the same contracts and verification rules as a normal JARVIS task.

## Baseline — Verify Phase 3 on Windows

The saved live report records **0 of 10 complete tasks**. Metrics and Git observations came from the native Runtime, but the editor step lacked a VS Code receipt confirming the exact workspace. The verifier source declares version `0.1.4`. Use the [native setup instructions](../../README.md#native-natural-language-tasks) to install the verifier, reload VS Code, and start the Broker and Windows Runtime with desktop access. [Phase 3 benchmark report](../benchmarks/phase3.md) · [Verifier manifest](../../integrations/vscode-verifier/package.json)

From the repo root in PowerShell, run one live case first. Once it returns the expected receipt, run the full development corpus. The output paths keep both new reports separate from the saved baseline. The live cases open the configured project.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
New-Item -ItemType Directory -Force -Path .local | Out-Null
python scripts/phase3_validate.py --limit 1 --output .local/phase3-smoke.json
python scripts/phase3_validate.py --output .local/phase3-lab-baseline.json
```

The smoke case passes when the task contains current metrics, a Git branch observation, and a receipt for the exact VS Code workspace. Record the full corpus results for Labs 5 and 6. Lab 1 can start with read-only tools while the editor receipt is being diagnosed. [Live validation script](../../scripts/phase3_validate.py)

## Lab 1 — Durable Task Execution with LangGraph

**Build.** Make a task that reads CPU and RAM, then reports the current Git branch, survive a Broker restart. Add a persistent SQLite checkpointer to the existing `StateGraph`, use `task_id` as the LangGraph `thread_id`, and persist the metadata `TaskService` needs to recover a task. Use a separate database under `/state` on the existing Broker volume. Restore progress and remaining execution limits when the task resumes. [Task graph](../../src/jarvis/brain/graph.py) · [Task service](../../src/jarvis/brain/service.py) · [Compose volumes](../../compose.yaml) · [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)

**Integration.** `NativeRegistry.execute()` currently creates a new Broker call ID at dispatch. Persist a stable call ID and the validated request before submission. On recovery, look up that call in the Broker ledger, reuse a recorded result, and let the Runtime journal protect execution. Surface an unresolved effect as `unknown` for reconciliation. Resume pending work only after the Runtime has registered again and the required capability is available. [Native registry](../../src/jarvis/tools/native.py) · [Broker ledger](../../src/jarvis/runtime/server.py) · [Runtime journal](../../src/jarvis/runtime/journal.py)

**Pass when.** Stop the Broker after the metrics tool has executed but before the graph checkpoints its result. Restart and resume the same task. Confirm that metrics executed once, the graph recovered the original observation, and the branch step completed. Use the existing [MVP end-to-end fixtures](../../tests/e2e/test_mvp.py) to make the failure point repeatable.

## Lab 2 — Human Approval Before Dispatch

**Build.** Add a simulated branch-creation tool to exercise approval without changing a working repository. Validate the request first, pause with `interrupt()` before dispatch, and show the exact project and branch name in the authenticated CLI or API. Store the decision against the task, tool, normalized arguments, and expiry. Resume the same thread with `Command(resume=...)`. [Task API](../../src/jarvis/brain/api.py) · [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)

**Integration.** Keep the approval node free of side effects before the interrupt because the node can run again on resume. Revalidate the approval at dispatch and retain the Windows Runtime's independent tool and project checks. Release the task execution lock while awaiting the user so other tasks can run. [Task service](../../src/jarvis/brain/service.py) · [Runtime dispatcher](../../src/jarvis/runtime/dispatcher.py)

**Pass when.** Restart with an approval pending, approve it, and observe exactly one dispatch. Denial, expiry, and altered arguments each produce zero dispatches. A duplicate approval cannot execute the action twice.

## Lab 3 — LangChain RAG and Conversation Memory

**Build.** Add a read-only knowledge workflow for `README.md`, `docs/architecture/`, `docs/plans/`, and Markdown reports in `docs/benchmarks/`. Split documents by heading, retain the file path and section as source metadata, and index the chunks with local embeddings. Start with two or three retrieved chunks per query and measure the prompt against the current 2,048-token context budget. [Inference configuration](../../compose.yaml) · [LangChain retrieval](https://docs.langchain.com/oss/python/langchain/retrieval)

**Integration.** Use a `session_id` for conversation context and keep it separate from task checkpoints. The current `storage/memory.py` resolves project aliases. Store conversation context separately so follow-up questions work without mixing it into execution state. Return source references with the answer and state when the retrieved material is insufficient. [Project preferences](../../src/jarvis/storage/memory.py)

**Pass when.** “What is still missing from Phase 3?” cites the benchmark report. “Which command reruns the check?” resolves the follow-up from the same session and cites the native setup instructions. A question outside the indexed material reports insufficient evidence.

## Lab 4 — MCP for Read-Only Windows Tools

**Build.** Add a local MCP server over `stdio` for `system.metrics` and `git.branch`. The original discussion used `git.status` as an example. Using `git.branch` lets this lab reuse a tool JARVIS already supports. [Runtime tool contracts](../../src/jarvis/runtime/protocol.py) · [MCP server concepts](https://modelcontextprotocol.io/docs/learn/server-concepts)

**Integration.** Reuse the Runtime schemas for discovery and validation. Forward calls through the authenticated Broker to the Windows Runtime and return the structured result. Keep the exposed capability list read-only and enforce the configured project scope. [Broker API](../../src/jarvis/runtime/server.py) · [Runtime dispatcher](../../src/jarvis/runtime/dispatcher.py)

**Pass when.** Two independent MCP clients can discover and call both tools with the same schemas and structured results. An invalid argument or an unconfigured project is rejected before tool execution.

## Lab 5 — Supervisor and Specialist Agents

**Build.** Add a LangGraph Supervisor for the Phase 3 task. The System Agent owns metrics, the Developer Agent owns Git and opening the project, and the Supervisor routes the request and combines structured observations. Start with bounded, sequential delegation and pass each specialist only its permitted tools. [Task graph](../../src/jarvis/brain/graph.py) · [Native registry](../../src/jarvis/tools/native.py)

**Integration.** Use the same Broker, approval rules, task limits, and evidence checks as the single-agent path. In particular, the Developer Agent needs a receipt for the exact workspace before the Supervisor can report the editor goal as complete. [Native verification](../../src/jarvis/brain/verification.py)

**Pass when.** The task “Check CPU, VRAM, and the Git branch, then open the project in VS Code” produces verified observations for all requested goals on a supported machine. A missing or mismatched receipt leaves the editor goal unfulfilled. Compare single-agent and Supervisor runs on the same corpus and record verified completion rate, model turns, tool calls, and latency. [MVP development corpus](../../evals/cases/mvp.jsonl)

## Lab 6 — LangGraph, BeeAI, and Microsoft Agent Framework Benchmark

**Build.** Put an isolated experiment under `evals/` that runs the same workflow in all three frameworks. Read metrics, read the branch, and assemble a structured result. Use the same inputs, tool schemas, and mock observations. Start with deterministic model responses to isolate orchestration, then repeat with the same local llama.cpp model to measure end-to-end behavior. Include a tool failure and a process restart at a defined step. [Existing eval runner](../../evals/runner.py) · [BeeAI Framework](https://github.com/i-am-bee/beeai-framework) · [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)

**Pass when.** Produce a reproducible comparison with completion rate, tool-call count, latency, recovery outcome, and the framework-specific code required for checkpointing, approval, and audit. Record the framework versions and configuration. Write a short architecture decision based on the measured trade-offs.

## Suggested order

Start with the Lab 1 read-only recovery case, then use that durable state for Lab 2. Labs 3 and 4 can be done in either order. Run Lab 5 against the verified Phase 3 baseline and carry its single-agent measurements into the Lab 6 comparison.
