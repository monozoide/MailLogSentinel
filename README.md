# MailLogSentinel

<p align="center">
  <img src="img/banner-logo.png" alt="MailLogSentinel Banner" height="100">
</p>

> **MailLogSentinel** – Your vigilant guard for Postfix/Dovecot mail server authentication logs.

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.x](https://img.shields.io/badge/python-3.6+-brightgreen.svg)](https://www.python.org/downloads/)
[![Issues Welcome](https://img.shields.io/badge/Issues-Welcome-brightgreen)](https://github.com/cryptozoide/MailLogSentinel/issues)

---

## Table of Contents

1.  [Introduction](#introduction)
2.  [Features](#features)
3.  [Prerequisites](#prerequisites)
4.  [Installation](#installation)
5.  [Configuration](#configuration)
    *   [Main Configuration File](#main-configuration-file)
    *   [Interactive Setup (`--setup`)](#interactive-setup---setup)
6.  [Usage (Command-Line Arguments)](#usage-command-line-arguments)
7.  [Output Files](#output-files)
8.  [Email Reports](#email-reports)
9.  [Automated Execution (Systemd)](#automated-execution-systemd)
10. [Contributing](#contributing)
11. [License](#license)
12. [Support](#support)

---

## 1. Introduction

**MailLogSentinel** is a Python-based tool designed to monitor and analyze SASL (Simple Authentication and Security Layer) authentication logs from Postfix/Dovecot mail servers. Its primary goal is to detect and report potential intrusion attempts by identifying failed login events. It operates using Python 3 and standard libraries, making it lightweight and easy to integrate into existing server environments.

---

## 2. Features

*   **SASL Log Parsing:** Extracts relevant information (server, date, IP address, username, client hostname) from Postfix/Dovecot authentication logs.
*   **Incremental Processing:** Efficiently processes logs by remembering the last read offset, making it suitable for frequent execution (e.g., via cron or Systemd timers).
*   **Log Rotation Handling:** Correctly handles rotated log files, including gzipped archives (e.g., `mail.log.1`, `mail.log.2.gz`).
*   **CSV Output:** Stores detected authentication attempts in a structured CSV file (default: `maillogsentinel.csv`).
*   **Reverse DNS Lookups:** Performs reverse DNS lookups for the source IP addresses of authentication attempts to provide client hostnames.
    *   **DNS Caching:** Includes a configurable LRU (Least Recently Used) cache for DNS lookup results to improve performance and reduce redundant external DNS queries.
*   **Daily Email Reports:** Generates and sends daily email summaries that include:
    *   Key statistics (total attempts, top offenders).
    *   The full CSV data as an email attachment.
*   **Interactive Setup (`--setup`):**
    *   A user-friendly command-line wizard for initial configuration.
    *   Guides users through setting up paths, email details, logging levels, and DNS cache settings.
    *   Generates example Systemd service and timer unit files, tailored to the user's environment, for easy automation of log processing and reporting.
    *   Can assist with directory creation and permission settings (requires root/sudo privileges).
*   **Automatic Setup Logging:** All console output generated during the interactive setup process (`--setup`) is automatically saved to `maillogsentinel_setup.log` in the current working directory from which the script was executed.
*   **Data Management Options:**
    *   `--reset`: Archives existing data files (CSV, state file, script's operational log) to a timestamped backup directory and then resets the log processing offset. This is useful for starting fresh with log analysis without losing historical data.
    *   `--purge`: Similar to `--reset`, archives all data for a complete clean start.
*   **Configurable Operational Logging:** The script's own operational logging (to `maillogsentinel.log`) has configurable levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).

---

## 3. Prerequisites

*   **Python:** Python 3.6 or newer is recommended.
*   **Mail Server:** An active Postfix/Dovecot mail server that is configured to generate SASL authentication logs. These logs are typically found in `/var/log/mail.log` or a similar system log file, depending on the system's `rsyslog` or `syslog-ng` configuration.
*   **Local MTA (Mail Transfer Agent):** A functional MTA (e.g., Postfix, Sendmail, Exim) must be installed and correctly configured on the server where MailLogSentinel runs. This is essential for MailLogSentinel to be able to send email reports.
*   **Permissions:**
    *   The user account under which `maillogsentinel.py` will run (the "operational user") requires **read access** to the mail server's log files. This often involves adding the user to a group like `adm`.
    *   The operational user also needs **write access** to the `working_dir` and `state_dir` directories that will be specified in the configuration file.
    *   **Root (`sudo`) privileges** are required *only* for the `--setup` command, as it may need to create system directories (like `/etc/maillogsentinel.conf`, `/var/log/maillogsentinel`), set their permissions, and potentially guide the user in adding the operational user to necessary groups.

---

## 4. Installation

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/cryptozoide/MailLogSentinel.git
    cd MailLogSentinel
    ```

2.  **Install the Script:**
    It is recommended to place the script in a system-wide accessible location (e.g., `/usr/local/bin`) and make it executable:
    ```bash
    sudo cp bin/maillogsentinel.py /usr/local/bin/maillogsentinel
    sudo chmod +x /usr/local/bin/maillogsentinel
    ```
    After installation, you can typically run the script as `maillogsentinel` or by its full path `/usr/local/bin/maillogsentinel`.

---

## 5. Configuration

MailLogSentinel is configured using a central configuration file. The interactive setup process (`--setup`) is the easiest and recommended way to create this file for the first time.

### Main Configuration File

*   **Default Path:** `/etc/maillogsentinel.conf`
*   **Creation Methods:**
    1.  **Interactive Setup (Highly Recommended):**
        Run `sudo maillogsentinel --setup`. This command initiates a wizard that will guide you through all necessary settings and create the configuration file at the default path.
    2.  **Manual Creation:**
        If you prefer, you can manually copy the template provided in the repository (`config/maillogsentinel.conf`) to `/etc/maillogsentinel.conf` and then edit it according to your environment.
        ```bash
        sudo cp config/maillogsentinel.conf /etc/maillogsentinel.conf
        # Ensure appropriate ownership and restrictive permissions, for example:
        # sudo chown your_chosen_operational_user:your_chosen_operational_user_group /etc/maillogsentinel.conf
        # sudo chmod 640 /etc/maillogsentinel.conf 
        ```

*   **File Structure and Options:**
    The configuration file uses a standard INI-style format.

    *   **`[paths]`**
        *   `working_dir`: Specifies the directory where the CSV output file (`maillogsentinel.csv`) and the script's own operational log file (`maillogsentinel.log`) will be stored.
            *   Example: `/var/log/maillogsentinel`
        *   `state_dir`: Defines the directory where the state file (`state.offset`) is stored. This file tracks the last processed position in the mail log, enabling incremental parsing. It can be the same as `working_dir` or a separate directory (e.g., for systems where `/var/lib` is preferred for state files).
            *   Example: `/var/lib/maillogsentinel` (or `/var/log/maillogsentinel/state`)
        *   `mail_log`: The full path to your mail server's primary log file where SASL authentication messages are recorded (e.g., Postfix/Dovecot combined log).
            *   Example: `/var/log/mail.log`

    *   **`[report]`**
        *   `email`: The email address to which daily summary reports will be sent.
            *   Example: `security-alerts@example.com`

    *   **`[general]`**
        *   `log_level`: Controls the verbosity of MailLogSentinel's own operational messages, which are written to `maillogsentinel.log`.
            *   Valid Options: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
            *   Default: `INFO`

    *   **`[dns_cache]`**
        *   `enabled`: Set to `true` to enable caching of DNS reverse lookup results, or `false` to disable caching (perform fresh lookups every time).
            *   Default: `true`
        *   `size`: The maximum number of DNS entries to store in the LRU (Least Recently Used) cache.
            *   Default: `128`
        *   `ttl_seconds`: The Time-To-Live (in seconds) for entries in the DNS cache. After this duration, a cached entry will be considered stale and will be re-fetched upon the next request for that IP.
            *   Default: `3600` (which corresponds to 1 hour)

### Interactive Setup (`--setup`)

*   **Purpose:** The `--setup` option provides a guided, interactive command-line process for configuring MailLogSentinel for the first time. This is the **recommended method for initial configuration** as it simplifies setting up paths, email details, and also helps in generating Systemd unit files for automation.
*   **Invocation:**
    ```bash
    sudo maillogsentinel --setup
    ```
    If `maillogsentinel` is not in your system's `PATH` (e.g., if you haven't run `sudo cp bin/maillogsentinel.py /usr/local/bin/maillogsentinel`), you'll need to use the full path to the script:
    ```bash
    sudo python3 /path/to/your/MailLogSentinel/bin/maillogsentinel.py --setup
    ```
*   **Process Details:**
    *   The script will prompt you for essential configuration parameters, including the paths for `working_dir`, `state_dir`, and `mail_log`, the recipient email address for reports, and the desired operational log level. Default values are suggested where applicable.
    *   It will then offer to generate example Systemd service (`.service`) and timer (`.timer`) unit files. These are customized with the paths and user you specify and are crucial for automating regular log processing and report generation.
    *   If run with sufficient privileges (i.e., `sudo`), the setup process can attempt to create the specified `working_dir` and `state_dir` if they don't exist, and set appropriate ownership and permissions for the operational user you define.
    *   It may also suggest adding the chosen operational user to a system group like `adm` (common on Debian/Ubuntu systems) to ensure the script has read access to system mail logs.
*   **Automatic Setup Logging:**
    Throughout the interactive setup, all information displayed on your console (including prompts, the values you select, and the generated Systemd examples) is automatically logged to a file named `maillogsentinel_setup.log`. This log file is created in the **current working directory** from which you executed the `--setup` command. This feature is invaluable for reviewing your setup choices and for troubleshooting.

---

## 6. Usage (Command-Line Arguments)

MailLogSentinel is executed from the command line. Standard options like `--help` (for a full list of arguments and their descriptions, including a reference to the man page and full README) and `--version` (to display the script version) are available. Key operational arguments include:

```bash
maillogsentinel [options]
```
Or, if not installed to a directory in your system's `PATH`:
```bash
python3 /path/to/your/MailLogSentinel/bin/maillogsentinel.py [options]
```

*   **Default Operation (Log Processing):**
    Running the script without any specific action flags (like `--setup` or `--report`) performs its primary log processing task:
    ```bash
    maillogsentinel
    ```
    This default action will:
    1.  Load the configuration (from `/etc/maillogsentinel.conf` by default).
    2.  Read the mail log file from the last processed position (stored in the `state.offset` file). If it's the first run or after a reset, it may process from the beginning of the current log file.
    3.  Parse new log entries for SASL authentication failures.
    4.  Perform reverse DNS lookups for IP addresses (utilizing the DNS cache if enabled).
    5.  Append any detected intrusion attempts to the CSV file (`maillogsentinel.csv`).
    6.  Update the `state.offset` file with the new log offset.

*   **`--config <path_to_config_file>`**
    Specifies a custom path to the configuration file. If this option is not provided, the script defaults to using `/etc/maillogsentinel.conf`.
    ```bash
    maillogsentinel --config /opt/maillogsentinel/custom_config.conf
    ```

*   **`--setup`**
    Initiates the interactive first-time setup wizard. This is primarily used to create the initial configuration file, define essential paths, and generate Systemd unit file templates for automation. **This command requires root (`sudo`) privileges** to perform actions like creating system directories or suggesting system group modifications.
    ```bash
    sudo maillogsentinel --setup
    ```
    Note: The setup process is also automatically triggered if the configuration file (either the default `/etc/maillogsentinel.conf` or one specified by `--config`) is not found.

*   **`--report`**
    Triggers the generation and sending of the daily email summary report. This action reads data from the existing `maillogsentinel.csv` file. It should typically be scheduled to run after a log processing run.
    ```bash
    maillogsentinel --report
    ```

*   **`--reset`**
    Resets the application's log processing state. When executed, this option:
    1.  Archives existing data: The main CSV file (`maillogsentinel.csv`), the script's operational log (`maillogsentinel.log`), and the state file (`state.offset`) are moved to a timestamped backup directory created within your user's home directory.
    2.  The log processing offset is effectively reset to zero. Consequently, the next standard run of the script will process mail logs from the beginning (or based on its logic for handling very old logs, if applicable), rather than from the last recorded offset.
    ```bash
    maillogsentinel --reset
    ```

*   **`--purge`**
    Similar to `--reset`, but intended for a more definitive "fresh start." It archives all data in the same manner as `--reset` (CSV, operational log, state file). Use this if you want to clear out all historical data and operational logs managed by the script and begin monitoring anew as if from a clean installation.
    ```bash
    maillogsentinel --purge
    ```

---

## 7. Output Files

MailLogSentinel generates and utilizes the following key files during its operation:

*   **CSV Data File: `maillogsentinel.csv`**
    *   **Location:** This file is stored in the directory specified by the `working_dir` setting in your `maillogsentinel.conf` file.
    *   **Purpose:** This is the primary data output, containing a chronological record of all detected SASL authentication attempts. Each new attempt found during log processing is appended as a new row.
    *   **Columns:**
        1.  `server`: The hostname of the server as it appears in the log entry (e.g., `mailserver01`).
        2.  `date`: The date and time of the authentication attempt, formatted as `DD/MM/YYYY HH:MM`.
        3.  `ip`: The source IP address from which the authentication attempt originated.
        4.  `user`: The username that was attempted during the login process.
        5.  `hostname`: The result of the reverse DNS lookup for the source IP address. If the lookup fails or is not available, this field will contain `"null"`.
        6.  `reverse_dns_status`: Provides the status of the reverse DNS lookup. Common values include `"OK"` (successful lookup), `"Timeout"`, `"Errno -2 (Name or service not known)"` (common for IPs without a PTR record), or `"Failed (Unknown)"`.
    *   **Example Row (Illustrative):**
        ```csv
        mail.example.com;23/10/2023 14:35;198.51.100.123;admin;host.attacker.net;OK
        ```

*   **Application Log File: `maillogsentinel.log`**
    *   **Location:** Also stored in the `working_dir` specified in the configuration.
    *   **Purpose:** This file contains operational logs generated by the MailLogSentinel script itself. It includes messages about script startup and shutdown, which log files are being processed, any errors encountered during normal operation (e.g., DNS lookup issues, file permission problems if not related to setup), DNS cache status messages, and information about report generation. The level of detail in this log is determined by the `log_level` setting in `maillogsentinel.conf`.
    *   **Rotation:** This log file is configured to automatically rotate when it reaches approximately 1MB in size. Up to 5 backup log files (e.g., `maillogsentinel.log.1`, `maillogsentinel.log.2`) are kept.

*   **Setup Log File: `maillogsentinel_setup.log`**
    *   **Location:** This file is created in the **current working directory** from which the `maillogsentinel --setup` command is executed.
    *   **Purpose:** It serves as a complete transcript of the interactive setup session. This includes all prompts shown to the user, the configuration values they selected or confirmed (user inputs like passwords are not logged if they were part of setup, though the current setup doesn't ask for them directly), and the full text of any example Systemd unit files that were generated. This log is very useful for reviewing the setup choices made and for troubleshooting the setup process itself.

---

## 8. Email Reports

*   **Triggering:** Email reports are generated and dispatched when MailLogSentinel is executed with the `--report` command-line argument. This action is typically scheduled to run on a daily basis using Systemd timers or cron.
*   **Content:** The email report is designed to provide a concise yet informative summary of SASL authentication activity. Each report includes:
    *   **Header Information:** Details such as the script name (`MailLogSentinel`), its version, the timestamp of when the report was generated, and the FQDN and IP address of the server running the script.
    *   **Daily Statistics:**
        *   Total number of failed authentication attempts recorded for the current day.
        *   A list of the "Top 10 failed authentications today," broken down by unique combinations of username, IP address, and client hostname, along with their respective attempt counts.
        *   A list of the "Top 10 Usernames today" that were involved in failed authentication attempts, with their corresponding counts.
        *   A "Reverse DNS Lookup Failure Summary," which shows the total number of failed reverse DNS lookups for the day and provides a breakdown of these failures by error type (e.g., "Timeout," "Errno -2").
    *   **CSV File Information:**
        *   The total current size of the `maillogsentinel.csv` file (e.g., "123.4K").
        *   The total number of lines currently in the `maillogsentinel.csv` file (this count excludes the header row).
    *   **Attachment:** The complete `maillogsentinel.csv` data file is attached to the email. This allows for detailed offline analysis, import into other security information and event management (SIEM) tools, or for historical record-keeping.

---

## 9. Automated Execution (Systemd)

For continuous monitoring and timely reporting, MailLogSentinel should be configured to run automatically at regular intervals. The use of Systemd timers and services is the recommended method on modern Linux systems. The interactive setup process (`--setup`) is designed to help you generate template unit files for this purpose.

*   **Generated Unit Files (during `--setup`):**
    When you run the `--setup` wizard, it will offer to generate the following Systemd unit files. These files will be saved in the directory where you execute the setup command:
    *   `maillogsentinel.service`: This service unit file defines how to run the core log extraction and processing task (i.e., running `maillogsentinel` without the `--report` flag).
    *   `maillogsentinel-extract.timer`: This timer unit file defines a schedule (e.g., hourly) to trigger the `maillogsentinel.service`.
    *   `maillogsentinel-report.service`: This service unit file defines how to run the email reporting task (i.e., running `maillogsentinel --report`).
    *   `maillogsentinel-report.timer`: This timer unit file defines a schedule (e.g., daily, typically late in the evening) to trigger the `maillogsentinel-report.service`.

*   **Manual Deployment and Activation Steps (User Responsibility):**
    1.  **Review and Customize:** After the unit files are generated, it is **crucial** to review them carefully.
        *   Verify all paths (e.g., to the Python executable, the `maillogsentinel` script itself, and its configuration file specified in the `ExecStart=` line).
        *   Most importantly, ensure the `User=` directive in the `.service` files is set to an appropriate **non-root user**. This user must have the necessary permissions to read the mail logs and write to MailLogSentinel's working and state directories.
        *   Adjust the `OnCalendar=` schedules in the `.timer` files to match your desired frequency for log processing and reporting.
    2.  **Copy to Systemd Directory:** Once you have reviewed and (if necessary) edited the unit files, copy them to the Systemd system directory, which is typically `/etc/systemd/system/`:
        ```bash
        sudo cp maillogsentinel.service maillogsentinel-extract.timer maillogsentinel-report.service maillogsentinel-report.timer /etc/systemd/system/
        ```
    3.  **Reload Systemd Daemon:** Instruct Systemd to read the new (or modified) unit files:
        ```bash
        sudo systemctl daemon-reload
        ```
    4.  **Enable and Start Timers:** To activate the schedules and ensure they persist across system reboots, enable and start the timers:
        ```bash
        sudo systemctl enable --now maillogsentinel-extract.timer
        sudo systemctl enable --now maillogsentinel-report.timer
        ```
        The `--now` option starts the timers immediately. If `Persistent=true` is set in the timer unit (which is the default for the generated templates), this may also trigger an immediate run of the associated service if it missed a scheduled run while the timer was inactive.
    5.  **Verify Operation:** Check the status and next scheduled run times of your timers:
        ```bash
        systemctl list-timers --all
        ```
        You should see `maillogsentinel-extract.timer` and `maillogsentinel-report.timer` in the output. You can also inspect the logs of the services to ensure they are running correctly using `journalctl`:
        ```bash
        journalctl -u maillogsentinel.service -f 
        journalctl -u maillogsentinel-report.service -f
        ```
        (Use `-f` to follow the logs in real time).

---

## 10. Contributing

Contributions are highly encouraged and warmly welcome! If you have suggestions for improvements, ideas for new features, or if you encounter any bugs, please feel free to open an issue on the [GitHub repository issues page](https://github.com/cryptozoide/MailLogSentinel/issues).

If you'd like to contribute code directly:
1.  Fork the repository on GitHub.
2.  Create a new branch for your feature or bug fix (e.g., `git checkout -b feature/my-new-feature` or `git checkout -b fix/issue-N`).
3.  Make your changes and commit them with clear, descriptive messages.
4.  If you add new functionality, please consider adding corresponding tests.
5.  Push your changes to your forked repository.
6.  Submit a pull request to the main MailLogSentinel repository, clearly describing the changes you've made and why.

(For more detailed guidelines, please refer to [CONTRIBUTING.md](docs/CONTRIBUTING.md).

---

## 11. License

This project is distributed under the terms of the GNU GPL v3 License.
Please see the [LICENSE](LICENCE) file in the root of the repository for the full license text.

---

## 12. Support

If you find MailLogSentinel useful, please consider giving it a star on GitHub!
For any issues, questions, or support requests, the primary channel is the [GitHub issue tracker](https://github.com/cryptozoide/MailLogSentinel/issues) for the project.

---
