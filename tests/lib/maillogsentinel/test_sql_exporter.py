# -*- coding: utf-8 -*-
"""
Tests for the maillogsentinel.sql_exporter module.
"""
import pytest
import json
from pathlib import Path
import datetime

from lib.maillogsentinel.sql_exporter import (
    load_column_mapping,
    get_current_offset,
    update_offset,
    validate_csv_header,
    escape_sql_string,
    format_sql_value,
    generate_insert_statement,
    run_sql_export,
    CSVSchemaError,
)
from lib.maillogsentinel.config import AppConfig  # For mocking config

# --- Fixtures ---


# Helper class for mocking datetime.datetime.now()
class MockFixedDatetime(datetime.datetime):
    _now_val = None
    _now_vals_list = []
    _pop_from_list = False

    @classmethod
    def set_now_values(cls, dt_vals_list):
        cls._now_vals_list = list(dt_vals_list)  # Store a copy
        cls._pop_from_list = True
        if cls._now_vals_list:
            cls._now_val = cls._now_vals_list.pop(0)  # Set first value immediately

    @classmethod
    def set_now(cls, dt_val):
        cls._pop_from_list = False
        cls._now_val = dt_val

    @classmethod
    def now(cls, tz=None):
        if cls._pop_from_list:
            if cls._now_vals_list:  # If there are more values in the list to pop
                current_val = cls._now_val
                cls._now_val = cls._now_vals_list.pop(0)
                return current_val
            elif cls._now_val is not None:  # Last value from the list
                current_val = cls._now_val
                # Optionally clear _now_val or keep returning last if list exhausted
                # For this test, let's assume list covers all calls or we'd set it again
                return current_val
            else:  # List exhausted and _now_val might be None if list was empty
                # Fallback or raise, for safety. For test, should be pre-populated.
                raise ValueError(
                    "MockFixedDatetime: now() called but no values in list and _now_val is None."
                )

        if cls._now_val is None:
            raise ValueError("MockFixedDatetime: now() called but _now_val not set.")
        return cls._now_val


from unittest.mock import patch, MagicMock

@pytest.fixture
def mock_logger():
    """Fixture to mock the logger."""
    with patch("lib.maillogsentinel.sql_exporter.logger") as mock_log:
        yield mock_log


@pytest.fixture
def temp_file(tmp_path):
    """Creates a temporary file and returns its Path object."""
    return tmp_path / "temp_file.txt"


@pytest.fixture
def sample_column_mapping_content():
    return {
        "id": {
            "sql_column_def": "INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY",
            "csv_column_name": "csv_id_placeholder",
        },
        "server": {
            "sql_column_def": "VARCHAR(50) NOT NULL",
            "csv_column_name": "server",
        },
        "event_time": {
            "sql_column_def": "DATETIME NOT NULL",
            "csv_column_name": "event_time",
        },
        "ip": {"sql_column_def": "VARCHAR(45) NOT NULL", "csv_column_name": "ip"},
        "username": {
            "sql_column_def": "VARCHAR(100) NOT NULL",
            "csv_column_name": "username",
        },
        "hostname": {
            "sql_column_def": "VARCHAR(255) DEFAULT NULL",
            "csv_column_name": "hostname",
        },
        "status": {
            "sql_column_def": "ENUM('OK', 'FAIL') NOT NULL",
            "csv_column_name": "status_col",
        },
    }


@pytest.fixture
def sample_column_mapping_file(tmp_path, sample_column_mapping_content):
    file_path = tmp_path / "mapping.json"
    with open(file_path, "w") as f:
        json.dump(sample_column_mapping_content, f)
    return file_path


@pytest.fixture
def mock_app_config(tmp_path, sample_column_mapping_file):
    """Mocks AppConfig for testing run_sql_export."""
    mock_config = AppConfig(
        config_path=(tmp_path / "dummy_maillogsentinel.conf")
    )  # Path for config itself

    # Path attributes
    mock_config.working_dir = tmp_path / "workdir"
    mock_config.state_dir = tmp_path / "statedir"
    mock_config.csv_filename = "test_maillog.csv"

    # Create dummy directories
    mock_config.working_dir.mkdir(parents=True, exist_ok=True)
    mock_config.state_dir.mkdir(parents=True, exist_ok=True)
    (mock_config.working_dir / "sql").mkdir(parents=True, exist_ok=True)

    # SQL export specific settings
    mock_config.sql_column_mapping_file_path_str = str(sample_column_mapping_file)
    mock_config.sql_target_table_name = "test_log_events"

    # Create a dummy main config file for mapping path resolution
    if not mock_config.config_path.exists():
        mock_config.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(mock_config.config_path, "w") as cf:
            cf.write("# Dummy config for test\n")
            cf.write(
                f"[sql_export_settings]\ncolumn_mapping_file = {sample_column_mapping_file.name}\n"
            )  # Relative to this dummy config
            # The actual sample_column_mapping_file is in tmp_path, so this makes it relative to tmp_path

    # Ensure the mapping file is placed relative to the dummy config if that's how it's resolved
    # The current fixture for sample_column_mapping_file places it directly in tmp_path.
    # If sql_column_mapping_file_path_str is relative, it needs to be relative to config_path.parent
    # Let's adjust sql_column_mapping_file_path_str to be just the filename if sample_column_mapping_file is in config_path.parent
    # For this test, sample_column_mapping_file is at tmp_path / "mapping.json"
    # And mock_config.config_path is tmp_path / "dummy_maillogsentinel.conf"
    # So, if sql_column_mapping_file_path_str is "mapping.json", it should resolve correctly.
    mock_config.sql_column_mapping_file_path_str = sample_column_mapping_file.name

    return mock_config


# --- Tests for helper functions ---


def test_escape_sql_string():
    assert escape_sql_string("test") == "'test'"
    assert escape_sql_string("test's") == "'test''s'"
    assert escape_sql_string("") == "''"
    assert escape_sql_string(None) == "NULL"  # As per current implementation


def test_format_sql_value():
    assert format_sql_value("hello", "VARCHAR(50)") == "'hello'"
    assert format_sql_value(123, "INT UNSIGNED") == "123"
    assert format_sql_value(None, "VARCHAR(50) DEFAULT NULL") == "NULL"
    assert (
        format_sql_value("", "VARCHAR(50) DEFAULT NULL") == "NULL"
    )  # Changed from "''" based on updated logic
    assert format_sql_value("test's", "TEXT") == "'test''s'"
    dt = datetime.datetime(2023, 1, 1, 10, 30, 0)
    assert format_sql_value(dt, "DATETIME") == "'2023-01-01 10:30:00'"
    assert (
        format_sql_value("2023-01-01 10:30:00", "DATETIME") == "'2023-01-01 10:30:00'"
    )
    assert format_sql_value(True, "BOOLEAN") == "1"  # SQLite stores as 0 or 1
    assert format_sql_value(False, "BOOLEAN") == "0"
    assert format_sql_value("OK", "ENUM('OK', 'FAIL')") == "'OK'"
    # Test for potentially problematic None conversion for NOT NULL without default
    # Current logic might return "NULL" which could be an issue, or "''" for text.
    # This depends on strictness desired.
    assert (
        format_sql_value(None, "INT NOT NULL") == "NULL"
    )  # This would likely fail on DB if column is NOT NULL


def test_load_column_mapping_success(
    sample_column_mapping_file, sample_column_mapping_content
):
    mapping = load_column_mapping(sample_column_mapping_file)
    assert mapping == sample_column_mapping_content


def test_load_column_mapping_file_not_found(tmp_path, mock_logger):
    with pytest.raises(FileNotFoundError):
        load_column_mapping(tmp_path / "nonexistent.json")
    mock_logger.error.assert_called_once()


def test_load_column_mapping_invalid_json(tmp_path, mock_logger):
    invalid_json_file = tmp_path / "invalid.json"
    with open(invalid_json_file, "w") as f:
        f.write("{'key': 'value',}")  # Invalid JSON (trailing comma, single quotes)
    with pytest.raises(json.JSONDecodeError):
        load_column_mapping(invalid_json_file)
    mock_logger.error.assert_called_once()


def test_get_and_update_offset(temp_file, mock_logger):
    # Test get_current_offset when file doesn't exist
    assert get_current_offset(temp_file) == 0
    mock_logger.info.assert_any_call(
        f"sql_export: Offset file {temp_file} not found, starting from beginning (offset 0)."
    )

    # Test update_offset
    update_offset(temp_file, 12345)
    mock_logger.info.assert_any_call(
        f"sql_export: Successfully updated offset to 12345 in {temp_file}."
    )
    assert temp_file.read_text() == "12345"

    # Test get_current_offset when file exists
    assert get_current_offset(temp_file) == 12345
    mock_logger.info.assert_any_call(
        f"sql_export: Successfully read offset: 12345 from {temp_file}."
    )

    # Test with invalid content in offset file
    temp_file.write_text("not_an_integer")
    assert get_current_offset(temp_file) == 0
    mock_logger.warning.assert_any_call(
        f"sql_export: Invalid content in offset file {temp_file}. Resetting to 0.",
        exc_info=True,
    )


def test_validate_csv_header_success(sample_column_mapping_content):
    header = [
        "server",
        "event_time",
        "ip",
        "username",
        "hostname",
        "status_col",
        "extra_col",
    ]
    # No exception should be raised
    validate_csv_header(header, sample_column_mapping_content, Path("dummy.csv"))


def test_validate_csv_header_missing_column(sample_column_mapping_content, mock_logger):
    header = ["server", "event_time", "ip"]  # Missing username, hostname, status_col
    with pytest.raises(CSVSchemaError) as excinfo:
        validate_csv_header(header, sample_column_mapping_content, Path("dummy.csv"))

    assert "is missing required columns" in str(excinfo.value)
    # Check specific missing columns (order in set might vary)
    assert "username" in str(excinfo.value)
    assert "status_col" in str(excinfo.value)
    mock_logger.error.assert_called_once()


def test_generate_insert_statement(sample_column_mapping_content):
    row_dict = {
        "server": "mail.example.com",
        "event_time": "2023-01-01 12:00:00",
        "ip": "192.168.1.1",
        "username": "testuser",
        "hostname": "client.local",
        "status_col": "OK",
        "extra_col": "ignored",  # This column is not in mapping
    }
    table_name = "logs"

    # Adjust mapping for this test: "id" is auto-increment, so it shouldn't be in INSERT
    # "status" is ENUM

    # Note: The order of columns in the output SQL depends on the iteration order of sample_column_mapping_content.
    # For robust testing, parse the generated SQL or compare sets of (column, value) pairs.
    # For simplicity here, we rely on dict iteration order (Python 3.7+).
    # A better way:
    # stmt = generate_insert_statement(row_dict, table_name, sample_column_mapping_content)
    # assert "INSERT INTO logs" in stmt
    # assert "server" in stmt and "'mail.example.com'" in stmt
    # ... and so on for all fields.

    # Simplified check based on current implementation:
    # Need to ensure the output columns are ordered as per dict keys in sample_column_mapping_content
    # Python 3.7+ dicts preserve insertion order. Let's assume that for the test.
    # The 'id' column will be skipped due to AUTO_INCREMENT.
    # The columns will be: server, event_time, ip, username, hostname, status

    # Reconstruct the expected string based on the order in sample_column_mapping_content, skipping 'id'

    # This test is a bit fragile due to string matching.
    # A more robust test would parse the SQL.
    stmt = generate_insert_statement(
        row_dict, table_name, sample_column_mapping_content
    )
    assert stmt is not None
    assert (
        "INSERT INTO logs (server, event_time, ip, username, hostname, status) VALUES ('mail.example.com', '2023-01-01 12:00:00', '192.168.1.1', 'testuser', 'client.local', 'OK');"
        in stmt
    )


def test_generate_insert_statement_with_none_for_nullable(
    sample_column_mapping_content,
):
    row_dict = {
        "server": "mail.example.com",
        "event_time": "2023-01-01 12:00:00",
        "ip": "192.168.1.1",
        "username": "testuser",
        "hostname": None,  # Nullable field
        "status_col": "FAIL",
    }
    table_name = "logs"
    stmt = generate_insert_statement(
        row_dict, table_name, sample_column_mapping_content
    )
    assert stmt is not None
    assert "hostname" in stmt
    assert "NULL" in stmt  # Check that hostname is NULL
    assert (
        "'mail.example.com', '2023-01-01 12:00:00', '192.168.1.1', 'testuser', NULL, 'FAIL'"
        in stmt
    )


def test_generate_insert_statement_skip_auto_increment_id(
    sample_column_mapping_content,
):
    row_dict = {
        "csv_id_placeholder": "should_be_ignored",
        "server": "s1",
        "event_time": "2023-01-01 12:00:00",
        "ip": "192.168.1.1",
        "username": "testuser",
        "hostname": "client.local",  # Can be None if column is nullable
        "status_col": "OK",
    }
    stmt = generate_insert_statement(row_dict, "logs", sample_column_mapping_content)
    assert stmt is not None
    assert "id" not in stmt.lower()  # 'id' column should be skipped
    assert "csv_id_placeholder" not in stmt.lower()


# More tests for run_sql_export would go here, mocking file operations, AppConfig, etc.
# These are more like integration tests for the function.


def test_run_sql_export_no_csv_file(mock_app_config, mock_logger):
    # Ensure CSV file does not exist
    csv_file = mock_app_config.working_dir / mock_app_config.csv_filename
    if csv_file.exists():
        csv_file.unlink()

    assert not run_sql_export(mock_app_config)
    mock_logger.error.assert_any_call(
        f"sql_export: CSV file {csv_file} not found. Aborting SQL export."
    )


def test_run_sql_export_empty_csv(
    mock_app_config, mock_logger, sample_column_mapping_content
):
    csv_file = mock_app_config.working_dir / mock_app_config.csv_filename
    # Create an empty CSV (or just header)
    header_cols = [
        v["csv_column_name"]
        for k, v in sample_column_mapping_content.items()
        if k != "id"
    ]
    csv_file.write_text(";".join(header_cols) + "\n")

    offset_file = mock_app_config.state_dir / "sql_state.offset"
    if offset_file.exists():
        offset_file.unlink()  # Start fresh

    assert run_sql_export(mock_app_config)  # Should be true, but export 0 records

    # Check that an SQL file was created (and is likely empty or just BEGIN/COMMIT)
    # and then removed because it was empty.
    # This requires inspecting the log or checking that no .sql file remains (if empty ones are deleted).
    # The current implementation deletes empty .sql files.
    sql_output_dir = mock_app_config.working_dir / "sql"
    exported_sql_files = list(sql_output_dir.glob("*.sql"))
    assert not exported_sql_files  # Empty file should have been deleted

    # Offset should be updated to the size of the header
    assert offset_file.exists()
    assert int(offset_file.read_text()) == len(
        ((";".join(header_cols) + "\n").encode("utf-8"))
    )


def test_run_sql_export_basic_flow(
    mock_app_config, sample_column_mapping_content, mock_logger
):
    with patch("lib.maillogsentinel.sql_exporter.datetime.datetime", MockFixedDatetime):
        csv_file = mock_app_config.working_dir / mock_app_config.csv_filename
        offset_file = mock_app_config.state_dir / "sql_state.offset"
        sql_output_dir = mock_app_config.working_dir / "sql"

        if offset_file.exists():
            offset_file.unlink()

        # Prepare CSV data
        # Get header from mapping, skipping placeholder for auto-increment ID
        csv_headers = [
            info["csv_column_name"]
            for _, info in sample_column_mapping_content.items()
            if info["csv_column_name"] != "csv_id_placeholder"
        ]

        csv_content = ";".join(csv_headers) + "\n"
        csv_content += "srv1;2023-01-01 10:00:00;1.1.1.1;user1;host1.com;OK\n"
        csv_content += "srv2;2023-01-02 11:00:00;2.2.2.2;user2;host2.net;FAIL\n"
        csv_file.write_text(csv_content)

        # Set specific times for each run
        # First run
        MockFixedDatetime.set_now(datetime.datetime(2023, 1, 1, 10, 0, 0))
        assert run_sql_export(mock_app_config)
        exported_files1 = list(sql_output_dir.glob("*.sql"))
        assert len(exported_files1) == 1
        expected_filename1 = sql_output_dir / "20230101_1000_maillogsentinel_export.sql"
        assert expected_filename1 in exported_files1
        sql_content1 = expected_filename1.read_text()
        assert (
            "INSERT INTO test_log_events (server, event_time, ip, username, hostname, status) VALUES ('srv1', '2023-01-01 10:00:00', '1.1.1.1', 'user1', 'host1.com', 'OK');"
            in sql_content1
        )
        assert (
            "INSERT INTO test_log_events (server, event_time, ip, username, hostname, status) VALUES ('srv2', '2023-01-02 11:00:00', '2.2.2.2', 'user2', 'host2.net', 'FAIL');"
            in sql_content1
        )
        assert "BEGIN TRANSACTION;" in sql_content1
        assert "COMMIT;" in sql_content1

        original_offset = len(csv_content.encode("utf-8"))
        assert int(offset_file.read_text()) == original_offset

        # Second run (no new data)
        MockFixedDatetime.set_now(datetime.datetime(2023, 1, 1, 10, 1, 0))  # Different time
        assert run_sql_export(mock_app_config)
        current_sql_files = list(sql_output_dir.glob("*.sql"))
        assert len(current_sql_files) == 1
        assert expected_filename1 in current_sql_files

        # Add new data
        new_line = "srv3;2023-01-03 12:00:00;3.3.3.3;user3;host3.org;OK\n"
        with open(csv_file, "a") as f:
            f.write(new_line)

        # Third run
        MockFixedDatetime.set_now(
            datetime.datetime(2023, 1, 1, 10, 2, 0)
        )  # Different time again
        assert run_sql_export(mock_app_config)
        exported_files3 = list(sql_output_dir.glob("*.sql"))
        assert len(exported_files3) == 2
        expected_filename3 = sql_output_dir / "20230101_1002_maillogsentinel_export.sql"
        assert expected_filename3 in exported_files3
        sql_content3 = expected_filename3.read_text()
        assert (
            "INSERT INTO test_log_events (server, event_time, ip, username, hostname, status) VALUES ('srv3', '2023-01-03 12:00:00', '3.3.3.3', 'user3', 'host3.org', 'OK');"
            in sql_content3
        )
        assert "BEGIN TRANSACTION;" in sql_content3
        assert "COMMIT;" in sql_content3

        assert int(offset_file.read_text()) == original_offset + len(
            new_line.encode("utf-8")
        )
        mock_logger.info.assert_any_call(
            "sql_export: SQL export process finished. Processed: 1 lines. Exported: 1 records."
        )


# (More tests for run_sql_export: mapping file issues, header validation on resume, etc.)
