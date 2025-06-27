"""
Provides common utilities for parsing mail log lines in MailLogSentinel.

This module includes functions and regular expressions to extract relevant
information from log entries, specifically focusing on SASL (Simple
Authentication and Security Layer) authentication attempts. It also handles
date parsing and integration with IP geolocation and reverse DNS lookups.
"""

import re
import logging
from typing import Optional, Callable
import sys
from pathlib import Path

# Add bin directory to sys.path to allow importing ipinfo
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "bin"))
import ipinfo  # Added import

# Constants for log parsing
MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

LOG_RE = re.compile(
    r"^(?P<month>\w{3})\s+"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<server>\S+)"
)
PAT = re.compile(r"(?P<ip>\d{1,3}(?:\.\d{1,3}){3}).*?sasl_username=(?P<user>[^,]+)")


def _parse_log_line(
    log_line_text: str,
    current_year: int,
    logger: logging.Logger,
    ip_info_mgr: Optional["ipinfo.ipinfo.IPInfoManager"],
    reverse_lookup_func: Callable[
        [str, logging.Logger], tuple[Optional[str], Optional[str]]
    ],
) -> Optional[dict]:
    """
    Parses a single log line to extract SASL authentication failure details.

    This function attempts to match known log line patterns for SASL
    authentication failures. If a match is found, it extracts the date, time,
    server, IP address, and username involved in the attempt. It then
    performs a reverse DNS lookup for the IP and queries IP geolocation
    information (country, ASN, ASO) if an `ip_info_mgr` is provided.

    Args:
        log_line_text: The raw text of the log line.
        current_year: The current year, used for constructing full dates from
                      log timestamps that may not include the year.
        logger: A logging.Logger instance for reporting parsing errors or warnings.
        ip_info_mgr: An optional `ipinfo.IPInfoManager` instance used to look up
                     geolocation data for the extracted IP address. If None,
                     geolocation fields will be "N/A".
        reverse_lookup_func: A callable that performs reverse DNS lookups.
                             It should accept an IP string and a logger, and return
                             a tuple (hostname, error_string).

    Returns:
        A dictionary containing the parsed information if successful, with keys:
        'server', 'date_s', 'ip', 'user', 'hostn', 'reverse_dns_status',
        'country_code', 'asn', 'aso'.
        Returns None if the log line does not match the expected pattern or
        if a critical parsing error occurs.
    """
    m_log = LOG_RE.match(log_line_text)
    if not m_log:
        return None

    msg_content = log_line_text[m_log.end() :]
    m_pat = PAT.search(msg_content)
    if not m_pat:
        return None

    try:
        month_abbr = m_log.group("month")
        mon_num = MONTHS[month_abbr]
        day = int(m_log.group("day"))
        hhmm = m_log.group("time")[:5]
        date_s = f"{day:02d}/{mon_num:02d}/{current_year} {hhmm}"

        server = m_log.group("server")
        ip = m_pat.group("ip")
        user = m_pat.group("user").strip()
        user = user.replace("\n", " ").replace("\r", " ")

        raw_hostn, rev_dns_error_str = reverse_lookup_func(ip, logger)

        hostn_val = "null"
        status_val = "OK"

        if raw_hostn is not None:
            hostn_val = raw_hostn.replace("\n", " ").replace("\r", " ")
        elif rev_dns_error_str is not None:
            status_val = rev_dns_error_str.replace("\n", " ").replace("\r", " ")
        else:
            status_val = "Failed (Unknown)"  # Should ideally not happen if reverse_lookup_func is robust

        country_code = "N/A"
        asn = "N/A"
        aso = "N/A"
        if ip_info_mgr:
            geo_info = ip_info_mgr.lookup_ip_info(ip)
            if geo_info:
                country_code = geo_info.get("country_code", "N/A")
                asn = geo_info.get("asn", "N/A")
                aso = geo_info.get("aso", "N/A")

        return {
            "server": server,
            "date_s": date_s,
            "ip": ip,
            "user": user,
            "hostn": hostn_val,
            "reverse_dns_status": status_val,
            "country_code": country_code,
            "asn": asn,
            "aso": aso,
        }
    except KeyError:
        logger.warning(
            f"Invalid month abbreviation in log line: {log_line_text.strip()}"
        )
        return None
    except ValueError:
        logger.warning(f"Invalid day format in log line: {log_line_text.strip()}")
        return None
    except Exception as e:
        logger.error(
            f"Unexpected error parsing log line '{log_line_text.strip()}': {e}"
        )
        return None
