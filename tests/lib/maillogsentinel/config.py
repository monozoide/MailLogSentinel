"""Configuration management for MailLogSentinel."""

import configparser
from pathlib import Path
import logging  # For potential logging within config loading itself
import sys  # For sys.stderr and sys.exit - ensure this is imported
from typing import Optional  # Added for type hints


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
                f"Config file not found at specified path: {config_path}. Proceeding with default values."
            )
            # Defaults will be used. Setup process should handle actual config file creation.
        else:
            try:
                self.parser.read(config_path)
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
        self.working_dir = Path(
            self._get_path("paths", "working_dir", "/var/log/maillogsentinel")
        )

        _state_dir_str = self._get_str("paths", "state_dir", "state")
        if _state_dir_str and Path(_state_dir_str).is_absolute():
            self.state_dir = Path(_state_dir_str)
        else:  # Relative to working_dir or default 'state'
            self.state_dir = self.working_dir / _state_dir_str

        self.mail_log = Path(self._get_path("paths", "mail_log", "/var/log/mail.log"))
        self.csv_filename = self._get_str(
            "paths", "csv_filename", "maillogsentinel.csv"
        )

        # [report]
        self.report_email = self._get_str(
            "report", "email", None
        )  # None makes it easy to check if set
        self.report_subject_prefix = self._get_str(
            "report", "subject_prefix", "[MailLogSentinel]"
        )
        self.report_sender_override = self._get_str(
            "report", "sender_override", None
        )  # None means not overridden

        # [geolocation]
        self.country_db_path = Path(
            self._get_path(
                "geolocation",
                "country_db_path",
                "/var/lib/maillogsentinel/country_aside.csv",
            )
        )
        self.country_db_url = self._get_str(
            "geolocation",
            "country_db_url",
            "https://raw.githubusercontent.com/ipinfo/data/master/geo/country_aside.csv",
        )

        # [ASN_ASO]
        self.asn_db_path = Path(
            self._get_path("ASN_ASO", "asn_db_path", "/var/lib/maillogsentinel/asn.csv")
        )
        self.asn_db_url = self._get_str(
            "ASN_ASO",
            "asn_db_url",
            "https://raw.githubusercontent.com/ipinfo/data/master/asn/asn.csv",
        )

        # [general]
        self.log_level = self._get_str("general", "log_level", "INFO").upper()
        self.log_file_max_bytes = self._get_int(
            "general", "log_file_max_bytes", 1_000_000
        )
        self.log_file_backup_count = self._get_int(
            "general", "log_file_backup_count", 5
        )

        # [dns_cache]
        self.dns_cache_enabled = self._get_bool("dns_cache", "enabled", True)
        self.dns_cache_size = self._get_int("dns_cache", "size", 128)
        self.dns_cache_ttl_seconds = self._get_int("dns_cache", "ttl_seconds", 3600)

    def _get_str(
        self, section: str, option: str, fallback: Optional[str] = None
    ) -> Optional[str]:
        """Safely gets a string value from the config parser, returning fallback if not found or config not loaded."""
        if not self.config_loaded_successfully:
            self.logger.debug(
                f"Config not loaded. Using fallback '{fallback}' for [{section}]{option}."
            )
            return fallback
        try:
            return self.parser.get(section, option, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError):
            self.logger.debug(
                f"Config option [{section}]{option} not found, using fallback: {fallback}"
            )
            return fallback

    def _get_path(self, section: str, option: str, fallback: str) -> str:
        """Safely gets a path string value from the config parser, ensuring a string is returned."""
        val = self._get_str(section, option, fallback=fallback)
        return val if val is not None else fallback

    def _get_int(self, section: str, option: str, fallback: int) -> int:
        """Safely gets an integer value from the config parser, returning fallback on error or if not found."""
        if not self.config_loaded_successfully:
            self.logger.debug(
                f"Config not loaded. Using fallback '{fallback}' for [{section}]{option}."
            )
            return fallback
        try:
            return self.parser.getint(section, option, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError):
            self.logger.debug(
                f"Config option [{section}]{option} not found, using fallback: {fallback}"
            )
            return fallback
        except ValueError:
            self.logger.warning(
                f"Invalid integer value for [{section}]{option}. Using fallback {fallback}."
            )
            return fallback

    def _get_bool(self, section: str, option: str, fallback: bool) -> bool:
        """Safely gets a boolean value from the config parser, returning fallback on error or if not found."""
        if not self.config_loaded_successfully:
            self.logger.debug(
                f"Config not loaded. Using fallback '{fallback}' for [{section}]{option}."
            )
            return fallback
        try:
            return self.parser.getboolean(section, option, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError):
            self.logger.debug(
                f"Config option [{section}]{option} not found, using fallback: {fallback}"
            )
            return fallback
        except ValueError:
            self.logger.warning(
                f"Invalid boolean value for [{section}]{option}. Using fallback {fallback}."
            )
            return fallback

    def get_section_dict(self, section: str) -> dict:
        """Returns a dictionary of a whole section, or empty if section not found or config not loaded."""
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
