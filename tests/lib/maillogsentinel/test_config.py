"""Tests for the new configuration module."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

from lib.maillogsentinel import config


def test_configuration_validation_success() -> None:
    cfg = config.Configuration()
    assert cfg.validate() == []


def test_configuration_validation_errors() -> None:
    cfg = config.Configuration()
    cfg.general.log_level = "INVALID"
    cfg.paths.mail_log = "relative.log"
    cfg.report.recipient = "not-an-email"
    errors = cfg.validate()
    assert "Log level" in errors[0]
    assert any("absolute" in error for error in errors)
    assert any("email" in error for error in errors)


def test_merger_respects_precedence(tmp_path: Path) -> None:
    config_path = tmp_path / "config.conf"
    config_path.write_text(
        """
[general]
log_level = WARNING

[paths]
working_dir = /var/log/custom
state_dir = /var/lib/custom
mail_log = /var/log/mail.log
csv_filename = custom.csv
""",
        encoding="utf-8",
    )

    env: Dict[str, str] = {
        "MAILLOGSENTINEL__GENERAL__LOG_LEVEL": "ERROR",
        "MAILLOGSENTINEL__REPORT__RECIPIENT": "env@example.com",
    }

    overrides = {"general__log_level": "DEBUG"}

    merger = config.ConfigurationMerger(
        config_path=config_path,
        environment=env,
        overrides=overrides,
    )
    cfg = merger.load()

    assert cfg.general.log_level == "DEBUG"
    assert cfg.report.recipient == "env@example.com"
    assert cfg.paths.working_dir == "/var/log/custom"


def test_configuration_writer_dry_run(tmp_path: Path) -> None:
    cfg = config.Configuration()
    path = tmp_path / "maillogsentinel.conf"
    writer = config.ConfigurationWriter(path)
    content, diff = writer.write(cfg, dry_run=True)
    assert "[general]" in content
    assert "maillogsentinel.conf" in diff
    assert not path.exists()


def test_configuration_writer_persists(tmp_path: Path) -> None:
    cfg = config.Configuration()
    path = tmp_path / "maillogsentinel.conf"
    writer = config.ConfigurationWriter(path)
    content, diff = writer.write(cfg, dry_run=False)
    assert path.exists()
    new_content, new_diff = writer.write(cfg, dry_run=False)
    assert "No newline at end" not in new_diff
    assert new_diff == ""


def test_appconfig_wrapper(tmp_path: Path) -> None:
    path = tmp_path / "config.conf"
    path.write_text(
        """
[paths]
working_dir = /tmp/work
state_dir = /tmp/state
mail_log = /tmp/mail.log
csv_filename = custom.csv

[report]
recipient = test@example.com

[general]
log_level = WARNING
log_file_max_mb = 10
log_file_backup_count = 3

[dns_cache]
enabled = false
size = 64
ttl = 600

[database]
path = /tmp/db.sqlite

[timers]
sql_export = *:0/10
sql_import = *:0/20
""",
        encoding="utf-8",
    )

    app_config = config.AppConfig(path)
    assert app_config.working_dir == Path("/tmp/work")
    assert app_config.dns_cache_enabled is False
    assert app_config.sql_export_frequency == "*:0/10"
