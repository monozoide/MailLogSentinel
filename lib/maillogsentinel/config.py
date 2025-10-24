"""Configuration management for MailLogSentinel setup and runtime.

This module provides a versioned configuration schema with helpers to
load, validate, review, and persist configuration data in an idempotent
way.  The public API is split between a modern `Configuration` dataclass
used by the setup workflow and a backwards-compatible `AppConfig` class
that retains the attribute interface consumed by the rest of the
application.

The precedence order for configuration sources is:

1. Command line overrides (highest priority)
2. Environment variables (``MAILLOGSENTINEL__SECTION__OPTION``)
3. Configuration file
4. Built-in defaults (lowest priority)

The module only relies on the Python standard library.
"""

from __future__ import annotations

import configparser
import copy
import difflib
import json
import logging
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

CONFIG_SCHEMA_VERSION = "1.0"


class ConfigurationError(Exception):
    """Raised when configuration validation fails."""


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in {"1", "true", "yes", "y", "on"}:
            return True
        if lower in {"0", "false", "no", "n", "off"}:
            return False
    raise ConfigurationError(f"Cannot coerce value to boolean: {value!r}")


def _expand_path(value: Any) -> str:
    if value in {None, ""}:
        return ""
    return str(Path(str(value)).expanduser())


def _validate_email(value: str) -> bool:
    if not value:
        return True
    email_re = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    return bool(email_re.match(value))


def _validate_log_level(value: str) -> bool:
    return value.upper() in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


def _ensure_absolute(path_str: str, *, allow_empty: bool = False) -> Path:
    if not path_str and allow_empty:
        return Path("")
    path = Path(path_str)
    if not path.is_absolute():
        raise ConfigurationError(f"Path must be absolute: {path_str}")
    return path


@dataclass
class GeneralSettings:
    log_level: str = "INFO"
    log_file_max_mb: int = 64
    log_file_backup_count: int = 7

    def validate(self) -> List[str]:
        issues: List[str] = []
        if not _validate_log_level(self.log_level):
            issues.append(
                "Log level must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL."
            )
        if self.log_file_max_mb <= 0:
            issues.append("Max log file size must be a positive integer.")
        if self.log_file_backup_count < 0:
            issues.append("Log file backup count cannot be negative.")
        return issues


@dataclass
class PathSettings:
    working_dir: str = "/var/log/maillogsentinel"
    state_dir: str = "/var/lib/maillogsentinel"
    mail_log: str = "/var/log/mail.log"
    csv_filename: str = "maillogsentinel.csv"

    def validate(self) -> List[str]:
        issues: List[str] = []
        try:
            _ensure_absolute(self.working_dir)
            _ensure_absolute(self.state_dir)
            _ensure_absolute(self.mail_log)
        except ConfigurationError as error:
            issues.append(str(error))
        if not self.csv_filename:
            issues.append("CSV filename must not be empty.")
        return issues


@dataclass
class PermissionSettings:
    service_user: str = "maillogsentinel"

    def validate(self) -> List[str]:
        issues: List[str] = []
        if not self.service_user:
            issues.append("Service user must not be empty.")
        return issues


@dataclass
class ReportSettings:
    recipient: str = ""
    subject_prefix: str = "[MailLogSentinel]"
    sender: str = ""

    def validate(self) -> List[str]:
        issues: List[str] = []
        if self.recipient and not _validate_email(self.recipient):
            issues.append("Report recipient must be a valid email address.")
        if self.sender and not _validate_email(self.sender):
            issues.append("Report sender must be a valid email address.")
        if not self.subject_prefix:
            issues.append("Report subject prefix must not be empty.")
        return issues


@dataclass
class DNSCacheSettings:
    enabled: bool = True
    size: int = 256
    ttl: int = 3600

    def validate(self) -> List[str]:
        issues: List[str] = []
        if self.size <= 0:
            issues.append("DNS cache size must be positive.")
        if self.ttl <= 0:
            issues.append("DNS cache TTL must be positive.")
        return issues


@dataclass
class GeoSettings:
    country_db_path: str = "/var/lib/maillogsentinel/country.mmdb"
    asn_db_path: str = "/var/lib/maillogsentinel/asn.mmdb"

    def validate(self) -> List[str]:
        issues: List[str] = []
        try:
            _ensure_absolute(self.country_db_path, allow_empty=True)
        except ConfigurationError as error:
            issues.append(str(error))
        try:
            _ensure_absolute(self.asn_db_path, allow_empty=True)
        except ConfigurationError as error:
            issues.append(str(error))
        return issues


@dataclass
class DatabaseSettings:
    path: str = "/var/lib/maillogsentinel/maillogsentinel.sqlite"

    def validate(self) -> List[str]:
        issues: List[str] = []
        try:
            _ensure_absolute(self.path)
        except ConfigurationError as error:
            issues.append(str(error))
        return issues


@dataclass
class TimerSettings:
    log_extraction: str = "*:0/5"
    report: str = "*-*-* 06:00:00"
    ip_db_update: str = "Mon *-*-* 03:00:00"
    sql_export: str = "*:0/30"
    sql_import: str = "*:0/30"

    def validate(self) -> List[str]:
        issues: List[str] = []
        for name, value in asdict(self).items():
            if not value:
                issues.append(f"Systemd timer '{name}' must not be empty.")
        return issues


@dataclass
class Configuration:
    general: GeneralSettings = field(default_factory=GeneralSettings)
    paths: PathSettings = field(default_factory=PathSettings)
    permissions: PermissionSettings = field(default_factory=PermissionSettings)
    report: ReportSettings = field(default_factory=ReportSettings)
    dns_cache: DNSCacheSettings = field(default_factory=DNSCacheSettings)
    geo: GeoSettings = field(default_factory=GeoSettings)
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    timers: TimerSettings = field(default_factory=TimerSettings)
    schema_version: str = CONFIG_SCHEMA_VERSION

    def validate(self) -> List[str]:
        issues: List[str] = []
        issues.extend(self.general.validate())
        issues.extend(self.paths.validate())
        issues.extend(self.permissions.validate())
        issues.extend(self.report.validate())
        issues.extend(self.dns_cache.validate())
        issues.extend(self.geo.validate())
        issues.extend(self.database.validate())
        issues.extend(self.timers.validate())
        if self.schema_version != CONFIG_SCHEMA_VERSION:
            issues.append(
                f"Configuration schema version {self.schema_version!r} is not supported."
            )
        return issues

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data

    def to_ini(self) -> configparser.ConfigParser:
        parser = configparser.ConfigParser()
        parser["meta"] = {"schema_version": self.schema_version}
        parser["general"] = {
            "log_level": self.general.log_level,
            "log_file_max_mb": str(self.general.log_file_max_mb),
            "log_file_backup_count": str(self.general.log_file_backup_count),
        }
        parser["paths"] = {
            "working_dir": self.paths.working_dir,
            "state_dir": self.paths.state_dir,
            "mail_log": self.paths.mail_log,
            "csv_filename": self.paths.csv_filename,
        }
        parser["permissions"] = {"service_user": self.permissions.service_user}
        parser["report"] = {
            "recipient": self.report.recipient,
            "subject_prefix": self.report.subject_prefix,
            "sender": self.report.sender,
        }
        parser["dns_cache"] = {
            "enabled": json.dumps(self.dns_cache.enabled),
            "size": str(self.dns_cache.size),
            "ttl": str(self.dns_cache.ttl),
        }
        parser["geo"] = {
            "country_db_path": self.geo.country_db_path,
            "asn_db_path": self.geo.asn_db_path,
        }
        parser["database"] = {"path": self.database.path}
        parser["timers"] = {
            "log_extraction": self.timers.log_extraction,
            "report": self.timers.report,
            "ip_db_update": self.timers.ip_db_update,
            "sql_export": self.timers.sql_export,
            "sql_import": self.timers.sql_import,
        }
        return parser

    @classmethod
    def from_ini(
        cls,
        parser: configparser.ConfigParser,
        *,
        base: Optional["Configuration"] = None,
    ) -> "Configuration":
        cfg = copy.deepcopy(base) if base else cls()
        if parser.has_section("meta") and parser.has_option("meta", "schema_version"):
            cfg.schema_version = parser.get("meta", "schema_version")
        if parser.has_section("general"):
            if parser.has_option("general", "log_level"):
                cfg.general.log_level = parser.get("general", "log_level")
            if parser.has_option("general", "log_file_max_mb"):
                cfg.general.log_file_max_mb = parser.getint(
                    "general", "log_file_max_mb"
                )
            if parser.has_option("general", "log_file_backup_count"):
                cfg.general.log_file_backup_count = parser.getint(
                    "general", "log_file_backup_count"
                )
        if parser.has_section("paths"):
            if parser.has_option("paths", "working_dir"):
                cfg.paths.working_dir = _expand_path(parser.get("paths", "working_dir"))
            if parser.has_option("paths", "state_dir"):
                cfg.paths.state_dir = _expand_path(parser.get("paths", "state_dir"))
            if parser.has_option("paths", "mail_log"):
                cfg.paths.mail_log = _expand_path(parser.get("paths", "mail_log"))
            if parser.has_option("paths", "csv_filename"):
                cfg.paths.csv_filename = parser.get("paths", "csv_filename")
        if parser.has_section("permissions") and parser.has_option(
            "permissions", "service_user"
        ):
            cfg.permissions.service_user = parser.get("permissions", "service_user")
        if parser.has_section("report"):
            if parser.has_option("report", "recipient"):
                cfg.report.recipient = parser.get("report", "recipient")
            if parser.has_option("report", "subject_prefix"):
                cfg.report.subject_prefix = parser.get("report", "subject_prefix")
            if parser.has_option("report", "sender"):
                cfg.report.sender = parser.get("report", "sender")
        if parser.has_section("dns_cache"):
            if parser.has_option("dns_cache", "enabled"):
                cfg.dns_cache.enabled = _to_bool(parser.get("dns_cache", "enabled"))
            if parser.has_option("dns_cache", "size"):
                cfg.dns_cache.size = parser.getint("dns_cache", "size")
            if parser.has_option("dns_cache", "ttl"):
                cfg.dns_cache.ttl = parser.getint("dns_cache", "ttl")
        if parser.has_section("geo"):
            if parser.has_option("geo", "country_db_path"):
                cfg.geo.country_db_path = _expand_path(
                    parser.get("geo", "country_db_path")
                )
            if parser.has_option("geo", "asn_db_path"):
                cfg.geo.asn_db_path = _expand_path(parser.get("geo", "asn_db_path"))
        if parser.has_section("database") and parser.has_option("database", "path"):
            cfg.database.path = _expand_path(parser.get("database", "path"))
        if parser.has_section("timers"):
            if parser.has_option("timers", "log_extraction"):
                cfg.timers.log_extraction = parser.get("timers", "log_extraction")
            if parser.has_option("timers", "report"):
                cfg.timers.report = parser.get("timers", "report")
            if parser.has_option("timers", "ip_db_update"):
                cfg.timers.ip_db_update = parser.get("timers", "ip_db_update")
            if parser.has_option("timers", "sql_export"):
                cfg.timers.sql_export = parser.get("timers", "sql_export")
            if parser.has_option("timers", "sql_import"):
                cfg.timers.sql_import = parser.get("timers", "sql_import")
        return cfg


def _env_to_dict(env: Mapping[str, str]) -> Dict[str, Dict[str, str]]:
    result: Dict[str, Dict[str, str]] = {}
    prefix = "MAILLOGSENTINEL__"
    for key, value in env.items():
        if not key.startswith(prefix):
            continue
        remainder = key[len(prefix) :]
        try:
            section, option = remainder.split("__", 1)
        except ValueError:
            continue
        section = section.lower()
        option = option.lower()
        section_dict = result.setdefault(section, {})
        section_dict[option] = value
    return result


class ConfigurationMerger:
    """Merges configuration sources with defined precedence."""

    def __init__(
        self,
        *,
        config_path: Path,
        environment: Optional[Mapping[str, str]] = None,
        overrides: Optional[Mapping[str, Any]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.config_path = config_path
        self.environment = environment or os.environ
        self.overrides = overrides or {}
        self.logger = logger or logging.getLogger(__name__)

    def load(self) -> Configuration:
        config = Configuration()
        if self.config_path.exists():
            file_parser = configparser.ConfigParser()
            try:
                file_parser.read(self.config_path)
                config = Configuration.from_ini(file_parser, base=config)
            except configparser.Error as error:
                raise ConfigurationError(
                    f"Failed to parse configuration file: {error}"
                ) from error

        env_data = _env_to_dict(self.environment)
        if env_data:
            env_parser = configparser.ConfigParser()
            env_parser.read_dict(env_data)
            config = Configuration.from_ini(env_parser, base=config)

        if self.overrides:
            cli_parser = configparser.ConfigParser()
            cli_parser.read_dict(self._normalize_overrides(self.overrides))
            config = Configuration.from_ini(cli_parser, base=config)

        issues = config.validate()
        if issues:
            raise ConfigurationError("; ".join(issues))
        return config

    def _normalize_overrides(
        self, overrides: Mapping[str, Any]
    ) -> Dict[str, Dict[str, str]]:
        normalized: Dict[str, Dict[str, str]] = {}
        for key, value in overrides.items():
            if "__" in key:
                section, option = key.split("__", 1)
            elif "." in key:
                section, option = key.split(".", 1)
            else:
                raise ConfigurationError(
                    "Overrides must use 'section__option' or 'section.option' format."
                )
            section_dict = normalized.setdefault(section.lower(), {})
            section_dict[option.lower()] = str(value)
        return normalized


def safe_write(path: Path, data: str) -> None:
    """Atomically write ``data`` to ``path`` with a deterministic backup."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = path.with_suffix(path.suffix + ".bak")
    if path.exists():
        shutil.copy2(path, backup_path)

    tmp_fd, tmp_path_str = tempfile.mkstemp(
        dir=str(path.parent), prefix=".tmp", suffix=path.suffix
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def generate_diff(original: Optional[str], new_content: str, *, path: Path) -> str:
    original_lines = original.splitlines(keepends=True) if original else []
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(
        original_lines,
        new_lines,
        fromfile=str(path),
        tofile=str(path),
        lineterm="",
    )
    return "\n".join(diff)


class ConfigurationWriter:
    """Persist a configuration instance to disk atomically."""

    def __init__(self, path: Path, logger: Optional[logging.Logger] = None) -> None:
        self.path = path
        self.logger = logger or logging.getLogger(__name__)

    def write(
        self, config: Configuration, *, dry_run: bool = False
    ) -> Tuple[str, Optional[str]]:
        parser = config.to_ini()
        buffer = []
        with tempfile.TemporaryFile("w+", encoding="utf-8") as temp:
            parser.write(temp)
            temp.seek(0)
            buffer = temp.read().splitlines()
        content = "\n".join(buffer) + "\n"
        previous = None
        if self.path.exists():
            previous = self.path.read_text(encoding="utf-8")
        diff = generate_diff(previous, content, path=self.path)
        if dry_run:
            return content, diff
        safe_write(self.path, content)
        self.logger.info("Configuration written to %s", self.path)
        return content, diff


def summarize_configuration(config: Configuration) -> List[Tuple[str, str]]:
    """Return a flat summary of configuration values for review displays."""

    summary = [
        ("Schema version", config.schema_version),
        ("Log level", config.general.log_level),
        ("Log file max (MB)", str(config.general.log_file_max_mb)),
        ("Log file backups", str(config.general.log_file_backup_count)),
        ("Working directory", config.paths.working_dir),
        ("State directory", config.paths.state_dir),
        ("Mail log", config.paths.mail_log),
        ("CSV filename", config.paths.csv_filename),
        ("Service user", config.permissions.service_user),
        ("Report recipient", config.report.recipient or "(disabled)"),
        ("Report subject prefix", config.report.subject_prefix),
        ("Report sender", config.report.sender or "(default)"),
        ("DNS cache enabled", "yes" if config.dns_cache.enabled else "no"),
        ("DNS cache size", str(config.dns_cache.size)),
        ("DNS cache TTL", str(config.dns_cache.ttl)),
        ("Country DB", config.geo.country_db_path or "(default)"),
        ("ASN DB", config.geo.asn_db_path or "(default)"),
        ("SQLite DB", config.database.path),
        ("Timer: log extraction", config.timers.log_extraction),
        ("Timer: report", config.timers.report),
        ("Timer: IP DB update", config.timers.ip_db_update),
        ("Timer: SQL export", config.timers.sql_export),
        ("Timer: SQL import", config.timers.sql_import),
    ]
    return summary


class AppConfig:
    """Compatibility wrapper exposing the legacy attribute interface."""

    def __init__(self, config_path: Path, logger: Optional[logging.Logger] = None):
        self._logger = logger or logging.getLogger(__name__)
        self.config_path = Path(config_path)
        merger = ConfigurationMerger(config_path=self.config_path, logger=self._logger)
        self._config = merger.load()
        self._materialize()

    def _materialize(self) -> None:
        cfg = self._config
        self.working_dir = Path(cfg.paths.working_dir)
        self.state_dir = Path(cfg.paths.state_dir)
        self.mail_log = Path(cfg.paths.mail_log)
        self.csv_filename = cfg.paths.csv_filename
        self.report_email = cfg.report.recipient or None
        self.report_subject_prefix = cfg.report.subject_prefix
        self.report_sender_override = cfg.report.sender or None
        self.country_db_path = (
            Path(cfg.geo.country_db_path) if cfg.geo.country_db_path else None
        )
        self.asn_db_path = Path(cfg.geo.asn_db_path) if cfg.geo.asn_db_path else None
        self.log_level = cfg.general.log_level
        self.log_file_max_bytes = cfg.general.log_file_max_mb * 1_048_576
        self.log_file_backup_count = cfg.general.log_file_backup_count
        self.log_file = Path(cfg.paths.working_dir) / "maillogsentinel.log"
        self.dns_cache_enabled = cfg.dns_cache.enabled
        self.dns_cache_size = cfg.dns_cache.size
        self.dns_cache_ttl_seconds = cfg.dns_cache.ttl
        self.sqlite_db_path = Path(cfg.database.path)
        self.sql_export_frequency = cfg.timers.sql_export
        self.sql_import_frequency = cfg.timers.sql_import

    @property
    def config_loaded_successfully(self) -> bool:
        return True
