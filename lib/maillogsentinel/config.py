"""Configuration management for MailLogSentinel."""

import configparser
from pathlib import Path
import logging  # For potential logging within config loading itself
import sys  # For sys.stderr and sys.exit - ensure this is imported
from typing import Optional, Dict, Any  # Added Dict and Any for type hints

# Centralized Default Configuration
DEFAULT_CONFIG: Dict[str, Dict[str, Any]] = {
    "paths": {
        "working_dir": "/var/log/maillogsentinel",
        "state_dir": "state",  # Relative to working_dir by default
        "mail_log": "/var/log/mail.log",
        "csv_filename": "maillogsentinel.csv",
    },
    "report": {
        "email": None,
        "subject_prefix": "[MailLogSentinel]",
        "sender_override": None,
    },
    "geolocation": {
        "country_db_path": "/var/lib/maillogsentinel/country_aside.csv",
        "country_db_url": "https://raw.githubusercontent.com/sapics/ip-location-db/main/asn-country/asn-country-ipv4-num.csv",  # noqa: E501
    },
    "ASN_ASO": {
        "asn_db_path": "/var/lib/maillogsentinel/asn.csv",
        "asn_db_url": "https://raw.githubusercontent.com/sapics/ip-location-db/refs/heads/main/asn/asn-ipv4-num.csv",  # noqa: E501
    },
    "general": {
        "log_level": "INFO",
        "log_file_max_bytes": 1_000_000,
        "log_file_backup_count": 5,
        "log_file": "/var/log/maillogsentinel/maillogsentinel.log",
    },
    "dns_cache": {
        "enabled": True,
        "size": 128,
        "ttl_seconds": 3600,
    },
}


class AppConfig:
    """Handles loading and providing access to application configuration settings."""

    def __init__(self, config_path: Path, logger: Optional[logging.Logger] = None):
        # type: (...) -> None
        """
        Initializes AppConfig by loading settings from the specified config_path.

        Args:
            config_path: Path to the maillogsentinel.conf file.
            logger: Optional logger instance. If None, a default logger is used.
        """
        self.logger = logger if logger else logging.getLogger(__name__)
        self.parser = configparser.ConfigParser()
        self.config_path = config_path  # Store for reference, e.g. in error messages
        self.config_loaded_successfully = False  # Initialize attribute

        if not config_path.is_file():
            # Log this attempt, but allow continuation for setup or default generation
            self.logger.warning(
                f"Config file not found at specified path: {config_path}. "
                f"Proceeding with default values."
            )
            # Defaults will be used. Setup process should handle actual config file creation.
        else:
            try:
                self.parser.read(
                    config_path
                )  # Simplified: removed all debug prints from this block
                self.config_loaded_successfully = True
                self.logger.info(
                    f"Successfully loaded configuration from {config_path}"
                )
            except configparser.Error as e:
                self.logger.error(f"Error parsing config file {config_path}: {e}")
                # print(f"⚠️  Error parsing config file {config_path}: {e}", file=sys.stderr) # Logger handles this
                # Depending on strictness, could exit or raise. For now, will use defaults.

        # --- Load configuration settings with defaults ---
        # [paths]
        self.working_dir = Path(self._get_path("paths", "working_dir"))

        _state_dir_str = self._get_str("paths", "state_dir")
        if _state_dir_str and Path(_state_dir_str).is_absolute():
            self.state_dir = Path(_state_dir_str)
        else:  # Relative to working_dir or default 'state'
            self.state_dir = self.working_dir / (
                _state_dir_str
                if _state_dir_str
                else DEFAULT_CONFIG["paths"]["state_dir"]
            )

        self.mail_log = Path(self._get_path("paths", "mail_log"))
        self.csv_filename = self._get_str("paths", "csv_filename")

        # [report]
        self.report_email = self._get_str("report", "email")
        self.report_subject_prefix = self._get_str("report", "subject_prefix")
        self.report_sender_override = self._get_str("report", "sender_override")

        # [geolocation]
        self.country_db_path = Path(self._get_path("geolocation", "country_db_path"))
        self.country_db_url = self._get_str("geolocation", "country_db_url")

        # [ASN_ASO]
        self.asn_db_path = Path(self._get_path("ASN_ASO", "asn_db_path"))
        self.asn_db_url = self._get_str("ASN_ASO", "asn_db_url")

        # [general]
        log_level_str = self._get_str("general", "log_level")
        self.log_level = (
            log_level_str.upper()
            if log_level_str
            else DEFAULT_CONFIG["general"]["log_level"].upper()
        )
        self.log_file_max_bytes = self._get_int("general", "log_file_max_bytes")
        self.log_file_backup_count = self._get_int("general", "log_file_backup_count")

        raw_log_file_str = self._get_str("general", "log_file")
        self.log_file = None if not raw_log_file_str else Path(raw_log_file_str)

        # [dns_cache]
        self.dns_cache_enabled = self._get_bool("dns_cache", "enabled")
        self.dns_cache_size = self._get_int("dns_cache", "size")
        self.dns_cache_ttl_seconds = self._get_int("dns_cache", "ttl_seconds")

    def _get_default(self, section: str, option: str) -> Any:
        """
        Retrieves the default value for a given configuration option.

        This helper function consults the `DEFAULT_CONFIG` dictionary to find the
        predefined default value for a specific option within a section.

        Args:
            section: The name of the configuration section (e.g., "paths", "report").
            option: The name of the configuration option (e.g., "working_dir", "email").

        Returns:
            The default value for the specified option. Returns None if the option
            is not found in `DEFAULT_CONFIG`, and logs an error.
        """
        try:
            return DEFAULT_CONFIG[section][option]
        except KeyError:
            self.logger.error(
                f"Default value not found for [{section}]{option}. This is a programming error."
            )
            # Potentially raise an error or return a very generic fallback
            return None

    def _get_str(
        self,
        section: str,
        option: str,
        fallback: Optional[
            str
        ] = None,  # Fallback here is for explicit override cases, not general defaults
    ) -> Optional[str]:
        """
        Safely gets a string value from the config parser, returning fallback
        if not found or config not loaded.

        Args:
            section: The configuration section name.
            option: The configuration option name.
            fallback: An optional explicit fallback value. If not provided,
                      the default from `DEFAULT_CONFIG` is used.

        Returns:
            The configuration value as a string, or the fallback/default if
            not found or if the configuration file was not loaded.
        """
        current_fallback = (
            fallback if fallback is not None else self._get_default(section, option)
        )
        if not self.config_loaded_successfully:
            self.logger.debug(
                f"Config not loaded. Using fallback '{current_fallback}' for "
                f"[{section}]{option}."
            )
            return current_fallback

        try:
            return self.parser.get(section, option, fallback=current_fallback)
        except (
            configparser.NoSectionError,
            configparser.NoOptionError,
        ):
            self.logger.debug(
                f"Config option [{section}]{option} not found, using fallback: {current_fallback}"
            )
            return current_fallback

    def _get_path(self, section: str, option: str) -> str:  # Removed fallback: str
        """
        Safely gets a path string value from the config parser, ensuring a
        string is returned. Uses default from DEFAULT_CONFIG.

        Args:
            section: The configuration section name.
            option: The configuration option name.

        Returns:
            The configuration value as a string, suitable for use as a path.
            Uses the default from `DEFAULT_CONFIG` if the option is not found.
        """
        # _get_str will use the default from DEFAULT_CONFIG if not found
        val = self._get_str(section, option)
        # Ensure a string is returned, even if default is None (though paths shouldn't be None)
        return val if val is not None else str(self._get_default(section, option))

    def _get_int(self, section: str, option: str) -> int:  # Removed fallback: int
        """
        Safely gets an integer value from the config parser, returning default
        on error or if not found.

        Args:
            section: The configuration section name.
            option: The configuration option name.

        Returns:
            The configuration value as an integer. Returns the default value
            from `DEFAULT_CONFIG` if the option is not found, if the config
            file was not loaded, or if the value cannot be converted to an integer.
        """
        default_val = self._get_default(section, option)
        if not self.config_loaded_successfully:
            self.logger.debug(
                f"Config not loaded. Using fallback '{default_val}' for "
                f"[{section}]{option}."
            )
            return default_val  # type: ignore
        try:
            return self.parser.getint(section, option, fallback=default_val)
        except (
            configparser.NoSectionError,
            configparser.NoOptionError,
        ):  # Should be caught by fallback
            self.logger.debug(
                f"Config option [{section}]{option} not found, using fallback: {default_val}"
            )
            return default_val  # type: ignore
        except ValueError:
            self.logger.warning(
                f"Invalid integer value for [{section}]{option}. Using fallback {default_val}."
            )
            return default_val  # type: ignore

    def _get_bool(self, section: str, option: str) -> bool:  # Removed fallback: bool
        """
        Safely gets a boolean value from the config parser, returning default
        on error or if not found.

        Args:
            section: The configuration section name.
            option: The configuration option name.

        Returns:
            The configuration value as a boolean. Returns the default value
            from `DEFAULT_CONFIG` if the option is not found, if the config
            file was not loaded, or if the value is not a valid boolean string.
        """
        default_val = self._get_default(section, option)
        if not self.config_loaded_successfully:
            self.logger.debug(
                f"Config not loaded. Using fallback '{default_val}' for "
                f"[{section}]{option}."
            )
            return default_val  # type: ignore
        try:
            # Ensure that the default_val is passed correctly to getboolean
            return self.parser.getboolean(section, option, fallback=default_val)
        except (
            configparser.NoSectionError,
            configparser.NoOptionError,
        ):  # Should be caught by fallback
            self.logger.debug(
                f"Config option [{section}]{option} not found, using fallback: {default_val}"
            )
            return default_val  # type: ignore
        except (
            ValueError
        ):  # Catches if the value in config file is not a valid boolean string
            self.logger.warning(
                f"Invalid boolean value for [{section}]{option} in config file. Using fallback {default_val}."
            )
            return default_val  # type: ignore

    def get_section_dict(self, section: str) -> Dict[str, str]:
        """
        Returns a dictionary of a whole section, or empty if section not
        found or config not loaded.

        Args:
            section: The name of the configuration section to retrieve.

        Returns:
            A dictionary where keys are option names and values are their
            corresponding string values from the specified section. Returns
            an empty dictionary if the section is not found or if the
            configuration file was not loaded.
        """
        if not self.config_loaded_successfully or not self.parser.has_section(section):
            return {}
        return dict(self.parser.items(section))

    def exit_if_not_loaded(self, message="Configuration could not be loaded. Exiting."):
        """Helper method to exit if the configuration wasn't loaded successfully."""
        if not self.config_loaded_successfully:
            self.logger.critical(
                message + f" (Config path attempted: {self.config_path})"
            )
            # Keep print for cases where logger itself might not be fully set up to console
            print(
                f"CRITICAL: {message} (Config path attempted: {self.config_path})",
                file=sys.stderr,
            )
            sys.exit(1)
