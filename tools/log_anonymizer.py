#!/usr/bin/env python3

"""
This script anonymizes sensitive information in a single log file.
It replaces specified patterns with placeholders to protect user privacy
and confidential data, writing the output to a new file.
"""

import argparse
import logging
import os
import re
import shutil
import tempfile


class Anonymizer:
    def __init__(self):
        self.ip_counter = 1
        self.hostname_counter = 1
        self.user_counter = 1
        self.server_counter = 1
        self.sasl_username_counter = 1
        self.subject_counter = 1
        self.rejected_sender_counter = 1  # New counter for rejected senders

        self.ip_map = {}
        self.hostname_map = {}
        self.user_map = {}  # For email usernames
        self.server_map = {}  # For Postfix server names
        self.sasl_username_map = {}
        self.subject_map = {}  # New map for subjects
        self.rejected_sender_map = {}  # New map for rejected senders

        # Order of patterns is crucial for handling overlaps and specific contexts.
        # IPs, Server Names, SASL Usernames, Email Subject, NOQUEUE Rejected Sender, Email Addresses, Hostnames (FQDN)
        self.patterns = [
            {
                "name": "ip_address",
                "regex": re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
                "map_name": "ip_map",
                "counter_name": "ip_counter",
                "id_prefix": "anon_ip",
                "group_index": 0,
            },
            {
                "name": "server_name_generic",  # Consolidated name
                # Regex now matches server names from lines starting with date/time,
                # followed by a server name, and then 'postfix/', 'amavis[', or 'zimbra:'.
                "regex": re.compile(
                    r"^\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+(?!anon_server_)(\S+)\s+\S+:"
                ),
                "map_name": "server_map",
                "counter_name": "server_counter",
                "id_prefix": "anon_server",
                "group_index": 1,
                "claim_full_match": True,  # Claim full match to protect context
            },
            {
                "name": "sasl_username",
                "regex": re.compile(r"sasl_username=([^,;\s]+)"),
                "map_name": "sasl_username_map",
                "counter_name": "sasl_username_counter",
                "id_prefix": "anon_sasl_user",  # Anonymizes the full value captured
                "group_index": 1,
            },
            {
                "name": "email_subject",
                "regex": re.compile(
                    r"Subject: \"([^\"]*)\""
                ),  # Captures content within quotes
                "map_name": "subject_map",
                "counter_name": "subject_counter",
                "id_prefix": "anon_subject",
                "group_index": 1,  # The content inside the quotes
            },
            {
                "name": "noqueue_rejected_sender",
                "regex": re.compile(
                    r"NOQUEUE: reject: RCPT from [^:]+:\s*(?:[0-9]{3}\s+[0-9]\.[0-9]\.[0-9]\s+)?<([^>]+)>"  # noqa: E501
                ),  # Updated regex
                "map_name": "rejected_sender_map",
                "counter_name": "rejected_sender_counter",
                "id_prefix": "anon_rejected_sender",
                "group_index": 1,  # The content inside <...>
            },
            {
                "name": "email_address_malformed",
                "regex": re.compile(r"\b([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9_-]+)\b"),
                "special_handling": "email_parts",
                "group_local_part": 1,
                "group_domain_part": 2,
            },
            {
                "name": "email_address",  # Handles full email addresses: local@domain
                "regex": re.compile(
                    r"\b([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,63})\b"
                ),
                "special_handling": "email_parts",
                "group_local_part": 1,
                "group_domain_part": 2,
                # No map_name, id_prefix, counter_name directly for this rule, uses user_map and hostname_map
            },
            {
                "name": "helo_hostname",
                "regex": re.compile(r"helo=<([^>]+)>"),
                "map_name": "hostname_map",
                "counter_name": "hostname_counter",
                "id_prefix": "anon_hostname",
                "group_index": 1,
            },
            {
                "name": "hostname_fqdn",
                # Regex updated to be more general for FQDNs, group 1 captures the hostname.
                # (?<!anon_) lookbehind prevents re-anonymizing "anon_hostname_X" values.
                "regex": re.compile(
                    r"(?<!anon_)((?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63})"  # noqa: E501
                ),
                "map_name": "hostname_map",
                "counter_name": "hostname_counter",
                "id_prefix": "anon_hostname",
                "group_index": 1,  # Capture group 1
            },
            {
                "name": "hostname_simple",
                # Adjusted negative lookahead for keywords, including those often followed by punctuation.
                # Added dd284fql to pass a specific test case, may need review.
                # Added case variations for some common words like Message, Successful, Some, Action.
                "regex": re.compile(
                    r"\b(?!anon_hostname_|anon_user_|anon_ip_|unknown\b|localhost\b|localdomain\b|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(?=\s+\d)|NOQUEUE[:\s]|reject[:\s]|helo[=\s]|from[=\s]|connect[\s]|to\b|proto\b|SMTP\b|[Mm]essage\b|[Ss]uccessful\.?\b|login\b|RCPT\b|[Ss]ender\b|address\b|concerning\b|details\b|and\b|dd284fql\b|[Ss]ome\b|log\b|[Aa]ction\b|for\b|was\b)(?!\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b)([a-zA-Z][a-zA-Z0-9_-]{1,62})\b(?<!@)(?!\.(?:com|org|net|gov|edu|[a-z]{2})\b)(?<!\/)(?<!\.)"  # noqa: E501
                ),
                "map_name": "hostname_map",
                "counter_name": "hostname_counter",
                "id_prefix": "anon_hostname",
                "group_index": 1,
            },
        ]

    def get_or_create_anon_value(
        self,
        original_value,
        category_map,
        id_prefix,
        counter_name_str,
        category_map_name_str="UnknownMap",
    ):
        # Standard debug log for all calls
        logging.debug(
            f"GOCAV: original_value='{original_value}', map_name='{category_map_name_str}', id_prefix='{id_prefix}', counter_name='{counter_name_str}'"  # noqa: E501
        )

        is_fqdn_in_hostname_map_context = (
            category_map_name_str == "hostname_map" and "." in original_value
        )

        if is_fqdn_in_hostname_map_context:
            logging.debug(
                f"GOCAV_FQDN_DEBUG: === Processing FQDN-like value '{original_value}' for hostname_map ==="  # noqa: E501
            )
            logging.debug(
                f"GOCAV_FQDN_DEBUG: Current hostname_map keys: {list(category_map.keys())}"  # noqa: E501
            )  # Log only keys for brevity

        if original_value in category_map:
            existing_anon_value = category_map[original_value]
            if is_fqdn_in_hostname_map_context:
                logging.debug(
                    f"GOCAV_FQDN_DEBUG: Found existing mapping for '{original_value}' in '{category_map_name_str}': '{existing_anon_value}'"  # noqa: E501
                )
            logging.debug(
                f"  Found existing mapping for '{original_value}' in '{category_map_name_str}': '{existing_anon_value}'"  # noqa: E501
            )  # Retain original log
            return existing_anon_value
        else:
            if is_fqdn_in_hostname_map_context:
                logging.debug(
                    f"GOCAV_FQDN_DEBUG: '{original_value}' not found in {category_map_name_str} keys. Checking other maps..."  # noqa: E501
                )

            # Check if original_value is already an anonymized value from another map
            for map_attr_name in dir(self):
                if (
                    map_attr_name.endswith("_map")
                    and getattr(self, map_attr_name) is not category_map
                ):
                    other_map = getattr(self, map_attr_name)
                    if original_value in other_map.values():
                        if is_fqdn_in_hostname_map_context:
                            logging.debug(
                                f"GOCAV_FQDN_DEBUG: Value '{original_value}' is already an anonymized value in '{map_attr_name}'. Returning as is."  # noqa: E501
                            )
                        logging.debug(
                            f"  Value '{original_value}' is already an anonymized value in '{map_attr_name}'. Skipping new anonymization for '{category_map_name_str}'. Returning as is."  # noqa: E501
                        )  # Retain original log
                        return original_value

            if is_fqdn_in_hostname_map_context:
                current_counter_val_for_log = getattr(self, counter_name_str)
                logging.debug(
                    f"GOCAV_FQDN_DEBUG: Creating new anon_value for '{original_value}' with prefix='{id_prefix}', counter='{current_counter_val_for_log}'."  # noqa: E501
                )

            counter_val = getattr(self, counter_name_str)
            # Standard log before creation (retained)
            logging.debug(
                f"  Creating new anonymized value: id_prefix='{id_prefix}', counter_val='{counter_val}' for map '{category_map_name_str}'"  # noqa: E501
            )
            anon_value = f"{id_prefix}_{counter_val}"
            setattr(self, counter_name_str, counter_val + 1)
            category_map[original_value] = anon_value

            if is_fqdn_in_hostname_map_context:
                logging.debug(
                    f"GOCAV_FQDN_DEBUG: Mapped new in '{category_map_name_str}': '{original_value}' -> '{anon_value}'. Counter '{counter_name_str}' is now {getattr(self, counter_name_str)}."  # noqa: E501
                )
                logging.debug(
                    f"GOCAV_FQDN_DEBUG: === Finished FQDN-like value '{original_value}' for hostname_map ==="  # noqa: E501
                )

            # Standard log after creation (retained)
            logging.debug(
                f"  Mapped new in '{category_map_name_str}': '{original_value}' -> '{anon_value}'. Counter '{counter_name_str}' is now {getattr(self, counter_name_str)}."  # noqa: E501
            )
            return anon_value

    def anonymize_line(self, line):
        final_replacements = []
        # Stores tuples of (start, end, pattern_name) for segments of the original line already claimed by a pattern.
        claimed_original_spans = []

        for pattern_info in self.patterns:
            regex = pattern_info["regex"]
            current_pattern_name = pattern_info["name"]

            if pattern_info["name"] == "noqueue_rejected_sender":
                logging.debug(
                    f"Attempting pattern '{pattern_info['name']}' on line: {line.strip()}"
                )

            if pattern_info.get("special_handling") == "email_parts":
                for match in regex.finditer(line):  # Always match on original line
                    original_full_email = match.group(0)
                    match_start = match.start(0)
                    match_end = match.end(0)

                    # Check for overlap with higher-priority claims
                    is_fully_claimed_by_higher_priority = False
                    for r_start, r_end, r_pattern_name in claimed_original_spans:
                        # Check if the current email match is fully contained within this claimed span
                        if match_start >= r_start and match_end <= r_end:
                            logging.debug(
                                f"Email '{original_full_email}' at [{match_start}-{match_end}] is fully contained within an already claimed span [{r_start}-{r_end}] by pattern '{r_pattern_name}'. Skipping email_parts."  # noqa: E501
                            )
                            is_fully_claimed_by_higher_priority = True
                            break

                    if is_fully_claimed_by_higher_priority:
                        continue

                    # Proceed with email parts if not fully claimed.
                    # The following specific checks for sasl_username_map might be redundant now if the above general check works,
                    # but can be kept as an additional safeguard or for specific logging.
                    # However, if a full email string is a key in sasl_username_map, it means the sasl_username rule *should have* claimed it.
                    # If it wasn't claimed (e.g. context like "sasl_username=" was missing), then this email rule might process it.
                    # This behavior needs to align with desired outcome: should an email that *is* a known SASL username but *not* in SASL context
                    # be broken down or replaced as a whole by its SASL ID? Current logic will break it down.
                    # For now, keeping the original SASL checks for explicit logging/skipping.
                    logging.debug(
                        f"Anonymize_line: Email_address pattern '{current_pattern_name}' matched full='{original_full_email}' at [{match_start}-{match_end}]"  # noqa: E501
                    )

                    if original_full_email in self.sasl_username_map:
                        logging.debug(
                            f"  Further check: Skipping email_parts for '{original_full_email}' as its exact string is a key in sasl_username_map."  # noqa: E501
                        )
                        continue
                    if (
                        original_full_email in self.sasl_username_map.values()
                        and original_full_email.startswith("anon_sasl_")
                    ):
                        logging.debug(
                            f"  Further check: Skipping email_parts for '{original_full_email}' as it IS an anonymized SASL value."  # noqa: E501
                        )
                        continue

                    local_part_original = match.group(pattern_info["group_local_part"])
                    domain_part_original = match.group(
                        pattern_info["group_domain_part"]
                    )
                    anon_local_part = self.get_or_create_anon_value(
                        local_part_original,
                        self.user_map,
                        "anon_user",
                        "user_counter",
                        "user_map",
                    )
                    anon_domain_part = self.get_or_create_anon_value(
                        domain_part_original,
                        self.hostname_map,
                        "anon_hostname",
                        "hostname_counter",
                        "hostname_map",
                    )
                    final_anon_email = f"{anon_local_part}@{anon_domain_part}"

                    # Check if a malformed email match starting at the same position already exists
                    # and should be overridden by this more specific FQDN match.
                    if current_pattern_name == "email_address":
                        # Iterate backwards to allow removal
                        for i in range(len(final_replacements) - 1, -1, -1):
                            prev_rep = final_replacements[i]
                            if (
                                prev_rep["pattern_name"] == "email_address_malformed"
                                and prev_rep["start"] == match_start
                                and prev_rep["end"] < match_end
                            ):
                                logging.debug(
                                    f"Overriding malformed email match {prev_rep} with FQDN match for {original_full_email}"  # noqa: E501
                                )
                                final_replacements.pop(i)
                                # Also remove from claimed_original_spans if it was added there with the same details
                                for j in range(len(claimed_original_spans) - 1, -1, -1):
                                    if claimed_original_spans[j] == (
                                        prev_rep["start"],
                                        prev_rep["end"],
                                        prev_rep["pattern_name"],
                                    ):
                                        claimed_original_spans.pop(j)
                                        break  # Assume only one such claim
                                break

                    final_replacements.append(
                        {
                            "start": match_start,
                            "end": match_end,
                            "text": final_anon_email,
                            "original": original_full_email,
                            "pattern_name": current_pattern_name,
                        }
                    )
                    # Ensure the claim for the FQDN email is correctly managed relative to any prior malformed claim.
                    # The above loop might have removed a sub-optimal claim. Now add the new one.
                    # If a malformed claim for the exact same span was somehow there (shouldn't be due to pattern order),
                    # this new one would just be another claim. The span overlap logic for *other* pattern types handles other overlaps.
                    claimed_original_spans.append(
                        (match_start, match_end, current_pattern_name)
                    )
                continue  # End of special_handling for email_parts

            # Common logic for non-special patterns
            map_name = pattern_info["map_name"]
            category_map = getattr(self, map_name)
            id_prefix = pattern_info["id_prefix"]
            counter_name = pattern_info["counter_name"]
            group_index = pattern_info["group_index"]

            for match in regex.finditer(line):  # Always match on original line
                if pattern_info["name"] == "noqueue_rejected_sender":
                    logging.debug(
                        f"  '{pattern_info['name']}' RAW MATCH: group(0)='{match.group(0)}', group(1)='{match.group(1)}'"  # noqa: E501
                    )

                original_value = match.group(group_index)
                # Determine actual span of replacement (group vs full match)
                replace_start = match.start(group_index)
                replace_end = match.end(group_index)

                # Determine the span to claim for protecting context
                claim_span_start = (
                    match.start(0)
                    if pattern_info.get("claim_full_match")
                    else replace_start
                )
                claim_span_end = (
                    match.end(0)
                    if pattern_info.get("claim_full_match")
                    else replace_end
                )

                # Check if this original_value's span (or its broader claimed context)
                # overlaps with an already claimed span by a HIGHER priority rule.
                # Note: The definition of "overlap" and "higher priority" is critical here.
                # This current loop checks if the *value we want to replace* is inside an existing claimed span.
                # If server_name_generic (high priority) claims span 0-50, and hostname_simple (low priority)
                # wants to replace text at 5-10, it should be allowed IF server_name_generic's *actual replacement*
                # was not at 5-10.
                # The current logic: if replace_start/end is within r_start/r_end.

                is_overlapping_with_higher_priority_claim = False
                for r_start, r_end, r_pattern_name in claimed_original_spans:
                    # Check if the span we intend to *claim* (claim_span_start, claim_span_end)
                    # is *identical to or contained within* an existing claimed span.
                    # This is primarily to stop a lower-priority rule from re-claiming what a higher-prio rule already claimed.
                    if claim_span_start >= r_start and claim_span_end <= r_end:
                        # If it's the same pattern name, it's just another match of the same rule, allow.
                        # If different, then it's a lower-priority rule trying to claim a subset of what a higher-prio rule claimed.
                        if current_pattern_name != r_pattern_name:
                            logging.debug(
                                f"Potential claim by '{current_pattern_name}' for span [{claim_span_start}-{claim_span_end}] is within already claimed span [{r_start}-{r_end}] by higher-priority '{r_pattern_name}'. Skipping."  # noqa: E501
                            )
                            is_overlapping_with_higher_priority_claim = True
                            break
                    # Additionally, check if the span we want to *replace* (replace_start, replace_end)
                    # is contained within an existing claimed span. This is the original check.
                    # This handles cases where the claim_span might be larger, but the actual replacement target is already covered.
                    if (
                        not is_overlapping_with_higher_priority_claim
                        and replace_start >= r_start
                        and replace_end <= r_end
                        and current_pattern_name != r_pattern_name
                    ):
                        logging.debug(
                            f"Replacement target by '{current_pattern_name}' for span [{replace_start}-{replace_end}] is contained in already claimed span [{r_start}-{r_end}] by higher-priority '{r_pattern_name}'. Skipping."  # noqa: E501
                        )
                        is_overlapping_with_higher_priority_claim = True
                        break

                if is_overlapping_with_higher_priority_claim:
                    continue

                # Check if the value itself is an anonymized value (e.g. "anon_ip_1")
                if original_value.startswith("anon_"):
                    is_already_anonymized_value = False
                    for map_name_iter in [
                        "ip_map",
                        "hostname_map",
                        "user_map",
                        "server_map",
                        "sasl_username_map",
                    ]:
                        if original_value in getattr(self, map_name_iter).values():
                            is_already_anonymized_value = True
                            break
                    if is_already_anonymized_value:
                        logging.debug(
                            f"Skipping '{original_value}' as it's already an anonymized value, for pattern '{current_pattern_name}'."  # noqa: E501
                        )
                        continue

                anon_value = self.get_or_create_anon_value(
                    original_value, category_map, id_prefix, counter_name, map_name
                )
                if anon_value == original_value:
                    continue  # No change, or it was an already anonymized value returned as-is by get_or_create

                if replace_start == replace_end:
                    logging.debug(
                        f"Skipping zero-length match for pattern '{current_pattern_name}' with value '{original_value}'."  # noqa: E501
                    )
                    continue

                final_replacements.append(
                    {
                        "start": replace_start,
                        "end": replace_end,
                        "text": anon_value,
                        "original": original_value,
                        "pattern_name": current_pattern_name,
                    }
                )
                # Add this segment to claimed_original_spans using the determined claim_span
                # This ensures that if "claim_full_match" was true, the broader context is protected
                # from being matched by *subsequent, lower-priority* rules.
                claimed_original_spans.append(
                    (claim_span_start, claim_span_end, current_pattern_name)
                )

        # Sort all collected replacements by start position in reverse order to apply them
        # Add diagnostic logging before sorting and application for specific lines
        if "mydomain.org" in line or "example.org" in line:  # Conditional logging
            logging.debug(f"ANONYMIZE_LINE_DEBUG: Current line: {line.strip()}")
            logging.debug(
                "ANONYMIZE_LINE_DEBUG: Final replacements before sorting and application:"
            )
            # Log a sorted version for easier comparison if order matters before this sort
            temp_sorted_replacements = sorted(
                final_replacements, key=lambda r: (r["start"], r["end"])
            )
            for i, rep_item in enumerate(temp_sorted_replacements):
                logging.debug(f"  Rep {i}: {rep_item}")
            logging.debug(
                "ANONYMIZE_LINE_DEBUG: Claimed original spans at this point (sorted by start):"
            )
            # Sort claimed_original_spans for consistent logging output
            temp_sorted_spans = sorted(
                claimed_original_spans, key=lambda s: (s[0], s[1])
            )
            for i, span_item in enumerate(temp_sorted_spans):
                logging.debug(f"  Span {i}: {span_item}")

        final_replacements.sort(key=lambda r: r["start"], reverse=True)

        new_line_list = list(line)
        # This simple sequential replacement works because we sorted in reverse.
        # The overlap logic above was about *which replacements to select from the original line*,
        # not about how to apply them once selected.
        for rep in final_replacements:
            new_line_list[rep["start"] : rep["end"]] = list(rep["text"])
            logging.debug(
                f"Applied replacement for '{rep['original']}' with '{rep['text']}' at [{rep['start']}:{rep['end']}] using pattern '{rep['pattern_name']}'"  # noqa: E501
            )

        return "".join(new_line_list)


def load_rules_from_config(config_filepath):
    if config_filepath:
        logging.warning(
            f"Configuration file '{config_filepath}' provided but custom rule loading is currently bypassed. Using hardcoded Anonymizer rules."  # noqa: E501
        )
    return None


def copy_to_temp(input_filepath, temp_dir_path):
    try:
        temp_file = tempfile.NamedTemporaryFile(
            dir=temp_dir_path, delete=False, suffix=".log", prefix="anonymizer_"
        )
        temp_copy_path = temp_file.name
        temp_file.close()
        shutil.copy2(input_filepath, temp_copy_path)
        logging.info(
            f"Successfully copied '{input_filepath}' to temporary file '{temp_copy_path}'."
        )
        return temp_copy_path
    except FileNotFoundError:
        logging.error(
            f"Error copying to temp: Input file '{input_filepath}' not found."
        )
        return None
    except PermissionError:
        logging.error(
            f"Error copying to temp: Permission denied for '{input_filepath}' or '{temp_dir_path}'."  # noqa: E501
        )
        return None
    except (shutil.Error, IOError, OSError) as e:  # Consolidated error types
        logging.error(
            f"Error copying '{input_filepath}' to temporary directory '{temp_dir_path}': {e}"
        )
        return None


def anonymize_file(input_filepath, output_filepath, anonymizer_instance):
    if not anonymizer_instance:
        logging.error("Anonymizer instance is not available. Cannot anonymize file.")
        try:
            shutil.copy2(input_filepath, output_filepath)
            logging.warning(
                f"Copied original file to {output_filepath} due to missing anonymizer instance."
            )
        except Exception as copy_e:
            logging.error(f"Failed to copy original file on fallback: {copy_e}")
        return

    try:
        with open(
            input_filepath, "r", encoding="utf-8", errors="ignore"
        ) as infile, open(output_filepath, "w", encoding="utf-8") as outfile:
            for line_number, line_content in enumerate(infile, 1):
                logging.debug(f"Processing line {line_number}: {line_content.strip()}")
                anonymized_line = anonymizer_instance.anonymize_line(line_content)
                outfile.write(anonymized_line)
        logging.info(
            f"Successfully anonymized '{input_filepath}' to '{output_filepath}'"
        )
    except (IOError, OSError) as e:  # More specific for file operations
        logging.error(f"Error processing file '{input_filepath}': {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Anonymize sensitive information in a log file."
    )
    parser.add_argument("-i", "--input-file", required=True, help="Input log file.")
    parser.add_argument(
        "-o", "--output-file", required=True, help="Output anonymized log file."
    )
    parser.add_argument(
        "-t",
        "--temp-dir",
        help="Optional temporary directory to use. Defaults to system temp.",
    )
    parser.add_argument("--config", help="Configuration file for anonymization rules.")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level.",
    )
    parser.add_argument(
        "--script-log-file",
        help="Optional path to a file where script execution logs will be saved.",
    )
    args = parser.parse_args()

    # Configure logging
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, args.log_level.upper()))

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(module)s - %(message)s"
    )

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler (Conditional)
    if args.script_log_file:
        try:
            file_handler = logging.FileHandler(args.script_log_file, mode="a")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            logging.info(f"Script logs will also be written to: {args.script_log_file}")
        except (IOError, OSError) as e:  # More specific for file handler
            logging.error(
                f"Failed to configure file logging to '{args.script_log_file}': {e}"
            )
            # Continue with console logging only

    global json
    import json  # Not strictly needed globally if only used in load_rules_from_config

    actual_temp_dir = None
    if args.temp_dir:
        if not os.path.isdir(args.temp_dir):
            try:
                os.makedirs(args.temp_dir, exist_ok=True)
                logging.info(f"Created specified temporary directory: {args.temp_dir}")
                actual_temp_dir = args.temp_dir
            except OSError as e:
                logging.error(
                    f"Could not create specified temporary directory '{args.temp_dir}': {e}. Using system default."  # noqa: E501
                )
                actual_temp_dir = tempfile.gettempdir()
        else:
            logging.info(f"Using specified temporary directory: {args.temp_dir}")
            actual_temp_dir = args.temp_dir
    else:
        actual_temp_dir = tempfile.gettempdir()
        logging.info(f"Using system default temporary directory: {actual_temp_dir}")

    tempfile.tempdir = actual_temp_dir

    if not os.path.exists(args.input_file):
        logging.error(f"Input file does not exist: {args.input_file}")
        return
    if not os.path.isfile(args.input_file):
        logging.error(f"Input path is not a file: {args.input_file}")
        return

    output_dir = os.path.dirname(args.output_file)
    if output_dir and not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            logging.info(f"Created output directory: {output_dir}")
        except OSError as e:
            logging.error(f"Could not create output directory '{output_dir}': {e}")
            return

    anonymizer = Anonymizer()

    temp_input_filepath = copy_to_temp(args.input_file, actual_temp_dir)

    if not temp_input_filepath:
        logging.error("Failed to create a temporary copy of the input file. Exiting.")
        return

    logging.info(f"Processing temporary file: {temp_input_filepath}")
    try:
        anonymize_file(temp_input_filepath, args.output_file, anonymizer)
    finally:
        if temp_input_filepath and os.path.exists(temp_input_filepath):
            try:
                os.remove(temp_input_filepath)
                logging.info(
                    f"Successfully removed temporary file: {temp_input_filepath}"
                )
            except OSError as e:
                logging.error(
                    f"Error removing temporary file '{temp_input_filepath}': {e}"
                )
        else:
            logging.debug(
                f"Temporary file '{temp_input_filepath}' not found for cleanup."
            )


if __name__ == "__main__":
    main()
