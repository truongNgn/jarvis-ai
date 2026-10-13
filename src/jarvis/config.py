"""Local-only inference configuration and hard execution limits."""
import os
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from jarvis.contracts import StrictModel


class Settings(StrictModel):
    base_url: str = "http://inference:8080/v1"
    model: str = "jarvis-qwen"
    max_calls: int = Field(default=8, ge=1, le=8)
    max_turns: int = Field(default=12, ge=1, le=12)
    task_timeout: float = Field(default=120.0, gt=0, le=120)
    model_timeout: float = Field(default=30.0, gt=0, le=60)
    tool_timeout: float = Field(default=2.0, gt=0, le=5)
    max_context_chars: int = Field(default=6500, ge=2000, le=6500)

    @model_validator(mode="after")
    def local_only(self):
        url = urlsplit(self.base_url)
        if (url.scheme != "http" or url.hostname not in {"inference", "localhost", "127.0.0.1"}
                or url.username or url.password or url.query or url.fragment
                or url.path.rstrip("/") != "/v1"):
            raise ValueError("Only explicit local inference endpoints are allowed")
        return self

    @classmethod
    def environment(cls):
        return cls(base_url=os.environ.get("JARVIS_LLM_URL", "http://inference:8080/v1"))
