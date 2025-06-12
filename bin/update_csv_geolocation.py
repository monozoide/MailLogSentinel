#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
from pathlib import Path
import argparse
import shutil
from datetime import datetime
import logging
import configparser
import sys

# Path Prepending for ipinfo import
# Add the script's directory (bin) to sys.path to allow direct import of ipinfo
# Assumes this script is in 'bin' and 'ipinfo.py' is also in 'bin'
sys.path.append(str(Path(__file__).resolve().parent))
try:
    import ipinfo
except ImportError:
    print("ERROR: Could not import 'ipinfo' module. Ensure it's in the same directory (bin) or PYTHONPATH.", file=sys.stderr)
    sys.exit(1)

# Basic Logger
logger = logging.getLogger("update_csv_geo")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    parser = argparse.ArgumentParser(description="Retroactively adds geolocation data to maillogsentinel.csv.")
    parser.add_argument("csv_file", type=str, help="Path to the maillogsentinel.csv file to update.")
    parser.add_argument("--config", default="/etc/maillogsentinel.conf",
                        help="Path to maillogsentinel.conf (to find asn_db_dir). Default: /etc/maillogsentinel.conf")
    args = parser.parse_args()

    csv_path = Path(args.csv_file)
    config_path = Path(args.config)

    if not csv_path.is_file():
        logger.error(f"CSV file not found: {csv_path}")
        sys.exit(1)

    if not config_path.is_file():
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)

    # Read asn_db_dir from config
    cfg = configparser.ConfigParser()
    try:
        cfg.read(config_path) # Read the config file
        # Try to get statedir for fallback, default to a sensible relative path if not found
        statedir_str = cfg.get("paths", "state_dir", fallback="/var/lib/maillogsentinel")
        statedir = Path(statedir_str)
        # Use statedir / "asn_db" as a more specific fallback for asn_db_dir
        asn_db_dir_str = cfg.get("geolocation", "asn_db_dir", fallback=str(statedir / "asn_db"))
        asn_db_dir = Path(asn_db_dir_str)
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        logger.error(f"Error reading configuration from {config_path}: {e}. "
                     "Ensure [paths] state_dir and [geolocation] asn_db_dir are present or use appropriate defaults.")
        # Attempt a default if config is problematic, but warn heavily
        asn_db_dir = Path("/var/lib/maillogsentinel/asn_db")
        logger.warning(f"Falling back to default ASN DB directory: {asn_db_dir}")


    # Check if ASN DB files exist
    asn_ipv4_db = asn_db_dir / "asn-ipv4.csv"
    asn_country_db = asn_db_dir / "asn-country.csv"
    if not asn_ipv4_db.is_file() or not asn_country_db.is_file(): # Use .is_file() for checks
        logger.error(f"ASN database files (asn-ipv4.csv or asn-country.csv) not found in {asn_db_dir}. "
                     "Please run the main maillogsentinel.py script first to download them, "
                     "or ensure the 'asn_db_dir' in maillogsentinel.conf is correct.")
        sys.exit(1)
    
    logger.info(f"Using ASN database directory: {asn_db_dir}")

    # Backup original file
    backup_suffix = datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = csv_path.with_name(f"{csv_path.name}.backup_{backup_suffix}")
    try:
        shutil.copy2(csv_path, backup_path)
        logger.info(f"Backed up original CSV to {backup_path}")
    except IOError as e:
        logger.error(f"Failed to backup CSV file: {e}")
        sys.exit(1)

    temp_csv_path = csv_path.with_name(f"{csv_path.name}.tmp_update_{datetime.now().strftime('%Y%m%d%H%M%S')}")
    updated_rows = 0
    processed_rows = 0

    new_header = ["server", "date", "ip", "user", "hostname", "reverse_dns_status", "country_code", "asn", "aso"]

    try:
        with open(csv_path, 'r', encoding='utf-8', newline='') as infile, \
             open(temp_csv_path, 'w', encoding='utf-8', newline='') as outfile:
            
            reader = csv.reader(infile, delimiter=';')
            writer = csv.writer(outfile, delimiter=';', quoting=csv.QUOTE_MINIMAL)

            # Handle header
            header = next(reader, None)
            if not header:
                logger.info("CSV file is empty (no header). Nothing to do.")
                # temp_csv_path will be empty, which is fine.
                # It will replace the original empty file.
                return # Exit function early

            if len(header) == 6:
                writer.writerow(new_header)
                logger.info("Original header has 6 columns. Writing new 9-column header.")
            elif len(header) == 9 and header[0] == new_header[0] and header[8] == new_header[8]: # Check first and last elements
                writer.writerow(header)
                logger.info("CSV appears to already have the 9-column header or a similar structure.")
            else: 
                logger.warning(f"Unexpected header format (length {len(header)}): {header}. Writing new 9-column header.")
                writer.writerow(new_header)


            # Process data rows
            for row_number, row in enumerate(reader, 1): # Start row count from 1 for logging
                processed_rows += 1
                if not row: # Skip empty rows
                    logger.warning(f"Skipping empty row at line number {row_number + 1}.") # +1 because header was read
                    continue

                if len(row) == 6:
                    ip_to_lookup = row[2] # IP is the 3rd column (index 2)
                    if ip_to_lookup: # Ensure IP field is not empty
                        country, asn, aso = ipinfo.lookup_ip(ip_to_lookup, asn_db_dir, logger)
                        writer.writerow(row + [country, asn, aso])
                        updated_rows += 1
                    else:
                        logger.warning(f"Empty IP field in row {row_number + 1}: {row}. Appending nulls for geo fields.")
                        writer.writerow(row + ["null", "null", "null"])
                elif len(row) == 9:
                    writer.writerow(row) # Already has 9 fields, assume correct or already processed
                else:
                    logger.warning(f"Row {row_number + 1} with unexpected number of fields ({len(row)}): {row}. Writing as-is.")
                    writer.writerow(row) # Write as-is to preserve data

        # Replace original with updated temp file
        shutil.move(str(temp_csv_path), str(csv_path))
        logger.info(f"Successfully updated CSV file: {csv_path}")
        logger.info(f"Processed {processed_rows} data rows, updated {updated_rows} rows by adding geo IP data.")

    except FileNotFoundError: 
        logger.error(f"Error: Input file {csv_path} not found during processing.")
    except csv.Error as e:
        logger.error(f"CSV processing error (likely near line {reader.line_num if 'reader' in locals() else 'unknown'}): {e}")
        if temp_csv_path.exists():
            temp_csv_path.unlink() 
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        if temp_csv_path.exists():
            temp_csv_path.unlink()
    finally:
        # Ensure temp file is removed if it still exists (e.g. if 'return' was hit early)
        if temp_csv_path.exists(): 
            try:
                temp_csv_path.unlink()
                logger.debug(f"Cleaned up temporary file: {temp_csv_path}")
            except OSError as e_unlink:
                logger.error(f"Error removing temporary file {temp_csv_path}: {e_unlink}")


if __name__ == "__main__":
    main()
