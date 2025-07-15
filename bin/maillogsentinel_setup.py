#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Setup script for MailLogSentinel.

This script guides the user through interactive setup or performs an
automated setup based on a provided configuration file. It handles:
- Collecting configuration parameters (paths, email, schedules, etc.).
- Creating necessary directories.
- Generating and installing Systemd service and timer units.
- Setting file ownership and user group memberships.

The script can be invoked with --interactive or --automated flags.
It is typically called by the main maillogsentinel.py application when
the --setup flag is used.
"""
import signal
import os
import sys
import shutil
import subprocess
import configparser
import tempfile

# import curses    # Removed
# import curses.textpad # Removed
# import socket # No longer used directly
# import csv # No longer used directly
# import smtplib # No longer used by setup
import getpass
import functools  # For partial
import argparse  # For command-line argument parsing

# import time # No longer used directly, datetime.now().strftime is used
# from email.message import EmailMessage  # F401: imported but unused
from datetime import datetime
from pathlib import Path

# typing.Optional and typing.Any are not used
# from typing import (
#     Optional,
#     Any,
# )
import copy  # For deepcopy of default config
import re  # For systemd unit generation input validation
import pwd  # For user validation

# Constants specific to the setup script
# SCRIPT_NAME_SETUP = "MailLogSentinelSetup" # F841: local variable 'SCRIPT_NAME_SETUP' is assigned to but never used
# VERSION_SETUP = "v1.0" # F841: local variable 'VERSION_SETUP' is assigned to but never used
DEFAULT_CONFIG_PATH_SETUP = Path("/etc/maillogsentinel.conf")
# SETUP_LOG_FILENAME = "maillogsentinel_setup.log" # F841: local variable 'SETUP_LOG_FILENAME' is assigned to but never used
LOG_FILENAME = "maillogsentinel.log"
CSV_FILENAME = "maillogsentinel.csv"
STATE_FILENAME = "state.offset"
# Constants for default paths used within interactive_setup
DEFAULT_WORKING_DIR = Path("/var/log/maillogsentinel")
DEFAULT_STATE_DIR = Path("/var/lib/maillogsentinel")
DEFAULT_MAIL_LOG = Path("/var/log/mail.log")
DEFAULT_COUNTRY_DB_PATH = Path("/var/lib/maillogsentinel/country_aside.csv")
DEFAULT_ASN_DB_PATH = Path("/var/lib/maillogsentinel/asn.csv")

# Global variables for signal handling and cleanup
# sigint_received = False # No longer used with custom exception
backed_up_items = []  # Stores (backup_path, original_path) tuples
created_final_paths = (
    []
)  # Stores paths of files/dirs created by setup in final locations


# Custom exception for SIGINT
class SigintEncountered(BaseException):
    pass


# Signal handler for SIGINT
def handle_sigint(signum, frame):
    # This handler will now directly raise an exception
    # to interrupt the main flow.
    raise SigintEncountered()


def _setup_print_and_log(
    message: str = "",
    file_handle=None,
    is_prompt: bool = False,
    end: str = "\n",
    console_out: bool = True,
):
    """
    Prints a message to the console and/or writes it to the provided file_handle.

    Args:
        message: The message string.
        file_handle: Open file handle for logging.
        is_prompt: If True, prints to console with end='' (for input prompts).
                   If False, uses 'end' parameter for console.
        end: String appended after the message in console (if not is_prompt).
        console_out: If False, message is only written to log file, not console.
    """
    # Print to console if console_out is True
    if console_out:
        if is_prompt:
            print(message, end="", flush=True)
        else:
            print(message, end=end, flush=True)

    # Write to log file
    if file_handle and not file_handle.closed:
        try:
            file_handle.write(message + "\n")  # Always add newline for log file entries
            file_handle.flush()
        except IOError as e:
            # If logging fails, print an error to actual stderr.
            original_stderr_print_for_logging_error = functools.partial(
                print, file=sys.stderr, flush=True
            )
            original_stderr_print_for_logging_error(
                f"ERROR: Could not write to setup log file: {e}"
            )


def _change_ownership(path_to_change, user_name, setup_log_fh):
    """Attempts to change the ownership of the given path to the specified user."""
    _setup_print_and_log(
        f"Attempting to change ownership of {path_to_change} to user {user_name}...",
        setup_log_fh,
    )
    try:
        shutil.chown(str(path_to_change), user=user_name, group=None)
        _setup_print_and_log(
            f"Successfully changed ownership of {path_to_change} to {user_name}.",
            setup_log_fh,
        )
        return True
    except Exception as e:
        _setup_print_and_log(
            f"ERROR: Failed to change ownership of {path_to_change} to {user_name}: {e}",
            setup_log_fh,
        )
        return False


# Removed display_main_menu(stdscr) as it was curses-dependent

# The _get_curses_input function is now removed as it's obsolete.
# The _update_progress_display function was already simplified.


def validate_calendar_expression(
    calendar_str: str, setup_log_fh, default_fallback_expr: str
) -> str:
    """
    Validates a Systemd OnCalendar string using 'systemd-analyze calendar'.

    Args:
        calendar_str: The OnCalendar string to validate.
        setup_log_fh: File handle for logging.
        default_fallback_expr: The default expression to return if validation fails.

    Returns:
        The original calendar_str if valid, otherwise default_fallback_expr.
    """
    if not calendar_str:
        _setup_print_and_log(
            f"WARNING: Calendar string is empty. Falling back to default: {default_fallback_expr}",
            setup_log_fh,
        )
        return default_fallback_expr

    systemd_analyze_cmd = shutil.which("systemd-analyze")
    if not systemd_analyze_cmd:
        _setup_print_and_log(
            "WARNING: 'systemd-analyze' command not found. Cannot validate OnCalendar expressions. "
            f"Using provided value '{calendar_str}' without validation, assuming it is correct or relying on Systemd's own error handling later."
            " This is not ideal. Falling back to default to be safe.",
            setup_log_fh,
        )
        # If validation tool is missing, fall back to default to be safe.
        return default_fallback_expr

    try:
        # We add --iterations=1 to make it faster and avoid it hanging or producing too much output.
        process = subprocess.run(
            [systemd_analyze_cmd, "calendar", "--iterations=1", calendar_str],
            capture_output=True,
            text=True,
            check=False,  # Do not raise exception on non-zero exit
        )
        if process.returncode == 0:
            _setup_print_and_log(
                f"Calendar expression '{calendar_str}' validated successfully.",
                setup_log_fh,
                console_out=False,
            )  # Log success only to file
            return calendar_str
        else:
            _setup_print_and_log(
                f"WARNING: Invalid Systemd OnCalendar expression: '{calendar_str}'. "
                f"Error: {process.stderr.strip()}. Falling back to default: {default_fallback_expr}",
                setup_log_fh,
            )
            return default_fallback_expr
    except FileNotFoundError: # Should be caught by shutil.which already, but as a safeguard.
        _setup_print_and_log(
            "WARNING: 'systemd-analyze' command not found during execution attempt. Cannot validate OnCalendar expressions. "
            f"Falling back to default: {default_fallback_expr}", # Also fallback here
            setup_log_fh,
        )
        return default_fallback_expr
    except Exception as e:
        _setup_print_and_log(
            f"WARNING: An unexpected error occurred while validating calendar expression '{calendar_str}': {e}. "
            f"Falling back to default: {default_fallback_expr}",
            setup_log_fh,
        )
        return default_fallback_expr


# Helper function for progress display
def _update_progress_display(message: str, setup_log_fh):
    """Prints a progress message to console and log."""
    _setup_print_and_log(f"PROGRESS: {message}", setup_log_fh)


def _get_cli_input(
    prompt_text: str,
    default_value: str,
    setup_log_fh,
    info_text: str = "",
    is_path: bool = False,
    is_email: bool = False,
    allowed_values: list = None,
    is_bool: bool = False,
    is_int: bool = False,
    int_non_negative: bool = False,
):
    """
    Handles user input from the command line for interactive setup.

    Displays prompts, default values, and additional info. Performs basic
    validation based on the type of input expected (path, email, boolean,
    integer, or choice from a list).

    Args:
        prompt_text: The main question to ask the user.
        default_value: The default value if the user enters nothing.
        setup_log_fh: File handle for logging.
        info_text: Additional context or help for the prompt.
        is_path: If True, checks that the input is not empty.
        is_email: If True, checks for non-empty and presence of '@'.
        allowed_values: A list of allowed string inputs (case-insensitive).
        is_bool: If True, expects a y/n answer, returns "True" or "False".
        is_int: If True, validates that the input is an integer.
        int_non_negative: If True (and is_int is True), ensures integer is >= 0.

    Returns:
        The validated user input as a string.

    Raises:
        SigintEncountered: If Ctrl+C is pressed during input.
    """
    full_prompt = f"{prompt_text} "
    if info_text:
        full_prompt += f"({info_text}) "
    if allowed_values:
        full_prompt += f"[Allowed: {', '.join(allowed_values)}] "
    if is_bool:
        full_prompt += "[y/n] "
    full_prompt += f"(default: {default_value}): "

    while True:
        try:
            _setup_print_and_log(
                full_prompt, setup_log_fh, is_prompt=True, console_out=True
            )  # Prompt always to console
            user_input_str = input().strip()
            # Log raw input, but not to console
            _setup_print_and_log(
                f"User input for '{prompt_text}': '{user_input_str}' (raw)",
                setup_log_fh,
                console_out=False,
            )

            chosen_value = user_input_str if user_input_str else default_value
            # Log effective value, but not to console
            _setup_print_and_log(
                f"Effective value for '{prompt_text}': '{chosen_value}'",
                setup_log_fh,
                console_out=False,
            )

            if is_path and not chosen_value:
                _setup_print_and_log(
                    "Error: Path cannot be empty. Please try again.",
                    setup_log_fh,
                    console_out=True,
                )  # Errors to console
                continue
            if (
                is_email
            ):  # Basic check for @, more robust validation can be added if needed
                if not chosen_value:
                    _setup_print_and_log(
                        "Error: Email cannot be empty. Please try again.",
                        setup_log_fh,
                        console_out=True,
                    )  # Errors to console
                    continue
                if "@" not in chosen_value:
                    _setup_print_and_log(
                        "Error: Invalid email format. Please try again.",
                        setup_log_fh,
                        console_out=True,
                    )  # Errors to console
                    continue
            if allowed_values and chosen_value.upper() not in [
                val.upper() for val in allowed_values
            ]:
                _setup_print_and_log(
                    f"Error: Invalid input. Must be one of {', '.join(allowed_values)}. Please try again.",
                    setup_log_fh,
                )
                continue
            if is_bool:
                if chosen_value.lower() in ["y", "yes", "true", "1"]:
                    return "True"
                elif chosen_value.lower() in ["n", "no", "false", "0"]:
                    return "False"
                else:
                    _setup_print_and_log(
                        "Error: Please answer 'y' or 'n'. Please try again.",
                        setup_log_fh,
                    )
                    continue
            if is_int:
                try:
                    int_val = int(chosen_value)
                    if int_non_negative and int_val < 0:
                        _setup_print_and_log(
                            "Error: Value must be a non-negative integer. Please try again.",
                            setup_log_fh,
                        )
                        continue
                    return str(int_val)  # Return as string to match configparser needs
                except ValueError:
                    _setup_print_and_log(
                        "Error: Value must be an integer. Please try again.",
                        setup_log_fh,
                    )
                    continue

            return chosen_value
        except KeyboardInterrupt:
            _setup_print_and_log("\nUser interrupted input.", setup_log_fh)
            raise SigintEncountered("User interrupted input.")


def interactive_cli_setup(target_config_path, setup_log_fh):
    global backed_up_items, created_final_paths
    backed_up_items = []
    created_final_paths = []

    _setup_print_and_log("--- MailLogSentinel Interactive Setup ---", setup_log_fh)
    _setup_print_and_log(
        "This script will guide you through the configuration process.", setup_log_fh
    )
    _setup_print_and_log("Press Ctrl+C at any time to abort.", setup_log_fh)

    default_config_values = {
        "paths": {
            "working_dir": str(DEFAULT_WORKING_DIR),
            "state_dir": str(DEFAULT_STATE_DIR),
            "mail_log": str(DEFAULT_MAIL_LOG),
            "csv_filename": CSV_FILENAME,
        },
        "report": {
            "email": "security-team@example.org",
            "subject_prefix": "[MailLogSentinel]",
            "sender_override": f"{getpass.getuser()}@localhost",
        },
        "geolocation": {
            "country_db_path": str(DEFAULT_COUNTRY_DB_PATH),
            "country_db_url": "https://raw.githubusercontent.com/sapics/ip-location-db/main/asn-country/asn-country-ipv4-num.csv",
        },
        "ASN_ASO": {
            "asn_db_path": str(DEFAULT_ASN_DB_PATH),
            "asn_db_url": "https://raw.githubusercontent.com/sapics/ip-location-db/refs/heads/main/asn/asn-ipv4-num.csv",
        },
        "general": {
            "log_level": "INFO",
            "log_file_max_bytes": "1000000",
            "log_file_backup_count": "5",
        },
        "dns_cache": {"enabled": "True", "size": "128", "ttl_seconds": "3600"},
        "sqlite_database": {
            "db_type": "sqlite3",  # Fixed for now
            "db_path": "/var/lib/maillogsentinel/maillogsentinel.sqlite",
            "user": "",  # Not used for SQLite
            "password_hash": "",  # Not used for SQLite
            "salt": "",  # Not used for SQLite
        },
        "sql_export_systemd": {
            "frequency": "*:0/4",
        },
        "sql_import_systemd": {
            "frequency": "*:0/5",
        },
    }
    collected_config = copy.deepcopy(default_config_values)
    sections_to_configure = [
        "paths",
        "report",
        "geolocation",
        "ASN_ASO",
        "general",
        "dns_cache",
        "sqlite_database",
        "sql_export_systemd",
        "sql_import_systemd",
    ]
    allowed_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    try:
        for section_name in sections_to_configure:
            _setup_print_and_log(
                f"\n--- Configuring {section_name.capitalize()} Settings ---",
                setup_log_fh,
            )
            if section_name in default_config_values:
                for key, default_value in default_config_values[section_name].items():
                    prompt_text = f"Enter {key.replace('_', ' ')} for '{section_name}'"
                    (
                        info_text,
                        is_a_path,
                        is_an_email,
                        allowed,
                        is_a_bool,
                        is_an_int,
                        is_nn_int,
                    ) = ("", False, False, None, False, False, False)

                    if section_name == "paths":
                        info_text = "Ensure path is writable by the run_as_user."
                        if key == "csv_filename":
                            info_text = f"Relative to working dir ({collected_config['paths']['working_dir']})."
                        is_a_path = True  # For emptiness check, actual path validation is harder here
                    elif section_name == "report":
                        is_an_email = key == "email"
                        if key == "sender_override":
                            info_text = (
                                "Must be an existing email on this server if used."
                            )
                    elif section_name in ["geolocation", "ASN_ASO"]:
                        if key.endswith("_url"):
                            # URLs are not configurable, skip prompt and use default.
                            collected_config[section_name][key] = str(default_value)
                            _setup_print_and_log(
                                f"  Set [{section_name}] {key} = {str(default_value)} (default, not configurable)",
                                setup_log_fh,
                                console_out=False,
                            )
                            continue  # Skip to next key
                        if key.endswith("_path"):
                            is_a_path = True
                            info_text = "Path for local DB copy. Recommended: default suggestions"  # Updated info text
                    elif section_name == "general":
                        if key == "log_level":
                            allowed = allowed_log_levels
                        else:
                            info_text = "Non-negative integer."
                            is_an_int = True
                            is_nn_int = True
                    elif section_name == "dns_cache":
                        if key == "enabled":
                            is_a_bool = True
                        else:
                            info_text = "Non-negative integer."
                            is_an_int = True
                            is_nn_int = True
                    elif section_name == "sqlite_database":
                        if key == "db_type":
                            # Fixed for now, so skip prompt and use default.
                            collected_config[section_name][key] = str(default_value)
                            _setup_print_and_log(
                                f"  Set [{section_name}] {key} = {str(default_value)} (fixed to sqlite3 for now)",
                                setup_log_fh,
                                console_out=False,
                            )
                            continue  # Skip to next key
                        elif key == "db_path":
                            is_a_path = True
                            info_text = "Path to the SQLite database file."
                        elif key in ["user", "password_hash", "salt"]:
                            # Not used for SQLite, skip prompt and use default (empty).
                            collected_config[section_name][key] = str(default_value)
                            _setup_print_and_log(
                                f"  Set [{section_name}] {key} = '{str(default_value)}' (not used for SQLite)",
                                setup_log_fh,
                                console_out=False,
                            )
                            continue  # Skip to next key
                    elif section_name == "sql_export_systemd":
                        if key == "frequency":
                            info_text = "Systemd OnCalendar format only (e.g., *:0/4, hourly, 08:30)."
                    elif section_name == "sql_import_systemd":
                        if key == "frequency":
                            info_text = "Systemd OnCalendar format only (e.g., *:0/5, 02:00)."

                    # Only call _get_cli_input if not skipped above
                    user_input_str = _get_cli_input(
                        prompt_text,
                        str(default_value),
                        setup_log_fh,
                        info_text,
                        is_path=is_a_path,
                        is_email=is_an_email,
                        allowed_values=allowed,
                        is_bool=is_a_bool,
                        is_int=is_an_int,
                        int_non_negative=is_nn_int,
                    )

                    processed_value = user_input_str
                    if section_name == "general" and key == "log_level":
                        processed_value = user_input_str.upper()
                    elif section_name == "sql_export_systemd" and key == "frequency":
                        processed_value = validate_calendar_expression(
                            user_input_str, setup_log_fh, "*:0/4" # Default fallback for export
                        )
                    elif section_name == "sql_import_systemd" and key == "frequency":
                        processed_value = validate_calendar_expression(
                            user_input_str, setup_log_fh, "*:0/5" # Default fallback for import
                        )

                    collected_config[section_name][key] = str(processed_value)
                    _setup_print_and_log(
                        f"  Set [{section_name}] {key} = {str(processed_value)}",
                        setup_log_fh,
                        console_out=False,
                    )  # Log only

        _setup_print_and_log(
            "\n--- Systemd Timer Configuration (Optional) ---",
            setup_log_fh,
            console_out=True,
        )
        extraction_schedule_str = _get_cli_input(
            "Log extraction frequency (e.g., 'hourly', '0 */6 * * *')",
            "hourly",
            setup_log_fh,
            info_text="Systemd OnCalendar format or keywords like hourly, daily.",
        )
        extraction_schedule_str = validate_calendar_expression(
            extraction_schedule_str, setup_log_fh, "hourly"
        )

        while True:
            raw_report_time_str = _get_cli_input(
                "Daily report OnCalendar value (e.g., '08:50', 'daily', '*-*-* HH:MM:SS')",
                "daily", # Default input to _get_cli_input
                setup_log_fh,
                info_text="Systemd OnCalendar format.",
            )
            # Validate the raw input first
            validated_report_time_str = validate_calendar_expression(
                raw_report_time_str, setup_log_fh, "daily" # Fallback for validation
            )

            if re.fullmatch(r"\d{2}:\d{2}", validated_report_time_str):
                h, m = map(int, validated_report_time_str.split(":"))
                report_on_calendar_formatted = f"*-*-* {h:02d}:{m:02d}:00"
                break
            elif validated_report_time_str.lower() == "daily":
                report_on_calendar_formatted = "*-*-* 23:59:59" # Systemd 'daily' often means midnight
                break
            else:
                # If already validated and not HH:MM or 'daily', use as is
                # (assuming it's a more complex valid OnCalendar string)
                report_on_calendar_formatted = validated_report_time_str
                break

        ip_update_schedule_str = _get_cli_input(
            "IP DB update frequency (e.g., 'daily', '0 2 * * 1')",
            "daily",
            setup_log_fh,
            info_text="Systemd OnCalendar format.",
        )
        ip_update_schedule_str = validate_calendar_expression(
            ip_update_schedule_str, setup_log_fh, "daily"
        )

        # Get SQL export and import schedules
        sql_export_schedule_str = _get_cli_input(
            "SQL export frequency",
            collected_config["sql_export_systemd"]["frequency"],  # Default from config
            setup_log_fh,
            info_text="Systemd OnCalendar format only (e.g., *:0/4, hourly, 08:30).",
        )
        sql_export_schedule_str = validate_calendar_expression(
            sql_export_schedule_str, setup_log_fh, "*:0/4"
        )
        collected_config["sql_export_systemd"][
            "frequency"
        ] = sql_export_schedule_str  # Update collected config

        sql_import_schedule_str = _get_cli_input(
            "SQL import frequency",
            collected_config["sql_import_systemd"]["frequency"],  # Default from config
            setup_log_fh,
            info_text="Systemd OnCalendar format only (e.g., *:0/5, 02:00).",
        )
        sql_import_schedule_str = validate_calendar_expression(
            sql_import_schedule_str, setup_log_fh, "*:0/5"
        )
        collected_config["sql_import_systemd"][
            "frequency"
        ] = sql_import_schedule_str  # Update collected config

        suggested_user = os.environ.get("SUDO_USER", getpass.getuser())
        suggested_user = (
            "your_non_root_user" if suggested_user == "root" else suggested_user
        )
        while True:
            run_as_user = _get_cli_input(
                "Non-root user for services",
                suggested_user,
                setup_log_fh,
                info_text="This user will own files and run cron jobs.",
            )
            if not run_as_user:
                _setup_print_and_log("Username cannot be empty.", setup_log_fh)
                continue
            if run_as_user == "root":
                _setup_print_and_log(
                    "Running as root is not allowed for services. Please choose a non-root user.",
                    setup_log_fh,
                )
                continue
            try:
                pwd.getpwnam(run_as_user)
                break
            except KeyError:
                _setup_print_and_log(
                    f"Error: User '{run_as_user}' not found on this system. Please create it first or use an existing non-root user.",
                    setup_log_fh,
                )

        _setup_print_and_log("\n--- Configuration Review ---", setup_log_fh)
        parser_display = configparser.ConfigParser()
        for s_name, s_options in collected_config.items():
            parser_display.add_section(s_name)
            for k, v_val in s_options.items():
                parser_display.set(s_name, k, str(v_val))

        _setup_print_and_log("Collected Configuration:", setup_log_fh)
        for section in parser_display.sections():
            _setup_print_and_log(f"[{section}]", setup_log_fh)
            for key, value in parser_display.items(section):
                _setup_print_and_log(f"  {key} = {value}", setup_log_fh)
        _setup_print_and_log("[Systemd]", setup_log_fh)
        _setup_print_and_log(
            f"  extraction_schedule = {extraction_schedule_str}", setup_log_fh
        )
        _setup_print_and_log(
            f"  report_on_calendar = {report_on_calendar_formatted}", setup_log_fh
        )
        _setup_print_and_log(
            f"  ip_update_schedule = {ip_update_schedule_str}", setup_log_fh
        )
        _setup_print_and_log(
            f"  sql_export_schedule = {sql_export_schedule_str}", setup_log_fh
        )
        _setup_print_and_log(
            f"  sql_import_schedule = {sql_import_schedule_str}", setup_log_fh
        )
        _setup_print_and_log(f"  run_as_user = {run_as_user}", setup_log_fh)

        confirm = _get_cli_input(
            "\nSave this configuration and proceed with setup?",
            "n",
            setup_log_fh,
            is_bool=True,
        )
        if confirm.lower() != "true":
            _setup_print_and_log(
                "Configuration not saved. Exiting setup.", setup_log_fh
            )
            return False

        _update_progress_display("Saving configuration file...", setup_log_fh)
        parser_save = configparser.ConfigParser()
        for s, o in collected_config.items():
            parser_save.add_section(s)
            for k, v in o.items():
                parser_save.set(s, k, str(v))

        # Add User and systemd sections for use by non_interactive_setup and other functions
        if not parser_save.has_section("User"):
            parser_save.add_section("User")
        parser_save.set("User", "run_as_user", run_as_user)
        if not parser_save.has_section("systemd"):
            parser_save.add_section("systemd")
        parser_save.set("systemd", "extraction_schedule", extraction_schedule_str)
        parser_save.set(
            "systemd", "report_schedule", report_on_calendar_formatted
        )  # Use the formatted one
        parser_save.set("systemd", "ip_update_schedule", ip_update_schedule_str)

        temp_dir_obj_cfg = tempfile.TemporaryDirectory(prefix="mls_cfg_")
        tmp_config_path = Path(temp_dir_obj_cfg.name) / "tmp.conf"
        with tmp_config_path.open("w") as cf_write:
            cf_write.write(
                f"# Generated by MailLogSentinel Interactive Setup {datetime.now().isoformat()}\n"
            )
            parser_save.write(cf_write)

        target_config_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_config_path), str(target_config_path))
        created_final_paths.append(str(target_config_path))
        _setup_print_and_log(
            f"Configuration saved to: {target_config_path}", setup_log_fh
        )
        if temp_dir_obj_cfg:
            temp_dir_obj_cfg.cleanup()

        _update_progress_display("Creating directories...", setup_log_fh)
        final_wd = Path(collected_config["paths"]["working_dir"])
        final_sd = Path(collected_config["paths"]["state_dir"])
        paths_to_create = {"Working Directory": final_wd, "State Directory": final_sd}
        ts_backup = datetime.now().strftime("%Y%m%d%H%M%S")

        for name, p_obj in paths_to_create.items():
            if p_obj.exists():
                backup_target = p_obj.parent / f"{p_obj.name}.backup_{ts_backup}"
                _setup_print_and_log(
                    f"{name} '{p_obj}' exists. Backing up to '{backup_target}'...",
                    setup_log_fh,
                )
                shutil.move(str(p_obj), str(backup_target))
                backed_up_items.append((str(backup_target), str(p_obj)))
            p_obj.mkdir(parents=True, exist_ok=True)
            created_final_paths.append(str(p_obj))
            _setup_print_and_log(f"Ensured {name} exists: {p_obj}", setup_log_fh)

        if os.geteuid() != 0:
            _setup_print_and_log("\nWARNING: Running as non-root user.", setup_log_fh)
            _setup_print_and_log(
                "Systemd unit installation, ownership changes, and systemctl commands will be skipped.",
                setup_log_fh,
            )
            _setup_print_and_log(
                f"You may need to manually perform these steps or re-run with sudo IF you want systemd integration.",
                setup_log_fh,
            )
            _setup_print_and_log(
                f"Ensure the user '{run_as_user}' has write permissions to '{target_config_path}', '{final_wd}', and '{final_sd}'.",
                setup_log_fh,
            )
            _setup_print_and_log(
                f"And read permissions for '{collected_config['paths']['mail_log']}'.",
                setup_log_fh,
            )
            _setup_print_and_log(
                "Interactive setup completed (manual steps may be required).",
                setup_log_fh,
            )
            return True  # Core config done, but with caveats

        _update_progress_display("Generating Systemd unit files...", setup_log_fh)
        python_exec = shutil.which("python3") or "/usr/bin/python3"
        script_main_path = (
            shutil.which("maillogsentinel.py") or "/usr/local/bin/maillogsentinel.py"
        )
        ipinfo_script_path_sysd = (
            shutil.which("ipinfo.py") or "/usr/local/bin/ipinfo.py"
        )

        units_content = _generate_systemd_units_content(
            run_as_user,
            python_exec,
            script_main_path,
            str(target_config_path),
            str(final_wd),
            extraction_schedule_str,
            report_on_calendar_formatted,
            ip_update_schedule_str,
            ipinfo_script_path_sysd,
            sql_export_schedule_str,  # New
            sql_import_schedule_str,  # New
        )

        install_systemd = _get_cli_input(
            "\nInstall Systemd unit files to /etc/systemd/system/?",
            "y",
            setup_log_fh,
            is_bool=True,
        )
        systemd_files_installed_flag = False
        if install_systemd.lower() == "true":
            _update_progress_display("Installing Systemd unit files...", setup_log_fh)
            systemd_dir = Path("/etc/systemd/system/")
            systemd_dir.mkdir(parents=True, exist_ok=True)
            for unit_filename, content in units_content.items():
                unit_path = systemd_dir / unit_filename
                # Basic backup for systemd files if they exist
                if unit_path.exists():
                    backup_unit_path = (
                        unit_path.parent / f"{unit_path.name}.backup_{ts_backup}"
                    )
                    _setup_print_and_log(
                        f"Backing up existing systemd unit {unit_path} to {backup_unit_path}",
                        setup_log_fh,
                    )
                    shutil.move(str(unit_path), str(backup_unit_path))  # Move, not copy
                    backed_up_items.append((str(backup_unit_path), str(unit_path)))
                unit_path.write_text(content)
                created_final_paths.append(str(unit_path))
                _setup_print_and_log(f"  Installed {unit_filename}", setup_log_fh)
            systemd_files_installed_flag = True
        else:
            _setup_print_and_log(
                "Systemd unit file installation skipped by user.", setup_log_fh
            )

        apply_system_changes = _get_cli_input(
            "\nProceed with final system changes (ownership, groups, systemctl daemon-reload/enable timers)?",
            "y",
            setup_log_fh,
            is_bool=True,
        )
        if apply_system_changes.lower() == "true":
            _update_progress_display("Applying ownership changes...", setup_log_fh)
            _change_ownership(str(target_config_path), run_as_user, setup_log_fh)
            _change_ownership(str(final_wd), run_as_user, setup_log_fh)
            _change_ownership(str(final_sd), run_as_user, setup_log_fh)
            # Also DB paths if they are not within workdir/statedir and exist
            for db_key in ["country_db_path", "asn_db_path"]:
                db_path_str = collected_config.get("geolocation", {}).get(
                    db_key
                ) or collected_config.get("ASN_ASO", {}).get(db_key)
                if db_path_str:
                    db_p = Path(db_path_str)
                    if (
                        db_p.parent != final_wd and db_p.parent != final_sd
                    ):  # Avoid chowning twice if inside
                        # Ensure parent dir is chowned if it was created by setup, or if file itself is chowned
                        # This is complex; for now, just chown the file if it exists.
                        # A better approach might be to ensure DBs are within workdir.
                        if db_p.exists():
                            _change_ownership(str(db_p), run_as_user, setup_log_fh)
                        elif db_p.parent.exists():
                            _change_ownership(
                                str(db_p.parent), run_as_user, setup_log_fh
                            )

            _update_progress_display(
                f"Adding user {run_as_user} to 'adm' group (if not already a member)...",
                setup_log_fh,
            )
            usermod_cmd_path = shutil.which("usermod")
            if usermod_cmd_path:
                usermod_proc = subprocess.run(
                    [usermod_cmd_path, "-aG", "adm", run_as_user],
                    capture_output=True,
                    text=True,
                )
                _setup_print_and_log(
                    f"usermod -aG adm {run_as_user}: RC={usermod_proc.returncode}, STDOUT='{usermod_proc.stdout.strip()}', STDERR='{usermod_proc.stderr.strip()}'",
                    setup_log_fh,
                )
                if usermod_proc.returncode != 0:
                    _setup_print_and_log(
                        f"  WARNING: usermod command failed. User '{run_as_user}' may need manual assignment to 'adm' group to read logs.",
                        setup_log_fh,
                    )
            else:
                _setup_print_and_log(
                    "  WARNING: 'usermod' command not found. Cannot add user to 'adm' group automatically.",
                    setup_log_fh,
                )

            if systemd_files_installed_flag:
                systemctl_cmd_path = shutil.which("systemctl")
                if systemctl_cmd_path:
                    _update_progress_display(
                        "Reloading systemd daemon...", setup_log_fh
                    )
                    try:
                        subprocess.run(
                            [systemctl_cmd_path, "daemon-reload"],
                            check=True,
                            capture_output=True,
                            text=True,
                        )
                        _setup_print_and_log(
                            "  systemctl daemon-reload successful.", setup_log_fh
                        )
                    except subprocess.CalledProcessError as e_ctl:
                        _setup_print_and_log(
                            f"  ERROR: systemctl daemon-reload failed: {e_ctl.stderr}",
                            setup_log_fh,
                        )

                    _update_progress_display(
                        "Enabling and starting Systemd timers...", setup_log_fh
                    )
                    for timer_name in [
                        "maillogsentinel-extract.timer",
                        "maillogsentinel-report.timer",
                        "ipinfo-update.timer",
                        "maillogsentinel-sql-export.timer",  # New
                        "maillogsentinel-sql-import.timer",  # New
                    ]:
                        if (Path("/etc/systemd/system") / timer_name).exists():
                            try:
                                subprocess.run(
                                    [systemctl_cmd_path, "enable", "--now", timer_name],
                                    check=True,
                                    capture_output=True,
                                    text=True,
                                )
                                _setup_print_and_log(
                                    f"  Enabled and started {timer_name}.", setup_log_fh
                                )
                            except subprocess.CalledProcessError as e_ctl_timer:
                                _setup_print_and_log(
                                    f"  ERROR: Failed to enable/start {timer_name}: {e_ctl_timer.stderr}",
                                    setup_log_fh,
                                )
                        else:
                            _setup_print_and_log(
                                f"  Timer {timer_name} not found in /etc/systemd/system, skipping enable/start.",
                                setup_log_fh,
                            )
                else:
                    _setup_print_and_log(
                        "  'systemctl' command not found. Systemd operations skipped.",
                        setup_log_fh,
                    )
            else:
                _setup_print_and_log(
                    "  Systemd files were not installed, skipping systemctl operations.",
                    setup_log_fh,
                )
        else:
            _setup_print_and_log("Final system changes skipped by user.", setup_log_fh)

        _setup_print_and_log("\n--- Interactive Setup Completed ---", setup_log_fh)
        _setup_print_and_log(
            f"Configuration file is at: {target_config_path}", setup_log_fh
        )
        _setup_print_and_log("Please review the setup log for details.", setup_log_fh)
        if os.geteuid() == 0 and systemd_files_installed_flag:
            _setup_print_and_log("Systemd timers should now be active.", setup_log_fh)

    except SigintEncountered:
        _setup_print_and_log(
            "\nUser interrupted interactive setup (Ctrl+C).", setup_log_fh
        )
        raise  # Re-raise to be caught by main_setup's handler for cleanup
    except Exception as e_main_interactive:
        _setup_print_and_log(
            f"FATAL ERROR during interactive setup: {e_main_interactive.__class__.__name__}: {e_main_interactive}",
            setup_log_fh,
        )
        import traceback

        _setup_print_and_log(traceback.format_exc(), setup_log_fh)
        return False  # Indicate failure
    return True


# The interactive_curses_setup function is now removed as it's obsolete.
# Removed curses_main function


def non_interactive_setup(source_config_path: Path, setup_log_fh):
    """
    Performs a non-interactive setup using a source configuration file.
    The target system configuration path is DEFAULT_CONFIG_PATH_SETUP.
    Updates global backed_up_items and created_final_paths lists.
    """
    import sys  # Ensure sys is imported for stdout
    import traceback

    print("non_interactive_setup CALLED", flush=True)
    # traceback.print_stack(file=sys.stdout, limit=10) # Removed for debugging
    print("---", flush=True)

    _setup_print_and_log(f"--- MailLogSentinel Non-Interactive Setup ---", setup_log_fh)

    if os.geteuid() != 0:
        _setup_print_and_log(
            "ERROR: Non-interactive setup requires root privileges. Please run with sudo.",
            setup_log_fh,
        )
        sys.exit(1)

    if not source_config_path.is_file():
        _setup_print_and_log(
            f"ERROR: Source configuration file '{source_config_path}' not found or is not a file.",
            setup_log_fh,
        )
        sys.exit(1)
    _setup_print_and_log(
        f"Using source configuration file: {source_config_path.resolve()}", setup_log_fh
    )

    _setup_print_and_log("Loading and validating source configuration...", setup_log_fh)
    config = configparser.ConfigParser()
    try:
        read_files = config.read(source_config_path)
        if not read_files:
            _setup_print_and_log(
                f"ERROR: Could not read or parse source configuration file: {source_config_path}",
                setup_log_fh,
            )
            sys.exit(1)
    except configparser.Error as e:
        _setup_print_and_log(
            f"ERROR: Invalid configuration file format in {source_config_path}: {e}",
            setup_log_fh,
        )
        sys.exit(1)

    required_sections = {
        "paths": ["working_dir", "state_dir", "mail_log"],
        "report": ["email"],
        "general": ["log_level"],
        "User": ["run_as_user"],
        # sqlite_database, sql_export_systemd, sql_import_systemd are optional for non-interactive
    }
    for section, keys in required_sections.items():
        if not config.has_section(section):
            _setup_print_and_log(
                f"ERROR: Missing section '[{section}]' in configuration file.",
                setup_log_fh,
            )  # Ensure brackets
            sys.exit(1)
        for key in keys:
            if not config.has_option(section, key) or (
                config.has_option(section, key) and not config.get(section, key).strip()
            ):
                _setup_print_and_log(
                    f"ERROR: Missing or empty value for '{key}' in section '[{section}]'.",
                    setup_log_fh,
                )  # Ensure brackets
                sys.exit(1)
    _setup_print_and_log(
        "Source configuration loaded and basic validation passed.", setup_log_fh
    )

    target_config_file = DEFAULT_CONFIG_PATH_SETUP
    _setup_print_and_log(
        f"Target system configuration file: {target_config_file}", setup_log_fh
    )
    if target_config_file.exists():
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_config_path = (
            target_config_file.parent / f"{target_config_file.name}.backup_{timestamp}"
        )
        try:
            shutil.move(str(target_config_file), str(backup_config_path))
            _setup_print_and_log(
                f"Backed up existing configuration {target_config_file} to {backup_config_path}",
                setup_log_fh,
            )
            backed_up_items.append((str(backup_config_path), str(target_config_file)))
        except (OSError, shutil.Error) as e:
            _setup_print_and_log(
                f"ERROR: Could not back up existing configuration file {target_config_file}: {e}",
                setup_log_fh,
            )
            sys.exit(1)

    try:
        target_config_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(source_config_path), str(target_config_file))
        _setup_print_and_log(
            f"Copied source configuration to {target_config_file}", setup_log_fh
        )
        created_final_paths.append(str(target_config_file))
    except (OSError, shutil.Error) as e:
        _setup_print_and_log(
            f"ERROR: Could not copy configuration file to {target_config_file}: {e}",
            setup_log_fh,
        )
        sys.exit(1)

    working_dir = Path(
        config.get("paths", "working_dir", fallback=str(DEFAULT_WORKING_DIR))
    )
    state_dir = Path(config.get("paths", "state_dir", fallback=str(DEFAULT_STATE_DIR)))
    _setup_print_and_log(f"Working directory from config: {working_dir}", setup_log_fh)
    _setup_print_and_log(f"State directory from config: {state_dir}", setup_log_fh)

    for dir_path, dir_name in [(working_dir, "working"), (state_dir, "state")]:
        if dir_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            backup_dir_path = dir_path.parent / f"{dir_path.name}.backup_{timestamp}"
            try:
                shutil.move(str(dir_path), str(backup_dir_path))
                _setup_print_and_log(
                    f"Backed up existing {dir_name} directory {dir_path} to {backup_dir_path}",
                    setup_log_fh,
                )
                backed_up_items.append((str(backup_dir_path), str(dir_path)))
            except (OSError, shutil.Error) as e:
                _setup_print_and_log(
                    f"ERROR: Could not back up existing {dir_name} directory {dir_path}: {e}",
                    setup_log_fh,
                )
                sys.exit(1)
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            _setup_print_and_log(
                f"Created {dir_name} directory: {dir_path}", setup_log_fh
            )
            created_final_paths.append(str(dir_path))
        except OSError as e:
            _setup_print_and_log(
                f"ERROR: Could not create {dir_name} directory {dir_path}: {e}",
                setup_log_fh,
            )
            sys.exit(1)

    run_as_user = config.get("User", "run_as_user")
    _setup_print_and_log(
        f"Service will be configured to run as user: '{run_as_user}' (from configuration).",
        setup_log_fh,
    )
    if run_as_user == "root":
        _setup_print_and_log(
            "ERROR: Configuration specifies 'root' as 'run_as_user'. Not allowed.",
            setup_log_fh,
        )
        sys.exit(1)
    try:
        pwd.getpwnam(run_as_user)
        _setup_print_and_log(
            f"User '{run_as_user}' verified successfully.", setup_log_fh
        )
    except KeyError:
        _setup_print_and_log(f"ERROR: User '{run_as_user}' not found.", setup_log_fh)
        sys.exit(1)  # Restored error
    except Exception as e:
        _setup_print_and_log(f"ERROR verifying user '{run_as_user}': {e}", setup_log_fh)
        sys.exit(1)

    adm_group = "adm"
    _setup_print_and_log(
        f"Attempting to add user '{run_as_user}' to group '{adm_group}'...",
        setup_log_fh,
    )
    usermod_cmd = shutil.which("usermod")
    if not usermod_cmd:
        _setup_print_and_log(f"ERROR: 'usermod' not found.", setup_log_fh)
        sys.exit(1)  # Restored error
    try:
        process_result = subprocess.run(
            [usermod_cmd, "-aG", adm_group, run_as_user],
            check=True,
            capture_output=True,
            text=True,
        )
        _setup_print_and_log(
            f"User '{run_as_user}' in group '{adm_group}'. STDOUT: {process_result.stdout.strip()} STDERR: {process_result.stderr.strip()}",
            setup_log_fh,
        )
    except Exception as e:
        _setup_print_and_log(f"ERROR adding user to group: {e}", setup_log_fh)
        sys.exit(1)  # Restored error

    _setup_print_and_log(
        f"Changing ownership of config, work, and state dirs to '{run_as_user}'...",
        setup_log_fh,
    )
    _change_ownership(str(target_config_file), run_as_user, setup_log_fh)
    _change_ownership(str(working_dir), run_as_user, setup_log_fh)
    _change_ownership(str(state_dir), run_as_user, setup_log_fh)

    _setup_print_and_log("Generating Systemd unit files...", setup_log_fh)
    python_executable = shutil.which("python3") or "/usr/bin/python3"
    script_path_for_systemd = (
        shutil.which("maillogsentinel.py") or "/usr/local/bin/maillogsentinel.py"
    )
    if not Path(
        script_path_for_systemd
    ).is_file() and not script_path_for_systemd.startswith("/usr/local/bin"):
        _setup_print_and_log(
            f"WARN: script not found at {script_path_for_systemd}", setup_log_fh
        )
    extraction_schedule_str = config.get(
        "systemd", "extraction_schedule", fallback="hourly"
    )
    report_on_calendar = config.get("systemd", "report_schedule", fallback="daily")
    if report_on_calendar.lower() == "daily":
        report_on_calendar = "*-*-* 23:59:00"
    elif re.fullmatch(r"\d{2}:\d{2}", report_on_calendar):
        h, m = map(int, report_on_calendar.split(":"))
        report_on_calendar = f"*-*-* {h:02d}:{m:02d}:00"
    ip_update_schedule_str = config.get(
        "systemd", "ip_update_schedule", fallback="daily"
    )
    ipinfo_script_path = shutil.which("ipinfo.py") or "/usr/local/bin/ipinfo.py"
    if not Path(ipinfo_script_path).is_file() and not ipinfo_script_path.startswith(
        "/usr/local/bin"
    ):
        _setup_print_and_log(
            f"WARN: ipinfo.py script not found at {ipinfo_script_path}", setup_log_fh
        )

    # Get SQL export and import schedules from config, with defaults
    sql_export_schedule_str = config.get(
        "sql_export_systemd", "frequency", fallback="*:0/4"
    )
    sql_export_schedule_str = validate_calendar_expression(
        sql_export_schedule_str, setup_log_fh, "*:0/4"
    )
    sql_import_schedule_str = config.get(
        "sql_import_systemd", "frequency", fallback="*:0/5"
    )
    sql_import_schedule_str = validate_calendar_expression(
        sql_import_schedule_str, setup_log_fh, "*:0/5"
    )

    # Validate other schedules as well
    extraction_schedule_str = validate_calendar_expression(
        extraction_schedule_str, setup_log_fh, "hourly"
    )
    report_on_calendar = validate_calendar_expression(
        report_on_calendar, setup_log_fh, "daily" # Assuming 'daily' implies a valid Systemd value like 00:00 or similar
    )
    ip_update_schedule_str = validate_calendar_expression(
        ip_update_schedule_str, setup_log_fh, "daily"
    )


    unit_files_content = _generate_systemd_units_content(
        run_as_user,
        python_executable,
        script_path_for_systemd,
        str(target_config_file),
        str(working_dir),
        extraction_schedule_str,
        report_on_calendar,
        ip_update_schedule_str,
        ipinfo_script_path,
        sql_export_schedule_str,  # New
        sql_import_schedule_str,  # New
    )
    systemd_dir_path = Path("/etc/systemd/system/")  # Restored
    temp_dir_obj_units = tempfile.TemporaryDirectory(prefix="mls_units_")
    temp_dir = Path(temp_dir_obj_units.name)
    all_units_prepared = True
    for filename, content in unit_files_content.items():
        try:
            (temp_dir / filename).write_text(content)
        except IOError as e:
            _setup_print_and_log(
                f"ERROR writing temp unit {filename}: {e}", setup_log_fh
            )
            all_units_prepared = False
            break
    if all_units_prepared:
        _setup_print_and_log(f"Systemd units prepared in {temp_dir}", setup_log_fh)
        systemd_dir_path.mkdir(
            parents=True, exist_ok=True
        )  # Ensure systemd dir exists before moving
        for filename in unit_files_content.keys():
            final_file_path = systemd_dir_path / filename
            if final_file_path.exists():
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                backup_unit_path = (
                    final_file_path.parent
                    / f"{final_file_path.name}.backup_{timestamp}"
                )
                try:
                    shutil.move(str(final_file_path), str(backup_unit_path))
                    _setup_print_and_log(
                        f"Backed up {final_file_path} to {backup_unit_path}",
                        setup_log_fh,
                    )
                    backed_up_items.append(
                        (str(backup_unit_path), str(final_file_path))
                    )
                except Exception as e:
                    _setup_print_and_log(
                        f"ERROR backing up {final_file_path}: {e}", setup_log_fh
                    )
            try:
                shutil.move(str(temp_dir / filename), str(final_file_path))
                _setup_print_and_log(f"Installed {final_file_path}", setup_log_fh)
                created_final_paths.append(str(final_file_path))
            except Exception as e:
                _setup_print_and_log(
                    f"ERROR installing {final_file_path}: {e}", setup_log_fh
                )
    if temp_dir_obj_units:
        temp_dir_obj_units.cleanup()

    _setup_print_and_log(
        "Reloading systemd daemon and enabling timers...", setup_log_fh
    )
    systemctl_cmd = shutil.which("systemctl")
    if not systemctl_cmd:
        _setup_print_and_log("ERROR: 'systemctl' not found.", setup_log_fh)
        sys.exit(1)  # Restored error
    try:
        subprocess.run(
            [systemctl_cmd, "daemon-reload"], check=True, capture_output=True, text=True
        )
        _setup_print_and_log("Systemd daemon reloaded.", setup_log_fh)
    except subprocess.CalledProcessError as e:
        error_detail = f"Stderr: {e.stderr.strip()}" if e.stderr else "No stderr."
        _setup_print_and_log(
            f"ERROR: 'systemctl daemon-reload' failed: {e}. {error_detail}",
            setup_log_fh,
        )
        sys.exit(1)
    except Exception as e:  # Catch other exceptions
        _setup_print_and_log(
            f"ERROR: 'systemctl daemon-reload' failed with an unexpected error: {e}",
            setup_log_fh,
        )
        sys.exit(1)

    timers_to_enable = [
        "maillogsentinel-extract.timer",
        "maillogsentinel-report.timer",
        "ipinfo-update.timer",
        "maillogsentinel-sql-export.timer",  # New
        "maillogsentinel-sql-import.timer",  # New
    ]
    for timer in timers_to_enable:
        if not (systemd_dir_path / timer).exists():
            _setup_print_and_log(
                f"WARN: Timer {timer} not found, skip enable.", setup_log_fh
            )
            continue
        try:
            subprocess.run(
                [systemctl_cmd, "enable", "--now", timer],
                check=True,
                capture_output=True,
                text=True,
            )
            _setup_print_and_log(f"Enabled/started {timer}", setup_log_fh)
        except subprocess.CalledProcessError as e:
            error_detail = f"Stderr: {e.stderr.strip()}" if e.stderr else "No stderr."
            _setup_print_and_log(
                f"ERROR: 'systemctl enable --now {timer}' failed: {e}. {error_detail}",
                setup_log_fh,
            )
            sys.exit(1)
        except Exception as e:  # Catch other exceptions
            _setup_print_and_log(
                f"ERROR: 'systemctl enable --now {timer}' failed with an unexpected error: {e}",
                setup_log_fh,
            )
            sys.exit(1)

    _setup_print_and_log("--- Non-Interactive Setup Completed ---", setup_log_fh)


def _generate_systemd_units_content(
    run_as_user,
    python_exec,
    script_path,
    config_path,
    work_dir,
    extract_sched,
    report_sched,
    ip_update_sched,
    ipinfo_script_path,
    sql_export_schedule,  # New
    sql_import_schedule,  # New
):
    _setup_print_and_log(
        f"Generating systemd units with user={run_as_user}, script={script_path}", None
    )
    maillogsentinel_service_content = f"""[Unit]\nDescription=MailLogSentinel Log Extraction Service\nAfter=network.target\n\n[Service]\nType=oneshot\nUser={run_as_user}\nExecStart={python_exec} {script_path} --config {config_path}\nWorkingDirectory={work_dir}\nStandardOutput=journal\nStandardError=journal\n\n[Install]\nWantedBy=multi-user.target\n"""
    maillogsentinel_extract_timer_content = f"""[Unit]\nDescription=Run MailLogSentinel Log Extraction periodically\n\n[Timer]\nUnit=maillogsentinel.service\nOnCalendar={extract_sched}\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n"""
    maillogsentinel_report_service_content = f"""[Unit]\nDescription=MailLogSentinel Daily Report Service\nAfter=network.target\n\n[Service]\nType=oneshot\nUser={run_as_user}\nExecStart={python_exec} {script_path} --config {config_path} --report\nWorkingDirectory={work_dir}\nStandardOutput=journal\nStandardError=journal\n\n[Install]\nWantedBy=multi-user.target\n"""
    maillogsentinel_report_timer_content = f"""[Unit]\nDescription=Run MailLogSentinel Daily Report\n\n[Timer]\nUnit=maillogsentinel-report.service\nOnCalendar={report_sched}\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n"""
    ipinfo_update_service_content = f"""[Unit]\nDescription=Service to update IP DBs for MailLogSentinel\nAfter=network.target\n\n[Service]\nType=oneshot\nUser={run_as_user}\nExecStart={python_exec} {ipinfo_script_path} --update --config {config_path}\nStandardOutput=journal\nStandardError=journal\n\n[Install]\nWantedBy=multi-user.target\n"""
    ipinfo_update_timer_content = f"""[Unit]\nDescription=Timer to update IP DBs\n\n[Timer]\nUnit=ipinfo-update.service\nOnCalendar={ip_update_sched}\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n"""

    # New SQL Export units
    maillogsentinel_sql_export_service_content = f"""[Unit]\nDescription=MailLogSentinel SQL Export Service\nAfter=network.target\n\n[Service]\nType=oneshot\nUser={run_as_user}\nExecStart={python_exec} {script_path} --config {config_path} --sql-export\nWorkingDirectory={work_dir}\nStandardOutput=journal\nStandardError=journal\n\n[Install]\nWantedBy=multi-user.target\n"""
    maillogsentinel_sql_export_timer_content = f"""[Unit]\nDescription=Run MailLogSentinel SQL Export periodically\n\n[Timer]\nUnit=maillogsentinel-sql-export.service\nOnCalendar={sql_export_schedule}\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n"""

    # New SQL Import units
    maillogsentinel_sql_import_service_content = f"""[Unit]\nDescription=MailLogSentinel SQL Import Service\nAfter=network.target\n\n[Service]\nType=oneshot\nUser={run_as_user}\nExecStart={python_exec} {script_path} --config {config_path} --sql-import\nWorkingDirectory={work_dir}\nStandardOutput=journal\nStandardError=journal\n\n[Install]\nWantedBy=multi-user.target\n"""
    maillogsentinel_sql_import_timer_content = f"""[Unit]\nDescription=Run MailLogSentinel SQL Import periodically\n\n[Timer]\nUnit=maillogsentinel-sql-import.service\nOnCalendar={sql_import_schedule}\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n"""

    return {
        "maillogsentinel.service": maillogsentinel_service_content,
        "maillogsentinel-extract.timer": maillogsentinel_extract_timer_content,
        "maillogsentinel-report.service": maillogsentinel_report_service_content,
        "maillogsentinel-report.timer": maillogsentinel_report_timer_content,
        "ipinfo-update.service": ipinfo_update_service_content,
        "ipinfo-update.timer": ipinfo_update_timer_content,
        "maillogsentinel-sql-export.service": maillogsentinel_sql_export_service_content,
        "maillogsentinel-sql-export.timer": maillogsentinel_sql_export_timer_content,
        "maillogsentinel-sql-import.service": maillogsentinel_sql_import_service_content,
        "maillogsentinel-sql-import.timer": maillogsentinel_sql_import_timer_content,
    }


def main_setup():
    """Main entry point for the setup script."""
    original_console_print = functools.partial(print, flush=True)
    SETUP_LOG_FILENAME = "maillogsentinel_setup.log"
    log_file_path = Path.cwd() / SETUP_LOG_FILENAME
    setup_log_fh = None
    # curses_was_active = False # No longer needed

    # Argument parsing
    parser = argparse.ArgumentParser(description="MailLogSentinel Setup Script.")
    parser.add_argument(
        "config_file_path",
        nargs="?",
        help="Path to the configuration file. For interactive setup, this is the target path (defaults to /etc/maillogsentinel.conf). For automated setup, this is the source config file.",
    )
    parser.add_argument(
        "--interactive", action="store_true", help="Run interactive setup."
    )
    parser.add_argument(
        "--automated",
        action="store_true",
        help="Run automated setup (requires config_file_path as source).",
    )
    # --test-non-interactive-direct is removed as it's obsolete

    args = parser.parse_args()

    try:
        setup_log_fh = open(log_file_path, "w", encoding="utf-8")
        original_console_print(
            f"Note: The setup process output will be saved to {log_file_path.resolve()}"
        )
        _setup_print_and_log(f"Setup script invoked. Args: {sys.argv}", setup_log_fh)

        global backed_up_items, created_final_paths  # Ensure global scope
        backed_up_items = []
        created_final_paths = []

        signal.signal(signal.SIGINT, handle_sigint)  # Setup SIGINT handler

        if args.interactive:
            _setup_print_and_log("Mode: Interactive Setup", setup_log_fh)
            target_config_path = (
                Path(args.config_file_path)
                if args.config_file_path
                else DEFAULT_CONFIG_PATH_SETUP
            )
            _setup_print_and_log(
                f"Target configuration file: {target_config_path}", setup_log_fh
            )
            interactive_cli_setup(target_config_path, setup_log_fh)  # Placeholder call

        elif args.automated:
            _setup_print_and_log("Mode: Automated Setup", setup_log_fh)
            if not args.config_file_path:
                _setup_print_and_log(
                    "ERROR: Automated setup requires a source configuration file path.",
                    setup_log_fh,
                )
                original_console_print(
                    "ERROR: --automated flag requires the config_file_path argument to be specified as the source.",
                    file=sys.stderr,
                )
                sys.exit(2)
            source_config_path = Path(args.config_file_path)
            if not source_config_path.is_file():
                _setup_print_and_log(
                    f"ERROR: Source configuration file not found: {source_config_path}",
                    setup_log_fh,
                )
                original_console_print(
                    f"ERROR: Source configuration file not found: {source_config_path}",
                    file=sys.stderr,
                )
                sys.exit(2)
            _setup_print_and_log(
                f"Source configuration file: {source_config_path}", setup_log_fh
            )
            non_interactive_setup(source_config_path, setup_log_fh)

        else:
            # Default behavior if no mode is specified: try to be helpful.
            # This part might be adjusted based on how maillogsentinel.py calls it.
            # If maillogsentinel.py *always* passes a mode, this 'else' might become an error.
            original_console_print(
                "No setup mode specified. Use --interactive or --automated."
            )
            _setup_print_and_log("No setup mode specified via arguments.", setup_log_fh)
            original_console_print(
                f"Example for interactive: {sys.argv[0]} --interactive [/path/to/target/config.conf]"
            )
            original_console_print(
                f"Example for automated: {sys.argv[0]} --automated /path/to/source/config.conf"
            )
            sys.exit(1)

    except SigintEncountered:
        log_msg = "\nCtrl+C detected. Setup process is stopping."
        # No curses cleanup needed here anymore
        if setup_log_fh and not setup_log_fh.closed:
            _setup_print_and_log(log_msg, setup_log_fh)
        else:
            original_console_print(log_msg)

        if backed_up_items:
            original_console_print(
                "Attempting to restore backed-up items due to interruption..."
            )
            for backup_path_str, original_path_str in reversed(backed_up_items):
                try:
                    shutil.move(str(backup_path_str), str(original_path_str))
                    original_console_print(
                        f"Restored: {backup_path_str} -> {original_path_str}"
                    )
                except Exception as e_restore:
                    original_console_print(
                        f"Error restoring {backup_path_str} to {original_path_str}: {e_restore}"
                    )
        if created_final_paths:
            original_console_print(
                "Attempting to delete created files/directories due to interruption..."
            )
            for path_str in reversed(created_final_paths):
                try:
                    path_obj = Path(path_str)
                    if path_obj.is_file():
                        path_obj.unlink()
                    elif path_obj.is_dir():
                        shutil.rmtree(str(path_obj))
                    original_console_print(f"Deleted: {path_obj}")
                except Exception as e_delete:
                    original_console_print(f"Error deleting {path_obj}: {e_delete}")
        sys.exit(130)

    except Exception as e:
        error_msg = f"FATAL ERROR during setup: {e.__class__.__name__}: {e}"
        # No curses cleanup needed here
        if setup_log_fh and not setup_log_fh.closed:
            _setup_print_and_log(error_msg, setup_log_fh)
            import traceback

            _setup_print_and_log(traceback.format_exc(), setup_log_fh)
        else:
            original_console_print(error_msg, file=sys.stderr)
            import traceback

            original_console_print(traceback.format_exc(), file=sys.stderr)
        sys.exit(3)
    finally:
        # No curses cleanup needed here
        if setup_log_fh and not setup_log_fh.closed:
            _setup_print_and_log("\nSetup script finished.", setup_log_fh)
            setup_log_fh.close()
            original_console_print(f"Setup log available at {log_file_path.resolve()}")
        elif not setup_log_fh:
            original_console_print(
                f"Setup log was intended for {log_file_path.resolve()}, but might not have been created/written due to an early error."
            )


if __name__ == "__main__":
    main_setup()
