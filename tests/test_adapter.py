import json

import httpx
import pytest

from jarvis.config import Settings
from jarvis.llm.llama_cpp import LlamaCppAdapter, ModelProtocolError


def chunk(delta=None, finish=None):
    return "data: " + json.dumps({"choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}]}) + "\n\n"


async def adapter_for(text):
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=text)))
    return LlamaCppAdapter(Settings(), client)


async def test_fragmented_call_assembled_before_use():
    text = chunk({"tool_calls": [{"index": 0, "id": "call-1", "type": "function",
                 "function": {"name": "project_", "arguments": '{"project_'}}]})
    text += chunk({"tool_calls": [{"index": 0, "function": {
        "name": "open", "arguments": 'id":"jarvis-ai"}'}}]})
    text += chunk(finish="tool_calls") + "data: [DONE]\n\n"
    adapter = await adapter_for(text)
    try:
        reply = await adapter.complete([], [])
        assert reply.calls[0].id == "call-1"
        assert reply.calls[0].name == "project_open"
        assert json.loads(reply.calls[0].arguments) == {"project_id": "jarvis-ai"}
    finally:
        await adapter.close()


@pytest.mark.parametrize("text", [
    chunk({"content": "pretend success"}),
    chunk(finish="length") + "data: [DONE]\n\n",
    "data: {bad\n\n",
    chunk({"tool_calls": [{"index": 0, "function": {"name": "system_metrics", "arguments": "{}"}}]}, "tool_calls")
        + "data: [DONE]\n\n",
    chunk({"tool_calls": [{"index": -1, "id": "1", "function": {"name": "x", "arguments": "{}"}}]})
        + chunk(finish="tool_calls") + "data: [DONE]\n\n",
])
async def test_malformed_or_truncated_stream_rejected(text):
    adapter = await adapter_for(text)
    try:
        with pytest.raises(ModelProtocolError):
            await adapter.complete([], [])
    finally:
        await adapter.close()


async def test_textual_fake_calls_remain_text():
    adapter = await adapter_for(chunk({"content": 'system_metrics({})'}, "stop") + "data: [DONE]\n\n")
    try:
        assert not (await adapter.complete([], [])).calls
    finally:
        await adapter.close()


async def test_oversized_unterminated_stream_rejected():
    adapter = await adapter_for("x" * 131073)
    try:
        with pytest.raises(ModelProtocolError, match="byte limit"):
            await adapter.complete([], [])
    finally:
        await adapter.close()


async def test_template_mismatch_disables_tool_mode():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(
        200, json={"chat_template": "unexpected"})))
    adapter = LlamaCppAdapter(Settings(), client)
    try:
        with pytest.raises(ModelProtocolError, match="template"):
            await adapter.health()
    finally:
        await adapter.close()


async def test_readiness_wait_is_bounded_on_unavailable_server():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    adapter = LlamaCppAdapter(Settings(model_timeout=0.01), client)
    try:
        with pytest.raises(TimeoutError):
            await adapter.wait_ready()
    finally:
        await adapter.close()


async def test_readiness_does_not_retry_template_mismatch():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(
        200, json={"chat_template": "changed"})))
    adapter = LlamaCppAdapter(Settings(), client)
    try:
        with pytest.raises(ModelProtocolError):
            await adapter.wait_ready()
    finally:
        await adapter.close()
