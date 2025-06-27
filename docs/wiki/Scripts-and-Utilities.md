# Scripts and Utilities

MailLogSentinel comes with a few core scripts and utilities that handle its main functionalities.

## `maillogsentinel.py` (Main Script)

This is the heart of the MailLogSentinel application. It's responsible for:

*   **Log Parsing and Analysis:**
    *   Reading Postfix mail logs (e.g., `/var/log/mail.log`).
    *   Incrementally parsing logs, keeping track of the last processed position (offset) to avoid redundant work.
    *   Detecting log rotation and truncation.
    *   Extracting relevant information from log entries related to failed SASL authentications (server, date, IP, user, client hostname).
*   **Data Enrichment:**
    *   Performing reverse DNS lookups for client IP addresses.
    *   Utilizing `ipinfo.py` to get geolocation (country) and ASN/ASO details for IP addresses.
*   **Reporting:**
    *   Appending extracted intrusion data to a CSV file (e.g., `maillogsentinel.csv`).
    *   Generating and sending email summary reports if configured.
*   **Setup and Configuration:**
    *   Providing an interactive or automated setup process (`--setup` flag) to configure paths, email settings, and Systemd services.
    *   Loading configuration from `maillogsentinel.conf`.
*   **State Management:**
    *   Managing its operational state (like log offset) in a state file.
    *   Offering `--reset` and `--purge` options for managing data and state.
*   **Operational Logging:**
    *   Writing its own detailed operational logs.

**Key Command-Line Arguments:**

*   `--config /path/to/conf`: Specify a configuration file.
*   `--report`: Generate and send an email report, then exit.
*   `--setup`: Run the initial setup routine. Can be combined with `--config` for automated setup or run alone for interactive setup.
*   `--reset`: Reset the application state (log offset) and archive existing data.
*   `--purge`: Archive all data and logs, effectively a more comprehensive reset.
*   `--version`: Display the script version.

The script uses various modules from the `lib/maillogsentinel/` directory for specific tasks like configuration loading (`config.py`), log parsing (`parser.py`), report generation (`report.py`), DNS utilities (`dns_utils.py`), and general utilities (`utils.py`).

## `ipinfo.py` (IP Information Utility)

`ipinfo.py` is a command-line tool and can also be used as a library component by `maillogsentinel.py`. Its primary functions are:

*   **IP Geolocation and ASN Lookup:**
    *   Takes an IP address as input.
    *   Looks up its country of origin, Autonomous System Number (ASN), and Autonomous System Organization (ASO).
*   **Local Database Management:**
    *   Uses local CSV database files for IP-to-country and IP-to-ASN/ASO mappings.
    *   Default database paths are often within `/var/lib/maillogsentinel/` (e.g., `country_aside.csv`, `asn.csv`) or `~/.ipinfo/` when run standalone.
    *   The paths and download URLs for these databases can be configured in `maillogsentinel.conf` or passed as command-line arguments to `ipinfo.py`.
*   **Database Updates:**
    *   Provides a mechanism to download and update these local databases from specified URLs (e.g., from `sapics/ip-location-db` on GitHub).

**Key Command-Line Arguments for Standalone Use:**

*   `--update`: Download or update both IP databases.
*   `ip_address`: The IP address to look up (e.g., `8.8.8.8`).
*   `--country-db-path /path/to/db`: Specify the path for the country database.
*   `--asn-db-path /path/to/db`: Specify the path for the ASN database.
*   `--country-db-url <URL>`: Specify the URL for the country database.
*   `--asn-db-url <URL>`: Specify the URL for the ASN database.
*   `--data-dir /path/to/dir`: Specify a general directory for database files.
*   `--config /path/to/maillogsentinel.conf`: Load database paths and URLs from the MailLogSentinel configuration file.

When `maillogsentinel.py` runs, it initializes an `IPInfoManager` instance from this utility to perform lookups.

## `tools/log_anonymizer.py` (Log Anonymizer)

This script is a utility designed to anonymize sensitive data within log files, particularly Postfix mail logs. This is useful for:

*   Sharing log excerpts for troubleshooting or support without exposing private information.
*   Archiving logs while minimizing privacy concerns.

**Functionality:**

*   Replaces identifiable information such as IP addresses, hostnames, email addresses (local parts and domains separately), server names, and SASL usernames with generic placeholders (e.g., `anon_ip_1`, `anon_hostname_1`, `anon_user_1@anon_hostname_2`).
*   Maintains consistency: the same original value will always be replaced by the same anonymized placeholder within a single run.
*   It uses a series of regular expressions to find and replace sensitive data. The order and specificity of these patterns are important to ensure correct anonymization.
*   The script reads an input log file and writes the anonymized content to a new output file.

**Key Command-Line Arguments:**

*   `-i, --input-file <filepath>`: (Required) The input log file to anonymize.
*   `-o, --output-file <filepath>`: (Required) The path where the anonymized log will be saved.
*   `--temp-dir <directory>`: Optional temporary directory for processing.
*   `--config <filepath>`: (Currently informational) Path to a configuration file for anonymization rules (future use).
*   `--log-level [DEBUG|INFO|WARNING|ERROR|CRITICAL]`: Sets the logging verbosity for the anonymizer script itself.
*   `--script-log-file <filepath>`: Optional file to save the anonymizer's execution logs.

This tool is standalone and not directly used by the main `maillogsentinel.py` script during its normal operation. It's provided as a helpful utility for users.

These three scripts form the core toolkit of MailLogSentinel, providing log analysis, IP information services, and data anonymization capabilities.
