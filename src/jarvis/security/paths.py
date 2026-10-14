"""Configured aliases only; reject reparse points and device/UNC paths."""
import os
from pathlib import Path

from jarvis.runtime.protocol import Rejected


def project_path(config, project_id):
    if project_id not in config["projects"]:
        raise Rejected("unknown_project")
    raw = config["projects"][project_id]
    if not isinstance(raw, str) or raw.startswith(("\\\\", "//")) or ".." in Path(raw).parts:
        raise Rejected("unsafe_project_path")
    if os.name == "nt" and (not Path(raw).is_absolute() or ":" in raw[2:]):
        raise Rejected("unsafe_project_path")
    path = Path(raw)
    for part in (path, *path.parents):
        stat = part.lstat()
        if part.is_symlink() or getattr(stat, "st_file_attributes", 0) & 0x400:
            raise Rejected("reparse_project_path")
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise Rejected("project_is_not_directory")
    return resolved


def executable(config, name):
    path = Path(config[name])
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise Rejected("untrusted_executable")
    return str(path.resolve(strict=True))
