#!/usr/bin/env python3
"""MailLogSentinel installation and configuration utility."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, Optional, Sequence

from lib.maillogsentinel import config as config_module
from lib.maillogsentinel.output import (
    OutputOptions,
    confirm,
    detect_color_support,
    divider,
    heading,
    info,
    list_block,
    prompt,
    success,
    warning,
)


LOG = logging.getLogger("maillogsentinel.setup")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("/etc/maillogsentinel.conf")
    )
    parser.add_argument(
        "--interactive", action="store_true", help="Run interactive setup"
    )
    parser.add_argument(
        "--non-interactive", action="store_true", help="Run without prompts"
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write files")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    parser.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        help="Override using section.option=value",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity",
    )
    return parser


def parse_overrides(pairs: Sequence[str]) -> Dict[str, str]:
    overrides: Dict[str, str] = {}
    for raw in pairs:
        if "=" not in raw:
            raise config_module.ConfigurationError(
                "Overrides must be formatted as section.option=value"
            )
        key, value = raw.split("=", 1)
        key = key.replace(".", "__")
        overrides[key] = value
    return overrides


def ensure_systemd_unit(name: str, *, options: OutputOptions) -> None:
    timer_path = Path("/etc/systemd/system") / name
    if timer_path.exists():
        info(f"Systemd unit {name} already exists", options=options)
        return
    info(f"Systemd unit {name} will be created on apply", options=options)


def verify_permissions(service_user: str, *, options: OutputOptions) -> None:
    try:
        import pwd  # Lazy import to avoid platform issues during tests

        pwd.getpwnam(service_user)
    except KeyError:
        warning(
            f"Service user '{service_user}' does not exist. Please create it before running the service.",
            options=options,
        )


def apply_configuration(
    cfg: config_module.Configuration,
    *,
    config_path: Path,
    dry_run: bool,
    options: OutputOptions,
) -> str:
    writer = config_module.ConfigurationWriter(config_path, logger=LOG)
    content, diff = writer.write(cfg, dry_run=dry_run)
    heading("Configuration diff", options=options, level=2)
    print(diff or "(no changes)", file=options.stream)
    return content


def review_configuration(
    cfg: config_module.Configuration, *, options: OutputOptions
) -> None:
    heading("Review configuration", options=options, level=2)
    divider(options=options)
    for key, value in config_module.summarize_configuration(cfg):
        print(f"{key:<30}: {value}", file=options.stream)
    divider(options=options)


def run_interactive_flow(
    cfg: config_module.Configuration,
    *,
    merger: config_module.ConfigurationMerger,
    options: OutputOptions,
) -> config_module.Configuration:
    info("Interactive setup", options=options)
    cfg.general.log_level = prompt(
        "Log level (DEBUG/INFO/WARNING/ERROR/CRITICAL)",
        default=cfg.general.log_level,
        options=options,
    ).upper()
    cfg.general.log_file_max_mb = int(
        prompt(
            "Max log file size (MB)",
            default=str(cfg.general.log_file_max_mb),
            options=options,
        )
    )
    cfg.general.log_file_backup_count = int(
        prompt(
            "Log file backup count",
            default=str(cfg.general.log_file_backup_count),
            options=options,
        )
    )

    cfg.paths.working_dir = prompt(
        "Working directory", default=cfg.paths.working_dir, options=options
    )
    cfg.paths.state_dir = prompt(
        "State directory", default=cfg.paths.state_dir, options=options
    )
    cfg.paths.mail_log = prompt(
        "Mail log path", default=cfg.paths.mail_log, options=options
    )
    cfg.paths.csv_filename = prompt(
        "CSV filename", default=cfg.paths.csv_filename, options=options
    )

    cfg.permissions.service_user = prompt(
        "Service user", default=cfg.permissions.service_user, options=options
    )

    cfg.report.recipient = prompt(
        "Report recipient email (leave blank to disable)",
        default=cfg.report.recipient,
        options=options,
    )
    cfg.report.subject_prefix = prompt(
        "Email subject prefix",
        default=cfg.report.subject_prefix,
        options=options,
    )
    cfg.report.sender = prompt(
        "Sender email override (leave blank for default)",
        default=cfg.report.sender,
        options=options,
    )

    cfg.dns_cache.enabled = confirm(
        "Enable DNS cache?",
        options=options,
        default=cfg.dns_cache.enabled,
    )
    cfg.dns_cache.size = int(
        prompt("DNS cache size", default=str(cfg.dns_cache.size), options=options)
    )
    cfg.dns_cache.ttl = int(
        prompt(
            "DNS cache TTL (seconds)", default=str(cfg.dns_cache.ttl), options=options
        )
    )

    cfg.geo.country_db_path = prompt(
        "Country DB path", default=cfg.geo.country_db_path, options=options
    )
    cfg.geo.asn_db_path = prompt(
        "ASN DB path", default=cfg.geo.asn_db_path, options=options
    )

    cfg.database.path = prompt(
        "SQLite database path", default=cfg.database.path, options=options
    )

    cfg.timers.log_extraction = prompt(
        "Log extraction frequency",
        default=cfg.timers.log_extraction,
        options=options,
    )
    cfg.timers.report = prompt(
        "Report frequency",
        default=cfg.timers.report,
        options=options,
    )
    cfg.timers.ip_db_update = prompt(
        "IP DB update frequency",
        default=cfg.timers.ip_db_update,
        options=options,
    )
    cfg.timers.sql_export = prompt(
        "SQL export frequency",
        default=cfg.timers.sql_export,
        options=options,
    )
    cfg.timers.sql_import = prompt(
        "SQL import frequency",
        default=cfg.timers.sql_import,
        options=options,
    )

    issues = cfg.validate()
    if issues:
        heading("Validation errors", options=options, level=2)
        list_block(issues, options=options)
        raise config_module.ConfigurationError("; ".join(issues))
    return cfg


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level))
    color_supported = detect_color_support() and not args.no_color
    options = OutputOptions(color=color_supported, stream=sys.stdout)

    overrides = parse_overrides(args.overrides)
    merger = config_module.ConfigurationMerger(
        config_path=args.config,
        overrides=overrides,
        logger=LOG,
    )

    try:
        cfg = merger.load()
    except config_module.ConfigurationError as error:
        warning(str(error), options=options)
        return 1

    if args.interactive:
        try:
            cfg = run_interactive_flow(cfg, merger=merger, options=options)
        except config_module.ConfigurationError as error:
            warning(str(error), options=options)
            return 1

    review_configuration(cfg, options=options)
    if args.dry_run:
        info("Dry-run mode: configuration will not be written.", options=options)
    else:
        if args.interactive and not confirm(
            "Apply configuration?", options=options, default=True
        ):
            warning("Configuration not applied.", options=options)
            return 0

    try:
        apply_configuration(
            cfg, config_path=args.config, dry_run=args.dry_run, options=options
        )
    except config_module.ConfigurationError as error:
        warning(str(error), options=options)
        return 1

    verify_permissions(cfg.permissions.service_user, options=options)
    ensure_systemd_unit("maillogsentinel.timer", options=options)
    ensure_systemd_unit("maillogsentinel-report.timer", options=options)

    success("Setup completed successfully.", options=options)
    return 0


if __name__ == "__main__":
    sys.exit(main())
