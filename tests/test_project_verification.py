import json
import time

import pytest

from jarvis.runtime.protocol import Rejected
from jarvis.runtime.tools.projects import workspace_receipt, editor_cli


def receipt(tmp_path, **changed):
    ident = "a"*32
    value = {"id": ident, "project_id": "jarvis-ai", "folder": str(tmp_path),
             "verified_at": time.time(), "method": "vscode_workspace_api", **changed}
    (tmp_path / (ident + ".result.json")).write_text(json.dumps(value), encoding="utf-8")
    return workspace_receipt(tmp_path, ident, tmp_path.resolve(), "jarvis-ai", time.time()-1)


def test_receipt_requires_exact_workspace_identity(tmp_path):
    assert receipt(tmp_path)["method"] == "vscode_workspace_api"
    assert workspace_receipt(tmp_path, "b"*32, tmp_path, "jarvis-ai", time.time()) is None


@pytest.mark.parametrize("changed", [{"id": "wrong"}, {"project_id": "other"},
    {"folder": "/unrelated"}, {"verified_at": 0}, {"method": "window_title"}, {"extra": True}])
def test_stale_or_substituted_receipt_rejected(tmp_path, changed):
    with pytest.raises(Rejected):
        receipt(tmp_path, **changed)


def test_editor_cli_resolves_only_vendor_launcher_path(tmp_path):
    (tmp_path / "bin").mkdir()
    script = tmp_path / "abc123" / "resources" / "app" / "out" / "cli.js"
    script.parent.mkdir(parents=True)
    script.write_text("// test vendor file")
    (tmp_path / "bin" / "code.cmd").write_text(r'"%~dp0..\Code.exe" "%~dp0..\abc123\resources\app\out\cli.js" %*')
    assert editor_cli(str(tmp_path / "Code.exe")) == str(script)
    (tmp_path / "bin" / "code.cmd").write_text("unrecognized launcher")
    with pytest.raises(Rejected):
        editor_cli(str(tmp_path / "Code.exe"))
