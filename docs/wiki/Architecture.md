# Architecture

This section provides an overview of MailLogSentinel's architecture and how data flows through the system.

## System Overview

MailLogSentinel is designed as a modular Python application that interacts with the local system (primarily Postfix logs) and can send notifications via email. It does not require a separate database server or complex external dependencies beyond what's typically available on a Linux system running Postfix.

**Key Components:**

1.  **Log Source (Postfix):**
    *   The primary input is the Postfix mail log file (e.g., `/var/log/mail.log`).
    *   MailLogSentinel also handles rotated log files (e.g., `mail.log.1`, `mail.log.2.gz`).

2.  **`maillogsentinel.py` (Core Engine):**
    *   **Log Parser:** Reads and processes log entries, specifically looking for SASL authentication failures.
    *   **State Manager:** Keeps track of the last processed log position (offset) to ensure incremental processing.
    *   **Data Extractor:** Pulls out key information (timestamp, IP, user, etc.) from relevant log lines.
    *   **Data Enricher:**
        *   Uses `dns_utils.py` for reverse DNS lookups (with caching).
        *   Integrates with `ipinfo.py` (via `IPInfoManager`) to fetch geolocation (country) and ASN/ASO information for IP addresses.
    *   **Report Generator:** Compiles data for CSV output and email summaries.
    *   **Notification Sender:** Sends email reports using `smtplib`.
    *   **Configuration Loader:** Reads settings from `maillogsentinel.conf`.

3.  **`ipinfo.py` (IP Information Module):**
    *   Manages local databases for IP-to-country and IP-to-ASN/ASO mappings.
    *   Provides functions to look up IP information and update these databases from external URLs.

4.  **Configuration File (`maillogsentinel.conf`):**
    *   Stores user-defined settings for paths, email, logging, database URLs, etc.

5.  **Output Files:**
    *   **CSV Report (`maillogsentinel.csv`):** A persistent record of all detected intrusion attempts.
    *   **Operational Logs (`maillogsentinel.log`):** Logs the script's own activities, errors, and debug information.
    *   **State File:** Stores the last log offset.

6.  **Systemd Services/Timers (Optional but Recommended):**
    *   `maillogsentinel.timer` and `maillogsentinel.service`: For periodic execution of log parsing and data extraction.
    *   `maillogsentinel-report.timer` and `maillogsentinel-report.service`: For periodic generation and sending of email summary reports.

## Data Flow

The following diagram illustrates the general data flow within MailLogSentinel:

```mermaid
graph LR
    A[Postfix Logs (.log, .log.gz)] -- Scans --> B(maillogsentinel.py Core Engine)
    
    subgraph B [maillogsentinel.py Core Engine]
        direction LR
        B1[Log Parser] --> B2[Data Extractor]
        B2 --> B3[Data Enricher]
        B3 -- Reverse DNS --> Dcache[(DNS Cache)]
        B3 -- IP Lookup --> IPMod(IPInfoManager)
        B2 --> B4[Report Generator]
        B4 --> B5[Notification Sender]
        B0[Config Loader] --> B
        BState[State Manager] <--> B1
    end

    IPMod -- Reads/Updates --> DBs[(Local GeoIP/ASN DBs)]
    ExtURL[External DB URLs] -- Downloads --> IPMod

    B4 -- Appends to --> CSV[CSV File (intrusions.csv)]
    B5 -- Sends --> Email[Email Report]
    B -- Writes to --> OpLogs[Operational Logs (maillogsentinel.log)]
    BState -- Reads/Writes --> StateFile[State File (offset)]
    Conf[maillogsentinel.conf] -- Loaded by --> B0

    SystemdTimer1[Systemd Timer (Extraction)] -- Triggers --> B
    SystemdTimer2[Systemd Timer (Report)] -- Triggers --> B5
```

**Explanation of Data Flow:**

1.  **Log Ingestion:**
    *   `maillogsentinel.py` (typically triggered by a Systemd timer or run manually) starts by reading its configuration.
    *   It consults its state file to find the last processed offset in the Postfix mail log.
    *   The Log Parser reads new entries from the Postfix log file(s).

2.  **Data Extraction and Enrichment:**
    *   If a log line indicates a failed SASL authentication, the Data Extractor pulls relevant fields (IP address, username, timestamp).
    *   The Data Enricher then:
        *   Performs a reverse DNS lookup for the attacker's IP address (utilizing an in-memory DNS cache to speed up repeated lookups).
        *   Queries the `IPInfoManager` (from `ipinfo.py`) for the country code, ASN, and ASO associated with the IP address. The `IPInfoManager` uses its local CSV databases for this.

3.  **Data Storage and Reporting:**
    *   The extracted and enriched information for each intrusion attempt is appended as a new row to the CSV report file.
    *   If the reporting interval has been met (often managed by a separate Systemd timer for the report service), the Report Generator compiles a summary.
    *   This summary typically includes top attackers, targeted usernames, source countries, etc., derived from the data collected since the last report (or for the current day).
    *   The Notification Sender then emails this summary report (often with the full CSV as an attachment) to the configured recipient.

4.  **State and Operational Logging:**
    *   After processing, `maillogsentinel.py` updates the state file with the new log offset.
    *   Throughout its operation, it writes informational messages, warnings, and errors to its own operational log file.

5.  **Database Updates (via `ipinfo.py`):**
    *   The `IPInfoManager` (either when first initialized by `maillogsentinel.py` or when `ipinfo.py --update` is run) can download fresh copies of the country and ASN/ASO databases from their configured URLs, ensuring the geolocation data remains relatively up-to-date.

This architecture allows MailLogSentinel to efficiently process logs, enrich the data with valuable context, and provide timely security alerts and reports with minimal external dependencies.
