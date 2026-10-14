"""Fixed read-only Git argv with hooks, pager, prompts and fsmonitor disabled."""
import os
import subprocess

from jarvis.runtime.protocol import Rejected
from jarvis.security.paths import executable, project_path


def branch(config, project_id):
    root = project_path(config, project_id)
    git = executable(config, "git_executable")
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "", "LC_ALL": "C"})
    def run(*args):
        p = subprocess.run([git, "--no-optional-locks", "-c", "core.fsmonitor=false", "-c",
            "core.hooksPath=" + os.devnull, "-C", str(root), *args], env=env,
            capture_output=True, text=True, encoding="utf-8", timeout=2, shell=False)
        if len(p.stdout) + len(p.stderr) > 8192:
            raise Rejected("git_output_too_large")
        return p
    top = run("rev-parse", "--show-toplevel")
    if top.returncode:
        if "not a git repository" in top.stderr:
            return {"project_id": project_id, "state": "not_a_repository", "branch": "", "commit": ""}
        raise Rejected("git_repository_unavailable")
    if os.path.normcase(os.path.realpath(top.stdout.strip())) != os.path.normcase(str(root)):
        raise Rejected("git_root_scope_mismatch")
    symbolic = run("symbolic-ref", "--quiet", "--short", "HEAD")
    commit = run("rev-parse", "--verify", "HEAD")
    if symbolic.returncode not in (0, 1) or commit.returncode not in (0, 128):
        raise Rejected("git_read_failed")
    return {"project_id": project_id, "state": "branch" if commit.returncode == 0 and symbolic.returncode == 0
            else "unborn" if symbolic.returncode == 0 else "detached", "branch": symbolic.stdout.strip(),
            "commit": commit.stdout.strip() if commit.returncode == 0 else ""}
