import pytest
from pathlib import Path
import csv
import gzip
from unittest.mock import (
    MagicMock,
    # call, # F401: call imported but unused
    patch,
)
import logging
from datetime import datetime

# Assuming utils.py is in lib.maillogsentinel and provides is_gzip
from lib.maillogsentinel.utils import is_gzip
from lib.maillogsentinel.parser import (
    extract_entries,
)  # _parse_log_line is no longer here

# --- Mocks and Fixtures ---
# These fixtures are still used by tests for extract_entries


@pytest.fixture
def mock_logger():
    return MagicMock(spec=logging.Logger)


@pytest.fixture
def mock_ip_info_mgr():
    mgr = MagicMock()
    # Default behavior: return None for any IP
    mgr.lookup_ip_info.return_value = None
    return mgr


@pytest.fixture
def mock_reverse_lookup_func():
    # Default behavior: return (None, "Mocked DNS Error")
    # This mock is passed to extract_entries, which then passes it to _parse_log_line (now in log_utils)
    return MagicMock(return_value=(None, "Mocked DNS Error"))


@pytest.fixture
def current_year():
    return datetime.now().year


# --- Tests for _parse_log_line ---
# These tests have been moved to tests/lib/maillogsentinel/test_log_utils.py


# --- Tests for extract_entries ---
# These tests remain here as extract_entries is still in parser.py
# They will implicitly test _parse_log_line via their calls to extract_entries.
SAMPLE_LOG_LINE_1 = "Mar 15 10:00:00 server1 postfix/submission/smtpd[100]: client=unknown[1.1.1.1], sasl_method=PLAIN, sasl_username=user1@example.com"
SAMPLE_LOG_LINE_2 = "Mar 15 10:05:00 server1 postfix/submission/smtpd[101]: client=unknown[2.2.2.2], sasl_method=PLAIN, sasl_username=user2@example.com"
MALFORMED_LOG_LINE = "This is not a log line."


@pytest.fixture
def setup_files(tmp_path: Path):
    maillog = tmp_path / "mail.log"
    maillog_old = tmp_path / "mail.log.1.gz"  # Example of a rotated log
    csv_output = tmp_path / "output.csv"
    return maillog, maillog_old, csv_output


def test_extract_entries_new_csv(
    tmp_path: Path,
    mock_logger,
    mock_ip_info_mgr,
    mock_reverse_lookup_func,
    current_year,
):
    maillog = tmp_path / "mail.log"
    csv_output_path_str = str(tmp_path / "output.csv")

    maillog.write_text(SAMPLE_LOG_LINE_1 + "\n" + SAMPLE_LOG_LINE_2 + "\n")

    # Mock DNS and IP lookups
    mock_reverse_lookup_func.side_effect = [("host1.com", None), ("host2.com", None)]
    mock_ip_info_mgr.lookup_ip_info.side_effect = [
        {"country_code": "C1", "asn": "AS1", "aso": "ISP1"},
        {"country_code": "C2", "asn": "AS2", "aso": "ISP2"},
    ]

    new_offset = extract_entries(
        filepaths=[maillog],
        maillog_path_obj=maillog,
        csvpath_param=csv_output_path_str,
        logger=mock_logger,
        ip_info_mgr=mock_ip_info_mgr,
        reverse_lookup_func=mock_reverse_lookup_func,
        is_gzip_func=is_gzip,  # Using the actual is_gzip from utils
        offset=0,
        progress_callback=None,
    )

    assert Path(csv_output_path_str).is_file()
    with Path(csv_output_path_str).open("r") as f:
        reader = csv.reader(f, delimiter=";")
        rows = list(reader)

    assert rows[0] == [
        "server",
        "date",
        "ip",
        "user",
        "hostname",
        "reverse_dns_status",
        "country_code",
        "asn",
        "aso",
    ]
    assert len(rows) == 3  # Header + 2 data rows
    assert rows[1] == [
        "server1",
        f"15/03/{current_year} 10:00",
        "1.1.1.1",
        "user1@example.com",
        "host1.com",
        "OK",
        "C1",
        "AS1",
        "ISP1",
    ]
    assert rows[2] == [
        "server1",
        f"15/03/{current_year} 10:05",
        "2.2.2.2",
        "user2@example.com",
        "host2.com",
        "OK",
        "C2",
        "AS2",
        "ISP2",
    ]
    assert new_offset == maillog.stat().st_size


def test_extract_entries_append_csv(
    tmp_path: Path,
    mock_logger,
    mock_ip_info_mgr,
    mock_reverse_lookup_func,
    current_year,
):
    maillog = tmp_path / "mail.log"
    csv_file = tmp_path / "output.csv"
    csv_output_path_str = str(csv_file)

    # Pre-populate CSV
    with csv_file.open("w", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(
            [
                "server",
                "date",
                "ip",
                "user",
                "hostname",
                "reverse_dns_status",
                "country_code",
                "asn",
                "aso",
            ]
        )
        writer.writerow(
            [
                "oldserver",
                f"01/01/{current_year} 00:00",
                "0.0.0.0",
                "olduser",
                "old.host",
                "OK",
                "C0",
                "AS0",
                "ISP0",
            ]
        )

    maillog.write_text(SAMPLE_LOG_LINE_1 + "\n")
    mock_reverse_lookup_func.return_value = ("host1.com", None)
    mock_ip_info_mgr.lookup_ip_info.return_value = {
        "country_code": "C1",
        "asn": "AS1",
        "aso": "ISP1",
    }

    extract_entries(
        [maillog],
        maillog,
        csv_output_path_str,
        mock_logger,
        mock_ip_info_mgr,
        mock_reverse_lookup_func,
        is_gzip,
        0,
        progress_callback=None,
    )

    with csv_file.open("r") as f:
        reader = csv.reader(f, delimiter=";")
        rows = list(reader)

    assert len(rows) == 3  # Original Header + Original Data + 1 new data row
    assert rows[2] == [
        "server1",
        f"15/03/{current_year} 10:00",
        "1.1.1.1",
        "user1@example.com",
        "host1.com",
        "OK",
        "C1",
        "AS1",
        "ISP1",
    ]


def test_extract_entries_offset_handling(
    tmp_path: Path, mock_logger, mock_ip_info_mgr, mock_reverse_lookup_func
):
    maillog = tmp_path / "mail.log"
    csv_output_path_str = str(tmp_path / "output.csv")

    # Write first line, then simulate reading it by setting offset
    first_line_bytes = (SAMPLE_LOG_LINE_1 + "\n").encode("utf-8")
    maillog.write_bytes(first_line_bytes + (SAMPLE_LOG_LINE_2 + "\n").encode("utf-8"))

    initial_offset = len(first_line_bytes)

    mock_reverse_lookup_func.return_value = (
        "host2.com",
        None,
    )  # Only second line should be processed
    mock_ip_info_mgr.lookup_ip_info.return_value = {
        "country_code": "C2",
        "asn": "AS2",
        "aso": "ISP2",
    }

    new_offset = extract_entries(
        [maillog],
        maillog,
        csv_output_path_str,
        mock_logger,
        mock_ip_info_mgr,
        mock_reverse_lookup_func,
        is_gzip,
        initial_offset,
        progress_callback=None,
    )

    with Path(csv_output_path_str).open("r") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert len(rows) == 2  # Header + 1 data row (only second line)
    assert "user2@example.com" in rows[1]
    assert new_offset == maillog.stat().st_size


def test_extract_entries_log_rotation(
    tmp_path: Path, mock_logger, mock_ip_info_mgr, mock_reverse_lookup_func
):
    maillog = tmp_path / "mail.log"
    csv_output_path_str = str(tmp_path / "output.csv")

    # Simulate smaller current log file than offset (rotation)
    maillog.write_text(SAMPLE_LOG_LINE_1 + "\n")  # Small content
    large_offset = 10000

    mock_reverse_lookup_func.return_value = ("host1.com", None)
    mock_ip_info_mgr.lookup_ip_info.return_value = {
        "country_code": "C1",
        "asn": "AS1",
        "aso": "ISP1",
    }

    extract_entries(
        [maillog],
        maillog,
        csv_output_path_str,
        mock_logger,
        mock_ip_info_mgr,
        mock_reverse_lookup_func,
        is_gzip,
        large_offset,
        progress_callback=None,
    )

    mock_logger.info.assert_any_call(
        f"Rotation detected for {maillog.name}, resetting offset {large_offset} -> 0"
    )
    with Path(csv_output_path_str).open("r") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert "user1@example.com" in rows[1]  # Ensure it processed the line after reset


def test_extract_entries_gzip_file(
    tmp_path: Path,
    mock_logger,
    mock_ip_info_mgr,
    mock_reverse_lookup_func,
    current_year,
):
    gz_file = tmp_path / "mail.log.1.gz"
    csv_output_path_str = str(tmp_path / "output.csv")

    with gzip.open(gz_file, "wt", encoding="utf-8") as f:
        f.write(SAMPLE_LOG_LINE_1 + "\n")
        f.write(SAMPLE_LOG_LINE_2 + "\n")

    mock_reverse_lookup_func.side_effect = [
        ("gzhost1.com", None),
        ("gzhost2.com", None),
    ]
    mock_ip_info_mgr.lookup_ip_info.side_effect = [
        {"country_code": "GZ1", "asn": "ASGZ1", "aso": "ISPGZ1"},
        {"country_code": "GZ2", "asn": "ASGZ2", "aso": "ISPGZ2"},
    ]

    # For gzipped files, offset is not used for reading within the file,
    # but the main maillog_path_obj might have an offset from previous runs.
    # Here, filepaths only contains the gz file, so extract_entries's internal curr_off won't apply to its content reading.
    new_offset_returned = extract_entries(
        filepaths=[gz_file],
        maillog_path_obj=tmp_path
        / "dummy_main_mail.log",  # A dummy main log not in filepaths for this test
        csvpath_param=csv_output_path_str,
        logger=mock_logger,
        ip_info_mgr=mock_ip_info_mgr,
        reverse_lookup_func=mock_reverse_lookup_func,
        is_gzip_func=is_gzip,
        offset=0,
        progress_callback=None,
    )

    with Path(csv_output_path_str).open("r") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert len(rows) == 3  # Header + 2 data rows
    assert rows[1] == [
        "server1",
        f"15/03/{current_year} 10:00",
        "1.1.1.1",
        "user1@example.com",
        "gzhost1.com",
        "OK",
        "GZ1",
        "ASGZ1",
        "ISPGZ1",
    ]
    assert (
        new_offset_returned == 0
    )  # Offset for the dummy_main_mail.log remains unchanged


def test_extract_entries_malformed_lines(
    tmp_path: Path, mock_logger, mock_ip_info_mgr, mock_reverse_lookup_func
):
    maillog = tmp_path / "mail.log"
    csv_output_path_str = str(tmp_path / "output.csv")

    maillog.write_text(MALFORMED_LOG_LINE + "\n" + SAMPLE_LOG_LINE_1 + "\n")

    mock_reverse_lookup_func.return_value = ("host1.com", None)
    mock_ip_info_mgr.lookup_ip_info.return_value = {
        "country_code": "C1",
        "asn": "AS1",
        "aso": "ISP1",
    }

    extract_entries(
        [maillog],
        maillog,
        csv_output_path_str,
        mock_logger,
        mock_ip_info_mgr,
        mock_reverse_lookup_func,
        is_gzip,
        0,
        progress_callback=None,
    )

    with Path(csv_output_path_str).open("r") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert len(rows) == 2  # Header + 1 valid data row
    assert "user1@example.com" in rows[1]
    # Check that _parse_log_line was called for malformed line (and returned None, not writing to CSV)
    # This is implicitly tested by only one valid row appearing.


def test_extract_entries_empty_file(
    tmp_path: Path, mock_logger, mock_ip_info_mgr, mock_reverse_lookup_func
):
    maillog = tmp_path / "mail.log"
    csv_output_path_str = str(tmp_path / "output.csv")
    maillog.write_text("")  # Empty file

    new_offset = extract_entries(
        [maillog],
        maillog,
        csv_output_path_str,
        mock_logger,
        mock_ip_info_mgr,
        mock_reverse_lookup_func,
        is_gzip,
        0,
    )

    with Path(csv_output_path_str).open("r") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert len(rows) == 1  # Only header
    assert new_offset == 0


def test_extract_entries_file_stat_error(
    tmp_path: Path, mock_logger, mock_ip_info_mgr, mock_reverse_lookup_func
):
    # This test requires more advanced mocking of Path.stat() if it's not found
    # For now, simulate by providing a path that might cause issues, or rely on logger check
    unstattable_file = tmp_path / "unstattable.log"
    # Don't create it, or mock stat to raise OSError

    # Mock Path.stat for the specific unstattable_file instance
    original_stat = Path.stat

    def mock_stat(self, *args, **kwargs):
        if self == unstattable_file:
            raise OSError("Mocked stat error")
        return original_stat(self, *args, **kwargs)

    with patch.object(Path, "stat", mock_stat):
        extract_entries(
            filepaths=[unstattable_file],
            maillog_path_obj=tmp_path / "main.log",  # Dummy main log
            csvpath_param=str(tmp_path / "output.csv"),
            logger=mock_logger,
            ip_info_mgr=mock_ip_info_mgr,
            reverse_lookup_func=mock_reverse_lookup_func,
            is_gzip_func=is_gzip,
            offset=0,
            progress_callback=None,
        )
    mock_logger.error.assert_any_call(
        f"Could not get size of {unstattable_file}: Mocked stat error"
    )
