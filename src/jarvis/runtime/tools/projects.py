"""A launch receipt is not proof that the exact workspace is visible."""
import os
import json
import re
import subprocess
import time
import uuid

from jarvis.runtime.tools.windows import interactive, list_windows
from jarvis.security.paths import executable, project_path
from jarvis.security.credentials import private_root
from jarvis.runtime.protocol import Rejected


def editor_cli(editor):
    from pathlib import Path
    directory = Path(editor).parent
    launcher = directory / "bin" / "code.cmd"
    if launcher.is_symlink():
        raise Rejected("untrusted_editor_cli")
    text = launcher.read_text(encoding="utf-8")
    match = re.search(r'%~dp0\.\.\\([a-f0-9]+\\)?resources\\app\\out\\cli\.js', text)
    if not match:
        raise Rejected("editor_cli_unavailable")
    relative = (match.group(1) or "") + "resources\\app\\out\\cli.js"
    cli = directory.joinpath(*relative.split("\\"))
    if not cli.is_file() or cli.is_symlink():
        raise Rejected("untrusted_editor_cli")
    return str(cli)


def workspace_receipt(directory, ident, root, project_id, launched_at):
    path = directory / (ident + ".result.json")
    if not path.exists():
        return None
    if path.stat().st_size > 4096:
        raise Rejected("workspace_receipt_too_large")
    value = json.loads(path.read_text(encoding="utf-8"))
    if (set(value) != {"id", "project_id", "folder", "verified_at", "method"}
            or value["id"] != ident or value["project_id"] != project_id
            or value["method"] != "vscode_workspace_api"
            or type(value["verified_at"]) not in (int, float)
            or not launched_at <= value["verified_at"] <= time.time()+1
            or os.path.normcase(os.path.realpath(value["folder"])) != os.path.normcase(str(root))):
        raise Rejected("workspace_receipt_mismatch")
    return {"method": "vscode_workspace_api", "request_id": ident, "verified_at": value["verified_at"]}


def open_project(config, project_id, key):
    interactive()
    root = project_path(config, project_id)
    editor = executable(config, "editor_executable")
    env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR", "LOCALAPPDATA", "APPDATA", "USERPROFILE",
            "TEMP", "TMP", "PATH", "HOMEDRIVE", "HOMEPATH") if k in os.environ}
    env["ELECTRON_RUN_AS_NODE"] = "1"
    cli = editor_cli(editor)
    # The extension reads the actual workspace API and returns a request-bound
    # receipt. No credentials or authority come from model text or window titles.
    directory = private_root() / "workspace-requests"
    directory.mkdir(exist_ok=True)
    ident, launched_at = uuid.uuid4().hex, time.time()
    request_path = directory / (ident + ".json")
    with request_path.open("x", encoding="utf-8") as handle:
        json.dump({"id": ident, "project_id": project_id, "folder": str(root), "expires": launched_at+9}, handle)
    # Start the configured folder even when the optional verifier is unavailable.
    subprocess.Popen([editor, cli, "--reuse-window", str(root)], shell=False, env=env,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until = time.monotonic()+7
    evidence = None
    while time.monotonic() < until:
        evidence = workspace_receipt(directory, ident, root, project_id, launched_at)
        if evidence:
            break
        time.sleep(0.2)
    matches = [w for w in list_windows(config, key)["windows"] if root.name.casefold() in w["title"].casefold()]
    output = {"project_id": project_id, "launch_requested": True, "matching_window_count": len(matches)}
    if evidence:
        output["workspace_evidence"] = evidence
    return output
