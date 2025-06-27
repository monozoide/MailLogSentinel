# Usage

This section describes how to run MailLogSentinel and understand the various forms of output it generates.

## Running MailLogSentinel

How you run MailLogSentinel depends on whether you're performing a one-time manual scan or have it set up as a continuous service.

### Manual Execution

You can run MailLogSentinel directly from the command line. This is useful for testing, initial setup verification, or manually processing logs for a specific period.

```bash
sudo /usr/local/bin/maillogsentinel.py
```

*   When run directly, progress messages, errors, and summaries (based on the configured log level) will be printed to the console.
*   It will process logs according to its configuration and update the CSV report and send an email summary if configured to do so.

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
