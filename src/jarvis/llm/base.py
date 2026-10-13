from typing import Protocol

from jarvis.contracts import ModelReply


class ModelAdapter(Protocol):
    async def complete(self, messages: list[dict], tools: list[dict]) -> ModelReply: ...
