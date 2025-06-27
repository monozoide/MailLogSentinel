"""
Handles the generation and sending of email reports for MailLogSentinel.

This module analyzes the collected CSV data of SASL authentication failures
to produce a summary report. The report includes statistics such as:
- Total attempts for the current day.
- Top 10 failed authentications (by user, IP, hostname, country).
- Top 10 usernames, countries, ASOs (Autonomous System Organizations), and ASNs
  (Autonomous System Numbers) associated with failures.
- Summary of reverse DNS lookup failures.
- CSV file size and line count.

The generated report is then formatted and sent as an email, with the CSV
file attached. Configuration for email (recipient, sender override, subject prefix)
is sourced from `AppConfig`.
"""

import csv
import socket
import smtplib
import getpass
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
import logging
from typing import Dict, Any, List, Optional, Tuple

from . import config

# SECTION_REPORT is not needed here as AppConfig directly provides attributes.


def get_extraction_frequency() -> str:
    """
    Reads the systemd timer to determine the log extraction frequency
    for the report header.

    This function attempts to read the `OnCalendar` value from the systemd timer
    file typically located at `/etc/systemd/system/maillogsentinel-extract.timer`.
    This value indicates how often the log extraction process is scheduled to run.

    Returns:
        The `OnCalendar` string (e.g., "hourly", "daily", "00:00") if found.
        Defaults to "hourly" if the file cannot be read or the line is not found.
    """
    # This function remains as it reads from a system file, not directly from AppConfig.
    # However, its usage in the report header might be re-evaluated if this info
    # should come from AppConfig or be determined differently.
    timer_file_path = "/etc/systemd/system/maillogsentinel-extract.timer"
    try:
        with open(timer_file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("OnCalendar="):
                    return line.split("=", 1)[1].strip()
    except IOError:
        pass
    return "hourly"


def _analyze_csv_for_report(
    csv_path: Path, logger: logging.Logger, today_date_str: str
) -> Optional[Dict[str, Any]]:
    """
    Analyzes the CSV data to generate statistics for the daily email report.

    This function reads the provided CSV file (containing log extraction results)
    and computes various statistics for entries matching `today_date_str`.
    These statistics include:
    - Total authentication attempts today.
    - Top 10 failed authentications (user, IP, hostname, country).
    - Top 10 usernames, countries, ASOs, and ASNs involved in failures today.
    - Total count of reverse DNS lookup failures and a breakdown by error type.
    - Total size and line count of the CSV file.

    Args:
        csv_path: Path to the CSV file to analyze.
        logger: A logging.Logger instance for messages.
        today_date_str: A string representing today's date in "dd/mm/YYYY" format,
                        used to filter entries for the current day's report.

    Returns:
        A dictionary containing the computed statistics if successful. The keys are:
        'total_today', 'top10_today', 'top10_usernames', 'total_rev_dns_failures',
        'rev_dns_error_counts', 'top10_countries', 'top10_aso', 'top10_asn',
        'csv_size_k_str', 'csv_lines_str'.
        Returns None if the CSV file cannot be read or if a CSV parsing error occurs.

    Note:
        For performance with very large CSV files, consider chunked reading or
        a database-backed approach for analysis.
    """
    # Performance: This function reads the entire CSV into memory for analysis.
    # For very large CSV files, consider chunked reading or database-backed analysis.
    logger.debug(
        f"Starting CSV analysis for {csv_path} with today_date_str: '{today_date_str}'"
    )
    stats: Dict[str, Any] = {
        "total_today": 0,
        "top10_today": [],
        "top10_usernames": [],
        "total_rev_dns_failures": 0,
        "rev_dns_error_counts": {},
        "top10_countries": [],
        "top10_aso": [],
        "top10_asn": [],
        "csv_size_k_str": "N/A",
        "csv_lines_str": "N/A",
    }
    counts_today: Dict[Tuple[str, str, str], int] = {}
    username_counts_today: Dict[str, int] = {}
    country_counts_today: Dict[str, int] = {}
    aso_counts_today: Dict[str, int] = {}
    asn_counts_today: Dict[str, int] = {}
    rev_dns_error_counts_agg: Dict[str, int] = {}
    total_lines_in_csv = 0

    try:
        with csv_path.open(newline="", encoding="utf-8") as f:
            logger.debug(f"Successfully opened {csv_path} for reading.")
            reader = csv.reader(f, delimiter=";")
            try:
                header = next(reader, None)  # Skip header
                if header is not None:
                    total_lines_in_csv = 1  # Count header
            except StopIteration:
                logger.warning(f"CSV file {csv_path} is empty or has no data rows.")
                # No pass needed here, loop won't run

            for row_num, row in enumerate(
                reader, start=1
            ):  # reader is already a generator
                total_lines_in_csv += 1
                if len(row) < 9:
                    logger.warning(
                        f"Skipping malformed CSV row {row_num + 1} (expected 9 fields, "  # +1 because header was line 1
                        f"got {len(row)}): {row}"
                    )
                    continue

                (
                    _,
                    date_field,
                    ip_val,
                    user_val,
                    hostn_val,
                    rev_dns_status_val,
                    country_val,
                    asn_val,
                    aso_val,
                ) = row[:9]

                if date_field.startswith(today_date_str):
                    stats["total_today"] += 1
                    # Include country_val in the key for top10_today
                    key_auth = (user_val, ip_val, hostn_val, country_val)
                    counts_today[key_auth] = counts_today.get(key_auth, 0) + 1
                    username_counts_today[user_val] = (
                        username_counts_today.get(user_val, 0) + 1
                    )
                    country_counts_today[country_val] = (
                        country_counts_today.get(country_val, 0) + 1
                    )
                    aso_counts_today[aso_val] = aso_counts_today.get(aso_val, 0) + 1
                    asn_counts_today[asn_val] = asn_counts_today.get(asn_val, 0) + 1

                    if rev_dns_status_val != "OK":
                        stats["total_rev_dns_failures"] += 1
                        rev_dns_error_counts_agg[rev_dns_status_val] = (
                            rev_dns_error_counts_agg.get(rev_dns_status_val, 0) + 1
                        )

        stats["csv_lines_str"] = str(
            max(0, total_lines_in_csv - 1)
        )  # total lines minus header

        stats["top10_today"] = sorted(
            counts_today.items(), key=lambda x: x[1], reverse=True
        )[:10]
        stats["top10_usernames"] = sorted(
            username_counts_today.items(), key=lambda x: x[1], reverse=True
        )[:10]
        stats["top10_countries"] = sorted(
            country_counts_today.items(), key=lambda x: x[1], reverse=True
        )[:10]
        stats["top10_aso"] = sorted(
            aso_counts_today.items(), key=lambda x: x[1], reverse=True
        )[:10]
        stats["top10_asn"] = sorted(
            asn_counts_today.items(), key=lambda x: x[1], reverse=True
        )[:10]
        stats["rev_dns_error_counts"] = sorted(
            rev_dns_error_counts_agg.items(), key=lambda item: item[1], reverse=True
        )

    except IOError as e:
        logger.error(f"Could not read or parse CSV file {csv_path}: {e}")
        return None
    except csv.Error as e:
        logger.error(f"CSV formatting error in {csv_path}: {e}")
        return None

    try:
        size_k = csv_path.stat().st_size / 1024
        stats["csv_size_k_str"] = f"{size_k:.1f}K"
    except OSError as e:
        logger.error(f"Could not get size of CSV file {csv_path}: {e}")

    # The line counting is now done during the main CSV processing loop.
    # try:
    #     with csv_path.open(encoding="utf-8") as f_count:
    #         line_count = sum(1 for _ in f_count) - 1
    #         stats["csv_lines_str"] = str(max(0, line_count))
    # except OSError as e: # More specific, Exception was too broad here
    #     logger.error(f"Could not get line count of CSV file {csv_path}: {e}")
    # except Exception as e: # Catch any other unexpected error during line counting
    #     logger.error(f"Unexpected error counting lines in {csv_path}: {e}", exc_info=True)

    return stats


def send_report(
    app_config: "config.AppConfig",
    logger: logging.Logger,
    script_name: str,
    script_version: str,
) -> None:
    """
    Generates and sends the daily email report with CSV attachment.

    This function orchestrates the report generation process:
    1. Checks if a recipient email is configured in `app_config`.
    2. Verifies the existence of the CSV data file.
    3. Calls `_analyze_csv_for_report` to get statistics for today.
    4. Formats these statistics into a human-readable email body.
    5. Constructs an `EmailMessage` object with the report content and
       attaches the full CSV file.
    6. Sends the email using a local SMTP server on `localhost`.

    Configuration details like recipient email, sender override, subject prefix,
    working directory, and CSV filename are obtained from the `app_config` object.

    Args:
        app_config: An `AppConfig` instance containing configuration settings,
                    especially for report email, paths, and sender details.
        logger: A `logging.Logger` instance for logging messages.
        script_name: The name of the script (e.g., "MailLogSentinel"), used in
                     the email header.
        script_version: The version of the script, used in the email header.
    """
    email_recipient = app_config.report_email
    if not email_recipient:  # report_email defaults to None in AppConfig if not set
        logger.error(
            "No email address configured for report (report -> email in config)."
        )
        return

    # Use working_dir and csv_filename from AppConfig
    csv_file = app_config.working_dir / app_config.csv_filename
    if not csv_file.is_file():
        logger.warning(f"CSV file {csv_file} not found. No report to send.")
        return

    today_date_str = datetime.now().strftime("%d/%m/%Y")
    report_stats = _analyze_csv_for_report(csv_file, logger, today_date_str)

    if report_stats is None:
        logger.error("CSV analysis failed. Cannot generate or send report.")
        return

    bash_user = getpass.getuser()  # Could be overridden by AppConfig
    fqdn = socket.getfqdn() or socket.gethostname()

    # Use sender_override from AppConfig if provided
    from_addr = (
        app_config.report_sender_override
        if app_config.report_sender_override
        else f"{bash_user}@{fqdn}"
    )

    try:
        ipaddr = socket.gethostbyname(fqdn)
    except socket.gaierror as e:
        logger.warning(f"Could not get IP for FQDN {fqdn}: {e}. Using 'unknown'.")
        ipaddr = "unknown"

    now_stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    extraction_freq = get_extraction_frequency()
    header_content_lines = [
        f"{script_name} {script_version}",
        f"Extraction interval : {extraction_freq}",
        f"Report at {now_stamp}",
        f"Server: {ipaddr} ({fqdn})",
    ]

    max_len = 0
    for line in header_content_lines:
        if len(line) > max_len:
            max_len = len(line)

    border_line = "#" * (max_len + 6)
    header_list_for_email = [border_line]
    for line_content in header_content_lines:
        formatted_line = f"### {line_content.ljust(max_len)} ###"
        header_list_for_email.append(formatted_line)
    header_list_for_email.append(border_line)
    header_list_for_email.append("")

    body: List[str] = []
    body.append(f"Total attempts today: {report_stats['total_today']}")
    body.append("")
    body.append("Top 10 failed authentications today:")

    if report_stats["top10_today"]:
        max_user_len = 4
        max_ip_len = 2
        max_hostn_len = 8
        max_country_len = 2  # For country code like "US"
        max_count_len = 5
        # Unpack country as well
        for (user, ip, hostn, country), cnt in report_stats["top10_today"]:
            max_user_len = max(max_user_len, len(user))
            max_ip_len = max(max_ip_len, len(ip))
            max_hostn_len = max(max_hostn_len, len(hostn))
            max_country_len = max(
                max_country_len, len(country if country else "")
            )  # Handle None or empty country
            max_count_len = max(max_count_len, len(str(cnt)))
        # Unpack country and add to the line
        for idx, ((user, ip, hostn, country), cnt) in enumerate(
            report_stats["top10_today"], 1
        ):
            country_str = (
                country if country else "N/A"
            )  # Display N/A if country is None or empty
            body.append(
                f"  {idx:>2d}. {user:<{max_user_len}}  {ip:<{max_ip_len}}  "
                f"{hostn:<{max_hostn_len}}  {country_str:<{max_country_len}}  "
                f"{str(cnt):>{max_count_len}} times"
            )
    else:
        body.append("  (no entries for today)")

    body.append("")
    body.append("Top 10 Usernames today:")
    top10_usernames = report_stats.get("top10_usernames", [])
    if top10_usernames:
        max_username_len = 4
        max_username_count_len = 5
        for username, count in top10_usernames:
            max_username_len = max(max_username_len, len(username))
            max_username_count_len = max(max_username_count_len, len(str(count)))
        for idx, (username, count) in enumerate(top10_usernames, 1):
            body.append(
                f"  {idx:>2d}. {username:<{max_username_len}}  "
                f"{str(count):>{max_username_count_len}} times"
            )
    else:
        body.append("  (no specific username stats for today)")

    # ... (similar blocks for countries, ASO, ASN) ...
    for cat_key, cat_title in [
        ("top10_countries", "Top 10 countries today:"),
        ("top10_aso", "Top 10 ASO today:"),
        ("top10_asn", "Top 10 ASN today:"),
    ]:
        body.append("")
        body.append(cat_title)
        items = report_stats.get(cat_key, [])
        if items:
            max_item_len = len(cat_title.split()[2])  # Approx header len
            max_item_count_len = 5  # len("Count")
            for item, count in items:
                max_item_len = max(max_item_len, len(item))
                max_item_count_len = max(max_item_count_len, len(str(count)))
            for idx, (item, count) in enumerate(items, 1):
                body.append(
                    f"  {idx:>2d}. {item:<{max_item_len}}  "
                    f"{str(count):>{max_item_count_len}} times"
                )
        else:
            body.append(f"  (no {cat_title.split()[2].lower()} stats for today)")

    body.append("")
    body.append("--- Reverse DNS Lookup Failure Summary ---")
    total_rev_dns_failures = report_stats.get("total_rev_dns_failures", 0)
    rev_dns_error_counts = report_stats.get("rev_dns_error_counts", [])
    body.append(f"Total failed reverse lookups today: {total_rev_dns_failures}")
    if total_rev_dns_failures > 0 and rev_dns_error_counts:
        body.append("Breakdown by error type:")
        max_error_str_len = 0
        max_error_count_len = 0
        if rev_dns_error_counts:
            max_error_str_len = max(len(err_str) for err_str, _ in rev_dns_error_counts)
            max_error_count_len = max(
                len(str(count)) for _, count in rev_dns_error_counts
            )
        for err_str, count in rev_dns_error_counts:
            body.append(
                f"  {err_str:<{max_error_str_len}} : {str(count):>{max_error_count_len}}"
            )
    else:
        body.append(
            "  (No reverse DNS lookup failures recorded for today or "
            "breakdown not available)"
        )

    body.append("")
    body.append(f"Total CSV file size: {report_stats['csv_size_k_str']}")
    body.append(f"Total CSV lines:     {report_stats['csv_lines_str']}")
    body.append("")
    body.append(
        f"Please see attached: {app_config.csv_filename}"
    )  # Use AppConfig attribute
    body.append("")
    body.append(
        "For more details and documentation, visit: "
        "https://github.com/monozoide/MailLogSentinel/blob/main/README.md"
    )

    msg = EmailMessage()
    # Use report_subject_prefix from AppConfig
    msg["Subject"] = (
        f"{app_config.report_subject_prefix} {script_name} report on {fqdn}"
    )
    msg["From"] = from_addr
    msg["To"] = email_recipient
    initial_body_content = "\n".join(header_list_for_email + body) + "\n"
    msg.set_content(initial_body_content)

    try:
        with csv_file.open("rb") as f:
            data = f.read()
        # Use AppConfig attribute for filename in attachment
        msg.add_attachment(
            data, maintype="text", subtype="csv", filename=app_config.csv_filename
        )
    except IOError as e:
        logger.error(f"Could not attach CSV {app_config.csv_filename} to report: {e}")
        msg.set_content(
            initial_body_content
            + f"\n\nNOTE: Could not attach {app_config.csv_filename} due to error.\n"
        )

    try:
        with smtplib.SMTP("localhost") as s:
            s.send_message(msg)
        logger.info(f"Report sent from {from_addr} to {email_recipient}")
    except (
        smtplib.SMTPException,
        socket.error,
        OSError,
    ) as e:  # More specific for SMTP operations
        logger.error(f"Failed to send report: {e}")
