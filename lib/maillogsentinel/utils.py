"""
Provides common utility functions for the MailLogSentinel application.

This module includes a variety of helper functions for tasks such as:
- Checking for root privileges.
- Setting up necessary file system paths (working directory, state directory, log paths).
- Configuring application logging with rotating file handlers.
- Reading and writing the application's state (e.g., last log offset).
- Listing mail log files, including rotated and gzipped versions.
- Checking if a file is gzipped based on its extension.

Constants for filenames (state, log) and log level mappings are also defined here.
"""

import os
import sys

import logging
import logging.handlers
from pathlib import Path
from typing import Optional, Tuple, List  # Union removed

from . import config  # Added import

# Constants that might be shared or specific to utils
STATE_FILENAME = "state.offset"
LOG_FILENAME = "maillogsentinel.log"

LOG_LEVELS_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def check_root():
    """Checks if the script is run as root and exits if true."""
    if os.geteuid() == 0:
        print("⚠️  Do not run as root; switch to a non-root account.", file=sys.stderr)
        sys.exit(1)


def setup_paths(app_config: "config.AppConfig") -> Tuple[Path, Path, Path, Path, Path]:
    """Sets up and creates necessary directories based on AppConfig settings.

    This function retrieves path configurations from the `AppConfig` object
    (working directory, state directory, mail log path, GeoIP database paths)
    and ensures that the working and state directories exist. It also attempts
    to create parent directories for GeoIP database files if they are specified,
    do not exist, and are not in standard system locations.

    If any required directory cannot be created due to permission issues or
    other `OSError` exceptions, an error is logged (and printed to stderr),
    and the program exits.

    Args:
        app_config: An `AppConfig` instance containing all path configurations.

    Returns:
        A tuple of `Path` objects:
        (workdir, statedir, maillog, country_db_path, asn_db_path).
        These are the resolved absolute paths obtained from `app_config`.

    Raises:
        SystemExit: If a directory cannot be created.
    """
    # AppConfig constructor already resolves these paths including fallbacks
    # and relative logic
    workdir = app_config.working_dir
    statedir = app_config.state_dir
    maillog = app_config.mail_log
    country_db_path = app_config.country_db_path
    asn_db_path = app_config.asn_db_path

    try:
        workdir.mkdir(parents=True, exist_ok=True)
        statedir.mkdir(parents=True, exist_ok=True)

        # Parent dir creation for DBs can be part of AppConfig validation or
        # IPInfoManager's responsibility. The AppConfig now ensures these
        # paths are absolute or resolved. We should ensure their parent
        # directories exist if they are not standard system locations or
        # already created (like workdir/statedir).

        # Example of ensuring parent for custom DB paths exists:
        # This could be more sophisticated, perhaps checking if the parent is
        # a common root like /var/lib and skipping mkdir in those cases, or
        # relying on the application/user to ensure system paths are valid.
        db_paths_to_check_parents_for = []
        if country_db_path:
            db_paths_to_check_parents_for.append(country_db_path)
        if asn_db_path:
            db_paths_to_check_parents_for.append(asn_db_path)

        for db_path in db_paths_to_check_parents_for:
            parent_dir = db_path.parent
            # Avoid trying to create root or very high-level dirs, or if
            # it's same as workdir/statedir
            if (
                not parent_dir.exists()
                and str(parent_dir) != "."
                and parent_dir
                not in [Path("/"), Path("/var"), Path("/var/lib"), workdir, statedir]
            ):
                app_config.logger.info(
                    f"Attempting to create database parent directory: {parent_dir}"
                )
                parent_dir.mkdir(parents=True, exist_ok=True)

    except OSError as e:
        # Use logger from app_config; it's initialized with a default if not
        # passed earlier, and then updated once main logger is set up.
        # Also print to stderr directly in case logger is not yet fully functional or uses NullHandler
        error_message = f"ERROR: Permission denied creating directory {e.filename}: {e}"
        # Check if logger exists and has handlers that are not NullHandler
        # (hasHandlers() is Python 3.7+)
        can_use_logger = False
        if app_config.logger:
            if hasattr(app_config.logger, "hasHandlers"):  # Python 3.7+
                if app_config.logger.hasHandlers():
                    can_use_logger = not isinstance(
                        app_config.logger.handlers[0], logging.NullHandler
                    )
            elif app_config.logger.handlers:  # Older Python versions
                can_use_logger = not isinstance(
                    app_config.logger.handlers[0], logging.NullHandler
                )

        if can_use_logger:
            app_config.logger.error(error_message)
        else:
            print(error_message, file=sys.stderr)
        sys.exit(1)
    return workdir, statedir, maillog, country_db_path, asn_db_path


def setup_logging(app_config: "config.AppConfig") -> logging.Logger:
    """Sets up rotating file logging based on AppConfig settings.

    This function configures the main application logger ("maillogsentinel").
    It sets the logging level based on `app_config.log_level`.
    If `app_config.log_file` is specified:
        - It ensures the parent directory for the log file exists.
        - It adds a `RotatingFileHandler` with log rotation based on
          `app_config.log_file_max_bytes` and `app_config.log_file_backup_count`.
        - A specific log format `%(asctime)s %(levelname)s %(message)s` is used.
    If `app_config.log_file` is not set (is None), a `NullHandler` is added,
    effectively disabling file logging.

    If critical errors occur during log setup (e.g., permission denied creating
    log directory or file), an error is printed to stderr, and the program may
    exit or fall back to a `NullHandler`.

    Args:
        app_config: An `AppConfig` instance containing logging configuration
                    (log_level, log_file, max_bytes, backup_count).

    Returns:
        The configured `logging.Logger` instance named "maillogsentinel".

    Raises:
        SystemExit: If the log file's parent directory cannot be created.
    """
    log_level = LOG_LEVELS_MAP.get(app_config.log_level, logging.INFO)
    logger = logging.getLogger("maillogsentinel")
    logger.setLevel(log_level)

    # If log_file is not set in config (is None), use NullHandler
    if app_config.log_file is None:
        logger.addHandler(logging.NullHandler())
        # Optional: Log to stderr that file logging is disabled if needed for debugging.
        # print("File logging disabled as per configuration.", file=sys.stderr)
        return logger

    # Proceed with file handler setup if log_file is configured
    logpath = Path(app_config.log_file)  # Use the actual configured path

    # Ensure parent directory for the log file exists
    try:
        logpath.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        # This specific error is critical as we can't write logs.
        print(
            f"CRITICAL: Failed to create parent directory for log file {logpath}: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        fh = logging.handlers.RotatingFileHandler(
            logpath,
            maxBytes=app_config.log_file_max_bytes,
            backupCount=app_config.log_file_backup_count,
        )
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)
    except (IOError, OSError) as e:
        # This error means we couldn't attach the file handler.
        print(
            f"CRITICAL: Failed to initialize file logging to {logpath}: {e}",
            file=sys.stderr,
        )
        # Fallback to NullHandler if file logging setup fails catastrophically
        logger.handlers = []  # Clear any potentially partially added handlers
        logger.addHandler(logging.NullHandler())
        # Depending on severity, might choose to exit or allow console-only logging.
        # For now, allow continuation with NullHandler but print critical error.
        # sys.exit(1) # Or let it continue with NullHandler
    return logger


def read_state(statedir: Path, logger: Optional[logging.Logger] = None) -> int:
    """
    Reads the last processed log offset from the state file.

    The state file (typically "state.offset") is located in `statedir`.
    It's expected to contain a single integer representing the byte offset
    up to which the main mail log file was processed in the previous run.

    Args:
        statedir: The `Path` object for the directory containing the state file.
        logger: An optional `logging.Logger` instance for warning messages if
                the state file cannot be read or parsed.

    Returns:
        The offset read from the state file as an integer.
        Returns 0 if the state file does not exist, cannot be read, or
        contains an invalid value.
    """
    state_file = statedir / STATE_FILENAME
    if not state_file.is_file():
        return 0
    try:
        return int(state_file.read_text().strip())
    except (IOError, ValueError) as e:
        if logger:
            logger.warning(
                f"Failed to read state from {state_file}: {e}. Assuming offset 0."
            )
        else:
            print(
                f"Warning: Failed to read state from {state_file}: {e}. "
                f"Assuming offset 0.",
                file=sys.stderr,
            )
        return 0


def write_state(statedir: Path, offset: int, logger: logging.Logger) -> None:
    """
    Writes the current log offset to the state file.

    The state file (typically "state.offset") is created/overwritten in `statedir`
    with the provided `offset` value. This offset represents the point up to
    which the main mail log has been processed.

    Args:
        statedir: The `Path` object for the directory where the state file
                  will be written.
        offset: The integer offset value to write to the state file.
        logger: A `logging.Logger` instance for error messages if the state
                file cannot be written.
    """
    state_file = statedir / STATE_FILENAME
    try:
        state_file.write_text(str(offset))
    except IOError as e:
        logger.error(f"Failed to write state to {state_file}: {e}")


def list_all_logs(maillog: Path) -> List[Path]:
    """
    Lists the main mail log file and its rotated versions.

    This function finds the specified main log file (`maillog`) and any
    rotated versions of it in the same directory. Rotated files are
    expected to follow common naming patterns like `maillog.0`, `maillog.1.gz`, etc.
    The list is sorted, typically meaning older logs come first.

    Args:
        maillog: The `Path` object representing the main mail log file.

    Returns:
        A list of `Path` objects, including `maillog` (if it exists and is a file)
        and all its found rotated versions that are files. The list is sorted.
    """
    files = []
    if maillog.is_file():
        files.append(maillog)
    if maillog.parent.exists():
        files.extend(sorted(list(maillog.parent.glob(maillog.name + ".*"))))
    return [p for p in files if p.is_file()]


def is_gzip(path: Path) -> bool:
    """
    Checks if a file path likely points to a gzipped file based on its extension.

    Args:
        path: The `Path` object of the file to check.

    Returns:
        True if the file name ends with ".gz", False otherwise.
    """
    return path.name.endswith(".gz")
