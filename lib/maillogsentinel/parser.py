"""
Handles the parsing of mail log files for MailLogSentinel.

This module is responsible for iterating through specified log files (including
rotated and gzipped ones), extracting relevant SASL (Simple Authentication and
Security Layer) authentication failure entries, and writing them to a CSV file.
It manages log rotation by tracking file offsets and handles different file
formats.
"""

import csv
import gzip
from datetime import datetime
from pathlib import Path
from typing import (
    Optional,
    List,
    Callable,
)
import logging

# Add bin directory to sys.path to allow importing ipinfo
# sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "bin")) # Removed for cleaner path management
import ipinfo

# Local imports
from lib.maillogsentinel.log_utils import (
    _parse_log_line,
)  # Import the centralized function


# Constants are now in log_utils.py
# Regex optimization considerations remain valid for log_utils.py.

# _parse_log_line is now imported from log_utils.py


def extract_entries(
    filepaths: List[Path],
    maillog_path_obj: Path,
    csvpath_param: str,
    logger: logging.Logger,
    ip_info_mgr: Optional[
        "ipinfo.ipinfo.IPInfoManager"
    ],  # Stylistic change: single quotes
    reverse_lookup_func: Callable,
    is_gzip_func: Callable,
    offset: int = 0,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> int:
    """
    Extracts SASL authentication failure entries from log files and appends them to a CSV file.

    This function processes a list of log files, including the main mail log and
    its rotated versions. It reads each file, identifies lines corresponding to
    SASL authentication failures using `_parse_log_line` from `log_utils`,
    and writes the extracted data as a new row in the specified CSV file.

    It handles log rotation for the main mail log file (`maillog_path_obj`) by
    using an offset. If the current file size is smaller than the last known
    offset, it assumes rotation and resets the offset to 0. For other (rotated)
    files, it always reads from the beginning.

    Gzipped files (identified by `is_gzip_func`) are supported.

    Args:
        filepaths: A list of `Path` objects representing the log files to process.
                   This list should typically be ordered from oldest to newest,
                   with the current main log file last.
        maillog_path_obj: The `Path` object for the main, currently active mail log file.
                          Used for offset tracking and rotation detection.
        csvpath_param: The path (string) to the CSV file where extracted entries
                       will be written. A header is added if the file doesn't exist.
        logger: A `logging.Logger` instance for logging progress and errors.
        ip_info_mgr: An optional `ipinfo.IPInfoManager` instance passed to
                     `_parse_log_line` for IP geolocation lookups.
        reverse_lookup_func: A callable passed to `_parse_log_line` for
                             performing reverse DNS lookups.
        is_gzip_func: A callable that takes a `Path` object and returns `True`
                      if the file is gzipped, `False` otherwise.
        offset: The initial offset (integer) to start reading from in the
                `maillog_path_obj`. Defaults to 0.
        progress_callback: An optional callable that is invoked with
                           (files_processed_count, total_files) during processing
                           to update progress.

    Returns:
        The new offset (integer) to be used for the next incremental read of
        `maillog_path_obj`. This is typically the size of `maillog_path_obj`
        after processing it, or the previous offset if `maillog_path_obj`
        was not processed or rotated.
    """
    # curr_off is initialized per file inside the loop.
    new_off = offset  # Will be updated only if maillog_path_obj is processed
    csv_file_path = Path(csvpath_param)
    header = not csv_file_path.is_file()
    current_year = datetime.now().year

    total_files = len(filepaths)
    files_processed_count = 0

    # Initial call to progress_callback to show 0% if there are files
    if progress_callback and total_files > 0:
        progress_callback(0, total_files)

    with csv_file_path.open("a", encoding="utf-8", newline="") as csvf:
        writer = csv.writer(csvf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        if header:
            writer.writerow(
                [
                    "server",
                    "date",
                    "ip",
                    "user",
                    "hostname",
                    "reverse_dns_status",
                    "country_code",
                    "asn",
                    "aso",
                ]
            )

        for idx, path_obj in enumerate(filepaths):
            logger.info(f"Processing file: {path_obj.name} ({idx + 1}/{total_files})")
            try:
                try:
                    path_size = path_obj.stat().st_size
                except OSError as e:
                    logger.error(f"Could not get size of {path_obj}: {e}")
                    # Skip this file for parsing, but count it as "processed" for progress
                    # The 'finally' block below will handle incrementing files_processed_count
                    # and calling the progress_callback.
                    continue

                # Initialize curr_off for the current file
                current_file_offset = 0
                if path_obj == maillog_path_obj:
                    current_file_offset = (
                        offset  # Use the passed offset for the main log
                    )
                    if path_size < current_file_offset:
                        logger.info(
                            f"Rotation detected for {path_obj.name}, resetting offset {current_file_offset} -> 0"
                        )
                        current_file_offset = 0
                # For rotated files, current_file_offset remains 0, meaning they are read from the start.

                is_gzipped_file = is_gzip_func(path_obj)
                file_open_mode = "rt"  # Text mode for both gzip and regular files

                if is_gzipped_file:
                    with gzip.open(
                        path_obj, mode=file_open_mode, encoding="utf-8", errors="ignore"
                    ) as fobj:
                        for line in fobj:
                            parsed_data = _parse_log_line(
                                line,
                                current_year,
                                logger,
                                ip_info_mgr,
                                reverse_lookup_func,
                            )
                            if parsed_data:
                                writer.writerow(list(parsed_data.values()))
                else:  # Not gzipped
                    with path_obj.open(
                        mode=file_open_mode, encoding="utf-8", errors="ignore"
                    ) as fobj:
                        # Only seek if it's the main log file and being read incrementally
                        if path_obj == maillog_path_obj:
                            logger.debug(
                                f"Incremental read of {path_obj.name} from offset {current_file_offset}"
                            )
                            fobj.seek(current_file_offset)
                        else:
                            logger.debug(
                                f"Reading rotated file {path_obj.name} from beginning"
                            )

                        for line in fobj:
                            parsed_data = _parse_log_line(
                                line,
                                current_year,
                                logger,
                                ip_info_mgr,
                                reverse_lookup_func,
                            )
                            if parsed_data:
                                writer.writerow(list(parsed_data.values()))

                        # Update offset only FROM the main log file
                        if path_obj == maillog_path_obj:
                            new_off = fobj.tell()
                            logger.debug(
                                f"Offset for {path_obj.name} updated to {new_off}"
                            )

            except (IOError, OSError) as e:
                logger.error(f"Error processing file {path_obj.name}: {e}")
            # Keep a broader exception for truly unexpected issues within the loop, but log type
            except Exception as e:
                logger.error(
                    f"Unexpected error of type {type(e).__name__} processing {path_obj.name}: {e}",
                    exc_info=True,
                )
            finally:
                files_processed_count += 1
                if progress_callback:
                    progress_callback(files_processed_count, total_files)

    # If filepaths was empty, new_off remains its initial value (offset).
    # If maillog_path_obj was not in filepaths (e.g. only rotated logs processed after initial run),
    # new_off also remains its initial value from the last successful processing of maillog_path_obj.
    logger.info(
        f"Finished processing all {total_files} specified file(s). Final offset for {maillog_path_obj.name} is {new_off}."
    )
    return new_off
