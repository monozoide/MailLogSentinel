# -*- coding: utf-8 -*-
"""
Handles the SQL export functionality for MailLogSentinel.

Reads data from the main CSV file, transforms it into SQL INSERT statements,
and writes it to an SQL file for later import.
"""

import csv
import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
import importlib.resources  # Added for loading bundled data

from lib.maillogsentinel.config import AppConfig  # Import AppConfig

# Constants
SQL_EXPORT_SUBDIR = "sql"
OFFSET_FILENAME = "sql_state.offset"  # Stored in state_dir
LOG_PREFIX = "sql_export"

logger = logging.getLogger(__name__)


class CSVSchemaError(ValueError):
    """Custom error for CSV schema validation issues."""

    pass


class SQLExportError(Exception):
    """Custom error for SQL export specific issues."""

    pass


def _get_logger_with_prefix(
    base_logger: logging.Logger, step_prefix: str
) -> logging.LoggerAdapter:
    """Adds a prefix to log messages."""
    # This is a simple way to add a prefix. A more robust solution might involve custom formatters.
    # For now, we can prepend to messages or use LoggerAdapter if complex context is needed.
    # Using a simple wrapper for now, or directly prefixing messages.
    # Let's assume direct prefixing in log messages for now for simplicity,
    # or use an adapter if it becomes cleaner.
    # For now, just return the base_logger and expect prefixing in the calls.
    return base_logger  # Placeholder


def load_column_mapping(mapping_file_path: Path) -> Dict[str, Dict[str, str]]:
    """
    Loads the CSV to SQL column mapping from the JSON configuration file.

    Args:
        mapping_file_path: Path to the column mapping JSON file.

    Returns:
        A dictionary representing the column mapping.

    Raises:
        FileNotFoundError: If the mapping file is not found.
        json.JSONDecodeError: If the mapping file is not valid JSON.
        SQLExportError: For other loading issues.
    """
    logger.info(f"{LOG_PREFIX}: Loading column mapping from {mapping_file_path}")
    if not mapping_file_path.is_file():
        logger.error(
            f"{LOG_PREFIX}: Column mapping file not found: {mapping_file_path}"
        )
        raise FileNotFoundError(f"Column mapping file not found: {mapping_file_path}")
    try:
        with open(mapping_file_path, "r", encoding="utf-8") as f:
            mapping = json.load(f)
        logger.info(f"{LOG_PREFIX}: Column mapping loaded successfully.")
        return mapping
    except json.JSONDecodeError as e:
        logger.error(
            f"{LOG_PREFIX}: Invalid JSON in column mapping file {mapping_file_path}: {e}"
        )
        raise
    except Exception as e:
        logger.error(
            f"{LOG_PREFIX}: Error loading column mapping file {mapping_file_path}: {e}"
        )
        raise SQLExportError(f"Could not load column mapping: {e}")


def get_current_offset(offset_file: Path) -> int:
    """
    Reads the current offset from the state file.

    Args:
        offset_file: Path to the offset file.

    Returns:
        The current offset (file position), or 0 if the file doesn't exist or is invalid.
    """
    logger.debug(f"{LOG_PREFIX}: Reading offset from {offset_file}")
    if not offset_file.is_file():
        logger.info(
            f"{LOG_PREFIX}: Offset file {offset_file} not found, starting from beginning (offset 0)."
        )
        return 0
    try:
        with open(offset_file, "r", encoding="utf-8") as f:
            offset_str = f.read().strip()
            offset = int(offset_str)
            logger.info(
                f"{LOG_PREFIX}: Successfully read offset: {offset} from {offset_file}."
            )
            return offset
    except ValueError:
        logger.warning(
            f"{LOG_PREFIX}: Invalid content in offset file {offset_file}. Resetting to 0.",
            exc_info=True,
        )
        return 0
    except Exception as e:
        logger.error(
            f"{LOG_PREFIX}: Error reading offset file {offset_file}: {e}. Resetting to 0.",
            exc_info=True,
        )
        return 0


def update_offset(offset_file: Path, new_offset: int) -> None:
    """
    Updates the offset in the state file.

    Args:
        offset_file: Path to the offset file.
        new_offset: The new offset to write.
    """
    logger.debug(f"{LOG_PREFIX}: Updating offset in {offset_file} to {new_offset}")
    try:
        offset_file.parent.mkdir(parents=True, exist_ok=True)
        with open(offset_file, "w", encoding="utf-8") as f:
            f.write(str(new_offset))
        logger.info(
            f"{LOG_PREFIX}: Successfully updated offset to {new_offset} in {offset_file}."
        )
    except Exception as e:
        logger.error(
            f"{LOG_PREFIX}: Failed to update offset file {offset_file}: {e}",
            exc_info=True,
        )
        # Depending on policy, we might want to raise an error here
        # For now, log and continue, but this could lead to reprocessing.


def validate_csv_header(
    header: List[str], column_mapping: Dict[str, Dict[str, str]], csv_path: Path
) -> None:
    """
    Validates the CSV header against the expected CSV columns in the mapping.
    Note: This is a basic check. The actual CSV file might have more columns
    than what is defined in the SQL mapping. This function checks if all
    CSV columns *needed* for the SQL export are present.

    Args:
        header: The list of column names from the CSV file header.
        column_mapping: The loaded column mapping.
        csv_path: Path to the CSV file (for logging).

    Raises:
        CSVSchemaError: If any required CSV column is missing.
    """
    logger.debug(f"{LOG_PREFIX}: Validating CSV header for {csv_path}")
    expected_csv_columns = set()
    for sql_col_info in column_mapping.values():
        csv_col_name = sql_col_info.get("csv_column_name")
        if csv_col_name and csv_col_name != "csv_id_placeholder":  # id is special
            expected_csv_columns.add(csv_col_name)

    missing_columns = expected_csv_columns - set(header)
    if missing_columns:
        msg = f"CSV file {csv_path} is missing required columns: {missing_columns}. Found header: {header}"
        logger.error(f"{LOG_PREFIX}: {msg}")
        raise CSVSchemaError(msg)
    logger.info(f"{LOG_PREFIX}: CSV header validation passed for {csv_path}.")


def escape_sql_string(value: str) -> str:
    """
    Escapes single quotes in a string for SQL insertion.

    Args:
        value: The string to escape.

    Returns:
        The escaped string.
    """
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def format_sql_value(value: Any, sql_type_def: str) -> str:
    """
    Formats a Python value into an SQL-compatible string based on its type.
    Handles None as NULL. For ENUMs, it assumes the value is already a string
    that will be quoted.

    Args:
        value: The value to format.
        sql_type_def: The SQL column definition string (e.g., "VARCHAR(50) NOT NULL", "INT UNSIGNED").

    Returns:
        SQL-formatted string representation of the value.
    """
    if (
        value is None
        or str(value).strip().lower() == "null"
        or str(value).strip() == ""
    ):
        # Allow 'DEFAULT NULL' columns to receive NULL
        if (
            "DEFAULT NULL" in sql_type_def.upper()
            or "PRIMARY KEY" not in sql_type_def.upper()
        ):  # Quick check
            return "NULL"
        # If it's a NOT NULL column without default and value is empty/None, this is an issue
        # The calling code should ideally handle this by providing a default or raising error
        # For now, if it's a string type, represent as empty string, otherwise problem.
        if "CHAR" in sql_type_def.upper() or "TEXT" in sql_type_def.upper():
            return "''"
        # This will likely cause an SQL error if the column is NOT NULL
        # Consider raising an error here if value is None and column is NOT NULL without default
        logger.warning(
            f"{LOG_PREFIX}: Null/empty value encountered for a potentially NOT NULL column: {sql_type_def} (value: {value})"
        )
        return "NULL"  # Or raise error

    sql_type_lower = sql_type_def.lower()

    if "int" in sql_type_lower or "serial" in sql_type_lower:
        try:
            return str(int(value))
        except ValueError:
            logger.warning(
                f"{LOG_PREFIX}: Could not convert '{value}' to int for SQL; using NULL. Column: {sql_type_def}"
            )
            return "NULL"  # Or raise error
    elif "datetime" in sql_type_lower or "timestamp" in sql_type_lower:
        # Assuming value is already in 'YYYY-MM-DD HH:MM:SS' format or a datetime object
        # For SQLite, it's typically a string.
        if isinstance(value, datetime.datetime):
            return f"'{value.strftime('%Y-%m-%d %H:%M:%S')}'"
        return escape_sql_string(str(value))  # Assuming pre-formatted string
    elif (
        "char" in sql_type_lower or "text" in sql_type_lower or "enum" in sql_type_lower
    ):
        return escape_sql_string(str(value))
    elif "bool" in sql_type_lower:  # SQLite stores booleans as integers 0 or 1
        return "1" if str(value).lower() in ["true", "1", "yes", "on"] else "0"
    else:  # Default to string escaping for unknown types (e.g. IP, custom types)
        return escape_sql_string(str(value))


def generate_insert_statement(
    row_dict: Dict[str, Any], table_name: str, column_mapping: Dict[str, Dict[str, str]]
) -> Optional[str]:
    """
    Generates an SQL INSERT statement from a CSV row dictionary.

    Args:
        row_dict: A dictionary representing a row from the CSV (header: value).
        table_name: The name of the SQL table to insert into.
        column_mapping: The column mapping dictionary.

    Returns:
        A string containing the SQL INSERT statement, or None if a row is skipped.
    """
    # Determine target SQL columns and their corresponding values from the row_dict
    sql_columns = []
    sql_values = []

    valid_row = True
    for sql_col_name, mapping_info in column_mapping.items():
        csv_col_name = mapping_info.get("csv_column_name")
        sql_col_def = mapping_info.get("sql_column_def", "")

        if sql_col_name == "id" and "AUTO_INCREMENT" in sql_col_def.upper():
            # Skip ID column if it's auto-incrementing; DB will handle it.
            # Alternatively, if CSV provides an ID, it should be used, and AUTO_INCREMENT removed from SQL def.
            # For now, assuming DB generates ID.
            continue

        if not csv_col_name:
            logger.warning(
                f"{LOG_PREFIX}: No CSV column specified for SQL column '{sql_col_name}'. Skipping this column."
            )
            continue

        raw_value = row_dict.get(csv_col_name)

        # Basic validation: if column is NOT NULL and has no DEFAULT, raw_value must exist
        # This is a simplified check; actual NOT NULL check depends on precise SQL definition
        if (
            raw_value is None
            and "NOT NULL" in sql_col_def.upper()
            and "DEFAULT" not in sql_col_def.upper()
            and "AUTO_INCREMENT" not in sql_col_def.upper()
        ):
            logger.error(
                f"{LOG_PREFIX}: Missing value for NOT NULL column '{sql_col_name}' (mapped from CSV '{csv_col_name}'). Row: {row_dict}. Skipping row."
            )
            valid_row = False
            break  # Skip this row

        formatted_value = format_sql_value(raw_value, sql_col_def)

        sql_columns.append(sql_col_name)
        sql_values.append(formatted_value)

    if not valid_row or not sql_columns:
        return None

    columns_str = ", ".join(sql_columns)
    values_str = ", ".join(sql_values)

    return f"INSERT INTO {table_name} ({columns_str}) VALUES ({values_str});"


def run_sql_export(config: AppConfig, output_log_level: str = "INFO") -> bool:
    """
    Main function to perform the SQL export process.

    Args:
        config: The application configuration object (AppConfig).
        output_log_level: The desired log level for console output during this process.
                         Note: Actual logging level is typically set globally by setup_logging.

    Returns:
        True if export completed successfully, False otherwise.
    """
    logger.info(f"{LOG_PREFIX}: Starting SQL export process.")

    # Use attributes directly from AppConfig instance
    csv_file_path = config.working_dir / config.csv_filename
    state_dir_path = config.state_dir
    offset_file_path = state_dir_path / OFFSET_FILENAME

    raw_mapping_path_str = config.sql_column_mapping_file_path_str
    column_mapping = None
    loaded_mapping_source = ""  # For logging

    if raw_mapping_path_str and raw_mapping_path_str.strip():
        # User has specified a path, attempt to load it.
        logger.info(
            f"{LOG_PREFIX}: User-specified column mapping file path: '{raw_mapping_path_str}'"
        )
        user_mapping_file_p = Path(raw_mapping_path_str)
        if not user_mapping_file_p.is_absolute():
            if config.config_path and config.config_path.is_file():
                user_mapping_file_p = config.config_path.parent / raw_mapping_path_str
                logger.debug(
                    f"{LOG_PREFIX}: Resolved relative user mapping path to: {user_mapping_file_p} (relative to config file {config.config_path})"
                )
            else:
                user_mapping_file_p = Path.cwd() / raw_mapping_path_str
                logger.debug(
                    f"{LOG_PREFIX}: Resolved relative user mapping path to: {user_mapping_file_p} (relative to CWD)"
                )

        final_user_path = user_mapping_file_p.resolve()
        logger.info(
            f"{LOG_PREFIX}: Attempting to load user-specified mapping file from: {final_user_path}"
        )
        try:
            column_mapping = load_column_mapping(final_user_path)
            loaded_mapping_source = f"user-specified file: {final_user_path}"
        except FileNotFoundError:
            logger.critical(
                f"{LOG_PREFIX}: User-specified column mapping file NOT FOUND: {final_user_path}. Aborting SQL export."
            )
            return False
        except json.JSONDecodeError as e:
            logger.critical(
                f"{LOG_PREFIX}: Invalid JSON in user-specified column mapping file {final_user_path}: {e}. Aborting SQL export."
            )
            return False
        except Exception as e:
            logger.critical(
                f"{LOG_PREFIX}: Error loading user-specified column mapping file {final_user_path}: {e}. Aborting SQL export.",
                exc_info=True,
            )
            return False
    else:
        # No user path specified, use bundled default.
        logger.info(
            f"{LOG_PREFIX}: No user-specific column mapping file configured, attempting to load bundled default."
        )
        try:
            with importlib.resources.files("lib.maillogsentinel.data").joinpath(
                "maillogsentinel_sql_column_mapping.json"
            ) as bundled_path:
                if (
                    not bundled_path.is_file()
                ):  # Should not happen if packaged correctly
                    logger.critical(
                        f"{LOG_PREFIX}: Bundled column mapping file not found at expected location via importlib.resources. Path: {bundled_path}. This indicates a packaging issue. Aborting."
                    )
                    return False
                column_mapping = load_column_mapping(
                    Path(bundled_path)
                )  # load_column_mapping expects a Path object
                loaded_mapping_source = f"bundled default: lib.maillogsentinel.data/maillogsentinel_sql_column_mapping.json (resolved to {bundled_path})"
        except ModuleNotFoundError:  # If lib.maillogsentinel.data is not a package
            logger.critical(
                f"{LOG_PREFIX}: Could not find the 'lib.maillogsentinel.data' package for bundled resources. This indicates a packaging issue. Aborting.",
                exc_info=True,
            )
            return False
        except (
            FileNotFoundError
        ):  # Should be caught by the bundled_path.is_file() check ideally
            logger.critical(
                f"{LOG_PREFIX}: Bundled column mapping file not found via importlib.resources. This indicates a packaging issue. Aborting.",
                exc_info=True,
            )
            return False
        except Exception as e:
            logger.critical(
                f"{LOG_PREFIX}: Error loading bundled default column mapping file: {e}. Aborting SQL export.",
                exc_info=True,
            )
            return False

    if (
        column_mapping is None
    ):  # Should have been caught by earlier returns, but as a safeguard
        logger.critical(
            f"{LOG_PREFIX}: Column mapping could not be loaded (reason unspecified, this is an unexpected state). Aborting."
        )
        return False

    logger.info(
        f"{LOG_PREFIX}: Successfully loaded column mapping from {loaded_mapping_source}."
    )

    sql_output_dir = config.working_dir / SQL_EXPORT_SUBDIR
    table_name = config.sql_target_table_name

    logger.info(f"{LOG_PREFIX}: CSV source: {csv_file_path}")
    logger.info(f"{LOG_PREFIX}: State directory: {state_dir_path}")
    logger.info(f"{LOG_PREFIX}: Offset file: {offset_file_path}")
    # No longer log final_mapping_file_path here, use loaded_mapping_source instead
    logger.info(f"{LOG_PREFIX}: SQL output directory: {sql_output_dir}")
    logger.info(f"{LOG_PREFIX}: Target SQL table name: {table_name}")

    if not csv_file_path.is_file():
        logger.error(
            f"{LOG_PREFIX}: CSV file {csv_file_path} not found. Aborting SQL export."
        )
        return False

    try:
        sql_output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.critical(
            f"{LOG_PREFIX}: Failed to create SQL output directory {sql_output_dir}: {e}. Aborting.",
            exc_info=True,
        )
        return False

    current_offset = get_current_offset(offset_file_path)
    new_offset = current_offset
    records_processed = 0
    records_exported = 0

    # Prepare output SQL file
    timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    # Original request: YYYYMMDD_HH:MM_maillogsentinel_export.sql. Colon is problematic in filenames.
    # Using YYYYMMDD_HHMM_maillogsentinel_export.sql
    timestamp_fn_str = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    sql_file_name = f"{timestamp_fn_str}_maillogsentinel_export.sql"
    sql_file_path = sql_output_dir / sql_file_name

    logger.info(
        f"{LOG_PREFIX}: Exporting new records from {csv_file_path} to {sql_file_path}"
    )

    try:
        with open(csv_file_path, "r", encoding="utf-8", newline="") as infile, open(
            sql_file_path, "w", encoding="utf-8"
        ) as outfile:

            infile.seek(current_offset)

            # Check if we are past the header (if offset is not 0)
            # If offset is 0, we read the header. If > 0, we assume header was processed.
            header = None
            if current_offset == 0:
                first_line = infile.readline()
                if not first_line:
                    logger.info(
                        f"{LOG_PREFIX}: CSV file {csv_file_path} is empty. No data to export."
                    )
                    # update_offset(offset_file_path, new_offset) # Offset remains 0
                    # It's better to remove the empty SQL file
                    outfile.close()  # Close before attempting to delete
                    sql_file_path.unlink(missing_ok=True)
                    return True

                new_offset += len(
                    first_line.encode("utf-8")
                )  # Update offset past header
                header = [h.strip() for h in first_line.strip().split(";")]
                try:
                    validate_csv_header(header, column_mapping, csv_file_path)
                except CSVSchemaError as e:
                    logger.error(
                        f"{LOG_PREFIX}: CSV header validation failed: {e}. Aborting."
                    )
                    # Consider what to do with sql_file_path - it might be empty.
                    # Clean up potentially empty or partially written SQL file
                    outfile.close()
                    sql_file_path.unlink(missing_ok=True)
                    return False
            else:
                # We don't have the header if resuming. This could be an issue if
                # validate_csv_header is crucial for every run or if column order changes.
                # For now, assume structure is stable. A robust way is to always read header
                # or store expected header hash.
                # For simplicity, we'll rely on column_mapping's csv_column_name for dict keys.
                # This means we need the header for dictreader.
                # Solution: If resuming, we still need the header. Store it or re-read it.
                # Let's re-read the header line without advancing the main processing offset.
                current_pos = infile.tell()
                infile.seek(0)
                header_line_for_resume = infile.readline()
                if not header_line_for_resume:
                    logger.error(
                        f"{LOG_PREFIX}: CSV file {csv_file_path} seems to contain no header. Aborting."
                    )
                    outfile.close()
                    sql_file_path.unlink(missing_ok=True)
                    return False
                header = [h.strip() for h in header_line_for_resume.strip().split(";")]
                infile.seek(current_pos)  # Return to where we were
                try:
                    validate_csv_header(header, column_mapping, csv_file_path)
                except CSVSchemaError as e:
                    logger.error(
                        f"{LOG_PREFIX}: CSV header validation failed on resume: {e}. Aborting."
                    )
                    outfile.close()
                    sql_file_path.unlink(missing_ok=True)
                    return False

            reader = csv.DictReader(infile, delimiter=";", fieldnames=header)

            outfile.write("BEGIN TRANSACTION;\n")

            for row in reader:
                records_processed += 1
                # Check for empty rows (e.g. just delimiters ;;;;)
                if not any(row.values()):
                    logger.debug(
                        f"{LOG_PREFIX}: Skipping empty or malformed row: {row}"
                    )
                    # Still need to update offset for this line
                    # The DictReader handles line ending consumption.
                    # To get the byte length of the line for offset:
                    # This is tricky with DictReader. Simplest is to read line by line first,
                    # then parse. For now, this part of offset update is imprecise with DictReader.
                    # A more robust offset: re-open and read line-by-line to count bytes.
                    # For now, new_offset will be updated at the end based on infile.tell().
                    continue

                try:
                    # Ensure all expected keys are present in row, map to None if not
                    # This is important if CSV is sparse or has missing optional fields
                    # Handled by row_dict.get(csv_col_name) in generate_insert_statement
                    insert_stmt = generate_insert_statement(
                        row, table_name, column_mapping
                    )
                    if insert_stmt:
                        outfile.write(insert_stmt + "\n")
                        records_exported += 1
                except Exception as e:
                    logger.error(
                        f"{LOG_PREFIX}: Error processing row: {row}. Error: {e}",
                        exc_info=True,
                    )
                    # Decide if we skip this row or abort. For now, skip.

            # After processing all available lines from the current offset
            new_offset = infile.tell()  # Get the end position

            outfile.write("COMMIT;\n")
            logger.info(
                f"{LOG_PREFIX}: SQL export process finished. Processed: {records_processed} lines. Exported: {records_exported} records."
            )

    except FileNotFoundError:  # Should be caught earlier for CSV, but for safety
        logger.critical(
            f"{LOG_PREFIX}: CSV file {csv_file_path} not found during processing. Aborting.",
            exc_info=True,
        )
        if "outfile" in locals() and not outfile.closed:
            outfile.close()
        if sql_file_path.exists():
            sql_file_path.unlink(missing_ok=True)  # cleanup
        return False
    except CSVSchemaError as e:  # Already logged by validate_csv_header
        # Cleanup already handled in validate_csv_header's calling block
        return False
    except Exception as e:
        logger.critical(
            f"{LOG_PREFIX}: Unexpected error during SQL export: {e}", exc_info=True
        )
        if "outfile" in locals() and not outfile.closed:
            outfile.close()
        if sql_file_path.exists():
            sql_file_path.unlink(missing_ok=True)  # cleanup
        return False
    finally:
        if "infile" in locals() and not infile.closed:
            # Ensure new_offset is captured if loop was exited prematurely by error after some reads
            new_offset = infile.tell()
            infile.close()
        if "outfile" in locals() and not outfile.closed:
            outfile.close()

    if records_exported == 0:
        if records_processed > 0:
            # Processed lines but exported nothing (e.g., all rows skipped due to errors/filters)
            logger.warning(
                f"{LOG_PREFIX}: Processed {records_processed} lines, but no records were actually exported. SQL file {sql_file_path} will contain only BEGIN/COMMIT. This might indicate data or mapping issues."
            )
            # Keep the file for inspection in this specific case.
        else:
            # No records exported AND no records processed (beyond header if it was the first run)
            # This includes:
            # 1. Truly empty CSV (already handled by returning after unlink if first_line is empty)
            # 2. Header-only CSV on first run (current_offset=0 initially, records_processed=0)
            # 3. Resume run with no new data lines (current_offset>0 initially, records_processed=0)
            logger.info(
                f"{LOG_PREFIX}: No records exported and no new data lines processed. Removing SQL export file: {sql_file_path}"
            )
            sql_file_path.unlink(missing_ok=True)
    else:  # records_exported > 0
        logger.info(
            f"{LOG_PREFIX}: Successfully created SQL export file: {sql_file_path} with {records_exported} records."
        )

    # Update offset only if processing was generally successful or partially successful
    # If a critical error happened early (e.g. cant load mapping), offset should not change.
    # Current logic updates offset if we reach here.
    # If CSV was not found, we return False before this.
    # If mapping failed, we return False before this.
    update_offset(offset_file_path, new_offset)

    logger.info(
        f"{LOG_PREFIX}: SQL export process complete. Final offset: {new_offset}"
    )
    return True


import tempfile
import shutil


# Test configuration class
class DummyTestConfig:
    def __init__(self, mapping_file_path_str="", base_dir_name=None):
        # Use a unique base directory for each test config instance to avoid conflicts
        self.base_dir = Path(tempfile.mkdtemp(prefix=base_dir_name or "maillog_test_"))
        self.working_dir = self.base_dir / "var/log/maillogsentinel"
        self.state_dir = self.base_dir / "var/lib/maillogsentinel"
        self.csv_filename = "maillogsentinel.csv"
        self.log_level = "DEBUG"  # For test output

        # For resolving relative paths, simulate a config file.
        # If sql_column_mapping_file_path_str is relative, it's resolved against this config_path.parent
        self.config_file_dir = self.base_dir / "etc/maillogsentinel"
        self.config_file_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config_file_dir / "dummy_test.conf"
        if not self.config_path.exists():
            with open(self.config_path, "w") as f:
                f.write("# Dummy test config\n")

        self.sql_column_mapping_file_path_str = mapping_file_path_str
        self.sql_target_table_name = "maillogsentinel_events_test"

        # Ensure directories exist
        self.working_dir.mkdir(parents=True, exist_ok=True)
        (self.working_dir / SQL_EXPORT_SUBDIR).mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def cleanup(self):
        if self.base_dir and self.base_dir.exists():
            shutil.rmtree(self.base_dir)
            # print(f"Cleaned up test directory: {self.base_dir}")


def _create_dummy_csv(
    config_obj: DummyTestConfig, headers: List[str], data_rows: List[List[str]]
):
    dummy_csv_path = config_obj.working_dir / config_obj.csv_filename
    with open(dummy_csv_path, "w", newline="", encoding="utf-8") as cf:
        writer = csv.writer(cf, delimiter=";")
        writer.writerow(headers)
        for row in data_rows:
            writer.writerow(row)
    # print(f"Created dummy CSV: {dummy_csv_path} with {len(data_rows)} data rows.")
    return dummy_csv_path


def _get_bundled_mapping_headers_for_test():
    try:
        with importlib.resources.files("lib.maillogsentinel.data").joinpath(
            "maillogsentinel_sql_column_mapping.json"
        ) as bundled_path_ref:
            # The object returned by importlib.resources.files() is a Traversable
            # We need to ensure it's treated as a Path object for load_column_mapping
            mapping = load_column_mapping(Path(bundled_path_ref))
            return sorted(
                list(
                    set(
                        info["csv_column_name"]
                        for info in mapping.values()
                        if info["csv_column_name"] != "csv_id_placeholder"
                    )
                )
            )
    except Exception as e:
        print(f"ERROR: Could not load headers from bundled mapping for test setup: {e}")
        return []


DUMMY_CSV_HEADERS = _get_bundled_mapping_headers_for_test()
if not DUMMY_CSV_HEADERS:
    DUMMY_CSV_HEADERS = [
        "server",
        "event_time",
        "ip",
        "username",
        "hostname",
        "reverse_dns_status",
        "country_code",
        "asn_number_placeholder",
        "asn_org_placeholder",
    ]
    logger.warning(f"Using fallback DUMMY_CSV_HEADERS for testing: {DUMMY_CSV_HEADERS}")


def _make_dummy_csv_data_row(custom_headers_order, values_dict):
    """Helper to create a CSV data row based on DUMMY_CSV_HEADERS global order."""
    row = []
    for header in DUMMY_CSV_HEADERS:  # Ensure consistent order
        row.append(values_dict.get(header, f"dummy_{header}"))
    return row


DUMMY_CSV_DATA_ROW_1_VALS = {
    "server": "mail.example.com",
    "event_time": "2023-10-26 10:00:00",
    "ip": "192.168.1.100",
    "username": "testuser",
    "hostname": "client.example.org",
    "reverse_dns_status": "OK",
    "country_code": "US",
    "asn_number_placeholder": "12345",
    "asn_org_placeholder": "AS-EXAMPLE Example ISP",
}
DUMMY_CSV_DATA_ROW_1 = _make_dummy_csv_data_row(
    DUMMY_CSV_HEADERS, DUMMY_CSV_DATA_ROW_1_VALS
)


def _reset_offset_file(config_obj: DummyTestConfig):
    offset_file = config_obj.state_dir / OFFSET_FILENAME
    if offset_file.exists():
        offset_file.unlink()


if __name__ == "__main__":
    # Setup basic logging for the test runner itself
    # Use a distinct logger name for test runner messages
    test_runner_logger = logging.getLogger("SQLExporterTestRunner")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    # You might want to set the main 'sql_export' logger to DEBUG for more verbose output from the module
    # logging.getLogger(LOG_PREFIX).setLevel(logging.DEBUG)

    test_runner_logger.info("Starting sql_exporter.py direct test scenarios.")

    # Keep track of test config objects for cleanup
    test_configs_to_clean = []
    all_tests_passed = True

    try:
        # --- Test Case 1: Load bundled default mapping ---
        test_runner_logger.info("\n--- Test Case 1: Load bundled default mapping ---")
        config_case1 = DummyTestConfig(
            mapping_file_path_str="", base_dir_name="maillog_test_case1_"
        )
        test_configs_to_clean.append(config_case1)
        _create_dummy_csv(config_case1, DUMMY_CSV_HEADERS, [DUMMY_CSV_DATA_ROW_1])
        _reset_offset_file(config_case1)
        success_case1 = run_sql_export(config_case1)
        if success_case1:
            test_runner_logger.info("Test Case 1 Result (Bundled Default): SUCCESS")
        else:
            test_runner_logger.error("Test Case 1 Result (Bundled Default): FAIL")
            all_tests_passed = False

        # --- Test Case 2: Load user-specified override (success) ---
        test_runner_logger.info(
            "\n--- Test Case 2: Load user-specified override (success) ---"
        )
        config_case2 = DummyTestConfig(base_dir_name="maillog_test_case2_")
        test_configs_to_clean.append(config_case2)

        custom_mapping_content_case2 = {
            "id": {
                "csv_column_name": "csv_id_placeholder",
                "sql_column_def": "INT PRIMARY KEY",
            },
            "ip_addr": {
                "csv_column_name": "ip",
                "sql_column_def": "TEXT NOT NULL",
            },  # Mapped from CSV 'ip'
            "log_time": {
                "csv_column_name": "event_time",
                "sql_column_def": "TEXT",
            },  # Mapped from CSV 'event_time'
        }
        custom_mapping_filename_case2 = "custom_test_mapping_case2.json"
        # For testing relative path resolution from config file's directory:
        custom_mapping_path_case2 = (
            config_case2.config_file_dir / custom_mapping_filename_case2
        )

        with open(custom_mapping_path_case2, "w") as f:
            json.dump(custom_mapping_content_case2, f)
        test_runner_logger.info(
            f"Created custom mapping file for Test Case 2: {custom_mapping_path_case2}"
        )

        # Provide the filename relative to config_case2.config_file_dir for the test
        config_case2.sql_column_mapping_file_path_str = custom_mapping_filename_case2

        # CSV for this test should only contain 'ip' and 'event_time' as per custom_mapping_content_case2
        _create_dummy_csv(
            config_case2, ["ip", "event_time"], [["1.2.3.4", "2023-01-01 11:00:00"]]
        )
        _reset_offset_file(config_case2)
        success_case2 = run_sql_export(config_case2)
        if success_case2:
            test_runner_logger.info(
                "Test Case 2 Result (User Override Success): SUCCESS"
            )
        else:
            test_runner_logger.error("Test Case 2 Result (User Override Success): FAIL")
            all_tests_passed = False

        # --- Test Case 3: Load user-specified override (failure - file not found) ---
        test_runner_logger.info(
            "\n--- Test Case 3: Load user-specified override (failure - file not found) ---"
        )
        # Give it a relative path that won't resolve correctly from config_case3.config_file_dir
        config_case3 = DummyTestConfig(
            mapping_file_path_str="non_existent_mapping.json",
            base_dir_name="maillog_test_case3_",
        )
        test_configs_to_clean.append(config_case3)
        _create_dummy_csv(config_case3, DUMMY_CSV_HEADERS, [DUMMY_CSV_DATA_ROW_1])
        _reset_offset_file(config_case3)
        success_case3 = run_sql_export(config_case3)
        if not success_case3:
            test_runner_logger.info(
                "Test Case 3 Result (User Override Not Found): SUCCESS (aborted as expected)"
            )
        else:
            test_runner_logger.error(
                "Test Case 3 Result (User Override Not Found): FAIL (should have aborted)"
            )
            all_tests_passed = False

        # --- Test Case 4: Load user-specified override (failure - invalid JSON) ---
        test_runner_logger.info(
            "\n--- Test Case 4: Load user-specified override (failure - invalid JSON) ---"
        )
        config_case4 = DummyTestConfig(base_dir_name="maillog_test_case4_")
        test_configs_to_clean.append(config_case4)

        invalid_mapping_filename_case4 = "invalid_custom_mapping_case4.json"
        invalid_mapping_path_case4 = (
            config_case4.config_file_dir / invalid_mapping_filename_case4
        )
        with open(invalid_mapping_path_case4, "w") as f:
            f.write("this is not valid json {{{{")
        test_runner_logger.info(
            f"Created invalid custom mapping file for Test Case 4: {invalid_mapping_path_case4}"
        )

        config_case4.sql_column_mapping_file_path_str = str(
            invalid_mapping_path_case4
        )  # Absolute path
        _create_dummy_csv(config_case4, DUMMY_CSV_HEADERS, [DUMMY_CSV_DATA_ROW_1])
        _reset_offset_file(config_case4)
        success_case4 = run_sql_export(config_case4)
        if not success_case4:
            test_runner_logger.info(
                "Test Case 4 Result (User Override Invalid JSON): SUCCESS (aborted as expected)"
            )
        else:
            test_runner_logger.error(
                "Test Case 4 Result (User Override Invalid JSON): FAIL (should have aborted)"
            )
            all_tests_passed = False

    except Exception as e:
        test_runner_logger.error(
            f"An unexpected error occurred during testing: {e}", exc_info=True
        )
        all_tests_passed = False
    finally:
        # Cleanup
        test_runner_logger.info("\n--- Cleaning up test directories ---")
        for cfg_to_clean in test_configs_to_clean:
            try:
                cfg_to_clean.cleanup()
            except Exception as e_clean:
                test_runner_logger.error(
                    f"Error cleaning up {cfg_to_clean.base_dir}: {e_clean}"
                )

    if all_tests_passed:
        test_runner_logger.info("\nAll sql_exporter.py direct test scenarios PASSED.")
    else:
        test_runner_logger.error(
            "\nOne or more sql_exporter.py direct test scenarios FAILED."
        )

    # Note: For a real test suite, use pytest and proper test functions, mocks, etc.
    # This direct run is for basic flow checking and demonstration.
