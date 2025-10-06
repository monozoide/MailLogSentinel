import pytest
from pathlib import Path

# import configparser # No longer used
from unittest.mock import MagicMock, patch

from lib.maillogsentinel.config import AppConfig, DEFAULT_CONFIG

# Default values used in AppConfig, for easier reference in tests
# DEFAULTS dictionary is now removed, DEFAULT_CONFIG from the module will be used.


@pytest.fixture
def mock_logger():
    return MagicMock()


def create_config_file(tmp_path: Path, content: str) -> Path:
    config_file = tmp_path / "test_maillogsentinel.conf"
    config_file.write_text(content)
    return config_file


def test_appconfig_no_config_file(tmp_path: Path, mock_logger: MagicMock):
    """Test AppConfig initialization when config file does not exist."""
    non_existent_path = tmp_path / "non_existent.conf"
    config = AppConfig(non_existent_path, logger=mock_logger)

    assert not config.config_loaded_successfully
    mock_logger.warning.assert_called_with(
        f"Config file not found at specified path: {non_existent_path}. "
        f"Proceeding with default values."
    )

    # Check a few default values
    assert config.working_dir == Path(DEFAULT_CONFIG["paths"]["working_dir"])
    assert (
        config.state_dir
        == Path(DEFAULT_CONFIG["paths"]["working_dir"])
        / DEFAULT_CONFIG["paths"]["state_dir"]
    )
    assert config.log_level == DEFAULT_CONFIG["general"]["log_level"]
    assert config.report_email is DEFAULT_CONFIG["report"]["email"]
    assert config.dns_cache_enabled == DEFAULT_CONFIG["dns_cache"]["enabled"]


def test_appconfig_valid_config_file(tmp_path: Path, mock_logger: MagicMock):
    """Test AppConfig with a valid configuration file."""
    content = """
[paths]
working_dir = /tmp/mywork
state_dir = my_state
mail_log = /var/log/custom_mail.log

[report]
email = test@example.com
subject_prefix = [TEST]

[general]
log_level = DEBUG
log_file_max_bytes = 2000000

[dns_cache]
enabled = false
size = 256
ttl_seconds = 1800
"""
    config_file = create_config_file(tmp_path, content)
    config = AppConfig(config_file, logger=mock_logger)

    assert config.config_loaded_successfully
    mock_logger.info.assert_called_with(
        f"Successfully loaded configuration from {config_file}"
    )

    assert config.working_dir == Path("/tmp/mywork")
    assert config.state_dir == Path("/tmp/mywork/my_state")  # Relative to working_dir
    assert config.mail_log == Path("/var/log/custom_mail.log")
    assert config.report_email == "test@example.com"
    assert config.report_subject_prefix == "[TEST]"
    assert config.log_level == "DEBUG"
    assert config.log_file_max_bytes == 2000000
    assert not config.dns_cache_enabled
    assert config.dns_cache_size == 256
    assert config.dns_cache_ttl_seconds == 1800


def test_appconfig_state_dir_absolute(tmp_path: Path, mock_logger: MagicMock):
    """Test AppConfig when state_dir is an absolute path."""
    content = """
[paths]
working_dir = /tmp/work
state_dir = /tmp/abs_state
"""
    config_file = create_config_file(tmp_path, content)
    config = AppConfig(config_file, logger=mock_logger)
    assert config.state_dir == Path("/tmp/abs_state")


def test_appconfig_invalid_config_file_parsing_error(
    tmp_path: Path, mock_logger: MagicMock
):
    """Test AppConfig with a config file that has parsing errors."""
    content = """
this_is_not_a_valid_line_outside_a_section
[paths]
working_dir = /tmp/valid_path
"""
    config_file = create_config_file(tmp_path, content)
    config = AppConfig(config_file, logger=mock_logger)

    assert not config.config_loaded_successfully
    mock_logger.error.assert_called_once()
    # Check that it fell back to defaults
    assert config.working_dir == Path(DEFAULT_CONFIG["paths"]["working_dir"])


# Tests for getter methods
def test_get_str_not_loaded(tmp_path: Path, mock_logger: MagicMock):
    config = AppConfig(tmp_path / "dummy.conf", logger=mock_logger)  # Config not loaded
    assert config._get_str("section", "option", "fallback_val") == "fallback_val"
    mock_logger.debug.assert_any_call(
        "Config not loaded. Using fallback 'fallback_val' for [section]option."
    )


def test_get_int_not_loaded(tmp_path: Path, mock_logger: MagicMock):
    config = AppConfig(tmp_path / "dummy.conf", logger=mock_logger)
    # We need to mock DEFAULT_CONFIG for this specific test case or ensure 'section'/'option' exists with a known default
    # For simplicity here, let's assume we are testing against a known default if we add it to DEFAULT_CONFIG
    # Or, more practically, test that it calls _get_default and returns its result.
    # For now, let's adjust the test to reflect that it will try to fetch from DEFAULT_CONFIG
    # and what the expected fallback logging would be.
    # Let's add a temporary entry to DEFAULT_CONFIG for testing this specific scenario or mock _get_default
    with patch.dict(DEFAULT_CONFIG, {"section": {"option": 12345}}, clear=True):
        assert config._get_int("section", "option") == 12345
        mock_logger.debug.assert_any_call(
            "Config not loaded. Using fallback '12345' for [section]option."
        )


def test_get_bool_not_loaded(tmp_path: Path, mock_logger: MagicMock):
    config = AppConfig(tmp_path / "dummy.conf", logger=mock_logger)
    with patch.dict(
        DEFAULT_CONFIG, {"section": {"option": False}}, clear=True
    ):  # Example with False
        assert config._get_bool("section", "option") is False
        mock_logger.debug.assert_any_call(
            "Config not loaded. Using fallback 'False' for [section]option."
        )


def test_get_int_value_error(tmp_path: Path, mock_logger: MagicMock):
    """Test _get_int when config value is not a valid integer."""
    content = """
[general]
log_file_max_bytes = not_an_int
"""
    config_file = create_config_file(tmp_path, content)
    config = AppConfig(config_file, logger=mock_logger)

    assert (
        config.log_file_max_bytes == DEFAULT_CONFIG["general"]["log_file_max_bytes"]
    )  # Falls back to default
    mock_logger.warning.assert_called_with(
        f"Invalid integer value for [general]log_file_max_bytes. "
        f"Using fallback {DEFAULT_CONFIG['general']['log_file_max_bytes']}."
    )


def test_get_bool_value_error(tmp_path: Path, mock_logger: MagicMock):
    """Test _get_bool when config value is not a valid boolean."""
    content = """
[dns_cache]
enabled = not_a_bool
"""
    config_file = create_config_file(tmp_path, content)
    config = AppConfig(config_file, logger=mock_logger)

    assert (
        config.dns_cache_enabled == DEFAULT_CONFIG["dns_cache"]["enabled"]
    )  # Falls back to default
    mock_logger.warning.assert_called_with(
        f"Invalid boolean value for [dns_cache]enabled in config file. "  # Modified message to reflect new logic in config.py
        f"Using fallback {DEFAULT_CONFIG['dns_cache']['enabled']}."
    )


def test_get_section_dict(tmp_path: Path, mock_logger: MagicMock):
    content = """
[report]
email = test@example.com
subject_prefix = [TEST]
"""
    config_file = create_config_file(tmp_path, content)
    config = AppConfig(config_file, logger=mock_logger)

    report_section = config.get_section_dict("report")
    assert report_section == {"email": "test@example.com", "subject_prefix": "[TEST]"}


def test_get_section_dict_missing_section(tmp_path: Path, mock_logger: MagicMock):
    content = """
[paths]
working_dir = /tmp
"""
    config_file = create_config_file(tmp_path, content)
    config = AppConfig(config_file, logger=mock_logger)
    assert config.get_section_dict("non_existent_section") == {}


def test_get_section_dict_config_not_loaded(tmp_path: Path, mock_logger: MagicMock):
    config = AppConfig(tmp_path / "dummy.conf", logger=mock_logger)  # Config not loaded
    assert config.get_section_dict("any_section") == {}


@patch("sys.exit")
def test_exit_if_not_loaded_when_not_loaded(
    mock_sys_exit: MagicMock, tmp_path: Path, mock_logger: MagicMock
):
    """
    Test exit_if_not_loaded calls sys.exit if config_loaded_successfully is False.
    """
    config_path = tmp_path / "non_existent.conf"
    config = AppConfig(
        config_path, logger=mock_logger
    )  # This will set config_loaded_successfully to False

    assert not config.config_loaded_successfully

    custom_message = "Test exit message."
    config.exit_if_not_loaded(message=custom_message)

    mock_logger.critical.assert_called_with(
        custom_message + f" (Config path attempted: {config_path})"
    )
    mock_sys_exit.assert_called_once_with(1)


@patch("sys.exit")
def test_exit_if_not_loaded_when_loaded(
    mock_sys_exit: MagicMock, tmp_path: Path, mock_logger: MagicMock
):
    """
    Test exit_if_not_loaded does not call sys.exit if
    config_loaded_successfully is True.
    """
    content = """
[paths]
working_dir = /tmp/work
"""
    config_file = create_config_file(tmp_path, content)
    config = AppConfig(
        config_file, logger=mock_logger
    )  # This will set config_loaded_successfully to True

    assert config.config_loaded_successfully

    config.exit_if_not_loaded()
    mock_sys_exit.assert_not_called()


# Example of testing a specific default when a value is missing
def test_appconfig_missing_specific_value_falls_back_to_default(
    tmp_path: Path, mock_logger: MagicMock
):
    content = """
[paths]
# working_dir is missing, should use default
state_dir = my_state
"""
    config_file = create_config_file(tmp_path, content)
    config = AppConfig(config_file, logger=mock_logger)

    assert config.working_dir == Path(
        DEFAULT_CONFIG["paths"]["working_dir"]
    )  # Falls back to default
    assert (
        config.state_dir == Path(DEFAULT_CONFIG["paths"]["working_dir"]) / "my_state"
    )  # Uses default working_dir for relative path


def test_appconfig_new_sections_defaults(tmp_path: Path, mock_logger: MagicMock):
    """Test AppConfig loads default values for new SQL-related sections."""
    non_existent_path = tmp_path / "non_existent_for_new_defaults.conf"
    config = AppConfig(non_existent_path, logger=mock_logger)

    assert not config.config_loaded_successfully

    # Check defaults for [sqlite_database]
    assert config.sqlite_db_type == DEFAULT_CONFIG["sqlite_database"]["db_type"]
    assert config.sqlite_db_path == Path(
        DEFAULT_CONFIG["sqlite_database"]["db_path"]
    )  # Path conversion happens
    assert config.sqlite_user == DEFAULT_CONFIG["sqlite_database"]["user"]
    assert (
        config.sqlite_password_hash
        == DEFAULT_CONFIG["sqlite_database"]["password_hash"]
    )
    assert config.sqlite_salt == DEFAULT_CONFIG["sqlite_database"]["salt"]

    # Check defaults for [sql_export_systemd]
    assert (
        config.sql_export_frequency == DEFAULT_CONFIG["sql_export_systemd"]["frequency"]
    )

    # Check defaults for [sql_import_systemd]
    assert (
        config.sql_import_frequency == DEFAULT_CONFIG["sql_import_systemd"]["frequency"]
    )

    # Check defaults for [sql_export_settings]
    assert (
        config.sql_column_mapping_file_path_str
        == DEFAULT_CONFIG["sql_export_settings"]["column_mapping_file"]
    )
    assert (
        config.sql_target_table_name
        == DEFAULT_CONFIG["sql_export_settings"]["table_name"]
    )


def test_appconfig_new_sections_from_file(tmp_path: Path, mock_logger: MagicMock):
    """Test AppConfig loads values from file for new SQL-related sections."""
    content = """
[sqlite_database]
db_type = test_sqlite
db_path = /tmp/test.db
user = test_user
# password_hash and salt would be set by setup, not typically in a raw config by user for SQLite

[sql_export_systemd]
frequency = every 10 minutes

[sql_import_systemd]
frequency = every 15 minutes

[sql_export_settings]
column_mapping_file = /etc/maillog_map.json
table_name = my_event_log
"""
    config_file = create_config_file(tmp_path, content)
    config = AppConfig(config_file, logger=mock_logger)

    assert config.config_loaded_successfully

    # Check values from file for [sqlite_database]
    assert config.sqlite_db_type == "test_sqlite"
    assert config.sqlite_db_path == Path("/tmp/test.db")
    assert config.sqlite_user == "test_user"
    # password_hash and salt will be empty string if not in file, as per _get_str default behavior with DEFAULT_CONFIG
    assert (
        config.sqlite_password_hash
        == DEFAULT_CONFIG["sqlite_database"]["password_hash"]
    )
    assert config.sqlite_salt == DEFAULT_CONFIG["sqlite_database"]["salt"]

    # Check values from file for [sql_export_systemd]
    assert config.sql_export_frequency == "every 10 minutes"

    # Check values from file for [sql_import_systemd]
    assert config.sql_import_frequency == "every 15 minutes"

    # Check values from file for [sql_export_settings]
    assert config.sql_column_mapping_file_path_str == "/etc/maillog_map.json"
    assert config.sql_target_table_name == "my_event_log"


def test_appconfig_log_source_defaults(tmp_path: Path, mock_logger: MagicMock):
    """Test that log_source defaults are used when no config file exists."""
    non_existent_path = tmp_path / "non_existent.conf"
    app_config = AppConfig(non_existent_path, logger=mock_logger)
    
    # Check log_source defaults
    assert app_config.log_source_type == "auto"
    assert app_config.journald_unit == "postfix.service"


def test_appconfig_log_source_from_file(tmp_path: Path, mock_logger: MagicMock):
    """Test that log_source configuration is loaded from file."""
    content = """
[log_source]
source_type = journald
journald_unit = mail.service

[paths]
working_dir = /custom/working
mail_log = /custom/mail.log
"""
    config_file = create_config_file(tmp_path, content)
    app_config = AppConfig(config_file, logger=mock_logger)

    assert app_config.config_loaded_successfully
    
    # Check that new log_source section is loaded
    assert app_config.log_source_type == "journald"
    assert app_config.journald_unit == "mail.service"
    
    # Check that existing sections still work
    assert app_config.working_dir == Path("/custom/working")
    assert app_config.mail_log == Path("/custom/mail.log")
