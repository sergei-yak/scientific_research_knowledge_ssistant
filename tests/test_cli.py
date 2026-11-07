"""Offline CLI tests: report integrity and safe configuration failure."""

import json
from pathlib import Path

import pytest

from research_assistant.__main__ import main


def test_report_overwrite_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "prior-report.json"
    target.write_text("existing evidence", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["smoke", "--checks", "imports", "--output", str(target)])
    assert exc.value.code == 2
    assert target.read_text(encoding="utf-8") == "existing evidence"


def test_invalid_settings_do_not_echo_credential_url(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setenv("NEO4J_URI", "bolt://user:do-not-print@localhost:7687")
    assert main(["smoke"]) == 2
    output = capsys.readouterr().out
    assert "do-not-print" not in output
    assert json.loads(output)["error"] == "invalid_settings"
