# Usage

This section describes how to run MailLogSentinel and understand the various forms of output it generates.

## Running MailLogSentinel

How you run MailLogSentinel depends on whether you're performing a one-time manual scan or have it set up as a continuous service.

### Manual Execution

You can run MailLogSentinel directly from the command line. This is useful for testing, initial setup verification, or manually processing logs for a specific period.

```bash
sudo /usr/local/bin/maillogsentinel.py
```

You can also use various command-line options for specific tasks:
*   `--config /path/to/your/maillogsentinel.conf`: Specify a custom configuration file.
*   `--report`: Generate and send the daily email summary immediately.
*   `--reset`: Archive existing data (CSV, state file, operational log) and reset the log processing offset. The next run will process logs from the beginning.
*   `--purge`: Similar to `--reset`, but intended for a more complete fresh start by archiving all data.
*   `--sql-export`: Export new log entries from the `maillogsentinel.csv` file to SQL files. These files are stored in the directory specified by `sql_export_dir` in your configuration. This is useful for backing up data to a SQL format or for integration with other database systems.
*   `--sql-import`: Import `.sql` files (typically generated by `--sql-export`) from the `sql_export_dir` into the database configured in `maillogsentinel.conf` (under the `[database]` section). This can be used to restore data or populate a database from exported SQL files.
*   `--version`: Show the script's version number.
*   `--help`: Show a detailed help message with all available options.


*   When run directly, progress messages, errors, and summaries (based on the configured log level) will be printed to the console.
*   It will process logs according to its configuration and update the CSV report and send an email summary if configured to do so (unless a specific action like `--report` or `--sql-export` is requested, which might alter the default flow).

### SQL Export and Import Workflow

The SQL export and import features provide a robust way to manage your intrusion data, allowing for integration with external databases or for more structured long-term storage.

1.  **Configuration:**
    Before using these features, ensure your `maillogsentinel.conf` file is properly configured. This includes:
    *   The `[paths]` section for general operation.
    *   A `[database]` section, which is crucial for SQL operations. Key settings here include:
        *   `sql_export_dir`: The directory where SQL files generated by `--sql-export` will be saved.
        *   `db_type`: The type of your database (e.g., `postgresql`, `mysql`).
        *   `db_host`, `db_name`, `db_user`, `db_password`: Credentials for your database if you plan to use `--sql-import`.
    Refer to the [Configuration](Configuration.md#database-settings) page for detailed instructions on setting up these parameters.

2.  **Exporting Data to SQL Files:**
    To export new entries from your `maillogsentinel.csv` file into SQL format, run the following command:
    ```bash
    sudo /usr/local/bin/maillogsentinel.py --sql-export
    ```
    This command reads the CSV file, determines which entries haven't been exported previously (based on a state mechanism for the export), and writes them as SQL statements into one or more `.sql` files within the configured `sql_export_dir`.

3.  **Importing Data from SQL Files into a Database:**
    If you have a database set up and configured in `maillogsentinel.conf`, you can import the SQL files (generated by the export process or placed there manually) using:
    ```bash
    sudo /usr/local/bin/maillogsentinel.py --sql-import
    ```
    This command will scan the `sql_export_dir` for `.sql` files and execute them against your database, inserting the intrusion data.

    > **Important Note on Dependencies:** For the `--sql-import` functionality to work, you must have the appropriate Python database driver installed for your specific database type. For example:
    > *   PostgreSQL: `psycopg2-binary`
    > *   MySQL: `mysql-connector-python`
    > These dependencies are not installed by default with MailLogSentinel and must be installed separately in your Python environment if you intend to use the SQL import feature. The setup script might offer to install these or guide you.

### Running as a Systemd Service (Recommended for Production)

For continuous monitoring, MailLogSentinel is best run as a Systemd service. The setup process (`maillogsentinel.py --setup`) typically installs Systemd unit files (`maillogsentinel.service` and `maillogsentinel-report.service`, along with their corresponding timers).

*   **`maillogsentinel.service`**: This service is responsible for the core log parsing and data extraction. It's usually triggered by a timer (e.g., `maillogsentinel.timer`) to run periodically (e.g., every hour).
*   **`maillogsentinel-report.service`**: This service handles the generation and sending of email summary reports. It's also triggered by a timer (e.g., `maillogsentinel-report.timer`) and typically runs less frequently than the extraction service (e.g., once a day).

**Common Systemd Commands:**

*   **Start a service immediately:**
    ```bash
    sudo systemctl start maillogsentinel.service
    sudo systemctl start maillogsentinel-report.service
    ```
*   **Enable a service to start on boot (and its timer):**
    ```bash
    sudo systemctl enable maillogsentinel.timer
    sudo systemctl enable maillogsentinel-report.timer
    sudo systemctl start maillogsentinel.timer  # Start the timer immediately
    sudo systemctl start maillogsentinel-report.timer # Start the timer immediately
    ```
*   **Check the status of a service:**
    ```bash
    sudo systemctl status maillogsentinel.service
    sudo systemctl status maillogsentinel-report.service
    ```
*   **View logs for a service (output is directed to the Systemd journal):**
    ```bash
    sudo journalctl -u maillogsentinel.service
    sudo journalctl -u maillogsentinel-report.service
    # To follow logs in real-time:
    sudo journalctl -f -u maillogsentinel.service
    ```

## Understanding the Output

MailLogSentinel produces several types of output:

### 1. Email Reports

If configured, MailLogSentinel sends email summaries detailing detected intrusion attempts. An example email might look like this:

```
##################################################
### MailLogSentinel v1.0.5-A                     ###
### Extraction interval : hourly                 ###
### Report at 2025-05-28 10:30                   ###
### Server: 192.168.1.10   (mail.example.com)    ###
##################################################

Total attempts today: 55

Top 10 failed authentications today:
   1. user@example.com     111.222.11.22  host.attacker.cn   CN  5 times
   2. admin@example.com    22.33.44.55    another.host.ru    RU  4 times
   ...

Top 10 Usernames today:
   1. user@example.com         10 times
   ...
  
Top 10 countries today:
   1. CN             6 times
   ...

Top 10 ASO today:
   1. CHINA UNICOM China169 Backbone       2 times
   ...

Top 10 ASN today:
   1. 4837        2 times
   ...

--- Reverse DNS Lookup Failure Summary ---
Total failed reverse lookups today: 26
Breakdown by error type:
  Errno 1 : 24  (Host name not found)
  Errno 2 :  2  (Server failed to respond)

Total CSV file size: 241.1K
Total CSV lines:     3613

Please see attached: maillogsentinel.csv

For more details and documentation, visit: https://github.com/monozoide/MailLogSentinel/wiki
```

The email includes:
*   A header with the MailLogSentinel version, reporting interval, report time, and server identifier.
*   Summary statistics like total attempts.
*   Top 10 lists for failed authentications (IP, hostname, country, count), targeted usernames, source countries, ASOs, and ASNs.
*   A summary of reverse DNS lookup failures.
*   Information about the attached CSV file.
*   The CSV report itself is usually attached to the email.

### 2. CSV File (`intrusions.csv` or configured name)

MailLogSentinel appends details of each detected failed SASL authentication attempt to a CSV file. This file is typically located in the `working_dir` specified in the configuration (e.g., `/var/log/maillogsentinel/maillogsentinel.csv`).

**CSV Structure:**

| server | date               | ip             | user        | hostname           | reverse_dns_status | country_code | asn          | aso                  |
| :----- | :----------------- | :------------- | :---------- | :----------------- | :----------------- | :----------- | :----------- | :------------------- |
| srv01  | 2025-05-17 11:13   | 105.73.190.126 | office@me   | null               | Errno 1            | CN           | 134810       | AAPT Limited         |
| srv01  | 2025-05-17 12:05   | 81.30.107.24   | contribute  | mail.example.com   | OK                 | US           | 9808         | China Mobile         |
| ...    | ...                | ...            | ...         | ...                | ...                | ...          | ...          | ...                  |

*   **server**: The hostname or identifier of the server where the log originated.
*   **date**: Timestamp of the failed authentication attempt.
*   **ip**: The source IP address of the failed attempt.
*   **user**: The username that was used in the failed login attempt.
*   **hostname**: The hostname associated with the source IP, if reverse DNS lookup was successful. 'null' or an error code if it failed.
*   **reverse_dns_status**: Status of the reverse DNS lookup (e.g., 'OK', 'Errno 1' for host not found, 'Errno 2' for server failure, 'Errno 4' for temporary failure).
*   **country_code**: Two-letter ISO country code for the source IP (e.g., CN, US, RU).
*   **asn**: Autonomous System Number associated with the source IP.
*   **aso**: Autonomous System Organization associated with the source IP.

This CSV file serves as a persistent log of all detected intrusion attempts and can be used for historical analysis, incident response, or importing into other security tools.

### 3. Operational Logs

MailLogSentinel maintains its own operational logs, which record its activities, errors, and debug information.

*   **Location:** Defined by the `log_file` setting in `maillogsentinel.conf` (e.g., `/var/log/maillogsentinel/maillogsentinel.log`).
*   **Content:** These logs show when MailLogSentinel starts and stops, which log files it's processing, any errors encountered (e.g., issues reading files, sending emails, DNS lookups), and detailed debug messages if the `log_level` is set to `DEBUG`.
*   **Rotation:** Log rotation (max size and backup count) is handled as configured in the `[general]` section of `maillogsentinel.conf`.

**Example Log Entries:**
```
2025-05-29 00:00:00,315 INFO === Start of MailLogSentinel v1.0.4-B ===
2025-05-29 00:00:00,315 DEBUG Files to process: [PosixPath('/var/log/mail.log')], starting from offset: 1198314
2025-05-29 00:00:00,315 INFO Processing /var/log/mail.log (gzip: False)
2025-05-29 00:00:00,351 DEBUG Reverse lookup failed for IP 206.231.72.34: Errno 4
2025-05-29 00:00:01,938 INFO === End of MailLogSentinel execution ===
2025-05-29 00:05:00,123 INFO === Report Generation Started ===
2025-05-29 00:05:01,567 INFO Report sent from sender@example.com to security-team@example.org
2025-05-29 00:05:01,568 INFO === Report Generation Finished ===
```

These logs are invaluable for troubleshooting MailLogSentinel itself. If it's run as a Systemd service, this output will also be captured by the Systemd journal (`journalctl`).

### 4. Setup Logs (`maillogsentinel_setup.log`)

During the initial setup (`maillogsentinel.py --setup`), a detailed log of the setup process is saved to `maillogsentinel_setup.log` in the directory where the setup command was executed. This log records all actions taken, such as directory creation, file copying, and Systemd unit installation, and can be helpful for diagnosing any setup-related problems.

By understanding these different outputs, administrators can effectively monitor their Postfix server's security and manage MailLogSentinel's operation.
