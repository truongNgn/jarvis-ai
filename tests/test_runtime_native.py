"""Also executable on Windows with unittest and no third-party dependencies."""
import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path

from jarvis.runtime.auth import authorize, endpoint
from jarvis.runtime.dispatcher import Dispatcher
from jarvis.runtime.journal import Journal
from jarvis.runtime.protocol import TOOLS, Rejected, canonical, digest, loads, manifest, result, sign, validate_call, validate_result
from jarvis.runtime.tools.git import branch
from jarvis.runtime.tools.windows import decode_reference
from jarvis.security.paths import project_path

KEY = "test-key-not-a-real-credential"


def make_call(tool="git.branch", args=None, ident="test-call", deadline=None):
    call = {"version": 1, "policy_version": 1, "call_id": ident, "task_id": "test-task", "tool": tool,
        "args": args if args is not None else {"project_id": "jarvis-ai"},
        "deadline": deadline or time.time()+20, "schema_hash": digest(TOOLS[tool]["args"]),
        "grant": {"principal": "local-user", "tools": [tool], "projects": ["jarvis-ai"]}}
    call["signature"] = sign(call, KEY)
    return call


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jarvis-runtime-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.journal = Journal(self.root / "journal.sqlite")
        self.addCleanup(self.journal.close)
        self.executed = []
        def runner(call, config, credentials, cancelled):
            self.executed.append(call["call_id"])
            return result(call, "succeeded", {"project_id": "jarvis-ai", "state": "branch", "branch": "test", "commit": "a"*40},
                          verification="verified")
        self.config = {"allowed_tools": list(TOOLS)}
        self.dispatcher = Dispatcher(self.config, {"signing_key": KEY}, self.journal, runner)

    def test_dispatch_once_and_replay(self):
        call = make_call()
        a = self.dispatcher.dispatch(call)
        b = self.dispatcher.dispatch(call)
        self.assertEqual(a, b)
        self.assertEqual(self.executed, ["test-call"])

    def test_call_id_collision(self):
        call = make_call()
        self.dispatcher.dispatch(call)
        other = make_call(deadline=time.time()+25)
        self.assertEqual(self.dispatcher.dispatch(other)["error"], "call_id_collision")
        self.assertEqual(len(self.executed), 1)

    def test_unfinished_journal_never_reexecutes(self):
        call = make_call()
        self.journal.begin(call)
        self.assertEqual(self.dispatcher.dispatch(call)["status"], "unknown")
        self.assertEqual(self.executed, [])

    def test_journal_survives_restart(self):
        call = make_call()
        expected = self.dispatcher.dispatch(call)
        other = Journal(self.root / "journal.sqlite")
        try:
            value, fresh = other.begin(call)
            self.assertFalse(fresh)
            self.assertEqual(expected, value)
        finally:
            other.close()

    def test_expired_call_is_denied(self):
        self.assertEqual(self.dispatcher.dispatch(make_call(deadline=time.time()-1))["status"], "denied")
        self.assertEqual(self.executed, [])

    def test_cancelled_before_dispatch(self):
        self.assertEqual(self.dispatcher.dispatch(make_call(), lambda: True)["status"], "cancelled")
        self.assertEqual(self.executed, [])

    def test_invalid_signature(self):
        call = make_call()
        call["signature"] = "0"*64
        self.assertEqual(self.dispatcher.dispatch(call)["status"], "denied")
        call = make_call()
        call["task_id"] = "tampered-valid-task-id"
        self.assertEqual(self.dispatcher.dispatch(call)["status"], "denied")
        self.assertEqual(self.executed, [])

    def test_unknown_tool_even_signed(self):
        call = make_call()
        call["tool"] = "exec_shell"
        self.assertEqual(self.dispatcher.dispatch(call)["status"], "denied")
        self.assertEqual(self.executed, [])

    def test_extra_arguments_rejected(self):
        call = make_call(args={"project_id": "jarvis-ai", "approved": True})
        self.assertEqual(self.dispatcher.dispatch(call)["status"], "denied")
        self.assertEqual(self.executed, [])

    def test_disabled_tool(self):
        self.config["allowed_tools"] = []
        self.assertEqual(self.dispatcher.dispatch(make_call())["status"], "denied")

    def test_wrong_principal_and_schema(self):
        for field, value in [("schema_hash", "wrong"), ("policy_version", 2)]:
            call = make_call()
            call[field] = value
            call["signature"] = sign({k: v for k, v in call.items() if k != "signature"}, KEY)
            self.assertEqual(self.dispatcher.dispatch(call)["status"], "denied")
        call = make_call()
        call["grant"]["principal"] = "attacker"
        self.assertEqual(self.dispatcher.dispatch(call)["status"], "denied")

    def test_result_identity_and_false_verification(self):
        call = make_call()
        with self.assertRaises(Rejected):
            validate_result(result({"call_id": "other", "tool": "git.branch"}, "failed", error="x"), call)
        launch = make_call("project.open")
        with self.assertRaises(Rejected):
            validate_result(result(launch, "succeeded", {"project_id": "jarvis-ai", "launch_requested": True,
                            "matching_window_count": 1}, verification="verified"), launch)

    def test_auth_host_origin_and_token(self):
        for headers in ({"host": "evil:18765", "authorization": "Bearer correct"},
            {"host": "localhost:18765", "authorization": "Bearer incorrect"},
            {"host": "localhost:18765", "authorization": "Bearer correct", "origin": "https://evil"}):
            with self.assertRaises(Rejected):
                authorize(headers, "correct")
        authorize({"host": "localhost:18765", "authorization": "Bearer correct"}, "correct")

    def test_remote_endpoint_rejected(self):
        for url in ("http://evil:18765", "http://user:password@localhost:18765", "http://localhost:18765/?token=x"):
            with self.assertRaises(Rejected):
                endpoint(url)

    def test_duplicate_json_and_reparse(self):
        with self.assertRaises(Rejected):
            loads('{"project_id":"other","project_id":"jarvis-ai"}')
        with self.assertRaises(Rejected):
            project_path({"projects": {"jarvis-ai": "//server/share"}}, "jarvis-ai")
        if os.name != "nt":
            linked = self.root / "link"
            linked.symlink_to(self.root, target_is_directory=True)
            with self.assertRaises(Rejected):
                project_path({"projects": {"jarvis-ai": str(linked)}}, "jarvis-ai")

    def test_stale_and_forged_window_reference(self):
        data = {"hwnd": 1, "pid": 1, "created": "1", "expiry": 1.0}
        reference = base64.urlsafe_b64encode(canonical(data).encode()).decode()+"."+sign(data, KEY)
        with self.assertRaises(Rejected):
            decode_reference(reference, KEY)
        with self.assertRaises(Rejected):
            decode_reference(reference, "other")

    def test_gpu_unavailable_is_explicit(self):
        call = make_call("system.metrics", {})
        data = {"cpu_percent": 12.5, "ram_used_bytes": 10, "ram_total_bytes": 20,
            "disk_free_bytes": 10, "disk_total_bytes": 20, "sample_time": time.time(), "sample_seconds": 0.1,
            "gpu": {"available": False, "reason": "nvml_unavailable"}}
        validate_result(result(call, "succeeded", data, verification="verified"), call)

    def test_worker_timeout_stops_only_owned_worker(self):
        from jarvis.runtime import workers
        class Process:
            killed = False
            def communicate(self, *args, **kwargs):
                if not self.killed:
                    raise subprocess.TimeoutExpired("owned-worker", 0.2)
                return "", ""
            def kill(self):
                self.killed = True
            def poll(self):
                return -9 if self.killed else None
        for tool, args, expected in [("git.branch", {"project_id": "jarvis-ai"}, "cancelled"),
                                     ("project.open", {"project_id": "jarvis-ai"}, "unknown")]:
            process = Process()
            with patch.object(workers.subprocess, "Popen", return_value=process):
                output = workers.execute(make_call(tool, args), self.config,
                    {"signing_key": KEY, "runtime_token": KEY}, lambda: True)
            self.assertTrue(process.killed)
            self.assertEqual(output["status"], expected)

    def test_foreground_is_verified_and_recycled_identity_rejected(self):
        from jarvis.runtime.tools import windows
        data = {"hwnd": 1, "pid": 2, "created": "3", "expiry": time.time()+20}
        reference = base64.urlsafe_b64encode(canonical(data).encode()).decode()+"."+sign(data, KEY)
        class User:
            def SetForegroundWindow(self, hwnd): return True
            def GetForegroundWindow(self): return 9
        with patch.object(windows, "interactive"), patch.object(windows, "identity", return_value=(2, "3")), \
                patch.object(windows, "apis", return_value=(User(), None)):
            with self.assertRaisesRegex(Rejected, "foreground_denied"):
                windows.activate({}, KEY, reference)
        with patch.object(windows, "interactive"), patch.object(windows, "identity", return_value=(2, "new-creation")):
            with self.assertRaisesRegex(Rejected, "stale_window_identity"):
                windows.activate({}, KEY, reference)

    @unittest.skipUnless(shutil.which("git"), "Git is not installed in the Linux AI image")
    def test_git_unborn_branch_detached_and_worktree(self):
        git = shutil.which("git")
        repo = self.root / "repo"
        repo.mkdir()
        def command(*args):
            return subprocess.run([git, "-C", str(repo), *args], check=True, capture_output=True,
                                  text=True, encoding="utf-8").stdout.strip()
        command("init", "-b", "main")
        config = {"projects": {"jarvis-ai": str(repo)}, "git_executable": git}
        self.assertEqual(branch(config, "jarvis-ai")["state"], "unborn")
        command("-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-m", "fixture")
        self.assertEqual(branch(config, "jarvis-ai")["branch"], "main")
        command("checkout", "-b", "feature/tiếng-Việt")
        self.assertEqual(branch(config, "jarvis-ai")["branch"], "feature/tiếng-Việt")
        command("checkout", "--detach")
        self.assertEqual(branch(config, "jarvis-ai")["state"], "detached")
        worktree = self.root / "worktree"
        command("worktree", "add", "-b", "topic", str(worktree))
        self.assertEqual(branch({**config, "projects": {"jarvis-ai": str(worktree)}}, "jarvis-ai")["branch"], "topic")

    @unittest.skipUnless(shutil.which("git"), "Git is not installed in the Linux AI image")
    def test_non_repository(self):
        value = branch({"projects": {"jarvis-ai": str(self.root)}, "git_executable": shutil.which("git")}, "jarvis-ai")
        self.assertEqual(value["state"], "not_a_repository")


if __name__ == "__main__":
    unittest.main()
