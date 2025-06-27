import pytest
from pathlib import Path
import csv
import smtplib  # For type hinting, will be mocked
from email.message import EmailMessage
from unittest.mock import MagicMock, patch, mock_open
import logging

from lib.maillogsentinel.report import (
    _analyze_csv_for_report,
    send_report,
    # get_extraction_frequency, # F401: imported but unused
)
from lib.maillogsentinel.config import (
    AppConfig,
)  # Needed for AppConfig type hint and creating mock instances


# --- Fixtures ---
@pytest.fixture
def mock_logger():
    return MagicMock(spec=logging.Logger)


@pytest.fixture
def mock_app_config(tmp_path: Path):
    config = MagicMock(spec=AppConfig)
    config.report_email = "recipient@example.com"
    config.working_dir = tmp_path
    config.csv_filename = "test_maillog.csv"
    config.report_subject_prefix = "[MLS_TEST]"
    config.report_sender_override = None  # Default to no override
    return config


@pytest.fixture
def sample_csv_path(tmp_path: Path) -> Path:
    csv_file = tmp_path / "test_maillog.csv"
    return csv_file


@pytest.fixture
def today_date_str():
    from datetime import datetime

    return datetime.now().strftime("%d/%m/%Y")


# --- Tests for _analyze_csv_for_report ---


def create_csv_content(header: list, data_rows: list, delimiter: str = ";") -> str:
    from io import StringIO

    si = StringIO()
    writer = csv.writer(si, delimiter=delimiter)
    writer.writerow(header)
    writer.writerows(data_rows)
    return si.getvalue()


HEADER = [
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


def test_analyze_csv_empty(sample_csv_path: Path, mock_logger, today_date_str):
    sample_csv_path.write_text("")  # Empty file
    stats = _analyze_csv_for_report(sample_csv_path, mock_logger, today_date_str)
    # Depending on implementation, might return None or default stats dictionary
    # Current implementation logs error and returns None if next(reader) fails due to empty.
    # Let's adjust test if it should return default stats for an empty (but existing) file.
    # For now, assuming it handles it by not crashing.
    # The code has been updated since original thought: it will try to skip header.
    # If only header or empty, it will produce zero counts.

    # If CSV is completely empty (0 bytes), open might not error but next(reader) would.
    # If CSV has only header, next(reader) is fine, loop is empty.
    # Let's test with only header first.
    sample_csv_path.write_text(";".join(HEADER) + "\n")
    stats = _analyze_csv_for_report(sample_csv_path, mock_logger, today_date_str)
    assert stats is not None
    assert stats["total_today"] == 0
    assert stats["top10_today"] == []
    assert stats["csv_lines_str"] == "0"  # 1 line (header) - 1 = 0


def test_analyze_csv_valid_data(sample_csv_path: Path, mock_logger, today_date_str):
    data = [
        [
            "srv1",
            f"{today_date_str} 10:00",
            "1.1.1.1",
            "user1",
            "host1",
            "OK",
            "US",
            "AS1",
            "ISP1",
        ],
        [
            "srv1",
            f"{today_date_str} 10:05",
            "1.1.1.1",
            "user1",
            "host1",
            "OK",
            "US",
            "AS1",
            "ISP1",
        ],  # Repeat for count
        [
            "srv2",
            f"{today_date_str} 11:00",
            "2.2.2.2",
            "user2",
            "host2",
            "DNS_ERROR",
            "CA",
            "AS2",
            "ISP2",
        ],
        [
            "srv3",
            "01/01/2000 00:00",
            "3.3.3.3",
            "user3",
            "host3",
            "OK",
            "GB",
            "AS3",
            "ISP3",
        ],  # Different date
    ]
    sample_csv_path.write_text(create_csv_content(HEADER, data))

    stats = _analyze_csv_for_report(sample_csv_path, mock_logger, today_date_str)
    assert stats["total_today"] == 3
    assert len(stats["top10_today"]) == 2
    # Expect country code ('US') to be part of the tuple key
    assert stats["top10_today"][0] == (("user1", "1.1.1.1", "host1", "US"), 2)
    assert stats["top10_usernames"][0] == ("user1", 2)
    assert stats["total_rev_dns_failures"] == 1
    assert stats["rev_dns_error_counts"][0] == ("DNS_ERROR", 1)
    assert stats["top10_countries"][0] == ("US", 2)
    assert stats["top10_aso"][0] == ("ISP1", 2)
    assert stats["top10_asn"][0] == ("AS1", 2)
    assert stats["csv_lines_str"] == "4"  # 5 lines - 1 header = 4


def test_analyze_csv_malformed_row(sample_csv_path: Path, mock_logger, today_date_str):
    # Valid row, malformed row, another valid row
    content = (
        ";".join(HEADER)
        + "\n"
        + f"srv1;{today_date_str} 10:00;1.1.1.1;user1;host1;OK;US;AS1;ISP1\n"
        + f"srv2;{today_date_str} 11:00;2.2.2.2;user2;host2;FAIL\n"  # Missing fields
        + f"srv3;{today_date_str} 12:00;3.3.3.3;user3;host3;OK;CA;AS3;ISP3\n"
    )
    sample_csv_path.write_text(content)
    stats = _analyze_csv_for_report(sample_csv_path, mock_logger, today_date_str)
    assert stats["total_today"] == 2  # Only two valid rows for today
    # Updated expected log message to include the row number.
    # The malformed row is the 2nd data row, which is 3rd line in CSV (header is 1st).
    # The enumerate in _analyze_csv_for_report starts at 1 for data rows,
    # so row_num in the log is relative to data rows.
    # The log message uses `row_num + 1` where row_num is from enumerate(reader, start=1)
    # after header. So, 1st data row is row_num=1, logged as row 2.
    # 2nd data row (malformed) is row_num=2, logged as row 3.
    expected_log_message = (
        f"Skipping malformed CSV row 3 (expected 9 fields, got 6): "
        f"['srv2', '{today_date_str} 11:00', '2.2.2.2', 'user2', 'host2', 'FAIL']"
    )
    mock_logger.warning.assert_any_call(expected_log_message)


def test_analyze_csv_io_error_read(sample_csv_path: Path, mock_logger, today_date_str):
    # sample_csv_path must exist for Path.open to be called on it, but we want the *read* to fail.
    sample_csv_path.touch()  # Ensure the file path exists to avoid FileNotFoundError from Path object itself
    m = mock_open()
    m.side_effect = IOError(
        "File read error"
    )  # This error should be caught by the except block
    with patch.object(Path, "open", m):
        stats = _analyze_csv_for_report(sample_csv_path, mock_logger, today_date_str)
        assert stats is None
        # The error message in the code is "Could not read or parse CSV file {csv_file_path}: {e}"
        # So, the expected log is exactly that, with "File read error" as e.
        mock_logger.error.assert_called_with(
            f"Could not read or parse CSV file {sample_csv_path}: File read error"
        )


def test_analyze_csv_stat_error(sample_csv_path: Path, mock_logger, today_date_str):
    sample_csv_path.write_text(
        ";".join(HEADER)
        + "\n"
        + f"srv1;{today_date_str} 10:00;1.1.1.1;user1;host1;OK;US;AS1;ISP1\n"
    )

    with patch.object(Path, "stat", side_effect=OSError("Stat error")):
        stats = _analyze_csv_for_report(sample_csv_path, mock_logger, today_date_str)
        assert stats is not None  # Analysis should proceed, but size/lines might be N/A
        assert stats["csv_size_k_str"] == "N/A"
        # Line count is separate, let's assume it also fails or test separately
        mock_logger.error.assert_any_call(
            f"Could not get size of CSV file {sample_csv_path}: Stat error"
        )


# --- Tests for send_report ---


@patch("lib.maillogsentinel.report.smtplib.SMTP")
@patch("lib.maillogsentinel.report._analyze_csv_for_report")
@patch("lib.maillogsentinel.report.getpass.getuser")
@patch("lib.maillogsentinel.report.socket.getfqdn")
@patch("lib.maillogsentinel.report.socket.gethostname")  # Fallback for getfqdn
@patch("lib.maillogsentinel.report.socket.gethostbyname")
@patch("lib.maillogsentinel.report.get_extraction_frequency")
def test_send_report_success(
    mock_get_freq,
    mock_gethostbyname,
    mock_gethostname,
    mock_getfqdn,
    mock_getuser,
    mock_analyze_csv,
    mock_smtp_class,
    mock_app_config: AppConfig,
    sample_csv_path: Path,
    mock_logger,
):
    # Setup mocks
    mock_get_freq.return_value = "daily"
    mock_getfqdn.return_value = "my.server.com"
    mock_gethostname.return_value = "my.server.com"  # Consistent
    mock_gethostbyname.return_value = "192.168.1.100"
    mock_getuser.return_value = "testuser"

    # Create a dummy CSV file that _analyze_csv_for_report would expect
    sample_csv_path.write_text("header1;header2\nval1;val2\n")

    # Mock what _analyze_csv_for_report returns
    mock_analyze_csv.return_value = {
        "total_today": 10,
        # Include country code in the tuple key, e.g., "CC" for country code
        "top10_today": [(("user", "ip", "host", "CC"), 5)],
        "top10_usernames": [("user", 5)],
        "total_rev_dns_failures": 1,
        "rev_dns_error_counts": [("Timeout", 1)],
        "top10_countries": [("US", 5)],
        "top10_aso": [("ISP", 5)],
        "top10_asn": [("AS123", 5)],
        "csv_size_k_str": "1.0K",
        "csv_lines_str": "100",
    }
    mock_smtp_instance = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance

    script_name = "MailLogSentinelTest"
    script_version = "0.1-test"

    send_report(mock_app_config, mock_logger, script_name, script_version)

    # Assertions
    mock_analyze_csv.assert_called_once()
    mock_smtp_class.assert_called_with("localhost")
    mock_smtp_instance.send_message.assert_called_once()

    sent_msg: EmailMessage = mock_smtp_instance.send_message.call_args[0][0]
    assert sent_msg["To"] == "recipient@example.com"
    assert sent_msg["From"] == "testuser@my.server.com"  # Default sender
    assert mock_app_config.report_subject_prefix in sent_msg["Subject"]
    assert script_name in sent_msg["Subject"]
    assert "my.server.com" in sent_msg["Subject"]

    # For multipart messages (with attachment), get_content() doesn't work directly for the text body.
    # The text body is expected to be the first part.
    body_part = sent_msg.get_payload(0)
    body = body_part.get_payload(decode=True).decode(
        body_part.get_content_charset(failobj="utf-8")
    )

    assert "Total attempts today: 10" in body
    assert "Top 10 failed authentications today:" in body
    assert (
        mock_app_config.csv_filename in body
    )  # "Please see attached: test_maillog.csv"

    attachments = list(sent_msg.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == mock_app_config.csv_filename
    mock_logger.info.assert_any_call(
        f"Report sent from testuser@my.server.com to recipient@example.com"
    )


def test_send_report_no_recipient(mock_app_config: AppConfig, mock_logger):
    mock_app_config.report_email = None
    send_report(mock_app_config, mock_logger, "test_script", "0.1")
    mock_logger.error.assert_called_with(
        "No email address configured for report (report -> email in config)."
    )


def test_send_report_csv_not_found(mock_app_config: AppConfig, mock_logger):
    # Ensure CSV does not exist by using a different filename than sample_csv_path would create
    mock_app_config.csv_filename = "non_existent.csv"
    expected_csv_path = mock_app_config.working_dir / "non_existent.csv"

    send_report(mock_app_config, mock_logger, "test_script", "0.1")
    mock_logger.warning.assert_called_with(
        f"CSV file {expected_csv_path} not found. No report to send."
    )


@patch("lib.maillogsentinel.report._analyze_csv_for_report")
def test_send_report_analysis_fails(
    mock_analyze_csv, mock_app_config: AppConfig, sample_csv_path: Path, mock_logger
):
    sample_csv_path.write_text("data")  # CSV exists
    mock_analyze_csv.return_value = None  # Analysis fails

    send_report(mock_app_config, mock_logger, "test_script", "0.1")
    mock_logger.error.assert_called_with(
        "CSV analysis failed. Cannot generate or send report."
    )


@patch("lib.maillogsentinel.report.smtplib.SMTP")
@patch("lib.maillogsentinel.report._analyze_csv_for_report")
@patch("lib.maillogsentinel.report.getpass.getuser", return_value="testuser")
@patch("lib.maillogsentinel.report.socket.getfqdn", return_value="my.server.com")
@patch("lib.maillogsentinel.report.socket.gethostname", return_value="my.server.com")
@patch("lib.maillogsentinel.report.socket.gethostbyname", return_value="192.168.1.100")
@patch("lib.maillogsentinel.report.get_extraction_frequency", return_value="daily")
def test_send_report_sender_override(
    mock_get_freq,
    mock_gethostbyname,
    mock_gethostname,
    mock_getfqdn,
    mock_getuser,
    mock_analyze_csv,
    mock_smtp_class,
    mock_app_config: AppConfig,
    sample_csv_path: Path,
    mock_logger,
):
    mock_app_config.report_sender_override = "override@sender.com"
    sample_csv_path.write_text("header\nval1")
    mock_analyze_csv.return_value = {
        "total_today": 1,
        "top10_today": [],
        "top10_usernames": [],
        "total_rev_dns_failures": 0,
        "rev_dns_error_counts": [],
        "top10_countries": [],
        "top10_aso": [],
        "top10_asn": [],
        "csv_size_k_str": "0K",
        "csv_lines_str": "1",
    }
    mock_smtp_instance = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance

    send_report(mock_app_config, mock_logger, "test_script", "0.1")

    sent_msg: EmailMessage = mock_smtp_instance.send_message.call_args[0][0]
    assert sent_msg["From"] == "override@sender.com"
    mock_logger.info.assert_any_call(
        f"Report sent from override@sender.com to recipient@example.com"
    )


@patch("lib.maillogsentinel.report.smtplib.SMTP")
@patch("lib.maillogsentinel.report._analyze_csv_for_report")
@patch(
    "lib.maillogsentinel.report.getpass.getuser", return_value="testuser"
)  # All other mocks needed for full run
@patch("lib.maillogsentinel.report.socket.getfqdn", return_value="my.server.com")
@patch("lib.maillogsentinel.report.socket.gethostname", return_value="my.server.com")
@patch("lib.maillogsentinel.report.socket.gethostbyname", return_value="192.168.1.100")
@patch("lib.maillogsentinel.report.get_extraction_frequency", return_value="daily")
def test_send_report_attachment_io_error(
    mock_get_freq,
    mock_gethostbyname,
    mock_gethostname,
    mock_getfqdn,
    mock_getuser,
    mock_analyze_csv,
    mock_smtp_class,
    mock_app_config: AppConfig,
    sample_csv_path: Path,
    mock_logger,
):
    sample_csv_path.write_text("header\nval1")  # File exists for analysis
    mock_analyze_csv.return_value = {
        "total_today": 1,
        "top10_today": [],
        "top10_usernames": [],
        "total_rev_dns_failures": 0,
        "rev_dns_error_counts": [],
        "top10_countries": [],
        "top10_aso": [],
        "top10_asn": [],
        "csv_size_k_str": "0K",
        "csv_lines_str": "1",
    }
    mock_smtp_instance = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance

    # Mock open for the attachment part to raise IOError
    # Need to be careful to only mock it for the 'rb' mode when attaching
    original_open = Path.open

    def faulty_open(self, mode="r", *args, **kwargs):
        if self == sample_csv_path and mode == "rb":
            raise IOError("Cannot attach file")
        return original_open(self, mode, *args, **kwargs)

    with patch.object(Path, "open", faulty_open):
        send_report(mock_app_config, mock_logger, "test_script", "0.1")

    mock_logger.error.assert_called_with(
        f"Could not attach CSV {mock_app_config.csv_filename} to report: Cannot attach file"
    )
    sent_msg: EmailMessage = mock_smtp_instance.send_message.call_args[0][0]
    assert "NOTE: Could not attach" in sent_msg.get_content()
    # Check email is still sent
    mock_smtp_instance.send_message.assert_called_once()


@patch("lib.maillogsentinel.report.smtplib.SMTP")
@patch("lib.maillogsentinel.report._analyze_csv_for_report")
@patch(
    "lib.maillogsentinel.report.getpass.getuser", return_value="testuser"
)  # All other mocks
@patch("lib.maillogsentinel.report.socket.getfqdn", return_value="my.server.com")
@patch("lib.maillogsentinel.report.socket.gethostname", return_value="my.server.com")
@patch("lib.maillogsentinel.report.socket.gethostbyname", return_value="192.168.1.100")
@patch("lib.maillogsentinel.report.get_extraction_frequency", return_value="daily")
def test_send_report_smtp_fails(
    mock_get_freq,
    mock_gethostbyname,
    mock_gethostname,
    mock_getfqdn,
    mock_getuser,
    mock_analyze_csv,
    mock_smtp_class,
    mock_app_config: AppConfig,
    sample_csv_path: Path,
    mock_logger,
):
    sample_csv_path.write_text("header\nval1")
    mock_analyze_csv.return_value = {
        "total_today": 1,
        "top10_today": [],
        "top10_usernames": [],
        "total_rev_dns_failures": 0,
        "rev_dns_error_counts": [],
        "top10_countries": [],
        "top10_aso": [],
        "top10_asn": [],
        "csv_size_k_str": "0K",
        "csv_lines_str": "1",
    }

    mock_smtp_instance = MagicMock()
    mock_smtp_instance.send_message.side_effect = smtplib.SMTPException(
        "Test SMTP error"
    )
    mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance

    send_report(mock_app_config, mock_logger, "test_script", "0.1")
    mock_logger.error.assert_called_with("Failed to send report: Test SMTP error")
