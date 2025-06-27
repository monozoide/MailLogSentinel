# API Documentation

While MailLogSentinel is primarily a command-line tool and a set of scripts, its components are structured in a way that some parts can be understood as providing an API, especially for internal use or for potential extension. The auto-generated API documentation from the source code provides a more granular view.

**Generated API Docs:**

For detailed information on specific modules, classes, and functions, refer to the Sphinx-generated API documentation located in the `docs/api/` directory of the repository. The main entry point is typically `docs/api/maillogsentinel.html`.

This includes documentation for modules such as:
*   `lib.maillogsentinel.config`: Handles configuration loading.
*   `lib.maillogsentinel.parser`: Contains logic for parsing log entries.
*   `lib.maillogsentinel.report`: Manages report generation and email sending.
*   `lib.maillogsentinel.dns_utils`: Provides DNS lookup functionalities.
*   `lib.maillogsentinel.utils`: Contains various utility functions.
*   `bin.ipinfo`: Provides the `IPInfoManager` class for IP lookups.

## How to Use the "API" (Internal Components)

If you were to extend MailLogSentinel or use its components in another Python project, you would typically import classes and functions from its library (`lib/maillogsentinel/`) and `bin/` (for `ipinfo`).

### Example: Using `IPInfoManager`

The `ipinfo.py` script provides the `IPInfoManager` class, which can be used to look up IP address information.

```python
import logging
from bin.ipinfo import IPInfoManager # Assuming ipinfo.py is in your PYTHONPATH

# Basic logger for the manager
logger = logging.getLogger("ipinfo_example")
logging.basicConfig(level=logging.INFO)

# Initialize with paths to your databases (and optionally URLs for updates)
# These paths would typically come from your AppConfig in a real scenario
manager = IPInfoManager(
    country_db_path="/path/to/your/country_aside.csv",
    asn_db_path="/path/to/your/asn.csv",
    country_db_url="https://example.com/country.csv", # Replace with actual URLs
    asn_db_url="https://example.com/asn.csv",         # Replace with actual URLs
    logger=logger
)

# Optional: Update databases if needed
# manager.update_databases()

# Lookup information for an IP
ip_address = "8.8.8.8"
info = manager.lookup_ip_info(ip_address)

if info:
    print(f"IP Address: {info.get('ip')}")
    print(f"Country Code: {info.get('country_code')}")
    print(f"ASN: {info.get('asn')}")
    print(f"ASO: {info.get('aso')}")
else:
    print(f"Information not found for {ip_address}")

```

### Example: Using Configuration Loading

The `AppConfig` class from `lib.maillogsentinel.config` loads and provides access to configuration settings.

```python
import logging
from pathlib import Path
from lib.maillogsentinel.config import AppConfig

logger = logging.getLogger("config_example")
logging.basicConfig(level=logging.INFO)

# Path to your configuration file
config_path = Path("/etc/maillogsentinel.conf") # Or your custom path

app_config = AppConfig(config_path, logger=logger)

if app_config.config_loaded_successfully:
    print(f"Mail log path: {app_config.mail_log}")
    print(f"Report email: {app_config.report_email}")
    print(f"Working directory: {app_config.working_dir}")
else:
    print(f"Failed to load config from {config_path}, using defaults.")
    # You can still access default values
    print(f"Default mail log path: {app_config.mail_log}")

```

## Key Modules and Their Purpose

*   **`lib/maillogsentinel/config.py` (`AppConfig` class):**
    *   Loads configuration from `maillogsentinel.conf`.
    *   Provides attributes to access various configuration parameters (paths, email settings, log levels, etc.).
    *   Handles default values if the configuration file is missing or an option is not specified.

*   **`lib/maillogsentinel/parser.py` (`extract_entries` function):**
    *   The core log processing function.
    *   Takes file paths, an offset, and various helper objects/functions (logger, IP info manager, DNS lookup function).
    *   Reads log lines, identifies relevant entries (failed SASL authentications).
    *   Extracts details, performs enrichment (reverse DNS, GeoIP).
    *   Writes data to the CSV file.
    *   Returns the new offset after processing.

*   **`lib/maillogsentinel/report.py` (`send_report` function):**
    *   Reads data from the CSV file.
    *   Generates summary statistics (top attackers, etc.).
    *   Formats the email content (text and HTML).
    *   Attaches the CSV file.
    *   Sends the email using `smtplib`.

*   **`lib/maillogsentinel/dns_utils.py` (`reverse_lookup`, `initialize_dns_cache`):**
    *   `initialize_dns_cache`: Sets up an in-memory cache for DNS results based on `AppConfig`.
    *   `reverse_lookup`: Performs a reverse DNS lookup for an IP address, using the cache to avoid redundant queries. Handles common lookup errors.

*   **`lib/maillogsentinel/utils.py`:**
    *   Contains various helper functions for:
        *   Path setup (`setup_paths`).
        *   Logging setup (`setup_logging`).
        *   State management (`read_state`, `write_state`).
        *   File type checks (`is_gzip`).
        *   Permissions checks (`check_root`).

*   **`bin/ipinfo.py` (`IPInfoManager` class):**
    *   Manages loading, updating, and querying local IP geolocation (country) and ASN/ASO databases.
    *   `update_databases()`: Downloads new database files.
    *   `lookup_ip_info(ip_address_str)`: Returns a dictionary with country code, ASN, and ASO for the given IP.

## Extending MailLogSentinel

If you plan to extend MailLogSentinel, understanding these components and how they interact is crucial. For instance:

*   To add a new type of report output, you might modify `report.py` or add a new reporting module that uses data from the CSV or directly from `parser.py`.
*   To support a different log format, the primary changes would be within `parser.py`.
*   To integrate with a different notification system, `report.py`'s email sending logic would be the place to adapt.

Always refer to the source code and the auto-generated API documentation for the most up-to-date details on function signatures, class methods, and internal logic.
