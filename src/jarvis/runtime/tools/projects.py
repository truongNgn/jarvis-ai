"""A launch receipt is not proof that the exact workspace is visible."""
import os
import subprocess
import time

from jarvis.runtime.tools.windows import interactive, list_windows
from jarvis.security.paths import executable, project_path


def open_project(config, project_id, key):
    interactive()
    root = project_path(config, project_id)
    editor = executable(config, "editor_executable")
    env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR", "LOCALAPPDATA", "APPDATA", "USERPROFILE",
            "TEMP", "TMP", "PATH", "HOMEDRIVE", "HOMEPATH") if k in os.environ}
    subprocess.Popen([editor, "--reuse-window", str(root)], shell=False, env=env,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.5)
    windows = list_windows(config, key)["windows"]
    matches = [w for w in windows if root.name.casefold() in w["title"].casefold()]
    return {"project_id": project_id, "launch_requested": True, "matching_window_count": len(matches)}
