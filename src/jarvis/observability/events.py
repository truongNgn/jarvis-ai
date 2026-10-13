"""Bounded per-task metadata, without user text or raw model reasoning."""
import time


def event(kind: str, **fields) -> dict:
    return {"type": kind, "time": round(time.time(), 3), **fields}
