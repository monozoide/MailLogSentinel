#!/usr/bin/env python3

import argparse
import csv
import gzip
import ipaddress
import json
import logging
import os
import shutil
# sys is already imported by maillogsentinel, but good to have explicitly for this file too.
# import sys # Not strictly needed if already imported, but good for clarity
import tempfile
import urllib.request
from typing import Optional, List, Dict, Any
import configparser # Added for reading maillogsentinel.conf

# Configuration
DEFAULT_COUNTRY_DB_URL = "https://raw.githubusercontent.com/sapics/ip-location-db/main/asn-country/asn-country-ipv4-num.csv"
DEFAULT_ASN_DB_URL = "https://raw.githubusercontent.com/sapics/ip-location-db/refs/heads/main/asn/asn-ipv4-num.csv"
DEFAULT_DATA_DIR = os.path.expanduser("~/.ipinfo") # Default for CLI direct use
DEFAULT_COUNTRY_DB_PATH = os.path.join(DEFAULT_DATA_DIR, "country_aside.csv") # Filename will be derived if using sapics
DEFAULT_ASN_DB_PATH = os.path.join(DEFAULT_DATA_DIR, "ip2asn-lite.csv") # Filename will be derived if using sapics


# Logging setup (global for the module, can be used by IPInfoManager instance logger)
module_logger = logging.getLogger(__name__)
# Configure basicConfig only if the script is run directly, to avoid issues when imported.
# The expectation is that an application importing this module will configure logging.
# However, for direct CLI use by ipinfo.py itself, basicConfig is useful.
# A common pattern is to check if __name__ == "__main__" before basicConfig,
# but since IPInfoManager can be used as a library, its logger should be passed.
# For now, ensure handlers are not duplicated if imported multiple times.
if __name__ != "__main__" and not module_logger.hasHandlers(): # Avoid duplicate handlers if imported
    # If imported, rely on the importing application to set up logging.
    # If needed, a null handler can be added: logging.getLogger(__name__).addHandler(logging.NullHandler())
    pass
elif __name__ == "__main__":
    if not module_logger.hasHandlers():
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def ip_to_int(ip_str: str) -> Optional[int]:
    """Converts an IP string (v4 or v6) to its integer representation."""
    try:
        return int(ipaddress.ip_address(ip_str))
    except ValueError:
        module_logger.warning(f"Invalid IP address format: {ip_str}")
        return None

def _download_single_data(url: str, dest_path: str, logger: logging.Logger) -> bool:
    """Downloads and extracts a single IP database."""
    logger.info(f"Downloading IP database from {url} to {dest_path}...")
    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        is_gzipped = url.endswith(".gz")

        if is_gzipped:
            with tempfile.NamedTemporaryFile(delete=False) as tmp_gz_file:
                temp_file_name = tmp_gz_file.name
                try:
                    with urllib.request.urlopen(url) as response:
                        shutil.copyfileobj(response, tmp_gz_file)
                    logger.info(f"Download complete for {url}.")

                    logger.info(f"Extracting data to {dest_path}...")
                    with gzip.open(temp_file_name, 'rb') as gz_f, open(dest_path, 'wb') as out_f:
                        shutil.copyfileobj(gz_f, out_f)
                    logger.info(f"Extraction complete for {dest_path}.")
                    return True
                except Exception as e:
                    logger.error(f"Error during download or extraction for {url}: {e}")
                    return False
                finally:
                    if os.path.exists(temp_file_name):
                        os.remove(temp_file_name)
        else: # Not gzipped, direct download to temp file then atomic replace
            temp_file_path = ""
            try:
                dest_dir = os.path.dirname(dest_path)
                # Ensure dest_dir exists (it should if dest_path is based on DEFAULT_COUNTRY_DB_PATH etc.)
                # os.makedirs(dest_dir, exist_ok=True) # This was already called at the start of the function.
                
                # Use a unique temporary filename in the destination directory
                # Prefix helps identify temp files; suffix might also be useful e.g. '.tmpdownload'
                with tempfile.NamedTemporaryFile(mode='wb', delete=False, dir=dest_dir, 
                                                 prefix=os.path.basename(dest_path) + ".tmp") as tmp_f:
                    temp_file_path = tmp_f.name
                    with urllib.request.urlopen(url) as response:
                        shutil.copyfileobj(response, tmp_f)
                
                # If download successful, atomically replace the destination file
                os.replace(temp_file_path, dest_path)
                logger.info(f"Direct download and atomic replace complete for {url} to {dest_path}.")
                return True
            except Exception as e: # Catch errors from urlopen, copyfileobj, or replace
                logger.error(f"Error during direct download for {url} to {dest_path}: {e}")
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.remove(temp_file_path) # Clean up temp file on error
                        logger.debug(f"Cleaned up temporary file {temp_file_path}")
                    except OSError as rm_e:
                        logger.error(f"Error removing temporary file {temp_file_path}: {rm_e}")
                return False
            # No 'finally' block needed here for temp_file_path removal, as it's handled in except or by os.replace

    except Exception as e: # Catches errors from initial os.makedirs or general setup
        logger.error(f"Setup or download error for {url}: {e}")
        return False


def _load_single_db(data_path: str, db_type: str, logger: logging.Logger) -> List[Dict[str, Any]]:
    """Loads a single IP database (country or ASN) from its CSV file."""
    db = []
    if not os.path.exists(data_path):
        logger.warning(f"{db_type.capitalize()} data file {data_path} not found. Database will be empty.")
        return []
    
    logger.info(f"Loading {db_type} database from {data_path}...")
    try:
        with open(data_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)  # Skip header
            
            # For country: start_ip_int, end_ip_int, country_code
            # For ASN: start_ip_int, end_ip_int, asn, aso
            min_cols_country = 3 
            min_cols_asn = 4
            
            for row_num, row in enumerate(reader, 1):
                entry = {}
                start_ip_str, end_ip_str = None, None
                
                try:
                    if db_type == 'country':
                        if len(row) < min_cols_country:
                            logger.warning(f"Skipping malformed country row {row_num} in {data_path}: {row}. Expected at least {min_cols_country} columns.")
                            continue
                        start_ip_str, end_ip_str, country_code = row[0], row[1], row[2]
                        entry = {"country": country_code.strip(), "asn": None, "aso": None}
                    elif db_type == 'asn':
                        if len(row) < min_cols_asn:
                            logger.warning(f"Skipping malformed ASN row {row_num} in {data_path}: {row}. Expected at least {min_cols_asn} columns.")
                            continue
                        start_ip_str, end_ip_str, asn, aso = row[0], row[1], row[2], row[3]
                        entry = {"asn": asn.strip(), "aso": aso.strip(), "country": None}
                    else:
                        logger.error(f"Invalid db_type '{db_type}' for loading.")
                        return []

                    start_ip_int = int(start_ip_str.strip())
                    end_ip_int = int(end_ip_str.strip())
                    
                    entry["start_ip"] = ipaddress.ip_address(start_ip_int)
                    entry["end_ip"] = ipaddress.ip_address(end_ip_int)
                    db.append(entry)

                except ValueError as e: # Catches int() conversion errors or ipaddress.ip_address() errors
                    logger.warning(f"Error processing row {row_num} in {data_path}: '{row}'. Invalid integer IP value or IP address: {e}. Skipping.")
                    continue # Skip to the next row
            
        db.sort(key=lambda x: x["start_ip"]) # Sort by IPAddress object (which supports comparison)
        logger.info(f"Successfully loaded {len(db)} IP ranges for {db_type} from {data_path}.")
        return db
    except Exception as e:
        logger.error(f"Error loading {db_type} IP database from {data_path}: {e}")
        return []


def search_ip_in_database(db: List[Dict[str, Any]], ip_address_str: str, logger: logging.Logger) -> Optional[Dict[str, Any]]:
    """Performs a binary search for an IP address string in a sorted database."""
    ip_int = ip_to_int(ip_address_str)
    if ip_int is None:
        return None # ip_to_int already logged warning

    low, high = 0, len(db) - 1
    while low <= high:
        mid = (low + high) // 2
        entry = db[mid]
        # Convert entry IPs to int for comparison if they are stored as IPAddress objects
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
    def __init__(self, country_db_path: str, asn_db_path: str,
                 country_db_url: str, asn_db_url: str, logger: logging.Logger):
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
            self.country_database = _load_single_db(self.country_db_path, 'country', self.logger)
        elif not self.country_database: # File doesn't exist
             self.logger.warning(f"Country DB file {self.country_db_path} not found. Database is empty.")
             self.country_database = []


        if not self.asn_database and os.path.exists(self.asn_db_path):
            self.asn_database = _load_single_db(self.asn_db_path, 'asn', self.logger)
        elif not self.asn_database: # File doesn't exist
            self.logger.warning(f"ASN DB file {self.asn_db_path} not found. Database is empty.")
            self.asn_database = []


    def update_databases(self) -> bool:
        """Downloads and reloads both databases."""
        self.logger.info("Starting database update process...")
        country_success = _download_single_data(self.country_db_url, self.country_db_path, self.logger)
        if country_success:
            self.country_database = _load_single_db(self.country_db_path, 'country', self.logger)
        else:
            self.logger.error("Failed to download or update country database. Existing data (if any) will be used.")

        asn_success = _download_single_data(self.asn_db_url, self.asn_db_path, self.logger)
        if asn_success:
            self.asn_database = _load_single_db(self.asn_db_path, 'asn', self.logger)
        else:
            self.logger.error("Failed to download or update ASN database. Existing data (if any) will be used.")
        
        # Ensure data is loaded even if download failed but files exist
        self._ensure_data_loaded()
        return country_success and asn_success

    def lookup_ip_info(self, ip_address_str: str) -> Optional[Dict[str, str]]:
        """Looks up combined information (country, ASN, ASO) for a given IP address."""
        self._ensure_data_loaded() # Make sure data is loaded

        if ip_to_int(ip_address_str) is None: # Validate IP first
            return None

        country_info = search_ip_in_database(self.country_database, ip_address_str, self.logger)
        asn_info = search_ip_in_database(self.asn_database, ip_address_str, self.logger)

        # Log if IP found in one DB but not other for debugging
        if country_info and not asn_info:
            self.logger.debug(f"IP {ip_address_str} found in Country DB but not ASN DB.")
        if not country_info and asn_info:
            self.logger.debug(f"IP {ip_address_str} found in ASN DB but not Country DB.")

        return {
            "ip": ip_address_str,
            "country_code": country_info["country"] if country_info and country_info.get("country") else "N/A",
            "asn": asn_info["asn"] if asn_info and asn_info.get("asn") else "N/A",
            "aso": asn_info["aso"] if asn_info and asn_info.get("aso") else "N/A",
        }

def main_cli():
    """Command-line interface for updating and looking up IP information."""
    # Use module_logger for CLI specific logging if IPInfoManager isn't instantiated
    # or pass module_logger to IPInfoManager if it's used.
    
    parser = argparse.ArgumentParser(description="IP Information Utility (ipinfo.py)")
    parser.add_argument(
        "--update", action="store_true",
        help="Download or update both IP databases (Country and ASN)."
    )
    parser.add_argument(
        "ip_address", nargs="?",
        help="IP address to look up (e.g., 8.8.8.8)."
    )
    parser.add_argument(
        "--country-db-path", default=DEFAULT_COUNTRY_DB_PATH,
        help=f"Path to store/load country database (default: {DEFAULT_COUNTRY_DB_PATH})"
    )
    parser.add_argument(
        "--asn-db-path", default=DEFAULT_ASN_DB_PATH,
        help=f"Path to store/load ASN database (default: {DEFAULT_ASN_DB_PATH})"
    )
    parser.add_argument(
        "--country-db-url", default=DEFAULT_COUNTRY_DB_URL,
        help=f"URL for country database (default: {DEFAULT_COUNTRY_DB_URL})"
    )
    parser.add_argument(
        "--asn-db-url", default=DEFAULT_ASN_DB_URL,
        help=f"URL for ASN database (default: {DEFAULT_ASN_DB_URL})"
    )
    # For maillogsentinel compatibility, allow --data-dir to set base for DB paths
    parser.add_argument(
        "--data-dir", default=None, # Default to None, paths will take precedence
        help=("Directory to store/load all IP database files. "
              "If specified, overrides default directory part of --country-db-path and --asn-db-path "
              "unless they are absolute paths.")
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to maillogsentinel.conf file for configuration-driven paths."
    )

    args = parser.parse_args()
    
    # Initialize path variables with defaults from argparse (which are the module's DEFAULT_..._PATH)
    country_db_path_val = args.country_db_path
    asn_db_path_val = args.asn_db_path

    if args.config:
        module_logger.info(f"Loading configuration from: {args.config}")
        config = configparser.ConfigParser()
        try:
            read_files = config.read(args.config)
            if not read_files:
                module_logger.error(f"Could not read config file: {args.config}. Exiting.")
                sys.exit(1)

            SECTION_GEOLOCATION = "geolocation" # As defined in maillogsentinel.py
            SECTION_ASN_ASO = "ASN_ASO"         # As defined in maillogsentinel.py
            
            # Use get from configparser, which can take a fallback.
            # If section or option is missing, it will use the fallback.
            # The initial values of country_db_path_val/asn_db_path_val serve as ultimate fallbacks if section/key missing.
            
            current_country_path_source = "default/argparse"
            if SECTION_GEOLOCATION in config:
                # Use config.get(section, option, fallback=current_value)
                # This means if 'country_db_path' is NOT in the section, it keeps country_db_path_val
                retrieved_path = config.get(SECTION_GEOLOCATION, 'country_db_path', fallback=None)
                if retrieved_path:
                    country_db_path_val = retrieved_path
                    current_country_path_source = f"config file ({args.config})"
                else: # Key not found in section
                    module_logger.warning(f"Key 'country_db_path' not found in section [{SECTION_GEOLOCATION}] in {args.config}. Current value ('{country_db_path_val}') retained.")
            else:
                module_logger.warning(f"Section [{SECTION_GEOLOCATION}] not found in {args.config}. Current value ('{country_db_path_val}') for country_db_path retained.")
            module_logger.info(f"Using 'country_db_path': {country_db_path_val} (Source: {current_country_path_source})")

            current_asn_path_source = "default/argparse"
            if SECTION_ASN_ASO in config:
                retrieved_path = config.get(SECTION_ASN_ASO, 'asn_db_path', fallback=None)
                if retrieved_path:
                    asn_db_path_val = retrieved_path
                    current_asn_path_source = f"config file ({args.config})"
                else: # Key not found in section
                     module_logger.warning(f"Key 'asn_db_path' not found in section [{SECTION_ASN_ASO}] in {args.config}. Current value ('{asn_db_path_val}') retained.")
            else:
                module_logger.warning(f"Section [{SECTION_ASN_ASO}] not found in {args.config}. Current value ('{asn_db_path_val}') for asn_db_path retained.")
            module_logger.info(f"Using 'asn_db_path': {asn_db_path_val} (Source: {current_asn_path_source})")

        except configparser.Error as e:
            module_logger.error(f"Error parsing config file {args.config}: {e}. Exiting.")
            sys.exit(1)
        except Exception as e:
            module_logger.error(f"Unexpected error processing config file {args.config}: {e}. Exiting.")
            sys.exit(1)
            
    elif args.data_dir: # This logic applies if --config is NOT used but --data-dir is
        # country_db_path_val and asn_db_path_val are from args (i.e. module defaults or explicit --country-db-path)
        if not os.path.isabs(country_db_path_val):
            country_db_path_val = os.path.join(args.data_dir, os.path.basename(country_db_path_val)) # Use basename of current val
        if not os.path.isabs(asn_db_path_val):
            asn_db_path_val = os.path.join(args.data_dir, os.path.basename(asn_db_path_val)) # Use basename of current val
        
        if not os.path.exists(args.data_dir): # Ensure data_dir itself exists
            try:
                os.makedirs(args.data_dir, exist_ok=True)
                module_logger.info(f"Created data directory: {args.data_dir}")
            except OSError as e:
                module_logger.error(f"Could not create data directory {args.data_dir}: {e}")
                sys.exit(1)
    
    # Ensure parent directories for final DB paths exist, especially if derived from config.
    # This is important because IPInfoManager itself doesn't create parent dirs for these paths.
    for path_val in [country_db_path_val, asn_db_path_val]:
        parent_dir = os.path.dirname(path_val)
        if parent_dir and not os.path.exists(parent_dir): # Check if parent_dir is not empty (e.g. for relative paths)
            try:
                os.makedirs(parent_dir, exist_ok=True)
                module_logger.info(f"Ensured parent directory exists: {parent_dir}")
            except OSError as e:
                module_logger.error(f"Could not create parent directory {parent_dir} for DB path {path_val}: {e}")
                # Depending on severity, might sys.exit(1)

    manager = IPInfoManager(
        country_db_path=country_db_path_val,
        asn_db_path=asn_db_path_val,
        country_db_url=args.country_db_url,
        asn_db_url=args.asn_db_url,
        logger=module_logger
    )

    if args.update:
        if manager.update_databases():
            module_logger.info("Databases updated successfully via IPInfoManager.")
        else:
            module_logger.error("One or more database updates failed via IPInfoManager.")
            sys.exit(1)

    if args.ip_address:
        result = manager.lookup_ip_info(args.ip_address)
        if result:
            # Output as JSON
            # For CLI, convert IPAddress objects in network entry back to string if they were stored
            # Current lookup_ip_info doesn't return network object, but if it did:
            # if "network_obj" in result and isinstance(result["network_obj"], ipaddress._BaseNetwork):
            #    result["network"] = str(result["network_obj"])
            #    del result["network_obj"]
            print(json.dumps(result))
        else:
            # lookup_ip_info returns None for invalid IP, or dict with N/A for not found
            # For CLI, provide consistent JSON error for not found vs invalid
            if ip_to_int(args.ip_address) is None: # Invalid IP was the reason
                 print(json.dumps({"ip": args.ip_address, "error": "Invalid IP address format."}))
            else:
                 print(json.dumps({"ip": args.ip_address, "error": "Information not found."}))
            # sys.exit(1) # Optionally exit with error for lookup failure

    elif not args.update: # No IP and no update means show help
        parser.print_help()

if __name__ == "__main__":
    main_cli()
