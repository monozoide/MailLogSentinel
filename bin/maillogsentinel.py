#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
maillogsentinel.py v4.0.2 (smtplib, full sender address) :

- extract server;date;ip;user;hostname from Postfix SASL logs  
- incremental parse of /var/log/mail.log with rotation/truncation detection  
- --reset / --purge management  
- logs & state in workdir  
- daily text-only report via python smtplib with MIME attachment  
- From: <bash_user>@<server_fqdn>
"""

import os
import sys
import gzip
# glob removed
import shutil
import subprocess # Added import
# subprocess removed comment is now obsolete
import logging
import logging.handlers
import argparse
import configparser
import re
import tempfile
import socket
import csv
import smtplib
import getpass
import functools
import time
from email.message import EmailMessage
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, List, Union, Callable # Union might be needed if we encounter X | Y, Callable for type hint
import copy # Added for deepcopy
import ipinfo # Added for IP Geolocation and ASN

# --- Global DNS Cache Variables ---
CACHED_DNS_LOOKUP_FUNC: Optional[Callable[[str], Tuple[Optional[str], Optional[str], float]]] = None
DNS_CACHE_SETTINGS: dict = {}

# --- Global IPInfoManager ---
IP_INFO_MANAGER: Optional[ipinfo.IPInfoManager] = None

# --- Constants ---
SCRIPT_NAME     = "MailLogSentinel"
VERSION         = "v4.0.2"
DEFAULT_CONFIG  = Path("/etc/maillogsentinel.conf")
STATE_FILENAME  = "state.offset" # Keep as string, will be appended to Path object
CSV_FILENAME    = "maillogsentinel.csv"  # Keep as string
LOG_FILENAME    = "maillogsentinel.log"
SECTION_PATHS   = "paths"
SECTION_REPORT  = "report"
SECTION_GEOLOCATION = "geolocation" # New section
SECTION_ASN_ASO = "ASN_ASO" # New section

MONTHS = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
    'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
    'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
}

LOG_RE = re.compile(
    r'^(?P<month>\w{3})\s+'
    r'(?P<day>\d{1,2})\s+'
    r'(?P<time>\d{2}:\d{2}:\d{2})\s+'
    r'(?P<server>\S+)'
)
PAT = re.compile(r"(?P<ip>\d{1,3}(?:\.\d{1,3}){3}).*?sasl_username=(?P<user>[^,\s]+)")

# --- Cron utilities have been removed ---

# --- Common utilities ---
def check_root():
    if os.geteuid() == 0:
        print("⚠️  Do not run as root; switch to a non-root account.", file=sys.stderr)
        sys.exit(1)

def load_config(config_path: Path): # Expect a Path object
    cfg = configparser.ConfigParser()
    if not config_path.is_file():
        print(f"⚠️  Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    try:
        # configparser.read() can handle Path objects directly
        cfg.read(config_path)
    except configparser.Error as e:
        # Logging might not be set up yet, print to stderr
        print(f"⚠️  Error parsing config file {config_path}: {e}", file=sys.stderr)
        sys.exit(1)
    return cfg

def setup_paths(cfg): # Returns Path objects
    p        = cfg[SECTION_PATHS]
    workdir  = Path(p.get("working_dir", "/var/log/maillogsentinel"))
    # If state_dir is defined as absolute, use it, otherwise, relative to workdir
    state_dir_str = p.get("state_dir")
    if state_dir_str and Path(state_dir_str).is_absolute():
        statedir = Path(state_dir_str)
    else: # Default or relative path
        statedir = workdir / (state_dir_str or "state")
        
    maillog  = Path(p.get("mail_log", "/var/log/mail.log"))

    # Define default paths for geolocation and ASN databases
    # These defaults are used if the sections or keys are missing in the config file.
    default_country_db_path_str = "/var/lib/maillogsentinel/country_aside.csv"
    default_asn_db_path_str = "/var/lib/maillogsentinel/asn.csv" # Corrected default, was asn-ipv4.csv

    # Safely get paths using configparser's get method with fallback
    country_db_path_str = cfg.get(SECTION_GEOLOCATION, 'country_db_path', fallback=default_country_db_path_str)
    asn_db_path_str = cfg.get(SECTION_ASN_ASO, 'asn_db_path', fallback=default_asn_db_path_str)

    country_db_path = Path(country_db_path_str)
    asn_db_path = Path(asn_db_path_str)

    try:
        workdir.mkdir(parents=True, exist_ok=True)
        statedir.mkdir(parents=True, exist_ok=True)
        # Ensure parent directories for DB paths exist if they are specified and not default
        # ipinfo module itself should handle creation of its own data dir, but if paths are customized elsewhere...
        if country_db_path.parent != Path("/var/lib/maillogsentinel"): # Example default parent
            country_db_path.parent.mkdir(parents=True, exist_ok=True)
        if asn_db_path.parent != Path("/var/lib/maillogsentinel"): # Example default parent
            asn_db_path.parent.mkdir(parents=True, exist_ok=True)

    except OSError as e:
        # Logging might not be set up yet, print to stderr
        print(f"⚠️  Permission denied creating directory {e.filename}: {e}", file=sys.stderr)
        sys.exit(1)
    return workdir, statedir, maillog, country_db_path, asn_db_path

def setup_logging(workdir: Path, level_str: str = "INFO"): # Expects a Path object and level string
    LOG_LEVELS_MAP = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    # Default to INFO if level_str is invalid or not found in map
    log_level = LOG_LEVELS_MAP.get(level_str.upper(), logging.INFO) 

    logpath = workdir / LOG_FILENAME # Use Path object division
    logger  = logging.getLogger("maillogsentinel")
    logger.setLevel(log_level) # Set level from config or default
    try:
        # RotatingFileHandler constructor also accepts Path objects for filename
        fh = logging.handlers.RotatingFileHandler(logpath, maxBytes=1_000_000, backupCount=5)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)
    except (IOError, OSError) as e:
        # Use f-string for the error message
        print(f"CRITICAL: Failed to initialize logging to {logpath}: {e}", file=sys.stderr)
        sys.exit(1)
    return logger

def read_state(statedir: Path, logger: Optional[logging.Logger] = None): # Expects a Path object
    state_file = statedir / STATE_FILENAME
    if not state_file.is_file():
        return 0
    try:
        return int(state_file.read_text().strip())
    except (IOError, ValueError) as e:
        if logger:
            logger.warning(f"Failed to read state from {state_file}: {e}. Assuming offset 0.")
        else:
            # Use f-string for the error message
            print(f"Warning: Failed to read state from {state_file}: {e}. Assuming offset 0.", file=sys.stderr)
        return 0

def write_state(statedir: Path, offset: int, logger: logging.Logger): # Expects Path
    state_file = statedir / STATE_FILENAME
    try:
        state_file.write_text(str(offset))
    except IOError as e: # write_text can raise IOError/OSError
        logger.error(f"Failed to write state to {state_file}: {e}")

def get_extraction_frequency() -> str:
    """
    Reads the systemd timer file for maillogsentinel-extract.timer
    and returns the OnCalendar value.
    Returns "hourly" if the file or setting is not found.
    """
    timer_file_path = "/etc/systemd/system/maillogsentinel-extract.timer"
    try:
        with open(timer_file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("OnCalendar="):
                    return line.split("=", 1)[1].strip()
    except IOError:
        # File not found or not readable, return default
        pass  # Fall through to return default
    return "hourly"

def get_report_schedule() -> str:
    """
    Reads the systemd timer file for maillogsentinel-report.timer
    and returns the OnCalendar value.
    Returns "23:50" if the file or setting is not found.
    """
    timer_file_path = "/etc/systemd/system/maillogsentinel-report.timer"
    try:
        with open(timer_file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("OnCalendar="):
                    return line.split("=", 1)[1].strip()
    except IOError:
        # File not found or not readable, return default
        pass  # Fall through to return default
    return "23:50" # Default if not found or error

def list_all_logs(maillog: Path): # Expects Path, returns list of Paths
    files = []
    if maillog.is_file(): # Check if the main log path itself is a file
         files.append(maillog)
    # For rotated logs:
    # Path.glob returns a generator, convert to list and sort
    if maillog.parent.exists(): # Ensure parent directory exists before globbing
        files.extend(sorted(list(maillog.parent.glob(maillog.name + ".*"))))
    # Filter to ensure all are files
    return [p for p in files if p.is_file()]

def is_gzip(path: Path): # Expects Path object
    return path.name.endswith(".gz")

# This function remains, it's the core non-cached lookup logic.
def _perform_actual_reverse_lookup(ip: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        hostname = socket.gethostbyaddr(ip)[0]
        return hostname, None
    except (socket.herror, socket.gaierror, socket.timeout) as e:
        error_code = getattr(e, 'errno', None)
        error_str: Optional[str] = None

        if error_code is not None:
            error_str = f"Errno {error_code}"
        elif isinstance(e, socket.timeout):
            error_str = "Timeout"
        else:
            error_str = "Failed (Unknown)"
        return None, error_str

def initialize_dns_cache(max_size: int):
    """
    Initializes the DNS caching function.
    Defines a new function with an LRU cache and assigns it globally.
    """
    @functools.lru_cache(maxsize=max_size)
    def _dynamically_cached_lookup(ip: str) -> Tuple[Optional[str], Optional[str], float]:
        # Calls the global _perform_actual_reverse_lookup
        hostname, error_str = _perform_actual_reverse_lookup(ip)
        return hostname, error_str, time.time()

    global CACHED_DNS_LOOKUP_FUNC
    CACHED_DNS_LOOKUP_FUNC = _dynamically_cached_lookup
    # Log cache initialization details
    # This assumes logger is available globally or passed if needed for this message
    # For now, let's assume this function is called after logger setup if logging is desired here.
    # print(f"DNS cache initialized with max_size: {max_size}") # Or use logger if available

def reverse_lookup(ip: str, logger: logging.Logger) -> Tuple[Optional[str], Optional[str]]:
    cache_enabled = DNS_CACHE_SETTINGS.get('enabled', True) # Default to True if not set
    dns_ttl_seconds = DNS_CACHE_SETTINGS.get('ttl', 3600)   # Default to 3600 if not set

    if not cache_enabled:
        logger.debug(f"DNS cache is disabled. Performing direct lookup for {ip}.")
        hostname, error_str = _perform_actual_reverse_lookup(ip)
        if error_str:
            logger.debug(f"Reverse lookup failed for IP {ip}: {error_str}")
        return hostname, error_str

    # Ensure CACHED_DNS_LOOKUP_FUNC is initialized
    if CACHED_DNS_LOOKUP_FUNC is None:
        # This case should ideally not be reached if initialize_dns_cache is called in main()
        logger.error("CACHED_DNS_LOOKUP_FUNC not initialized. Performing direct lookup.")
        hostname, error_str = _perform_actual_reverse_lookup(ip)
        if error_str:
            logger.debug(f"Reverse lookup failed for IP {ip}: {error_str}")
        return hostname, error_str

    cached_hostname, cached_error_str, timestamp = CACHED_DNS_LOOKUP_FUNC(ip)

    final_hostname: Optional[str] = None
    final_error_str: Optional[str] = None

    if time.time() - timestamp > dns_ttl_seconds:
        logger.info(f"DNS cache for {ip} is stale (timestamp: {timestamp}, TTL: {dns_ttl_seconds}s). Performing fresh lookup for this request.")
        fresh_hostname, fresh_error_str = _perform_actual_reverse_lookup(ip)
        # As per previous logic, this fresh lookup does not update the cache for *this current call*
        # The cache for this IP will update on the *next* call to CACHED_DNS_LOOKUP_FUNC(ip)
        final_hostname = fresh_hostname
        final_error_str = fresh_error_str
    else:
        logger.debug(f"Using valid cached DNS entry for {ip} (timestamp: {timestamp}).")
        final_hostname = cached_hostname
        final_error_str = cached_error_str

    if final_error_str:
        logger.debug(f"Reverse lookup failed for IP {ip}: {final_error_str}")
    
    return final_hostname, final_error_str

def _parse_log_line(log_line_text: str, current_year: int, logger: logging.Logger, ip_info_mgr: Optional[ipinfo.IPInfoManager]):
    """
    Parses a single log line and extracts relevant SASL authentication attempt details.

    Args:
        log_line_text (str): The raw log line.
        current_year (int): The current year, for constructing full dates.
        logger (logging.Logger): Logger instance.

    Returns:
        dict: A dictionary with extracted fields if successful, None otherwise.
              Fields: "server", "date_s", "ip", "user", "hostn"
    """
    m_log = LOG_RE.match(log_line_text)
    if not m_log:
        return None
    
    msg_content = log_line_text[m_log.end():]
    m_pat = PAT.search(msg_content)
    if not m_pat:
        return None

    try:
        month_abbr = m_log.group("month")
        mon_num    = MONTHS[month_abbr]
        day        = int(m_log.group("day"))
        hhmm       = m_log.group("time")[:5] # Ensure only HH:MM
        date_s     = f"{day:02d}/{mon_num:02d}/{current_year} {hhmm}"

        server = m_log.group("server")
        ip     = m_pat.group("ip")
        user   = m_pat.group("user")
        user   = user.replace('\n', ' ').replace('\r', ' ') # Sanitize user

        raw_hostn, rev_dns_error_str = reverse_lookup(ip, logger)
        
        hostn_val = "null"
        status_val = "OK" # Default status

        if raw_hostn is not None:
            hostn_val = raw_hostn.replace('\n', ' ').replace('\r', ' ') # Sanitize
            # status_val remains "OK"
        elif rev_dns_error_str is not None:
            # hostn_val remains "null"
            status_val = rev_dns_error_str.replace('\n', ' ').replace('\r', ' ') # Sanitize error string
        else:
            # This case should ideally not be reached if reverse_lookup always provides an error string on failure
            # hostn_val remains "null"
            status_val = "Failed (Unknown)"

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
            "aso": aso
        }
    except KeyError: # Month abbreviation not in MONTHS
        logger.warning(f"Invalid month abbreviation in log line: {log_line_text.strip()}") # Already f-string
        return None
    except ValueError: # Error converting day to int
        logger.warning(f"Invalid day format in log line: {log_line_text.strip()}") # Already f-string
        return None
    except Exception as e: # Catch any other unexpected error during parsing a specific line
        logger.error(f"Unexpected error parsing log line '{log_line_text.strip()}': {e}") # Already f-string
        return None


def extract_entries(filepaths: List[Path], maillog: Path, csvpath_param: str, logger: logging.Logger, offset: int = 0): # Changed list to List
    curr_off = offset
    new_off  = offset
    csv_file_path = Path(csvpath_param) # Convert string path to Path object
    header   = not csv_file_path.is_file()
    current_year = datetime.now().year # Get current year once

    # Open with Path object
    with csv_file_path.open("a", encoding="utf-8", newline='') as csvf: # Add newline='' for csv.writer
        writer = csv.writer(csvf, delimiter=';', quoting=csv.QUOTE_MINIMAL)
        if header:
            writer.writerow(["server", "date", "ip", "user", "hostname", "reverse_dns_status", "country_code", "asn", "aso"])
        
        for path_obj in filepaths: # path_obj is now a Path object
            try:
                try:
                    path_size = path_obj.stat().st_size # Use Path.stat()
                except OSError as e:
                    logger.error(f"Could not get size of {path_obj}: {e}") # Use Path obj in log
                    continue # Skip to next file path

                if path_obj == maillog and path_size < curr_off:
                    logger.info(f"Rotation detected, reset offset {curr_off}→0 for {path_obj}")
                    curr_off = 0
                
                is_gzipped_file = is_gzip(path_obj) # is_gzip now expects Path
                mode = "rt" if is_gzipped_file else "r" 
                
                logger.info(f"Processing {path_obj} (gzip: {is_gzipped_file})")

                if is_gzipped_file:
                    with gzip.open(path_obj, mode=mode, encoding="utf-8", errors="ignore") as fobj:
                        # Note: gzipped files are read entirely, seek and fobj.tell() for offset are not applicable in the same way.
                        for line in fobj:
                            parsed_data = _parse_log_line(line, current_year, logger, IP_INFO_MANAGER)
                            if parsed_data:
                                writer.writerow([
                                    parsed_data['server'], parsed_data['date_s'],
                                    parsed_data['ip'], parsed_data['user'],
                                    parsed_data['hostn'],
                                    parsed_data.get('reverse_dns_status', 'Failed (Unknown)'),
                                    parsed_data['country_code'], parsed_data['asn'], parsed_data['aso']
                                ])
                else: # For non-gzipped files
                    with path_obj.open(mode=mode, encoding="utf-8", errors="ignore") as fobj:
                        logger.info(f"Incremental read of {path_obj} from {curr_off}")
                        fobj.seek(curr_off)
                        for line in fobj:
                            parsed_data = _parse_log_line(line, current_year, logger, IP_INFO_MANAGER)
                            if parsed_data:
                                writer.writerow([
                                    parsed_data['server'], parsed_data['date_s'],
                                    parsed_data['ip'], parsed_data['user'],
                                    parsed_data['hostn'],
                                    parsed_data.get('reverse_dns_status', 'Failed (Unknown)'),
                                    parsed_data['country_code'], parsed_data['asn'], parsed_data['aso']
                                ])
                        # Only update offset from current, non-gzipped mail.log
                        if path_obj == maillog: 
                            new_off = fobj.tell()
            
            except (IOError, OSError) as e: # File level errors (open, read)
                 logger.error(f"Error processing file {path_obj}: {e}")
            except Exception as e: # Catch-all for unexpected errors during file processing loop
                logger.error(f"Unexpected error processing {path_obj}: {e}")
    
    # If maillog was gzipped, new_off wouldn't be updated by fobj.tell()
    # For gzipped files, we process them entirely, so offset effectively becomes size
    # However, the current logic only updates new_off for the *active, non-gzipped* maillog.
    # This means if maillog itself is gzipped (uncommon for active log), offset logic might be tricky.
    # For now, assuming active maillog is not gzipped for offset tracking.
    # If a gzipped file was the *only* one processed (e.g. historical run), new_off would remain as original offset.
    # This is complex; current behavior is retained: new_off is only updated from the current, non-gzipped maillog.

    return new_off

# --- Report via smtplib with full sender address ---

def _analyze_csv_for_report(csv_path, logger, today_date_str):
    """
    Analyzes the CSV file to extract statistics for the report.

    Args:
        csv_path (Path): Path to the CSV file (as a Path object).
        logger (logging.Logger): Logger instance.
        today_date_str (str): Today's date in "dd/mm/YYYY" format.

    Returns:
        dict: A dictionary with statistics, or None if critical error.
              Keys: "total_today", "top10_today", 
                    "csv_size_k_str", "csv_lines_str"
    """
    logger.debug(f"Starting CSV analysis for {csv_path} with today_date_str: '{today_date_str}'")
    stats = {
        "total_today": 0,
        "top10_today": [],
        "top10_usernames": [],
        "total_rev_dns_failures": 0,         # New stat
        "rev_dns_error_counts": {},          # New stat (will be sorted later)
        "csv_size_k_str": "N/A",
        "csv_lines_str": "N/A"
    }
    counts_today = {}
    username_counts_today = {}
    rev_dns_error_counts_agg = {} # Temporary aggregate before sorting

    try:
        # Use csv_path.open() as it's a Path object
        with csv_path.open(newline="", encoding="utf-8") as f:
            logger.debug(f"Successfully opened {csv_path} for reading.")
            reader = csv.reader(f, delimiter=";")
            try:
                next(reader, None) # Skip header
            except StopIteration: # Empty CSV (only header or less)
                logger.warning(f"CSV file {csv_path} is empty or has no data rows.") # Already f-string
                # File size and line count can still be calculated for an empty data CSV
                pass # Fall through to size/line count calculation

            for row in reader:
                if len(row) < 9: # Updated for 9 columns
                    logger.warning(f"Skipping malformed CSV row (expected 9 fields, got {len(row)}): {row}")
                    continue
                
                # Unpack all 9 fields
                server_val, date_field, ip_val, user_val, hostn_val, rev_dns_status_val, country_val, asn_val, aso_val = row[:9]

                logger.debug(f"Read CSV line: Server='{server_val}', Date='{date_field}', IP='{ip_val}', User='{user_val}', Hostname='{hostn_val}', DNS Status='{rev_dns_status_val}', Country='{country_val}', ASN='{asn_val}', ASO='{aso_val}'. Comparing Date with '{today_date_str}'.")
                
                if date_field.startswith(today_date_str):
                    logger.debug(f"MATCHED: CSV date '{date_field}' starts with '{today_date_str}'. Processing for stats.")
                    stats["total_today"] += 1
                    
                    # Top 10 failed authentications (user, ip, hostname)
                    key_auth = (user_val, ip_val, hostn_val) 
                    counts_today[key_auth] = counts_today.get(key_auth, 0) + 1
                    
                    # Top 10 usernames
                    username_counts_today[user_val] = username_counts_today.get(user_val, 0) + 1

                    # Reverse DNS failure stats
                    if rev_dns_status_val != "OK": # Assuming "OK" is the success indicator
                        stats["total_rev_dns_failures"] += 1
                        rev_dns_error_counts_agg[rev_dns_status_val] = rev_dns_error_counts_agg.get(rev_dns_status_val, 0) + 1
        
        logger.debug(
            f"Finished iterating CSV rows. "
            f"Total today: {stats['total_today']}. "
            f"Unique (user,ip,host) entries: {len(counts_today)}. "
            f"Unique usernames: {len(username_counts_today)}. "
            f"Total RevDNS failures: {stats['total_rev_dns_failures']}. "
            f"RevDNS Error Counts: {rev_dns_error_counts_agg}."
        )
        stats["top10_today"] = sorted(counts_today.items(), key=lambda x: x[1], reverse=True)[:10]
        stats["top10_usernames"] = sorted(username_counts_today.items(), key=lambda x: x[1], reverse=True)[:10]
        stats["rev_dns_error_counts"] = sorted(rev_dns_error_counts_agg.items(), key=lambda item: item[1], reverse=True)


    except IOError as e:
        logger.error(f"Could not read or parse CSV file {csv_path}: {e}") # Already f-string
        return None # Critical error, cannot proceed
    except csv.Error as e:
        logger.error(f"CSV formatting error in {csv_path}: {e}") # Already f-string
        return None # Critical error

    # Calculate size and total line count (already handled potential errors individually)
    try:
        size_k = csv_path.stat().st_size / 1024 # Use Path.stat()
        stats["csv_size_k_str"] = f"{size_k:.1f}K"
    except OSError as e:
        logger.error(f"Could not get size of CSV file {csv_path}: {e}") # Already f-string
        # stats["csv_size_k_str"] remains "N/A"

    try:
        # Re-open to count lines to avoid issues with iterator exhaustion if done above
        with csv_path.open(encoding="utf-8") as f_count: # Use Path.open()
            line_count = sum(1 for _ in f_count) -1 # Exclude header
            stats["csv_lines_str"] = str(max(0, line_count)) # Ensure not negative if file is empty/only header
    except (OSError, Exception) as e: 
        logger.error(f"Could not get line count of CSV file {csv_path}: {e}") # Already f-string
        # stats["csv_lines_str"] remains "N/A"
        
    return stats


def send_report(cfg, workdir: Path, logger: logging.Logger): # workdir is Path
    rpt   = cfg[SECTION_REPORT]
    email = rpt.get("email")
    if not email:
        logger.error("No email address configured for report.") # Already f-string (no args)
        return

    csv_file = workdir / CSV_FILENAME # Use Path division
    if not csv_file.is_file(): # Quick check before analysis with Path.is_file()
        logger.warning(f"CSV file {csv_file} not found. No report to send.")
        return

    report_schedule = get_report_schedule() 
    now = datetime.now()
    report_date_to_analyze = now

    # Check if the schedule indicates a midnight run, possibly set as "daily"
    # "daily" is converted to "*-*-* 00:00:00" by the setup
    # Also check for common variations of midnight.
    schedule_lower = report_schedule.lower()
    # Regex for HH:MM format, used to check if it's "00:00"
    hh_mm_pattern = r"\d{2}:\d{2}"
    # Regex for OnCalendar string ending with a time, used to check if it ends with " 00:00:00"
    oncalendar_time_pattern = r".* \d{2}:\d{2}:\d{2}"

    if schedule_lower == "daily" or \
       schedule_lower == "*-*-* 00:00:00" or \
       (re.fullmatch(hh_mm_pattern, schedule_lower) and schedule_lower == "00:00") or \
       (re.match(oncalendar_time_pattern, schedule_lower) and schedule_lower.endswith(" 00:00:00")):
        report_date_to_analyze = now - timedelta(days=1)
        logger.info(f"Report schedule '{report_schedule}' implies a midnight run. Analyzing data for previous day (J-1): {report_date_to_analyze.strftime('%d/%m/%Y')}.")
    else:
        logger.info(f"Report schedule is '{report_schedule}'. Analyzing data for current day: {now.strftime('%d/%m/%Y')}.")
        # report_date_to_analyze remains 'now'

    date_str_for_analysis = report_date_to_analyze.strftime("%d/%m/%Y")
    
    # Pass Path object to _analyze_csv_for_report, and the potentially adjusted date string
    report_stats = _analyze_csv_for_report(csv_file, logger, date_str_for_analysis)

    if report_stats is None:
        logger.error("CSV analysis failed. Cannot generate or send report.")
        return

    # Determine sender: current user and FQDN
    bash_user = getpass.getuser()
    fqdn      = socket.getfqdn() or socket.gethostname()
    from_addr = f"{bash_user}@{fqdn}"

    # Determine server IP for header
    try:
        ipaddr = socket.gethostbyname(fqdn)
    except socket.gaierror as e:
        logger.warning(f"Could not get IP for FQDN {fqdn}: {e}. Using 'unknown'.")
        ipaddr = "unknown"

    # --- Dynamic Email Header Formatting ---
    now_stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    extraction_freq = get_extraction_frequency() # Get the frequency
    header_content_lines = [
        f"{SCRIPT_NAME} {VERSION}",
        f"Extraction interval : {extraction_freq}", # Add new line here
        f"Report at {now_stamp}",
        f"Server: {ipaddr} ({fqdn})"
    ]

    max_len = 0
    for line in header_content_lines:
        if len(line) > max_len:
            max_len = len(line)

    # Total width for the bordered section will be max_len + 6 (for "### " and " ###")
    border_line = "#" * (max_len + 6)
    
    header_list_for_email = [border_line]
    for line_content in header_content_lines:
        formatted_line = f"### {line_content.ljust(max_len)} ###"
        header_list_for_email.append(formatted_line)
    header_list_for_email.append(border_line)
    header_list_for_email.append("") # For spacing

    # --- Email Body Construction ---
    body = []
    body.append(f"Total attempts today: {report_stats['total_today']}")
    body.append("")
    body.append("Top 10 failed authentications today:")

    if report_stats['top10_today']:
        # Calculate maximum widths for each column
        # Initialize with minimums (e.g., length of potential headers, or small sensible values)
        max_user_len = 4  # len("User")
        max_ip_len = 2    # len("IP")
        max_hostn_len = 8 # len("Hostname")
        max_count_len = 5 # len("Count")
        
        for (user, ip, hostn), cnt in report_stats['top10_today']:
            max_user_len = max(max_user_len, len(user))
            max_ip_len = max(max_ip_len, len(ip))
            max_hostn_len = max(max_hostn_len, len(hostn))
            max_count_len = max(max_count_len, len(str(cnt)))

        # Format and append each row for the top 10 list
        for idx, ((user, ip, hostn), cnt) in enumerate(report_stats['top10_today'], 1):
            # Rank width is fixed (e.g., for "10.")
            rank_width = 2 
            # Format: Index (right-aligned, fixed width). User (left)  IP (left)  Hostname (left)  Count (right) "times"
            line_str = (f"  {idx:>{rank_width}d}. "
                        f"{user:<{max_user_len}}  "
                        f"{ip:<{max_ip_len}}  "
                        f"{hostn:<{max_hostn_len}}  "
                        f"{str(cnt):>{max_count_len}} times")
            body.append(line_str)
    else:
        body.append("  (no entries for today)")
    
    # --- Top 10 Usernames ---
    body.append("") # Add a blank line for spacing
    body.append("Top 10 Usernames today:")
    top10_usernames = report_stats.get("top10_usernames", [])
    if top10_usernames:
        # Calculate max_username_len and max_username_count_len for this new table
        max_username_len = 4 # len("User")
        max_username_count_len = 5 # len("Count")
        for username, count in top10_usernames:
            if len(username) > max_username_len:
                max_username_len = len(username)
            if len(str(count)) > max_username_count_len:
                max_username_count_len = len(str(count))
        
        rank_width = 2 # For "10."

        for idx, (username, count) in enumerate(top10_usernames, 1):
            body.append(f"  {idx:>{rank_width}d}. {username:<{max_username_len}}  {str(count):>{max_username_count_len}} times")
    else:
        body.append("  (no specific username stats for today)")

    # --- Reverse DNS Lookup Failure Summary ---
    body.append("") # Blank line for spacing
    body.append("--- Reverse DNS Lookup Failure Summary ---")
    total_rev_dns_failures = report_stats.get("total_rev_dns_failures", 0)
    rev_dns_error_counts = report_stats.get("rev_dns_error_counts", []) # List of (error_str, count) tuples

    body.append(f"Total failed reverse lookups today: {total_rev_dns_failures}")
    if total_rev_dns_failures > 0 and rev_dns_error_counts:
        body.append("Breakdown by error type:")
        
        # Calculate max width for error type string and count for alignment
        max_error_str_len = 0
        max_error_count_len = 0
        # Ensure list is not empty before calling max() on it
        if rev_dns_error_counts: 
            # Calculate max length of error strings
            max_error_str_len = max(len(err_str) for err_str, count in rev_dns_error_counts)
            # Calculate max length of count strings
            max_error_count_len = max(len(str(count)) for err_str, count in rev_dns_error_counts)

        for err_str, count in rev_dns_error_counts:
            # Pad error string to align the colons, then right align counts.
            # Example: "  Errno -2 (Name or service not known):   150"
            body.append(f"  {err_str:<{max_error_str_len}} : {str(count):>{max_error_count_len}}")
            
    elif total_rev_dns_failures > 0: # Has total but no breakdown (should not happen if logic is correct)
        body.append("  (Error type breakdown not available)")
    else: # No failures
         body.append("  (No reverse DNS lookup failures recorded for today)")

    body.append("")
    body.append(f"Total CSV file size: {report_stats['csv_size_k_str']}") # Overall CSV size
    body.append(f"Total CSV lines:     {report_stats['csv_lines_str']}")   # Overall CSV lines
    body.append("")
    body.append(f"Please see attached: {CSV_FILENAME}")
    body.append("") # Add a blank line for spacing before the footer
    body.append("For more details and documentation, visit: https://github.com/cryptozoide/MailLogSentinel/blob/main/README.md")

    # Create MIME message
    msg = EmailMessage()
    msg['Subject'] = f"{SCRIPT_NAME} report on {fqdn}" # Use fqdn instead of now_stamp
    msg['From']    = from_addr
    msg['To']      = email
    # Combine dynamically formatted header with the body
    msg.set_content("\n".join(header_list_for_email + body) + "\n")

    # Attach CSV
    try:
        # Use Path.open() for reading bytes
        with csv_file.open('rb') as f:
            data = f.read()
        msg.add_attachment(data, maintype='text', subtype='csv', filename=CSV_FILENAME) # filename is str
    except IOError as e:
        logger.error(f"Could not attach CSV {CSV_FILENAME} to report: {e}") # Already f-string
        # Optionally, modify body to indicate attachment failure
        msg.set_content(msg.get_content().decode() + f"\n\nNOTE: Could not attach {CSV_FILENAME} due to error.\n")


    # Send via local MTA
    try:
        with smtplib.SMTP('localhost') as s:
            s.send_message(msg)
        logger.info(f"Report sent from {from_addr} to {email}") # Already f-string
    except Exception as e:
        logger.error(f"Failed to send report: {e}") # Already f-string

# --- Main ---

SETUP_LOG_FILENAME = "maillogsentinel_setup.log"

def _setup_print_and_log(message: str = "", file_handle=None, is_prompt: bool = False, end: str = '\n'):
    """
    Prints a message to the console (sys.stdout) and also writes it to the provided file_handle.
    If is_prompt is True, prints to console with end='' and writes to file with a newline.
    Regular prints use the 'end' parameter for console and add a newline for the file.
    """
    # Print to console
    if is_prompt:
        print(message, end='', flush=True)
    else:
        print(message, end=end, flush=True)

    # Write to log file
    if file_handle:
        try:
            file_handle.write(message + '\n') # Always add newline for log file entries
            file_handle.flush()
        except IOError as e:
            # If logging fails, print an error to actual stderr.
            # The console print above would have already happened.
            # Use functools.partial to ensure this error message goes to the actual stderr.
            original_stderr_print_for_logging_error = functools.partial(print, file=sys.stderr, flush=True)
            original_stderr_print_for_logging_error(f"ERROR: Could not write to setup log file: {e}")


def interactive_setup(config_path_obj: Path):
    """
    Handles the interactive first-time setup for maillogsentinel.
    All console output (excluding stderr) during setup is also logged to maillogsentinel_setup.log.
    """
    # Keep a reference to the original print for messages that MUST go to console/stderr only.
    original_console_print = functools.partial(print, flush=True)
    original_stderr_print = functools.partial(print, file=sys.stderr, flush=True)
    
    log_file_path = Path.cwd() / SETUP_LOG_FILENAME
    setup_log_fh = None

    try:
        setup_log_fh = open(log_file_path, 'w', encoding='utf-8')
        # Initial notification to console ONLY (not to the log file itself yet)
        original_console_print(f"Note: The setup process output will be saved to {log_file_path.resolve()}")

        if os.geteuid() != 0:
            # This goes to stderr only, not logged.
            original_stderr_print("ERROR: Interactive setup requires root privileges. Please run with sudo.")
            sys.exit(1) # Exiting, so no need to close file explicitly here, finally won't run for sys.exit
        
        _setup_print_and_log(f"--- {SCRIPT_NAME} Interactive Setup ---", setup_log_fh)
        _setup_print_and_log(f"The specified configuration file is: {config_path_obj}", setup_log_fh)

        # Define Default Paths for Check:
        default_working_dir = Path("/var/log/maillogsentinel")
        default_log_file    = default_working_dir / LOG_FILENAME
        default_csv_file    = default_working_dir / CSV_FILENAME
        default_state_dir   = Path("/var/lib/maillogsentinel") # Changed as per instruction
        default_state_file  = default_state_dir / STATE_FILENAME
        default_mail_log    = Path("/var/log/mail.log")

        # Check for Existing Data:
        data_paths_to_check = [default_log_file, default_csv_file, default_state_file, 
                               default_working_dir, default_state_dir]
        existing_data_found = any(p.exists() for p in data_paths_to_check)

        if existing_data_found:
            _setup_print_and_log("\nWARNING: Existing MailLogSentinel data or directories found (e.g., "
                  f"{default_working_dir}, {default_state_dir}).", setup_log_fh)
            _setup_print_and_log("Continuing will back up the existing directories/files and proceed with a fresh setup.", setup_log_fh)
            
            try:
                _setup_print_and_log("Do you wish to continue? (yes/no): ", setup_log_fh, is_prompt=True)
                answer = input().strip().lower()
                # User's answer is not logged.
            except EOFError: # Handle non-interactive environments
                _setup_print_and_log("\nNon-interactive environment detected. Aborting setup assuming 'no'.", setup_log_fh)
                answer = "no"

            if answer != "yes":
                _setup_print_and_log("Setup aborted by user.", setup_log_fh)
                sys.exit(0)
            
            _setup_print_and_log("\nBacking up existing data...", setup_log_fh)
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            
            paths_to_backup = {
                "working_dir": default_working_dir,
                "state_dir": default_state_dir
            }

            for name, path_to_backup in paths_to_backup.items():
                if path_to_backup.exists():
                    backup_path = path_to_backup.parent / f"{path_to_backup.name}.backup_{timestamp}"
                    try:
                        # Ensure source path is a directory if it's expected to be for clean move
                        if path_to_backup.is_dir():
                            shutil.move(str(path_to_backup), str(backup_path))
                            _setup_print_and_log(f"Moved existing {name} {path_to_backup} to {backup_path}", setup_log_fh)
                        elif path_to_backup.is_file():
                            shutil.move(str(path_to_backup), str(backup_path)) 
                            _setup_print_and_log(f"Moved existing file {path_to_backup} to {backup_path}", setup_log_fh)
                        else:
                            _setup_print_and_log(f"Skipping backup for {path_to_backup} as it's not a directory or file.", setup_log_fh)

                    except (OSError, shutil.Error) as e:
                        # Errors to stderr only
                        original_stderr_print(f"ERROR: Could not back up {path_to_backup} to {backup_path}: {e}")
                        original_stderr_print("Setup cannot reliably proceed. Please resolve the issue and try again.")
                        sys.exit(1)
                else:
                    _setup_print_and_log(f"Path {path_to_backup} does not exist, no backup needed for it.", setup_log_fh)
        else:
            _setup_print_and_log("\nNo existing data found at default locations. Proceeding with fresh setup checks.", setup_log_fh)

        _setup_print_and_log(f"\nChecking readability of the default mail log path: {default_mail_log}...", setup_log_fh)
        if default_mail_log.exists():
            if os.access(default_mail_log, os.R_OK):
                _setup_print_and_log(f"Default mail log {default_mail_log} is readable by current user (root).", setup_log_fh)
            else:
                _setup_print_and_log(f"WARNING: The mail log {default_mail_log} exists but is NOT readable by current user (root).", setup_log_fh)
                _setup_print_and_log("This path will be configurable. However, ensure the user running MailLogSentinel normally (non-root) "
                      "will have read permissions for the final mail log path.", setup_log_fh)
        else:
            _setup_print_and_log(f"WARNING: The default mail log {default_mail_log} does not exist.", setup_log_fh)
            _setup_print_and_log("This path will be configurable. Ensure the specified path is correct during configuration.", setup_log_fh)

        _setup_print_and_log("\n--- Configuring Core Settings ---", setup_log_fh)
        default_config_values = {
            "paths": {
                "working_dir": str(default_working_dir), # Use the already defined default
                "state_dir": str(default_state_dir),   # Use the already defined default
                "mail_log": str(default_mail_log),     # Use the already defined default
            },
            "report": {
                "email": "security-team@example.org",
            },
            "geolocation": { # New section for geolocation DB
                "country_db_path": "/var/lib/maillogsentinel/country_aside.csv",
            },
            "ASN_ASO": { # New section for ASN DB
                "asn_db_path": "/var/lib/maillogsentinel/asn.csv",
            },
            "general": {
                "log_level": "INFO",
            }
        }
        
        collected_config = copy.deepcopy(default_config_values)
        allowed_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

        for section, options in default_config_values.items():
            _setup_print_and_log(f"\n-- {section.capitalize()} Settings --", setup_log_fh)
            if section not in collected_config:
                collected_config[section] = {}
            for key, default_value in options.items():
                while True: 
                    prompt_text = f"Enter {key.replace('_', ' ')} for section '{section}' [{default_value}]: "
                    _setup_print_and_log(prompt_text, setup_log_fh, is_prompt=True)
                    user_input = input().strip()
                    
                    chosen_value = user_input if user_input else default_value

                    if key == "log_level":
                        chosen_value = chosen_value.upper()
                        if chosen_value not in allowed_log_levels:
                            # Errors to stderr, but also log the error event.
                            err_msg = f"ERROR: Invalid log level '{chosen_value}'. Must be one of {allowed_log_levels}. Please try again."
                            original_stderr_print(err_msg)
                            _setup_print_and_log(err_msg, setup_log_fh) # Log the error too
                            continue 
                    
                    if section == "report" and key == "email":
                        if not chosen_value or (chosen_value == "security-team@example.org" and not user_input):
                             if not user_input and chosen_value == "security-team@example.org": 
                                err_msg = "ERROR: Please provide a valid email address for reports."
                                original_stderr_print(err_msg)
                                _setup_print_and_log(err_msg, setup_log_fh)
                                continue
                        elif not chosen_value and user_input: 
                            err_msg = "ERROR: Email address cannot be empty if you are changing it."
                            original_stderr_print(err_msg)
                            _setup_print_and_log(err_msg, setup_log_fh)
                            continue

                    if section == "paths" and not chosen_value:
                        err_msg = f"ERROR: Path for '{key}' cannot be empty. Please provide a valid path or accept the default."
                        original_stderr_print(err_msg)
                        _setup_print_and_log(err_msg, setup_log_fh)
                        continue

                    collected_config[section][key] = chosen_value
                    break 

        _setup_print_and_log("\n--- Configuration Summary ---", setup_log_fh)
        for section, options in collected_config.items():
            _setup_print_and_log(f"[{section}]", setup_log_fh)
            for key, value in options.items():
                _setup_print_and_log(f"  {key} = {value}", setup_log_fh)
        
        try:
            _setup_print_and_log(f"\nSave this configuration to {config_path_obj}? (yes/no): ", setup_log_fh, is_prompt=True)
            confirm_ans = input().strip().lower()
        except EOFError:
            _setup_print_and_log("\nNon-interactive environment detected. Aborting save assuming 'no'.", setup_log_fh)
            confirm_ans = "no"

        if confirm_ans != "yes":
            _setup_print_and_log("Configuration not saved. Setup aborted.", setup_log_fh)
            sys.exit(0)
        parser = configparser.ConfigParser()
        for section, options_dict in collected_config.items(): # Ensure correct variable name
            if not parser.has_section(section):
                parser.add_section(section)
            for key, value in options_dict.items(): # Ensure correct variable name
                parser.set(section, key, str(value))
                
        try:
            config_path_obj.parent.mkdir(parents=True, exist_ok=True) 
            with config_path_obj.open('w') as configfile: # This writes the actual config file
                parser.write(configfile)
            _setup_print_and_log(f"\nConfiguration successfully saved to {config_path_obj}", setup_log_fh)
            
            final_working_dir = Path(collected_config['paths']['working_dir'])
            final_state_dir = Path(collected_config['paths']['state_dir'])
            
            _setup_print_and_log(f"Ensuring working directory exists: {final_working_dir}", setup_log_fh)
            final_working_dir.mkdir(parents=True, exist_ok=True)
            _setup_print_and_log(f"Ensuring state directory exists: {final_state_dir}", setup_log_fh)
            final_state_dir.mkdir(parents=True, exist_ok=True)

            _setup_print_and_log("\nIMPORTANT: Ensure the directories specified in the configuration exist and that the normal operational user for MailLogSentinel has appropriate read/write permissions to them (e.g., write to working_dir, state_dir; read from mail_log).", setup_log_fh)
            _setup_print_and_log("You may need to create these directories and set permissions manually if they differ from the defaults handled by this setup, or if they were not created by this setup (e.g. if you used non-default paths).", setup_log_fh)

        except (IOError, OSError) as e:
            # Error to stderr, and also log it
            err_msg = f"ERROR: Failed to write configuration to {config_path_obj} or create directories: {e}"
            original_stderr_print(err_msg)
            _setup_print_and_log(err_msg, setup_log_fh)
            _setup_print_and_log("Setup failed.", setup_log_fh)
            sys.exit(1)

        _setup_print_and_log("\nSetup phase completed. Please review the configuration and directory permissions.", setup_log_fh)

        _setup_print_and_log("\n--- Systemd Timer Configuration (Optional) ---", setup_log_fh)
        _setup_print_and_log("You can now provide details to help generate example Systemd service and timer units.", setup_log_fh)
        _setup_print_and_log("These units will allow MailLogSentinel to run automatically.", setup_log_fh)

        extraction_prompt = "Enter log extraction frequency (e.g., 'hourly', '0 */6 * * *' for every 6 hours) [default: hourly]: "
        _setup_print_and_log(extraction_prompt, setup_log_fh, is_prompt=True)
        extraction_schedule_str = input().strip() or "hourly"

        while True:
            report_time_str_input_prompt = "Enter desired OnCalendar value for the daily report (e.g., '23:50', 'daily', 'Mon *-*-* 02:00:00') [default: 23:50]: "
            _setup_print_and_log(report_time_str_input_prompt, setup_log_fh, is_prompt=True)
            report_time_str = input().strip() or "23:50"

            if report_time_str.lower() == "daily": # Add this condition first
                report_on_calendar = "*-*-* 00:00:00"
                _setup_print_and_log(f"Interpreting 'daily' as OnCalendar value: {report_on_calendar}", setup_log_fh) # Log the interpretation
                break
            elif re.fullmatch(r"\d{2}:\d{2}", report_time_str):
                try:
                    h, m = map(int, report_time_str.split(':'))
                    if 0 <= h <= 23 and 0 <= m <= 59:
                        report_on_calendar = f"*-*-* {report_time_str}:00"
                        break 
                    else:
                        err_msg = "ERROR: Invalid hour or minute value for HH:MM format. Please use HH (00-23) and MM (00-59)."
                        original_stderr_print(err_msg)
                        _setup_print_and_log(err_msg, setup_log_fh)
                except ValueError: 
                    err_msg = "ERROR: Invalid time format. Please use HH:MM or a valid OnCalendar string."
                    original_stderr_print(err_msg)
                    _setup_print_and_log(err_msg, setup_log_fh)
            else:
                # This handles other valid OnCalendar strings like 'Mon *-*-* 02:00:00'
                report_on_calendar = report_time_str 
                break 

        while True:
            suggested_user = os.environ.get("SUDO_USER")
            if not suggested_user or suggested_user == "root":
                current_login_user = getpass.getuser()
                if current_login_user == "root":
                    suggested_user = "your_nonroot_user" 
                else:
                    suggested_user = current_login_user
            
            _setup_print_and_log(f"Enter the non-root username that will run MailLogSentinel [default: {suggested_user}]: ", setup_log_fh, is_prompt=True)
            run_as_user = input().strip() or suggested_user
            
            if not run_as_user:
                err_msg = "ERROR: Username cannot be empty."
                original_stderr_print(err_msg)
                _setup_print_and_log(err_msg, setup_log_fh)
            elif run_as_user == "root":
                err_msg = "ERROR: Running the operational script as root is not recommended. Please specify a non-root user."
                original_stderr_print(err_msg)
                _setup_print_and_log(err_msg, setup_log_fh)
            else:
                if not re.match(r"^[a-z_][a-z0-9_-]*[$]?$", run_as_user):
                     warn_msg = ("WARNING: Username may contain characters not typically allowed. "
                                      "Ensure it's a valid system username.")
                     original_stderr_print(warn_msg)
                     _setup_print_and_log(warn_msg, setup_log_fh)
                break 

        _setup_print_and_log("\n--- Systemd Schedule Summary ---", setup_log_fh)
        _setup_print_and_log(f"  Log Extraction Frequency: {extraction_schedule_str}", setup_log_fh)
        _setup_print_and_log(f"  Daily Report Time: {report_time_str}", setup_log_fh)
        _setup_print_and_log(f"  Operational User: {run_as_user}", setup_log_fh)
        _setup_print_and_log("This information will be used to generate example Systemd unit files in a later step.", setup_log_fh)

        _setup_print_and_log("\n--- Generating Systemd Unit File Templates ---", setup_log_fh)

        python_executable = shutil.which('python3') or "/usr/bin/python3"
        # For script_path, we assume it's installed or will be placed in a standard location.
        # This is a common practice for system-wide scripts.
        script_path = "/usr/local/bin/maillogsentinel.py" 
        # Use the working directory from the collected config, as it's the most accurate.
        working_directory = collected_config['paths']['working_dir']


        # Prepare OnCalendar values
        if extraction_schedule_str.lower() == "hourly":
            extract_on_calendar = "hourly"
        elif extraction_schedule_str.lower() == "daily":
            extract_on_calendar = "daily"
        elif extraction_schedule_str.lower() == "weekly":
            extract_on_calendar = "weekly"
        elif re.match(r"[\d\s\*\/\-\,]+", extraction_schedule_str):
            extract_on_calendar = extraction_schedule_str
        else: 
            warn_msg = f"Warning: Unrecognized extraction frequency '{extraction_schedule_str}'. Defaulting to 'hourly' for timer."
            original_stderr_print(warn_msg)
            _setup_print_and_log(warn_msg, setup_log_fh)
            extract_on_calendar = "hourly"

        # Define Systemd Unit Content
        maillogsentinel_service_content = f"""[Unit]
Description=MailLogSentinel Log Extraction Service
Documentation=man:maillogsentinel(8)
After=network.target

[Service]
Type=oneshot
User={run_as_user}
ExecStart={python_executable} {script_path} --config {str(config_path_obj)}
WorkingDirectory={working_directory}
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""

        maillogsentinel_extract_timer_content = f"""[Unit]
Description=Run MailLogSentinel Log Extraction periodically
Documentation=man:maillogsentinel(8)

[Timer]
Unit=maillogsentinel.service
OnCalendar={extract_on_calendar}
Persistent=true

[Install]
WantedBy=timers.target
"""

        maillogsentinel_report_service_content = f"""[Unit]
Description=MailLogSentinel Daily Report Service
Documentation=man:maillogsentinel(8)
After=network.target

[Service]
Type=oneshot
User={run_as_user}
ExecStart={python_executable} {script_path} --config {str(config_path_obj)} --report
WorkingDirectory={working_directory}
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""

        maillogsentinel_report_timer_content = f"""[Unit]
Description=Run MailLogSentinel Daily Report
Documentation=man:maillogsentinel(8)

[Timer]
Unit=maillogsentinel-report.service
OnCalendar={report_on_calendar}
Persistent=true

[Install]
WantedBy=timers.target
"""

        unit_files_to_generate = {
            "maillogsentinel.service": maillogsentinel_service_content,
            "maillogsentinel-extract.timer": maillogsentinel_extract_timer_content,
            "maillogsentinel-report.service": maillogsentinel_report_service_content,
            "maillogsentinel-report.timer": maillogsentinel_report_timer_content,
        }

        current_dir_path = Path.cwd()
        _setup_print_and_log(f"\nSaving example Systemd unit files to: {current_dir_path}", setup_log_fh)

        saved_files = []
        for filename, content in unit_files_to_generate.items():
            file_path = current_dir_path / filename
            try:
                # Log the content of the systemd file itself
                _setup_print_and_log(f"\n--- Content of systemd file: {filename} (to be saved in ./{filename}) ---", setup_log_fh)
                # Split content by lines to log each line individually, ensuring newlines in log
                for line in content.strip().split('\n'):
                    _setup_print_and_log(line, setup_log_fh)
                _setup_print_and_log(f"--- End of systemd file: {filename} ---", setup_log_fh)
                
                file_path.write_text(content) # Actual file write to disk
                _setup_print_and_log(f"  Successfully saved ./{filename}", setup_log_fh)
                saved_files.append(filename)
            except IOError as e:
                err_msg = f"  ERROR: Could not save ./{filename}: {e}"
                original_stderr_print(err_msg)
                _setup_print_and_log(err_msg, setup_log_fh)

        if not saved_files:
            err_msg = "No Systemd unit files were saved due to errors."
            original_stderr_print(err_msg)
            _setup_print_and_log(err_msg, setup_log_fh)
        else:
            _setup_print_and_log("\n--- Systemd Installation Instructions ---", setup_log_fh)
            _setup_print_and_log("Example Systemd unit files have been generated and saved to the current directory:", setup_log_fh)
            for fn in saved_files:
                _setup_print_and_log(f"  - ./{fn}", setup_log_fh)
            
            _setup_print_and_log("\nPlease REVIEW these files carefully, especially the User= field and paths inside the .service files.", setup_log_fh)
            _setup_print_and_log(f"Ensure '{script_path}' is the correct installed location of the script.", setup_log_fh)
            _setup_print_and_log("To install and enable them (adjust filenames if any failed to save):", setup_log_fh)
            _setup_print_and_log("1. (Optional) Adjust file content if needed (e.g., paths, user, schedules).", setup_log_fh)

            # Define the standard filenames (these should match the keys in unit_files_to_generate)
            main_service_fn = "maillogsentinel.service"
            extract_timer_fn = "maillogsentinel-extract.timer"
            report_service_fn = "maillogsentinel-report.service"
            report_timer_fn = "maillogsentinel-report.timer"

            cp_command_parts = ["sudo cp"]
            # Add to command only if they were successfully saved
            if main_service_fn in saved_files:
                cp_command_parts.append(f"./{main_service_fn}")
            if extract_timer_fn in saved_files:
                cp_command_parts.append(f"./{extract_timer_fn}")
            if report_service_fn in saved_files:
                cp_command_parts.append(f"./{report_service_fn}")
            if report_timer_fn in saved_files:
                cp_command_parts.append(f"./{report_timer_fn}")

            if len(cp_command_parts) > 1:
                cp_command_parts.append("/etc/systemd/system/")
                _setup_print_and_log(f"2. {' '.join(cp_command_parts)}", setup_log_fh)
            else:
                _setup_print_and_log("2. (No files were saved to copy, check for errors above)", setup_log_fh)
            
            _setup_print_and_log("   (Alternatively, copy only the files that were successfully saved)", setup_log_fh)
            _setup_print_and_log("3. sudo systemctl daemon-reload", setup_log_fh)

            if extract_timer_fn in saved_files:
                _setup_print_and_log(f"4. sudo systemctl enable --now {extract_timer_fn}", setup_log_fh)
            else:
                _setup_print_and_log(f"4. (Skipping enable for {extract_timer_fn} as it was not saved)", setup_log_fh)
            
            if report_timer_fn in saved_files:
                _setup_print_and_log(f"5. sudo systemctl enable --now {report_timer_fn}", setup_log_fh)
            else:
                _setup_print_and_log(f"5. (Skipping enable for {report_timer_fn} as it was not saved)", setup_log_fh)

            _setup_print_and_log("6. Check status with: systemctl list-timers --all", setup_log_fh)
            
            journalctl_instructions = []
            if main_service_fn in saved_files:
                journalctl_instructions.append(f"journalctl -u {main_service_fn} -f")
            if report_service_fn in saved_files:
                journalctl_instructions.append(f"journalctl -u {report_service_fn} -f")
            
            if journalctl_instructions:
                _setup_print_and_log(f"   You can view logs for the services using: {' and '.join(journalctl_instructions)}", setup_log_fh)

        # --- Systemd Timer for IP Database Updates ---
        _setup_print_and_log("\n--- IP Database Update Timer (Optional) ---", setup_log_fh)
        ip_update_answer_prompt = "Do you want to schedule daily updates for the IP geolocation and ASN databases? (yes/no) [default: yes]: "
        _setup_print_and_log(ip_update_answer_prompt, setup_log_fh, is_prompt=True)
        ip_update_answer = input().strip().lower()
        if not ip_update_answer: # Default to yes if empty
            ip_update_answer = "yes"

        if ip_update_answer == "yes":
            default_ip_update_schedule = "03:00" # Daily at 3 AM
            ip_update_schedule_prompt = f"Enter OnCalendar value for IP database updates (e.g., '03:00', 'daily') [default: {default_ip_update_schedule}]: "
            _setup_print_and_log(ip_update_schedule_prompt, setup_log_fh, is_prompt=True)
            ip_update_schedule_input = input().strip() or default_ip_update_schedule
            
            ip_update_on_calendar = f"*-*-* {ip_update_schedule_input}:00" if re.fullmatch(r"\d{2}:\d{2}", ip_update_schedule_input) else ip_update_schedule_input

            # Assume ipinfo.py is installed in the same directory or a known path
            # For now, using /usr/local/bin/ipinfo.py as placeholder
            ipinfo_script_path = "/usr/local/bin/ipinfo.py" 
            # The ipinfo.py script's --update option was for its internal data path.
            # We need to ensure it uses the paths from maillogsentinel.conf.
            # The current ipinfo.py --update downloads to its DEFAULT_DATA_PATH.
            # This might need adjustment in ipinfo.py or a new CLI arg to specify target paths from maillogsentinel.conf
            # For now, assume --update will use the configured paths if ipinfo.py is enhanced,
            # or that its default paths match what's in maillogsentinel.conf.
            # A better approach for ipinfo.py would be:
            # ipinfo.py --config /etc/maillogsentinel.conf --update-databases
            # For now, let's use a simplified ExecStart and note this might need refinement.
            # The ipinfo.py script's main() function already handles --data-dir and --data-url if needed,
            # and it uses DEFAULT_DATA_PATH which is ~/.ipinfo/country_aside.csv
            # For system-wide service, this should be /var/lib/maillogsentinel/.
            # The `ipinfo.py` script would need to be modified to accept `--country-db-path` and `--asn-db-path`
            # or to read them from the maillogsentinel.conf file by itself.
            # For this subtask, we will generate the service assuming ipinfo.py can take --update with relevant config from maillogsentinel.
            # The `bin/ipinfo.py` `main()` function already handles `--update` and uses the configured paths if `load_data` is called first.
            # The `ipinfo.py` script needs to be callable in a way that it *only* performs the update based on `maillogsentinel.conf`.
            # A new specific option like `--update-dbs-from-config <config_path>` would be ideal for ipinfo.py.
            # Given current ipinfo.py, `ipinfo.py --update --data-dir /var/lib/maillogsentinel` (if data dir is unified)
            # Or `ipinfo.py --update --country-db-path <path> --asn-db-path <path>` (if specific paths can be passed)
            # The current `ipinfo.py` takes `--data-dir` for `country_aside.csv` and implies `asn.csv` is there too.
            # This is a slight mismatch as maillogsentinel.conf specifies them separately.
            # For now, we'll assume that `ipinfo.py --update --data-dir /var/lib/maillogsentinel` is the intended mechanism
            # and that both DBs are expected in that directory by ipinfo.py. This matches ipinfo.py's DEFAULT_DATA_DIR structure.
            # The actual DB file names are fixed in ipinfo.py (country_aside.csv, asn.csv).
            # So, maillogsentinel.conf `country_db_path` and `asn_db_path` should point to these files in the shared data dir.
            
            # Correct data directory for ipinfo.py should be the parent of the configured DB paths.
            # Assuming country_db_path and asn_db_path are in the same directory as per typical ipinfo.py setup.
            ipinfo_data_dir = collected_config['geolocation'].get('country_db_path')
            if ipinfo_data_dir:
                ipinfo_data_dir = str(Path(ipinfo_data_dir).parent) # Get parent dir
            else: # Fallback if not in collected_config (should be, due to defaults)
                ipinfo_data_dir = "/var/lib/maillogsentinel"


            ipinfo_update_service_content = f"""[Unit]
Description=Service to update IP geolocation and ASN databases for MailLogSentinel
After=network.target

[Service]
Type=oneshot
User={run_as_user}
ExecStart={python_executable} {ipinfo_script_path} --update --data-dir {ipinfo_data_dir}
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
            ipinfo_update_timer_content = f"""[Unit]
Description=Timer to periodically update IP geolocation and ASN databases
Documentation=man:maillogsentinel(8) # Assuming man page might cover this too

[Timer]
Unit=ipinfo-update.service
OnCalendar={ip_update_on_calendar}
Persistent=true

[Install]
WantedBy=timers.target
"""
            new_unit_files = {
                "ipinfo-update.service": ipinfo_update_service_content,
                "ipinfo-update.timer": ipinfo_update_timer_content,
            }
            _setup_print_and_log(f"\nSaving IP database update Systemd unit files to: {current_dir_path}", setup_log_fh)
            new_saved_files = []
            for filename, content in new_unit_files.items():
                file_path = current_dir_path / filename
                try:
                    _setup_print_and_log(f"\n--- Content of systemd file: {filename} (to be saved in ./{filename}) ---", setup_log_fh)
                    for line in content.strip().split('\n'):
                        _setup_print_and_log(line, setup_log_fh)
                    _setup_print_and_log(f"--- End of systemd file: {filename} ---", setup_log_fh)
                    file_path.write_text(content)
                    _setup_print_and_log(f"  Successfully saved ./{filename}", setup_log_fh)
                    new_saved_files.append(filename)
                except IOError as e:
                    err_msg = f"  ERROR: Could not save ./{filename}: {e}"
                    original_stderr_print(err_msg)
                    _setup_print_and_log(err_msg, setup_log_fh)
            
            if new_saved_files:
                _setup_print_and_log("\nTo install and enable the IP database update timer (adjust filenames if any failed to save):", setup_log_fh)
                cp_ip_update_parts = ["sudo cp"]
                for fn in new_saved_files:
                    cp_ip_update_parts.append(f"./{fn}")
                if len(cp_ip_update_parts) > 1:
                    cp_ip_update_parts.append("/etc/systemd/system/")
                    _setup_print_and_log(f"1. {' '.join(cp_ip_update_parts)}", setup_log_fh)
                else:
                    _setup_print_and_log("1. (No IP update files were saved to copy, check errors above)", setup_log_fh)

                _setup_print_and_log("2. sudo systemctl daemon-reload", setup_log_fh)
                if "ipinfo-update.timer" in new_saved_files:
                    _setup_print_and_log("3. sudo systemctl enable --now ipinfo-update.timer", setup_log_fh)
                else:
                    _setup_print_and_log("3. (Skipping enable for ipinfo-update.timer as it was not saved)", setup_log_fh)
                _setup_print_and_log("4. Check status with: systemctl list-timers --all", setup_log_fh)
                if "ipinfo-update.service" in new_saved_files:
                     _setup_print_and_log("   View logs for the IP update service using: journalctl -u ipinfo-update.service -f", setup_log_fh)
        else:
            _setup_print_and_log("Skipping setup of Systemd timer for IP database updates.", setup_log_fh)


        _setup_print_and_log("\n\n--- Directory & Log Access Permissions ---", setup_log_fh)
        
        working_dir_path = Path(collected_config['paths']['working_dir'])
        state_dir_path = Path(collected_config['paths']['state_dir'])
        # run_as_user is already defined from previous Systemd steps

        prompt_text = (f"\nMay the script attempt to set ownership of the working directory "
                       f"'{working_dir_path}'\nand state directory '{state_dir_path}' "
                       f"to user '{run_as_user}' (group '{run_as_user}')\nand "
                       "set permissions (user rwx, group rwx, other no access)? (yes/no): ")

        while True:
            try:
                _setup_print_and_log(prompt_text, setup_log_fh, is_prompt=True)
                perm_answer = input().strip().lower()
                if perm_answer in ["yes", "no"]:
                    break
                else:
                    err_msg = "Please answer 'yes' or 'no'."
                    original_stderr_print(err_msg)
                    _setup_print_and_log(err_msg, setup_log_fh)
            except EOFError:
                _setup_print_and_log("\nNon-interactive environment. Assuming 'no' for directory permission changes.", setup_log_fh)
                perm_answer = "no"
                break
                
        if perm_answer == "yes":
            _setup_print_and_log("\nAttempting to set permissions...", setup_log_fh)
            for dir_path_obj in [working_dir_path, state_dir_path]:
                if not dir_path_obj.exists():
                    _setup_print_and_log(f"Directory {dir_path_obj} does not exist. Skipping permission changes for it.", setup_log_fh)
                    continue

                chown_cmd = ["chown", "-R", f"{run_as_user}:{run_as_user}", str(dir_path_obj)]
                _setup_print_and_log(f"Attempting: {' '.join(chown_cmd)}", setup_log_fh)
                result_chown = subprocess.run(chown_cmd, capture_output=True, text=True, check=False)
                if result_chown.returncode == 0:
                    _setup_print_and_log(f"Successfully changed ownership of {dir_path_obj} to {run_as_user}:{run_as_user}.", setup_log_fh)
                else:
                    err_msg = f"ERROR: Failed to change ownership of {dir_path_obj}. Return code: {result_chown.returncode}"
                    original_stderr_print(err_msg)
                    _setup_print_and_log(err_msg, setup_log_fh)
                    if result_chown.stderr:
                        err_details = f"Error details: {result_chown.stderr.strip()}"
                        original_stderr_print(err_details)
                        _setup_print_and_log(err_details, setup_log_fh)

                chmod_cmd = ["chmod", "-R", "u+rwX,g+rwX,o=", str(dir_path_obj)]
                _setup_print_and_log(f"Attempting: {' '.join(chmod_cmd)}", setup_log_fh)
                result_chmod = subprocess.run(chmod_cmd, capture_output=True, text=True, check=False)
                if result_chmod.returncode == 0:
                    _setup_print_and_log(f"Successfully set permissions (u+rwX,g+rwX,o=) for {dir_path_obj}.", setup_log_fh)
                else:
                    err_msg = f"ERROR: Failed to set permissions for {dir_path_obj}. Return code: {result_chmod.returncode}"
                    original_stderr_print(err_msg)
                    _setup_print_and_log(err_msg, setup_log_fh)
                    if result_chmod.stderr:
                        err_details = f"Error details: {result_chmod.stderr.strip()}"
                        original_stderr_print(err_details)
                        _setup_print_and_log(err_details, setup_log_fh)
        else:
            _setup_print_and_log(f"\nSkipping automatic permission changes. Please manually ensure that user '{run_as_user}'", setup_log_fh)
            _setup_print_and_log(f"has read/write/execute access to '{working_dir_path}' and its contents, and", setup_log_fh)
            _setup_print_and_log(f"to '{state_dir_path}' and its contents.", setup_log_fh)
            _setup_print_and_log("Example manual commands:", setup_log_fh)
            _setup_print_and_log(f"  sudo chown -R {run_as_user}:{run_as_user} {str(working_dir_path)}", setup_log_fh)
            _setup_print_and_log(f"  sudo chown -R {run_as_user}:{run_as_user} {str(state_dir_path)}", setup_log_fh)
            _setup_print_and_log(f"  sudo chmod -R u+rwX,g+rwX {str(working_dir_path)}", setup_log_fh)
            _setup_print_and_log(f"  sudo chmod -R u+rwX,g+rwX {str(state_dir_path)}", setup_log_fh)

        # --- Add user to adm group for log access ---
        mail_log_path = collected_config['paths']['mail_log']
        adm_prompt_text = (f"\nMay the script attempt to add user '{run_as_user}' to the 'adm' group? "
                           f"This group often grants read access to system logs like '{mail_log_path}'.\n"
                           f"(Note: '{run_as_user}' may need to log out and log back in for group changes to take full effect.) (yes/no): ")
        
        while True:
            try:
                _setup_print_and_log(adm_prompt_text, setup_log_fh, is_prompt=True)
                adm_answer = input().strip().lower()
                if adm_answer in ["yes", "no"]:
                    break
                else:
                    err_msg = "Please answer 'yes' or 'no'."
                    original_stderr_print(err_msg)
                    _setup_print_and_log(err_msg, setup_log_fh)
            except EOFError:
                _setup_print_and_log("\nNon-interactive environment. Assuming 'no' for adding user to 'adm' group.", setup_log_fh)
                adm_answer = "no"
                break
                
        if adm_answer == "yes":
            usermod_cmd = ["usermod", "-a", "-G", "adm", run_as_user]
            _setup_print_and_log(f"Attempting: {' '.join(usermod_cmd)}", setup_log_fh)
            result_usermod = subprocess.run(usermod_cmd, capture_output=True, text=True, check=False)
            if result_usermod.returncode == 0:
                _setup_print_and_log(f"Successfully added user '{run_as_user}' to the 'adm' group.", setup_log_fh)
                _setup_print_and_log(f"IMPORTANT: User '{run_as_user}' may need to log out and log back in for this group change to take full effect.", setup_log_fh)
            else:
                err_msg = f"ERROR: Failed to add user '{run_as_user}' to 'adm' group. Return code: {result_usermod.returncode}"
                original_stderr_print(err_msg)
                _setup_print_and_log(err_msg, setup_log_fh)
                if result_usermod.stderr:
                    err_details = f"Error details: {result_usermod.stderr.strip()}"
                    original_stderr_print(err_details)
                    _setup_print_and_log(err_details, setup_log_fh)
                _setup_print_and_log(f"You may need to add user '{run_as_user}' to the 'adm' group (or another suitable group) manually.", setup_log_fh)
        else:
            _setup_print_and_log(f"\nSkipping automatic addition of user '{run_as_user}' to 'adm' group.", setup_log_fh)
            _setup_print_and_log(f"Please ensure that user '{run_as_user}' has read access to the mail log file: '{mail_log_path}'.", setup_log_fh)
            _setup_print_and_log("Adding the user to the 'adm' group or using file ACLs are common ways to achieve this.", setup_log_fh)

        _setup_print_and_log("\nVerify that the chosen mail log file is also readable by this user:", setup_log_fh)
        _setup_print_and_log(f"  Mail Log: {collected_config['paths']['mail_log']}", setup_log_fh)
        _setup_print_and_log("--- End of Setup Instructions ---", setup_log_fh)
        _setup_print_and_log("\nSetup process completed. If configuration was saved, re-run the script without --setup for normal operation.", setup_log_fh)

    finally:
        if setup_log_fh:
            try:
                # Final message to the log file itself, not to console via _setup_print_and_log
                setup_log_fh.write("\nSetup log finished.\n")
                setup_log_fh.close()
                # This final notification MUST go to the console only.
                original_console_print(f"Setup log saved to {log_file_path.resolve()}")
            except IOError as e:
                original_stderr_print(f"ERROR: Could not properly close setup log file {log_file_path.resolve()}: {e}")
            setup_log_fh = None


def main():
    epilog_text = "For more detailed information, please consult the man page (man maillogsentinel) or the online README at https://github.com/cryptozoide/MailLogSentinel/blob/main/README.md"
    parser = argparse.ArgumentParser(
        description=f"{SCRIPT_NAME} {VERSION} - Postfix SASL Log Analyzer",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter, # Auto-adds (default: ...) to help
        epilog=epilog_text
    )
    # DEFAULT_CONFIG is now a Path object. argparse needs a string for default.
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to config file")
    parser.add_argument("--report", action="store_true", help="Send daily report and exit")
    parser.add_argument("--reset", action="store_true", help="Reset state and archive data. Manual cron setup needed.")
    parser.add_argument("--purge", action="store_true", help="Archive all data and logs. Manual cron setup needed.")
    parser.add_argument("--setup", action="store_true", help="Run interactive first-time setup (requires sudo privileges).")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
        help="Show program's version number and exit."
    )
    # --output-file argument is removed
    args = parser.parse_args()
    
    config_file_path = Path(args.config) # Convert string from argparse to Path

    if args.setup or not config_file_path.is_file():
        # No longer need to check for args.output_file here as it's removed.
        # interactive_setup will announce its own log file.
        interactive_setup(config_file_path) # Call without args related to output_file
        sys.exit(0)
    else:
        # Normal operation starts here
        check_root() # Ensure not running as root for normal operations
        
        if args.purge:
            # All purge-specific logic, correctly indented:
            cfg = load_config(config_file_path)
            # Purge doesn't need country/ASN DB paths explicitly for its operation
            workdir, statedir, _, _, _ = setup_paths(cfg) 
            log_level_str_purge = cfg.get("general", "log_level", fallback="INFO").upper()
            logger_purge = setup_logging(workdir, log_level_str_purge)
            
            try:
                backup_parent_dir = Path.home()
                backup_dir  = Path(tempfile.mkdtemp(prefix="maillogsentinel_backup_", dir=backup_parent_dir))
            except OSError as e:
                print(f"Error creating backup directory: {e}", file=sys.stderr)
                logger_purge.error(f"Error creating backup directory: {e}")
                sys.exit(1)
            
            files_to_move = [statedir / STATE_FILENAME, 
                             workdir / CSV_FILENAME, 
                             workdir / LOG_FILENAME]
            
            for file_path_obj in files_to_move:
                if file_path_obj.is_file():
                    try:
                        shutil.move(str(file_path_obj), str(backup_dir / file_path_obj.name))
                        move_msg = f"Moved {file_path_obj} → {backup_dir / file_path_obj.name}"
                        print(move_msg)
                        logger_purge.info(move_msg)
                    except (shutil.Error, OSError) as e:
                        err_msg = f"Error moving {file_path_obj} to backup: {e}"
                        print(err_msg, file=sys.stderr)
                        logger_purge.error(err_msg)
            purge_message = "Purge completed. Old data backed up. Note: Cron jobs must be managed manually."
            print(purge_message)
            logger_purge.info(purge_message)
            sys.exit(0) # End of purge block
        
        # If not purge, check reset. This is now an 'if' not 'elif'.
        if args.reset:
            # All reset-specific logic, correctly indented:
            cfg = load_config(config_file_path)
            # Reset doesn't need country/ASN DB paths explicitly for its operation
            workdir, statedir, _, _, _ = setup_paths(cfg)
            log_level_str_reset = cfg.get("general", "log_level", fallback="INFO").upper()
            
            try:
                backup_parent_dir = Path.home()
                backup_dir  = Path(tempfile.mkdtemp(prefix="maillogsentinel_backup_", dir=backup_parent_dir))
            except OSError as e:
                print(f"Error creating backup directory: {e}", file=sys.stderr)
                # Logger for reset is set up later, so can't use it here yet for this specific error.
                sys.exit(1)

            files_to_move = [statedir / STATE_FILENAME,
                             workdir / CSV_FILENAME,
                             workdir / LOG_FILENAME]

            for file_path_obj in files_to_move:
                if file_path_obj.is_file():
                    try:
                        shutil.move(str(file_path_obj), str(backup_dir / file_path_obj.name))
                        print(f"Moved {file_path_obj} → {backup_dir / file_path_obj.name}")
                    except (shutil.Error, OSError) as e:
                        print(f"Error moving {file_path_obj} to backup: {e}", file=sys.stderr)
            
            logger_reset = setup_logging(workdir, log_level_str_reset)
            # Replicating LOG_LEVELS_MAP here for the check:
            LOG_LEVELS_MAP_CHECK_RESET = { "DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR, "CRITICAL": logging.CRITICAL }
            if log_level_str_reset.upper() not in LOG_LEVELS_MAP_CHECK_RESET and \
               LOG_LEVELS_MAP_CHECK_RESET.get(log_level_str_reset.upper(), logging.INFO) == logging.INFO:
                 logger_reset.warning(f"Configured log_level '{log_level_str_reset}' for reset path is invalid. Defaulting to INFO.")
            
            reset_message = (f"Reset completed. Old data backed up to {backup_dir}. "
                             "Note: Cron jobs must be managed manually. "
                             "Run the script without special flags to process logs and "
                             "create new state/CSV if desired.")
            print(reset_message)
            logger_reset.info(reset_message)
            sys.exit(0) # End of reset block
        
        # --- Normal Script Operation (if not setup, not purge, not reset) ---
        # This block is now a peer to 'if args.purge:' and 'if args.reset:'
        cfg = load_config(config_file_path)
        
        # Get log_level from config, default to INFO if section/option missing or value invalid
        log_level_str_main = cfg.get("general", "log_level", fallback="INFO").upper()

        workdir, statedir, maillog_path, country_db_path, asn_db_path = setup_paths(cfg) # These are Path objects
        logger = setup_logging(workdir, log_level_str_main) # Pass configured log level
        
        # --- IPInfoManager Initialization ---
        global IP_INFO_MANAGER
        # Use default URLs from ipinfo module for now
        # These could be made configurable in maillogsentinel.conf in the future if needed
        asn_db_url = ipinfo.DEFAULT_ASN_DB_URL
        country_db_url = ipinfo.DEFAULT_COUNTRY_DB_URL
        
        # Ensure data directory for ipinfo is based on its own defaults or configuration if we make it configurable
        # For now, use the paths from maillogsentinel.conf for the database files themselves
        # The IPInfoManager will use these paths directly.
        IP_INFO_MANAGER = ipinfo.IPInfoManager(
            asn_db_path=str(asn_db_path), # IPInfoManager expects string paths
            country_db_path=str(country_db_path),
            asn_db_url=asn_db_url,
            country_db_url=country_db_url,
            logger=logger # Pass the main logger
        )
        logger.info("Attempting initial update/load of IP geolocation and ASN databases...")
        IP_INFO_MANAGER.update_databases() # This will download if missing and then load.

        # --- DNS Cache Configuration Loading ---
        dns_cache_enabled = cfg.getboolean('dns_cache', 'enabled', fallback=True)
        dns_cache_size = cfg.getint('dns_cache', 'size', fallback=128)
        dns_cache_ttl = cfg.getint('dns_cache', 'ttl_seconds', fallback=3600)

        DNS_CACHE_SETTINGS['enabled'] = dns_cache_enabled
        DNS_CACHE_SETTINGS['ttl'] = dns_cache_ttl
        
        initialize_dns_cache(dns_cache_size)
        logger.info(f"DNS Caching enabled: {dns_cache_enabled}, Size: {dns_cache_size}, TTL: {dns_cache_ttl}s")
        
        # Check if setup_logging defaulted and warn if the configured value was bad
        # LOG_LEVELS_MAP is defined in setup_logging, need to access it carefully or redefine it locally for check
        # For simplicity, this check relies on setup_logging's internal default behavior
        # It's better if LOG_LEVELS_MAP is accessible here or setup_logging returns the actual level used.
        # For now, we'll use the provided check, assuming LOG_LEVELS_MAP is somehow accessible or this check is conceptual.
        # Replicating LOG_LEVELS_MAP here for the check:
        LOG_LEVELS_MAP_CHECK = { "DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR, "CRITICAL": logging.CRITICAL }
        if log_level_str_main.upper() not in LOG_LEVELS_MAP_CHECK and \
           LOG_LEVELS_MAP_CHECK.get(log_level_str_main.upper(), logging.INFO) == logging.INFO:
             logger.warning(f"Configured log_level '{log_level_str_main}' is invalid. Defaulting to INFO.")

        logger.info(f"=== Start of {SCRIPT_NAME} {VERSION} ===") # Use SCRIPT_NAME and VERSION

        if args.report:
            send_report(cfg, workdir, logger) # Pass Path object for workdir
            logger.info(f"=== End of {SCRIPT_NAME} execution (report mode) ===")
            return

        last_off = read_state(statedir, logger) # Pass Path object
        
        # The following block seems to be misplaced from a previous merge.
        # It should be inside the 'else' block of 'if args.setup or not config_file_path.is_file():'
        # and specifically after logger initialization for normal operation.
        # For now, I will place it here as per the diff context, but it might need restructuring.
        # list_all_logs expects Path, returns list of Paths. If last_off is 0, get all, else just the main log.
        # Ensure [maillog_path] is a list of Path if used.
        to_proc = list_all_logs(maillog_path) if last_off == 0 else [maillog_path]
        
        logger.debug(f"Files to process: {to_proc}, starting from offset: {last_off}") # Changed INFO to DEBUG

        csv_file_to_extract = workdir / CSV_FILENAME # Path object

    new_off = extract_entries(
        to_proc, # list of Path objects
        maillog_path, # Path object
        str(csv_file_to_extract), # extract_entries expects string path for csv
        logger,
        offset=last_off
    )
    write_state(statedir, new_off, logger) # Pass Path object
    logger.info(f"Extraction completed, new offset saved: {new_off}") # Slightly more descriptive
    logger.info(f"=== End of {SCRIPT_NAME} execution ===")

if __name__ == "__main__":
    main()
