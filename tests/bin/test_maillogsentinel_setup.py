"""CLI tests for the refactored MailLogSentinel setup utility."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Dict

import pytest

import bin.maillogsentinel_setup as cli
from lib.maillogsentinel import config


@pytest.fixture(autouse=True)
def _no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "detect_color_support", lambda: False)
    monkeypatch.setattr(cli, "verify_permissions", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "ensure_systemd_unit", lambda *args, **kwargs: None)


def test_non_interactive_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO())
    config_path = tmp_path / "cfg.conf"
    exit_code = cli.main(
        ["--config", str(config_path), "--dry-run", "--no-color", "--non-interactive"]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Dry-run mode" in captured.out
    assert "Configuration diff" in captured.out


def test_interactive_updates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    config_path = tmp_path / "cfg.conf"

    def fake_prompt(
        text: str, *, default: str | None, options: cli.OutputOptions
    ) -> str:
        if "Log level" in text:
            return "DEBUG"
        if "Max log file size" in text:
            return "128"
        if "Enable DNS cache" in text:
            return "n"
        return default or ""

    def fake_confirm(
        text: str, *, options: cli.OutputOptions, default: bool = True
    ) -> bool:
        if "Enable DNS cache" in text:
            return False
        return True

    written: Dict[str, config.Configuration] = {}

    def fake_write(
        self: config.ConfigurationWriter,
        cfg: config.Configuration,
        *,
        dry_run: bool = False,
    ):
        written["config"] = cfg
        return "content", "diff"

    monkeypatch.setattr(cli, "prompt", fake_prompt)
    monkeypatch.setattr(cli, "confirm", fake_confirm)
    monkeypatch.setattr(config.ConfigurationWriter, "write", fake_write, raising=False)

    exit_code = cli.main(
        [
            "--config",
            str(config_path),
            "--interactive",
            "--no-color",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Setup completed successfully" in captured.out
    assert written["config"].general.log_level == "DEBUG"
    assert written["config"].general.log_file_max_mb == 128
    assert written["config"].dns_cache.enabled is False


def test_invalid_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO())
    config_path = tmp_path / "cfg.conf"
    exit_code = cli.main(
        [
            "--config",
            str(config_path),
            "--set",
            "general.log_level=INVALID",
            "--no-color",
            "--non-interactive",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Log level" in captured.out
