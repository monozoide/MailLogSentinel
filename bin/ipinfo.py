#!/usr/bin/env python3

import argparse
import csv
import gzip
import ipaddress
import json
import logging
import os
import shutil
import sys
import tempfile
import urllib.request
from typing import Optional, List, Dict, Any  # Tuple removed
import configparser

# Configuration
DEFAULT_COUNTRY_DB_URL = "https://raw.githubusercontent.com/sapics/ip-location-db/main/asn-country/asn-country-ipv4-num.csv"  # noqa: E501
DEFAULT_ASN_DB_URL = "https://raw.githubusercontent.com/sapics/ip-location-db/refs/heads/main/asn/asn-ipv4-num.csv"  # noqa: E501
DEFAULT_DATA_DIR = os.path.expanduser("~/.ipinfo")
DEFAULT_COUNTRY_DB_PATH = os.path.join(DEFAULT_DATA_DIR, "country_aside.csv")
DEFAULT_ASN_DB_PATH = os.path.join(DEFAULT_DATA_DIR, "ip2asn-lite.csv")

module_logger = logging.getLogger(__name__)

if __name__ == "__main__":
    if not module_logger.hasHandlers():
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )


def ip_to_int(
    ip_str: str, logger_override: Optional[logging.Logger] = None
) -> Optional[int]:
    logger_to_use = logger_override if logger_override else module_logger
    try:
        return int(ipaddress.ip_address(ip_str))
    except ValueError:
        logger_to_use.warning(f"Invalid IP address format: {ip_str}")
        return None


def _fetch_and_write_to_temp(url: str, tmp_file: Any, logger: logging.Logger) -> bool:
    """Fetches data from URL and writes to a temporary file."""
    try:
        with urllib.request.urlopen(url) as response:
            shutil.copyfileobj(response, tmp_file)
        logger.info(f"Download complete for {url}.")
        return True
    except (urllib.error.URLError, urllib.error.HTTPError, IOError) as e:
        logger.error(f"Error during download for {url}: {e}")
        return False


def _handle_gzipped_download_logic(
    url: str, dest_path: str, logger: logging.Logger
) -> bool:
    """Handles the download and extraction of a gzipped file."""
    with tempfile.NamedTemporaryFile(delete=False) as tmp_gz_file:
        temp_file_name = tmp_gz_file.name
        try:
            if not _fetch_and_write_to_temp(url, tmp_gz_file, logger):
                return False
            logger.info(f"Extracting data to {dest_path}...")
            with gzip.open(temp_file_name, "rb") as gz_f, open(
                dest_path, "wb"
            ) as out_f:
                shutil.copyfileobj(gz_f, out_f)
            logger.info(f"Extraction complete for {dest_path}.")
            return True
        except (gzip.BadGzipFile, IOError, OSError) as e:
            logger.error(f"Error during extraction for {url}: {e}")
            return False
        finally:
            if os.path.exists(temp_file_name):
                os.remove(temp_file_name)


def _handle_direct_download_logic(
    url: str, dest_path: str, logger: logging.Logger
) -> bool:
    """Handles the direct download of a non-gzipped file."""
    temp_file_path = ""
    try:
        dest_dir = os.path.dirname(dest_path)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=dest_dir,
            prefix=os.path.basename(dest_path) + ".tmp",
        ) as tmp_f:
            temp_file_path = tmp_f.name
            if not _fetch_and_write_to_temp(url, tmp_f, logger):
                return False
        os.replace(temp_file_path, dest_path)
        logger.info(
            f"Direct download and atomic replace complete for {url} to {dest_path}."
        )
        return True
    except (IOError, OSError) as e:
        logger.error(f"Error during direct download for {url} to {dest_path}: {e}")
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.debug(f"Cleaned up temporary file {temp_file_path}")
            except OSError as rm_e:
                logger.error(f"Error removing temporary file {temp_file_path}: {rm_e}")
        return False


def _download_single_data(url: str, dest_path: str, logger: logging.Logger) -> bool:
    """Downloads and extracts a single IP database."""
    logger.info(f"Downloading IP database from {url} to {dest_path}...")
    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        is_gzipped = url.endswith(".gz")
        if is_gzipped:
            return _handle_gzipped_download_logic(url, dest_path, logger)
        else:
            return _handle_direct_download_logic(url, dest_path, logger)
    except (
        OSError
    ) as e:  # Specifically for os.makedirs, other download errors handled internally
        logger.error(f"Setup (directory creation) error for {url}: {e}")
        return False


def _load_single_db(
    data_path: str, db_type: str, logger: logging.Logger
) -> List[Dict[str, Any]]:
    """Loads a single IP database (country or ASN) from its CSV file."""
    if db_type not in ["country", "asn"]:
        logger.error(f"Invalid db_type '{db_type}' for loading.")
        return []

    db = []
    if not os.path.exists(data_path):
        logger.warning(
            f"{db_type.capitalize()} data file {data_path} not found. "
            "Database will be empty."
        )
        return []

    logger.info(f"Loading {db_type} database from {data_path}...")
    try:
        with open(data_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            _ = next(reader)  # Skip header

            min_cols_country = 3
            min_cols_asn = 4

            for row_num, row in enumerate(reader, 1):
                entry = {}
                start_ip_str, end_ip_str = None, None

                try:
                    if db_type == "country":
                        if len(row) < min_cols_country:
                            logger.warning(
                                f"Skipping malformed country row {row_num} in "
                                f"{data_path}: {row}. Expected at least "
                                f"{min_cols_country} columns."
                            )
                            continue
                        start_ip_str, end_ip_str, country_code = row[0], row[1], row[2]
                        entry = {
                            "country": country_code.strip(),
                            "asn": None,
                            "aso": None,
                        }
                    elif db_type == "asn":
                        if len(row) < min_cols_asn:
                            logger.warning(
                                f"Skipping malformed ASN row {row_num} in {data_path}: "
                                f"{row}. Expected at least {min_cols_asn} columns."
                            )
                            continue
                        start_ip_str, end_ip_str, asn, aso = (
                            row[0],
                            row[1],
                            row[2],
                            row[3],
                        )
                        entry = {
                            "asn": asn.strip(),
                            "aso": aso.strip(),
                            "country": None,
                        }
                    # No else needed due to the initial db_type check

                    start_ip_int = int(start_ip_str.strip())
                    end_ip_int = int(end_ip_str.strip())

                    entry["start_ip"] = ipaddress.ip_address(start_ip_int)
                    entry["end_ip"] = ipaddress.ip_address(end_ip_int)
                    db.append(entry)

                except ValueError as e:
                    logger.warning(
                        f"Error processing row {row_num} in {data_path}: '{row}'. "
                        f"Invalid integer IP value or IP address: {e}. Skipping."
                    )
                    continue

        db.sort(key=lambda x: x["start_ip"])
        logger.info(
            f"Successfully loaded {len(db)} IP ranges for {db_type} from {data_path}."
        )
        return db
    except (IOError, OSError, csv.Error) as e:
        logger.error(f"Error loading {db_type} IP database from {data_path}: {e}")
        return []


def search_ip_in_database(
    db: List[Dict[str, Any]], ip_address_str: str, logger: logging.Logger
) -> Optional[Dict[str, Any]]:
    """Performs a binary search for an IP address string in a sorted database."""
    ip_int = ip_to_int(ip_address_str, logger_override=logger)
    if ip_int is None:
        return None

    low, high = 0, len(db) - 1
    while low <= high:
        mid = (low + high) // 2
        entry = db[mid]
        start_ip_int = int(entry["start_ip"])
        end_ip_int = int(entry["end_ip"])

        if start_ip_int <= ip_int <= end_ip_int:
            return entry
        elif ip_int < start_ip_int:
            high = mid - 1
        else:
            low = mid + 1
    return None


class IPInfoManager:
    def __init__(
        self,
        country_db_path: str,
        asn_db_path: str,
        country_db_url: str,
        asn_db_url: str,
        logger: logging.Logger,
    ):
        self.country_db_path = country_db_path
        self.asn_db_path = asn_db_path
        self.country_db_url = country_db_url
        self.asn_db_url = asn_db_url
        self.logger = logger
        self.country_database: List[Dict[str, Any]] = []
        self.asn_database: List[Dict[str, Any]] = []
        self._ensure_data_loaded()

    def _ensure_data_loaded(self):
        """Ensures both databases are loaded into memory if not already."""
        if not self.country_database and os.path.exists(self.country_db_path):
            self.country_database = _load_single_db(
                self.country_db_path, "country", self.logger
            )
        elif not self.country_database:
            self.logger.warning(
                f"Country DB file {self.country_db_path} not found. Database is empty."
            )
            self.country_database = []

        if not self.asn_database and os.path.exists(self.asn_db_path):
            self.asn_database = _load_single_db(self.asn_db_path, "asn", self.logger)
        elif not self.asn_database:
            self.logger.warning(
                f"ASN DB file {self.asn_db_path} not found. Database is empty."
            )
            self.asn_database = []

    def update_databases(self) -> bool:
        """Downloads and reloads both databases."""
        self.logger.info("Starting database update process...")
        country_success = _download_single_data(
            self.country_db_url, self.country_db_path, self.logger
        )
        if country_success:
            self.country_database = _load_single_db(
                self.country_db_path, "country", self.logger
            )
        else:
            self.logger.error(
                "Failed to download or update country database. "
                "Existing data (if any) will be used."
            )

        asn_success = _download_single_data(
            self.asn_db_url, self.asn_db_path, self.logger
        )
        if asn_success:
            self.asn_database = _load_single_db(self.asn_db_path, "asn", self.logger)
        else:
            self.logger.error(
                "Failed to download or update ASN database. "
                "Existing data (if any) will be used."
            )

        self._ensure_data_loaded()
        return country_success and asn_success

    def lookup_ip_info(self, ip_address_str: str) -> Optional[Dict[str, str]]:
        """Looks up combined information (country, ASN, ASO) for a given IP address."""
        self._ensure_data_loaded()

        if ip_to_int(ip_address_str, logger_override=self.logger) is None:
            return None

        country_info = search_ip_in_database(
            self.country_database, ip_address_str, self.logger
        )
        asn_info = search_ip_in_database(self.asn_database, ip_address_str, self.logger)

        if country_info and not asn_info:
            self.logger.debug(
                f"IP {ip_address_str} found in Country DB but not ASN DB."
            )
        if not country_info and asn_info:
            self.logger.debug(
                f"IP {ip_address_str} found in ASN DB but not Country DB."
            )

        return {
            "ip": ip_address_str,
            "country_code": (
                country_info["country"]
                if country_info and country_info.get("country")
                else "N/A"
            ),
            "asn": asn_info["asn"] if asn_info and asn_info.get("asn") else "N/A",
            "aso": asn_info["aso"] if asn_info and asn_info.get("aso") else "N/A",
        }


def main_cli():
    """Command-line interface for updating and looking up IP information."""
    parser = argparse.ArgumentParser(description="IP Information Utility (ipinfo.py)")
    parser.add_argument(
        "--update",
        action="store_true",
        help="Download or update both IP databases (Country and ASN).",
    )
    parser.add_argument(
        "ip_address", nargs="?", help="IP address to look up (e.g., 8.8.8.8)."
    )
    parser.add_argument(
        "--country-db-path",
        default=DEFAULT_COUNTRY_DB_PATH,
        help=f"Path to store/load country database (default: {DEFAULT_COUNTRY_DB_PATH})",
    )
    parser.add_argument(
        "--asn-db-path",
        default=DEFAULT_ASN_DB_PATH,
        help=f"Path to store/load ASN database (default: {DEFAULT_ASN_DB_PATH})",
    )
    parser.add_argument(
        "--country-db-url",
        default=DEFAULT_COUNTRY_DB_URL,
        help=f"URL for country database (default: {DEFAULT_COUNTRY_DB_URL})",
    )
    parser.add_argument(
        "--asn-db-url",
        default=DEFAULT_ASN_DB_URL,
        help=f"URL for ASN database (default: {DEFAULT_ASN_DB_URL})",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help=(
            "Directory to store/load all IP database files. If specified, "
            "overrides default directory part of --country-db-path and "
            "--asn-db-path unless they are absolute paths."
        ),
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to maillogsentinel.conf file for configuration-driven paths.",
    )

    args = parser.parse_args()

    country_db_path_val = args.country_db_path
    asn_db_path_val = args.asn_db_path
    country_db_url_val = args.country_db_url
    asn_db_url_val = args.asn_db_url

    if args.config:
        module_logger.info(f"Loading configuration from: {args.config}")
        config = configparser.ConfigParser()
        try:
            read_files = config.read(args.config)
            if not read_files:
                module_logger.error(
                    f"Could not read config file: {args.config}. Exiting."
                )
                sys.exit(1)

            SECTION_GEOLOCATION = "geolocation"
            SECTION_ASN_ASO = "ASN_ASO"

            current_country_path_source = "default/argparse"
            if SECTION_GEOLOCATION in config:
                retrieved_path = config.get(
                    SECTION_GEOLOCATION, "country_db_path", fallback=None
                )
                if retrieved_path:
                    country_db_path_val = retrieved_path
                    current_country_path_source = f"config file ({args.config})"
                else:
                    module_logger.warning(
                        f"Key 'country_db_path' not found in section "
                        f"[{SECTION_GEOLOCATION}] in {args.config}. Current "
                        f"value ('{country_db_path_val}') retained."
                    )
            else:
                module_logger.warning(
                    f"Section [{SECTION_GEOLOCATION}] not found in {args.config}. "
                    f"Current value ('{country_db_path_val}') for "
                    f"country_db_path retained."
                )
            retrieved_url = config.get(
                SECTION_GEOLOCATION, "country_db_url", fallback=None
            )
            if retrieved_url:
                country_db_url_val = retrieved_url
                module_logger.info(
                    f"Using 'country_db_url': {country_db_url_val} "
                    f"(Source: config file)"
                )
            else:
                module_logger.info(
                    f"Using 'country_db_url': {country_db_url_val} "
                    f"(Source: default/argparse)"
                )
            module_logger.info(
                f"Using 'country_db_path': {country_db_path_val} "
                f"(Source: {current_country_path_source})"
            )

            current_asn_path_source = "default/argparse"
            if SECTION_ASN_ASO in config:
                retrieved_path = config.get(
                    SECTION_ASN_ASO, "asn_db_path", fallback=None
                )
                if retrieved_path:
                    asn_db_path_val = retrieved_path
                    current_asn_path_source = f"config file ({args.config})"
                else:
                    module_logger.warning(
                        f"Key 'asn_db_path' not found in section "
                        f"[{SECTION_ASN_ASO}] in {args.config}. Current value "
                        f"('{asn_db_path_val}') retained."
                    )
            else:
                module_logger.warning(
                    f"Section [{SECTION_ASN_ASO}] not found in {args.config}. "
                    f"Current value ('{asn_db_path_val}') for "
                    f"asn_db_path retained."
                )
            retrieved_url = config.get(SECTION_ASN_ASO, "asn_db_url", fallback=None)
            if retrieved_url:
                asn_db_url_val = retrieved_url
                module_logger.info(
                    f"Using 'asn_db_url': {asn_db_url_val} (Source: config file)"
                )
            else:
                module_logger.info(
                    f"Using 'asn_db_url': {asn_db_url_val} "
                    f"(Source: default/argparse)"
                )
            module_logger.info(
                f"Using 'asn_db_path': {asn_db_path_val} "
                f"(Source: {current_asn_path_source})"
            )

        except configparser.Error as e:
            module_logger.error(
                f"Error parsing config file {args.config}: {e}. Exiting."
            )
            sys.exit(1)
        except (
            OSError
        ) as e:  # Catching OSError for file/path operations if configparser itself doesn't fail
            module_logger.error(
                f"OS error processing config file or related paths {args.config}: {e}. Exiting."
            )
            sys.exit(1)

    elif args.data_dir:
        if not os.path.isabs(country_db_path_val):
            country_db_path_val = os.path.join(
                args.data_dir, os.path.basename(country_db_path_val)
            )
        if not os.path.isabs(asn_db_path_val):
            asn_db_path_val = os.path.join(
                args.data_dir, os.path.basename(asn_db_path_val)
            )

        if not os.path.exists(args.data_dir):
            try:
                os.makedirs(args.data_dir, exist_ok=True)
                module_logger.info(f"Created data directory: {args.data_dir}")
            except OSError as e:
                module_logger.error(
                    f"Could not create data directory {args.data_dir}: {e}"
                )
                sys.exit(1)

    for path_val in [country_db_path_val, asn_db_path_val]:
        parent_dir = os.path.dirname(path_val)
        if parent_dir and not os.path.exists(parent_dir):
            try:
                os.makedirs(parent_dir, exist_ok=True)
                module_logger.info(f"Ensured parent directory exists: {parent_dir}")
            except OSError as e:
                module_logger.error(
                    f"Could not create parent directory {parent_dir} for "
                    f"DB path {path_val}: {e}"
                )

    manager = IPInfoManager(
        country_db_path=country_db_path_val,
        asn_db_path=asn_db_path_val,
        country_db_url=country_db_url_val,
        asn_db_url=asn_db_url_val,
        logger=module_logger,
    )

    if args.update:
        if manager.update_databases():
            module_logger.info("Databases updated successfully via IPInfoManager.")
        else:
            module_logger.error(
                "One or more database updates failed via IPInfoManager."
            )
            sys.exit(1)

    if args.ip_address:
        result = manager.lookup_ip_info(args.ip_address)
        if result:
            print(json.dumps(result))
        else:
            if ip_to_int(args.ip_address, logger_override=module_logger) is None:
                print(
                    json.dumps(
                        {"ip": args.ip_address, "error": "Invalid IP address format."}
                    )
                )
            else:
                print(
                    json.dumps(
                        {"ip": args.ip_address, "error": "Information not found."}
                    )
                )

    elif not args.update:
        parser.print_help()


if __name__ == "__main__":
    main_cli()
