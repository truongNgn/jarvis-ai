"""Bounded OpenAI-style streamed tool calls; partial arguments never execute."""
import asyncio
import hashlib
import json

import httpx

from jarvis.config import Settings
from jarvis.contracts import ModelReply, ToolCall
from jarvis.llm.profiles import TEMPLATE_SHA256


class ModelProtocolError(RuntimeError):
    pass


async def bounded_lines(response):
    buffered = b""
    total = 0
    async for part in response.aiter_bytes():
        total += len(part)
        if total > 131072:
            raise ModelProtocolError("Stream byte limit exceeded")
        buffered += part
        while b"\n" in buffered:
            line, buffered = buffered.split(b"\n", 1)
            try:
                yield line.rstrip(b"\r").decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ModelProtocolError("Invalid stream encoding") from exc
    if buffered:
        yield buffered.decode("utf-8")


class LlamaCppAdapter:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=settings.model_timeout, trust_env=False,
                                                  follow_redirects=False)

    async def close(self):
        await self.client.aclose()

    async def health(self) -> dict:
        root = self.settings.base_url.removesuffix("/v1")
        health = await self.client.get(root + "/health")
        health.raise_for_status()
        props = await self.client.get(root + "/props")
        props.raise_for_status()
        template_hash = hashlib.sha256(props.json().get("chat_template", "").encode()).hexdigest()
        if template_hash != TEMPLATE_SHA256:
            raise ModelProtocolError("Model template does not match the validated profile")
        return {"ready": True, "template_sha256": template_hash}

    async def wait_ready(self, cancel: asyncio.Event | None = None) -> dict:
        async with asyncio.timeout(self.settings.model_timeout):
            while True:
                if cancel and cancel.is_set():
                    raise asyncio.CancelledError
                try:
                    return await self.health()
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 503:
                        raise
                except httpx.TransportError:
                    pass
                if cancel:
                    try:
                        await asyncio.wait_for(cancel.wait(), 0.25)
                    except TimeoutError:
                        pass
                else:
                    await asyncio.sleep(0.25)

    async def complete(self, messages: list[dict], tools: list[dict]) -> ModelReply:
        payload = {"model": self.settings.model, "messages": messages, "tools": tools,
                   "tool_choice": "auto", "parallel_tool_calls": False,
                   "temperature": 0, "max_tokens": 256, "stream": True}
        fragments: dict[int, dict] = {}
        content = ""
        finished = None
        done = False
        async with self.client.stream("POST", self.settings.base_url + "/chat/completions",
                                      json=payload) as response:
            response.raise_for_status()
            async for line in bounded_lines(response):
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    done = True
                    break
                try:
                    chunk = json.loads(data)
                    choices = chunk.get("choices", [])
                    if not choices:
                        continue
                    if len(choices) != 1 or choices[0].get("index", 0) != 0:
                        raise ValueError("Unexpected choices")
                    choice = choices[0]
                    delta = choice.get("delta", {})
                    content += delta.get("content") or ""
                    if len(content) > 4000:
                        raise ValueError("Content limit exceeded")
                    for call in delta.get("tool_calls", []):
                        index = call["index"]
                        if type(index) is not int or not 0 <= index < 8:
                            raise ValueError("Invalid call index")
                        item = fragments.setdefault(index, {"id": "", "name": "", "arguments": ""})
                        if call.get("type", "function") != "function":
                            raise ValueError("Unsupported call type")
                        if call.get("id"):
                            if item["id"] and item["id"] != call["id"]:
                                raise ValueError("Call ID changed in stream")
                            item["id"] = call["id"]
                        fn = call.get("function", {})
                        item["name"] += fn.get("name") or ""
                        item["arguments"] += fn.get("arguments") or ""
                        if len(item["arguments"]) > 2048 or len(item["name"]) > 64:
                            raise ValueError("Call size limit exceeded")
                    if choice.get("finish_reason") is not None:
                        finished = choice["finish_reason"]
                except (ValueError, KeyError, TypeError) as exc:
                    raise ModelProtocolError("Malformed inference stream") from exc
        if not done or finished not in {"stop", "tool_calls"}:
            raise ModelProtocolError("Incomplete or truncated inference stream")
        try:
            calls = [ToolCall.model_validate(fragments[i]) for i in sorted(fragments)]
            if len({c.id for c in calls}) != len(calls):
                raise ValueError("Duplicate tool call ID")
            return ModelReply(content=content, calls=calls)
        except ValueError as exc:
            raise ModelProtocolError("Invalid tool call envelope") from exc
