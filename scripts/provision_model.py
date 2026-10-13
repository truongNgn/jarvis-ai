"""Run only inside a temporary container with /source:ro and /target mounts.

Copies a verified local artifact into the JARVIS-owned model volume. No download.
"""
import hashlib
import os
from pathlib import Path

NAME = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
EXPECTED = "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"
source, target = Path("/source") / NAME, Path("/target") / NAME


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


if target.is_symlink() or source.is_symlink():
    raise SystemExit("Symlink artifacts are not allowed")
if target.exists():
    if digest(target) != EXPECTED:
        raise SystemExit("Existing JARVIS model has an unexpected checksum; refusing overwrite")
    print("Existing JARVIS model verified")
else:
    if digest(source) != EXPECTED:
        raise SystemExit("Source checksum mismatch")
    temporary = target.with_suffix(".partial")
    # Exclusive creation avoids overwriting another provisioning operation.
    with source.open("rb") as src, temporary.open("xb") as dst:
        for chunk in iter(lambda: src.read(4 * 1024 * 1024), b""):
            dst.write(chunk)
        dst.flush()
        os.fsync(dst.fileno())
    if digest(temporary) != EXPECTED:
        temporary.unlink()
        raise SystemExit("Copied model checksum mismatch")
    temporary.replace(target)
    print("Independent JARVIS model installed and verified")
