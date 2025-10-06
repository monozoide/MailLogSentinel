#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
maillogsentinel.py v5 (smtplib, full sender address) :

- extract server;date;ip;user;hostname from Postfix SASL logs
- incremental parse of /var/log/mail.log with rotation/truncation detection
- --reset / --purge management
- logs & state in workdir
- daily text-only report via python smtplib with MIME attachment
- From: <bash_user>@<server_fqdn>
"""

import sys

# import gzip  # F401: imported but unused
import shutil
import subprocess
import logging

# import logging.handlers  # F401: imported but unused
import argparse

# import re  # F401: imported but unused
import tempfile

import smtplib  # F401: imported but unused
import socket
import csv

# import getpass  # F401: imported but unused
# import functools  # F401: imported but unused
# import time  # F401: imported but unused
# from email.message import EmailMessage  # F401: imported but unused
# from datetime import datetime  # F401: imported but unused
from pathlib import Path
from typing import Optional
import ipinfo
from lib.maillogsentinel.progress import ProgressTracker  # Updated import
from lib.maillogsentinel.utils import (
    check_root,
    # list_all_logs, # This function is defined locally below
    is_gzip,
    LOG_LEVELS_MAP,
    STATE_FILENAME,
    LOG_FILENAME,
    setup_logging,
    setup_paths,
    read_state,
    write_state,
)
from lib.maillogsentinel.config import (
    AppConfig,
)
from lib.maillogsentinel.parser import extract_entries, extract_entries_with_reader
from lib.maillogsentinel.log_reader import detect_log_source, create_log_reader
from lib.maillogsentinel.dns_utils import initialize_dns_cache, reverse_lookup
from lib.maillogsentinel.report import send_report
from lib.maillogsentinel.sql_exporter import run_sql_export
from lib.maillogsentinel.sql_importer import run_sql_import  # New import

# --- Global IPInfoManager ---
IP_INFO_MANAGER: Optional[ipinfo.IPInfoManager] = None

# --- Constants ---
SCRIPT_NAME = "MailLogSentinel"
VERSION = "v1.0.4-B"
DEFAULT_CONFIG_PATH = Path("/etc/maillogsentinel.conf")  # Renamed for clarity
CSV_FILENAME = "maillogsentinel.csv"  # Keep as string
# SECTION_REPORT = "report" # No longer used


# --- Cron utilities have been removed ---


# --- Common utilities ---
# F811: redefinition of unused 'list_all_logs' from line 36
# The import from lib.maillogsentinel.utils was removed, so this is no longer a redefinition.
def list_all_logs(maillog: Path):  # Expects Path, returns list of Paths
    files = []
    if maillog.is_file():  # Check if the main log path itself is a file
        files.append(maillog)
    # For rotated logs:
    # Path.glob returns a generator, convert to list and sort
    if maillog.parent.exists():  # Ensure parent directory exists before globbing
        files.extend(sorted(list(maillog.parent.glob(maillog.name + ".*"))))
    # Filter to ensure all are files
    return [p for p in files if p.is_file()]


# --- Main ---


def main():
    epilog_text = (
        "For more detailed information, please consult the man page (man maillogsentinel) "
        "or the online README at https://github.com/monozoide/MailLogSentinel/blob/main/README.md"
    )
    parser = argparse.ArgumentParser(
        description=f"{SCRIPT_NAME} {VERSION} - Postfix SASL Log Analyzer",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=epilog_text,
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config file. If not provided, defaults will be used for setup or operation.",
    )
    parser.add_argument(
        "--report", action="store_true", help="Send daily report and exit"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset state and archive data. Manual cron setup needed.",
    )
    parser.add_argument(
        "--purge",
        action="store_true",
        help="Archive all data and logs. Manual cron setup needed.",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run the setup process. Interactively if --config is not given, otherwise automated using the specified config.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
        help="Show program's version number and exit.",
    )
    parser.add_argument(
        "--sql-export",
        action="store_true",
        help="Export new log entries from CSV to an SQL file.",
    )
    parser.add_argument(
        "--sql-import",
        action="store_true",
        help="Import .sql files from the SQL export directory into the database.",
    )
    # --output-file argument is removed
    args = parser.parse_args()

    progress_tracker = ProgressTracker()  # Instantiate ProgressTracker

    config_file_explicitly_passed = args.config is not None
    if config_file_explicitly_passed:
        config_file_path_for_ops = Path(args.config)
    else:
        config_file_path_for_ops = DEFAULT_CONFIG_PATH

    if args.setup:
        setup_script_path = Path(__file__).parent / "maillogsentinel_setup.py"
        if (
            not setup_script_path.is_file()
        ):  # Basic check, setup script should be executable too
            progress_tracker.print_message(  # Updated call
                f"ERROR: Setup script not found or not executable at {setup_script_path}",
                level="error",
            )
            sys.exit(1)

        setup_source_config_path_str: str
        setup_mode_flag_str: str

        if config_file_explicitly_passed:
            setup_source_config_path_str = str(config_file_path_for_ops)
            setup_mode_flag_str = "--automated"
            progress_tracker.print_message(  # Updated call
                f"Attempting automated setup using configuration file: {setup_source_config_path_str}",
                level="info",
            )
        else:
            # For interactive setup, DEFAULT_CONFIG_PATH is the *target* configuration file.
            setup_source_config_path_str = str(DEFAULT_CONFIG_PATH)
            setup_mode_flag_str = "--interactive"
            progress_tracker.print_message(
                "Starting interactive setup process...", level="info"
            )  # Updated call

        # Common message for setup script execution
        progress_tracker.print_message(  # Updated call
            "The setup script will handle Ctrl+C for its operations.", level="info"
        )

        process_args = [
            sys.executable,
            str(setup_script_path),
            setup_source_config_path_str,
            setup_mode_flag_str,
        ]
        process = subprocess.Popen(
            process_args
        )  # stdout/stderr go to parent's by default

        exit_code = None
        try:
            exit_code = process.wait()
        except KeyboardInterrupt:
            progress_tracker.print_message(  # Updated call
                "\nMain script received Ctrl+C. Waiting for setup script to complete its handling...",
                level="info",
            )
            try:
                exit_code = process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                progress_tracker.print_message(  # Updated call
                    "Setup script did not exit cleanly after interrupt. Terminating it.",
                    level="warning",
                )
                process.terminate()
                try:
                    exit_code = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    progress_tracker.print_message(  # Updated call
                        "Setup script did not terminate. Killing it.", level="error"
                    )
                    process.kill()
                    exit_code = process.wait()
            except KeyboardInterrupt:
                progress_tracker.print_message(  # Updated call
                    "\nSecond Ctrl+C detected in parent. Terminating setup script forcefully.",
                    level="warning",
                )
                process.terminate()
                exit_code = process.wait()

            if exit_code is None:
                exit_code = 130

        if exit_code == 0:
            progress_tracker.print_message(
                "Setup process completed successfully.", level="info"
            )  # Updated call
            if not config_file_explicitly_passed:
                progress_tracker.print_message(  # Updated call
                    f"Configuration file should now be at {DEFAULT_CONFIG_PATH}", "info"
                )
            progress_tracker.print_message(  # Updated call
                "You can now run the application without the --setup flag (if applicable).",
                "info",
            )
        elif (
            exit_code == 1 and config_file_explicitly_passed
        ):  # Automated setup might fail with 1
            progress_tracker.print_message(  # Updated call
                f"Automated setup process failed with exit code {exit_code}.", "error"
            )
        elif exit_code == 1:  # Interactive setup specific message for non-zero exit
            progress_tracker.print_message(  # Updated call
                "Setup process was interrupted or failed, but user chose not to proceed with cancellation within setup; script exited as requested.",
                level="info",
            )
        else:
            progress_tracker.print_message(  # Updated call
                f"Setup script finished with a non-standard exit code: {exit_code}.",
                level="warning",
            )

        sys.exit(exit_code)

    # If not --setup, proceed with normal operation.
    check_root()  # Ensure not running as root for normal operations

    if args.purge:
        progress_tracker.start_step("Initializing purge operation")  # Updated call
        # Use config_file_path_for_ops for AppConfig initialization
        app_config = AppConfig(config_file_path_for_ops, logger=None)
        app_config.exit_if_not_loaded(  # This method might need adjustment if it assumes config_path attribute directly
            "Purge operation cannot proceed without a valid configuration."
        )
        # Ensure setup_paths can work with the AppConfig instance as passed
        workdir, statedir, _, _, _ = setup_paths(app_config)
        logger_purge = setup_logging(app_config)
        app_config.logger = logger_purge
        progress_tracker.complete_step(
            "Initializing purge operation", True
        )  # Translated # Updated call

        progress_tracker.start_step(
            "Backing up data and logs"
        )  # Translated # Updated call
        try:
            backup_parent_dir = Path.home()
            backup_dir = Path(
                tempfile.mkdtemp(
                    prefix="maillogsentinel_backup_", dir=backup_parent_dir
                )
            )
            files_to_move = [
                statedir / STATE_FILENAME,
                workdir / app_config.csv_filename,
                workdir / LOG_FILENAME,
            ]
            for file_path_obj in files_to_move:
                if file_path_obj.is_file():
                    try:
                        shutil.move(
                            str(file_path_obj), str(backup_dir / file_path_obj.name)
                        )
                        # Log individual file moves for logger, not for console progress
                        logger_purge.info(
                            f"Moved {file_path_obj} → {backup_dir / file_path_obj.name}"
                        )
                    except (shutil.Error, OSError) as e:
                        # Log detailed error for this specific file
                        logger_purge.error(
                            f"Error moving {file_path_obj} to backup: {e}"
                        )
                        # Raise e to be caught by the outer try/except for step completion
                        raise
            progress_tracker.complete_step(
                "Backing up data and logs", True
            )  # Translated # Updated call
            progress_tracker.print_message(  # Updated call
                f"Old data has been backed up to {backup_dir}",  # Translated
                level="info",
            )
        except OSError as e:
            progress_tracker.complete_step(  # Updated call
                "Backing up data and logs", False, details=str(e)  # Translated
            )
            logger_purge.error(
                f"Error during backup process: {e}"
            )  # Log the error that caused failure
            progress_tracker.finalize(
                False, "Purge operation failed."
            )  # Translated # Updated call
            sys.exit(1)

        logger_purge.info("Purge completed. Old data backed up.")
        progress_tracker.finalize(  # Updated call
            True,
            "Purge completed. Cron jobs must be managed manually.",  # Translated
        )
        sys.exit(0)

    if args.reset:
        progress_tracker.start_step("Initializing reset operation")  # Updated call
        # Use config_file_path_for_ops for AppConfig initialization
        app_config = AppConfig(config_file_path_for_ops, logger=None)
        app_config.exit_if_not_loaded(
            "Reset operation cannot proceed without a valid configuration."
        )
        # Ensure setup_paths can work with the AppConfig instance as passed
        workdir, statedir, _, _, _ = setup_paths(app_config)
        logger_reset = setup_logging(app_config)
        app_config.logger = logger_reset
        progress_tracker.complete_step(
            "Initializing reset operation", True
        )  # Translated # Updated call

        progress_tracker.start_step(
            "Backing up data and logs for reset"
        )  # Translated # Updated call
        try:
            backup_parent_dir = Path.home()
            backup_dir = Path(
                tempfile.mkdtemp(
                    prefix="maillogsentinel_backup_", dir=backup_parent_dir
                )
            )
            files_to_move = [
                statedir / STATE_FILENAME,
                workdir / app_config.csv_filename,
                workdir / LOG_FILENAME,
            ]
            for file_path_obj in files_to_move:
                if file_path_obj.is_file():
                    try:
                        shutil.move(
                            str(file_path_obj), str(backup_dir / file_path_obj.name)
                        )
                        logger_reset.info(
                            f"Moved {file_path_obj} → {backup_dir / file_path_obj.name}"
                        )
                    except (shutil.Error, OSError) as e:
                        logger_reset.error(
                            f"Error moving {file_path_obj} to backup: {e}"
                        )
                        raise
            progress_tracker.complete_step(
                "Backing up data and logs for reset", True
            )  # Translated # Updated call
            progress_tracker.print_message(  # Updated call
                f"Old data has been backed up to {backup_dir}",  # Translated
                level="info",
            )
        except OSError as e:
            progress_tracker.complete_step(  # Updated call
                "Backing up data and logs for reset",  # Translated
                False,
                details=str(e),
            )
            logger_reset.error(f"Error during backup process for reset: {e}")
            progress_tracker.finalize(
                False, "Reset operation failed."
            )  # Translated # Updated call
            sys.exit(1)

        if (
            app_config.log_level not in LOG_LEVELS_MAP
        ):  # This log is for the file, print_message for console
            logger_reset.warning(
                f"Configured log_level '{app_config.log_level}' for reset path "
                f"is invalid. Defaulting to INFO."
            )
        logger_reset.info(f"Reset completed. Old data backed up to {backup_dir}.")
        progress_tracker.finalize(  # Updated call
            True,
            f"Reset completed. Old data backed up to {backup_dir}. Cron jobs must be managed manually.",  # Translated
        )
        sys.exit(0)

    # --- Normal Operation Flow & --report common initialization ---
    overall_success_flag = True
    # Use config_file_path_for_ops for AppConfig initialization
    app_config = AppConfig(config_file_path_for_ops, logger=None)

    # Handle config loading messages
    if not app_config.config_loaded_successfully:
        if config_file_explicitly_passed:
            # If a specific config file was passed and failed to load
            progress_tracker.print_message(  # Updated call
                f"CRITICAL: Specified configuration file {config_file_path_for_ops} could not be loaded. Exiting.",
                level="error",
            )
            sys.exit(1)
        else:
            # If the default config path was used and it failed to load (or doesn't exist)
            progress_tracker.print_message(  # Updated call
                f"INFO: Default configuration {DEFAULT_CONFIG_PATH} not found or failed to load. Using internal defaults. Consider running --setup.",
                level="info",
            )
            # Continue with internal defaults, AppConfig should handle this.

    # Now setup logger and attach to app_config
    logger = setup_logging(app_config)
    app_config.logger = logger

    progress_tracker.start_step("Loading configuration")  # Translated # Updated call
    # Assuming config is "loaded" by AppConfig instantiation.
    if app_config.config_loaded_successfully:
        progress_tracker.complete_step(  # Updated call
            "Loading configuration",
            True,
            details=f"File: {app_config.config_path}",  # app_config.config_path should reflect the actual path used
        )
    else:  # Default config not found, using internal defaults
        progress_tracker.complete_step(
            "Loading configuration", True, details="Defaults used"
        )  # Updated call
        # Message about default config not found is handled above.
        # AppConfig internally uses defaults, so this isn't a failure to load in itself.

    # The following block seems redundant now given the refined logic above for explicit vs. default config
    # if (
    #     not app_config.config_loaded_successfully
    # ):
    #     progress_tracker.print_message(
    #         f"Configuration file {app_config.config_path} was not loaded. Using default settings.",
    #         level="warning",
    #     )

    progress_tracker.start_step("Setting up logging")  # Translated # Updated call
    progress_tracker.complete_step(  # Updated call
        "Setting up logging",  # Translated
        True,
        details=f"Log level: {app_config.log_level}",  # Translated "Niveau de log"
    )

    progress_tracker.start_step("Initializing paths")  # Translated # Updated call
    try:
        workdir, statedir, maillog_path, country_db_path, asn_db_path = setup_paths(
            app_config
        )
        progress_tracker.complete_step(
            "Initializing paths", True
        )  # Translated # Updated call
    except (
        OSError
    ) as e:  # setup_paths primarily raises OSError for directory creation issues
        logger.error(f"Path initialization failed: {e}", exc_info=True)
        progress_tracker.complete_step(
            "Initializing paths", False, details=str(e)
        )  # Translated # Updated call
        progress_tracker.finalize(
            False, "Path initialization failed."
        )  # Translated # Updated call
        overall_success_flag = False
        sys.exit(1)

    if overall_success_flag:
        progress_tracker.start_step(
            "Initializing GeoIP/ASN databases"
        )  # Translated # Updated call
        progress_tracker.update_indeterminate_progress(
            "Loading/Updating..."
        )  # Translated # Updated call
        try:
            global IP_INFO_MANAGER
            IP_INFO_MANAGER = ipinfo.IPInfoManager(
                asn_db_path=str(app_config.asn_db_path),
                country_db_path=str(app_config.country_db_path),
                asn_db_url=app_config.asn_db_url,
                country_db_url=app_config.country_db_url,
                logger=logger,
            )
            # logger.info("Attempting initial update/load of IP geolocation and ASN databases...") # Logged by IPInfoManager
            IP_INFO_MANAGER.update_databases()
            progress_tracker.complete_step(
                "Initializing GeoIP/ASN databases", True
            )  # Translated # Updated call
        except (
            IOError,
            OSError,
            ipinfo.urllib.error.URLError,
            ipinfo.urllib.error.HTTPError,
        ) as e:  # More specific
            logger.error(
                f"Failed to initialize/update IPInfoManager: {e}", exc_info=True
            )
            progress_tracker.complete_step(  # Updated call
                step_name="Initializing GeoIP/ASN databases",
                success=False,
                details=str(e),  # Now with all keyword args
            )
            overall_success_flag = False
            # Not necessarily fatal, could continue without GeoIP depending on requirements
            progress_tracker.print_message(  # Updated call
                f"Error initializing GeoIP/ASN databases: {e}. Processing may continue with reduced functionality.",  # Translated
                level="warning",
            )

    if overall_success_flag:  # Or if GeoIP failure is not considered fatal
        progress_tracker.start_step(
            "Initializing DNS cache"
        )  # Translated # Updated call
        try:
            initialize_dns_cache(app_config=app_config, logger=logger)
            progress_tracker.complete_step(
                "Initializing DNS cache", True
            )  # Translated # Updated call
        except (
            AttributeError
        ) as e:  # Catch if app_config is missing expected attributes
            logger.error(
                f"Failed to initialize DNS cache due to config error: {e}",
                exc_info=True,
            )
            progress_tracker.complete_step(
                "Initializing DNS cache", False, details=str(e)
            )  # Translated # Updated call
            overall_success_flag = False  # DNS cache might be critical
            progress_tracker.print_message(  # Updated call
                f"Error initializing DNS cache: {e}. Some host name resolutions may fail or be slow.",  # Translated
                level="warning",
            )

    if app_config.log_level not in LOG_LEVELS_MAP:  # Logged by logger
        progress_tracker.print_message(  # Updated call
            f"Configured log level '{app_config.log_level}' is invalid. Effective: {logging.getLevelName(logger.getEffectiveLevel())}",  # Translated
            level="warning",
        )

    logger.info(f"=== Start of {SCRIPT_NAME} {VERSION} ===")  # Log file marker

    if args.report:
        if not overall_success_flag:
            progress_tracker.finalize(  # Updated call
                False,
                "Cannot generate report due to previous errors.",  # Translated
            )
            sys.exit(1)

        progress_tracker.start_step(
            "Generating and sending report"
        )  # Translated # Updated call
        progress_tracker.update_indeterminate_progress(
            "In progress..."
        )  # Translated # Updated call
        try:
            send_report(
                app_config=app_config,
                logger=logger,
                script_name=SCRIPT_NAME,
                script_version=VERSION,
            )
            progress_tracker.complete_step(
                "Generating and sending report", True
            )  # Translated # Updated call
            logger.info(f"=== End of {SCRIPT_NAME} execution (report mode) ===")
            progress_tracker.finalize(True, "Report sent.")  # Translated # Updated call
        except (
            IOError,
            OSError,
            smtplib.SMTPException,
            socket.gaierror,
        ) as e:  # Specific to send_report
            logger.error(f"Failed to send report: {e}", exc_info=True)
            progress_tracker.complete_step(  # Updated call
                "Generating and sending report", False, details=str(e)
            )  # Translated
            progress_tracker.finalize(
                False, f"Failed to send report: {e}"
            )  # Translated # Updated call
        sys.exit(0)  # Report mode always exits here

    # --- Normal Log Processing Mode (if not --report) ---
    if not overall_success_flag:
        progress_tracker.finalize(  # Updated call
            False, "Initialization steps failed, aborting log processing."  # Translated
        )
        sys.exit(1)

    progress_tracker.start_step(
        "Reading previous state (offset)"
    )  # Translated # Updated call
    last_off = -1  # Initialize to a value indicating failure or not read
    try:
        last_off = read_state(statedir, logger)
        progress_tracker.complete_step(  # Updated call
            "Reading previous state (offset)",
            True,
            details=f"Offset: {last_off}",  # Translated
        )
    except (IOError, ValueError) as e:  # read_state specific exceptions
        logger.error(f"Failed to read state: {e}", exc_info=True)
        progress_tracker.complete_step(  # Updated call
            "Reading previous state (offset)", False, details=str(e)
        )  # Translated
        progress_tracker.finalize(
            False, "Could not read previous state."
        )  # Translated # Updated call
        sys.exit(1)

    # --- Determine log source and create appropriate reader ---
    progress_tracker.start_step(
        "Determining log source"
    )  # Translated # Updated call
    
    # Get log source preference from config
    configured_source_type = app_config.log_source_type
    journald_unit = app_config.journald_unit
    
    if configured_source_type == "auto":
        # Autodetect the best log source
        detected_source = detect_log_source(logger, journald_unit)
        logger.info(f"Auto-detected log source: {detected_source}")
        source_type = detected_source
    elif configured_source_type in ["syslog", "journald"]:
        # Use explicitly configured source
        source_type = configured_source_type
        logger.info(f"Using configured log source: {source_type}")
    else:
        # Invalid configuration, fall back to syslog
        logger.warning(f"Invalid log source configuration '{configured_source_type}', falling back to syslog")
        source_type = "syslog"
    
    progress_tracker.complete_step(
        "Determining log source", True, details=f"Using: {source_type}"
    )  # Translated # Updated call

    progress_tracker.start_step(
        "Identifying log files to process"
    )  # Translated # Updated call
    
    if source_type == "syslog":
        # Traditional syslog file processing
        to_proc = []
        try:
            to_proc = list_all_logs(maillog_path) if last_off == 0 else [maillog_path]
            progress_tracker.complete_step(  # Updated call
                "Identifying log files to process",  # Translated
                True,
                details=f"{len(to_proc)} file(s)",  # Translated
            )
            logger.debug(f"Files to process: {to_proc}, starting from offset: {last_off}")
        except OSError as e:  # Path.glob can raise OSError
            logger.error(f"Failed to identify log files: {e}", exc_info=True)
            progress_tracker.complete_step(  # Updated call
                "Identifying log files to process", False, details=str(e)  # Translated
            )
            progress_tracker.finalize(
                False, "Could not identify log files."
            )  # Translated # Updated call
            sys.exit(1)

        # Create syslog reader
        try:
            log_reader = create_log_reader(
                "syslog",
                filepaths=to_proc,
                maillog_path=maillog_path,
                is_gzip_func=is_gzip,
                logger=logger
            )
        except ValueError as e:
            logger.error(f"Failed to create syslog reader: {e}")
            progress_tracker.complete_step(
                "Identifying log files to process", False, details=str(e)
            )
            progress_tracker.finalize(False, "Could not create log reader.")
            sys.exit(1)
    else:
        # Journald processing
        try:
            # For journald, we don't need file identification
            progress_tracker.complete_step(
                "Identifying log files to process",
                True,
                details=f"Using journald unit: {journald_unit}"
            )
            
            # Create journald reader
            log_reader = create_log_reader(
                "journald",
                logger=logger,
                unit=journald_unit
            )
        except ValueError as e:
            logger.error(f"Failed to create journald reader: {e}")
            progress_tracker.complete_step(
                "Identifying log files to process", False, details=str(e)
            )
            progress_tracker.finalize(False, "Could not create log reader.")
            sys.exit(1)

    csv_file_to_extract = workdir / CSV_FILENAME

    progress_tracker.start_step(
        "Extracting entries from log files"
    )  # Translated # Updated call
    # update_indeterminate_progress("Traitement en cours...") # REMOVED
    new_off = -1
    try:
        # Use the new LogReader abstraction
        new_off = extract_entries_with_reader(
            log_reader=log_reader,
            csvpath_param=str(csv_file_to_extract),
            logger=logger,
            ip_info_mgr=IP_INFO_MANAGER,
            reverse_lookup_func=reverse_lookup,
            offset=last_off,
            progress_callback=progress_tracker.update_progress,  # ADDED # Updated call
        )
        # Handle different outcomes of extract_entries_with_reader regarding new_off
        # The success/failure of complete_step for "Extracting log entries"
        # should still be determined by the value of new_off or exceptions as before.
        # The progress_callback within extract_entries only handles the bar itself.
        if (
            new_off == -1 and last_off == 0
        ):  # Adjusted condition based on previous diff
            progress_tracker.complete_step(  # Updated call
                "Extracting entries from log files",  # Translated
                True,
                details="No new logs to process or logs are empty.",  # Translated
            )
        elif new_off >= last_off:  # Simplified this condition block
            progress_tracker.complete_step(  # Updated call
                "Extracting entries from log files",  # Translated
                True,
                details=f"New offset: {new_off}",  # Translated
            )
        else:  # new_off < last_off or other unexpected value from new_off logic in parser
            progress_tracker.complete_step(  # Updated call
                "Extracting entries from log files",  # Translated
                False,
                details=f"Offset issue after extraction (before: {last_off}, after: {new_off})",  # Translated
            )
            overall_success_flag = False

    except (IOError, OSError, csv.Error) as e:  # Specific to extract_entries
        logger.error(f"Error during log extraction: {e}", exc_info=True)
        # The complete_step call for failure is already here, which is correct.
        # It will clear the progress bar line set by start_step.
        progress_tracker.complete_step(  # Updated call
            "Extracting entries from log files", False, details=str(e)
        )  # Translated
        overall_success_flag = False

    if overall_success_flag:  # Only write state if extraction was considered successful
        progress_tracker.start_step(
            "Saving new state (offset)"
        )  # Translated # Updated call
        try:
            # Only write state if new_off is valid (not -1 if it indicates an error)
            # or if it's a scenario where -1 is acceptable (e.g. no logs processed, offset res 0 or previous value)
            if new_off != -1 or (
                new_off == -1 and last_off == 0 and not to_proc
            ):  # allow writing -1 if it was initial state and no files
                write_state(
                    statedir, new_off if new_off != -1 else last_off, logger
                )  # write last_off if new_off is -1 from no new entries
                progress_tracker.complete_step(  # Updated call
                    "Saving new state (offset)",  # Translated
                    True,
                    details=f"New offset: {new_off if new_off !=-1 else last_off}",  # Translated
                )
            else:  # new_off is -1 and it's an error state from extraction
                progress_tracker.complete_step(  # Updated call
                    "Saving new state (offset)",  # Translated
                    False,
                    details=f"Invalid offset ({new_off}), state not saved.",  # Translated
                )
                overall_success_flag = (
                    False  # Mark as failure as state wasn't saved correctly
                )
        except (IOError, OSError) as e:  # write_state specific
            logger.error(f"Failed to write state: {e}", exc_info=True)
            progress_tracker.complete_step(  # Updated call
                "Saving new state (offset)", False, details=str(e)
            )  # Translated
            overall_success_flag = False

    logger.info(
        f"Extraction completed, new offset: {new_off if new_off !=-1 else last_off}"
    )  # Log what was (or would be) saved
    logger.info(f"=== End of {SCRIPT_NAME} execution ===")

    if overall_success_flag:
        progress_tracker.finalize(
            True, f"{SCRIPT_NAME} has finished execution."
        )  # Translated # Updated call
    else:
        progress_tracker.finalize(
            False, f"{SCRIPT_NAME} encountered errors."
        )  # Translated # Updated call

    # --- SQL Export Mode ---
    if args.sql_export:
        if (
            not overall_success_flag
        ):  # Checks if initializations like config, logging, paths were okay
            progress_tracker.finalize(
                False,
                "Cannot proceed with SQL export due to previous initialization errors.",
            )
            sys.exit(1)

        progress_tracker.print_message("Starting SQL export process...", level="info")

        # The AppConfig (app_config) and logger should already be initialized from the common block.
        # Paths (workdir, statedir etc.) should also be initialized.
        # IP_INFO_MANAGER and DNS cache also initialized if overall_success_flag is true.

        # Directly call run_sql_export
        # Ensure sql_exporter.py is adapted to use AppConfig object correctly.
        export_successful = run_sql_export(
            config=app_config, output_log_level=app_config.log_level
        )

        if export_successful:
            progress_tracker.finalize(True, "SQL export completed successfully.")
            logger.info(f"=== End of {SCRIPT_NAME} execution (SQL export mode) ===")
        else:
            progress_tracker.finalize(False, "SQL export failed.")
            logger.error(f"=== {SCRIPT_NAME} execution failed (SQL export mode) ===")
        sys.exit(0 if export_successful else 1)

    # --- SQL Import Mode ---
    if args.sql_import:
        if (
            not overall_success_flag
        ):  # Checks if initializations like config, logging, paths were okay
            progress_tracker.finalize(
                False,
                "Cannot proceed with SQL import due to previous initialization errors.",
            )
            sys.exit(1)

        progress_tracker.print_message("Starting SQL import process...", level="info")

        # AppConfig, logger, paths should be initialized from the common block.

        import_successful = run_sql_import(
            config=app_config, output_log_level=app_config.log_level
        )

        if import_successful:
            progress_tracker.finalize(True, "SQL import completed successfully.")
            logger.info(f"=== End of {SCRIPT_NAME} execution (SQL import mode) ===")
        else:
            progress_tracker.finalize(False, "SQL import failed.")
            logger.error(f"=== {SCRIPT_NAME} execution failed (SQL import mode) ===")
        sys.exit(0 if import_successful else 1)


if __name__ == "__main__":
    main()
