import pytest
from unittest.mock import MagicMock
import logging
from datetime import datetime

# Import the function to be tested
from lib.maillogsentinel.log_utils import (
    _parse_log_line,
    MONTHS,
)  # MONTHS needed for test_parse_log_line_invalid_month by implication

# --- Mocks and Fixtures ---


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
    return MagicMock(return_value=(None, "Mocked DNS Error"))


@pytest.fixture
def current_year():
    return datetime.now().year


# --- Tests for _parse_log_line ---


def test_parse_log_line_valid(
    current_year, mock_logger, mock_ip_info_mgr, mock_reverse_lookup_func
):
    log_line = "Jan  1 12:00:00 server postfix/submission/smtpd[123]: client=unknown[1.2.3.4], sasl_method=PLAIN, sasl_username=test@example.com"
    mock_reverse_lookup_func.return_value = ("host.example.com", None)
    mock_ip_info_mgr.lookup_ip_info.return_value = {
        "country_code": "US",
        "asn": "AS123",
        "aso": "Test ISP",
    }

    expected = {
        "server": "server",
        "date_s": f"01/01/{current_year} 12:00",
        "ip": "1.2.3.4",
        "user": "test@example.com",
        "hostn": "host.example.com",
        "reverse_dns_status": "OK",
        "country_code": "US",
        "asn": "AS123",
        "aso": "Test ISP",
    }
    result = _parse_log_line(
        log_line, current_year, mock_logger, mock_ip_info_mgr, mock_reverse_lookup_func
    )
    assert result == expected
    mock_reverse_lookup_func.assert_called_once_with("1.2.3.4", mock_logger)
    mock_ip_info_mgr.lookup_ip_info.assert_called_once_with("1.2.3.4")


def test_parse_log_line_no_log_re_match(
    current_year, mock_logger, mock_ip_info_mgr, mock_reverse_lookup_func
):
    log_line = "This is not a valid log line"
    assert (
        _parse_log_line(
            log_line,
            current_year,
            mock_logger,
            mock_ip_info_mgr,
            mock_reverse_lookup_func,
        )
        is None
    )


def test_parse_log_line_no_pat_match(
    current_year, mock_logger, mock_ip_info_mgr, mock_reverse_lookup_func
):
    log_line = "Jan  1 12:00:00 server postfix/submission/smtpd[123]: client=unknown[1.2.3.4]"  # No SASL
    assert (
        _parse_log_line(
            log_line,
            current_year,
            mock_logger,
            mock_ip_info_mgr,
            mock_reverse_lookup_func,
        )
        is None
    )


def test_parse_log_line_dns_error(
    current_year, mock_logger, mock_ip_info_mgr, mock_reverse_lookup_func
):
    log_line = "Jan  1 12:00:00 server postfix/submission/smtpd[123]: client=unknown[1.2.3.4], sasl_method=PLAIN, sasl_username=user"
    mock_reverse_lookup_func.return_value = (None, "DNS Timeout")
    result = _parse_log_line(
        log_line, current_year, mock_logger, mock_ip_info_mgr, mock_reverse_lookup_func
    )
    assert result["hostn"] == "null"
    assert result["reverse_dns_status"] == "DNS Timeout"


def test_parse_log_line_ip_info_none(
    current_year, mock_logger, mock_ip_info_mgr, mock_reverse_lookup_func
):
    log_line = "Jan  1 12:00:00 server postfix/submission/smtpd[123]: client=unknown[1.2.3.4], sasl_method=PLAIN, sasl_username=user"
    mock_reverse_lookup_func.return_value = ("host.example.com", None)
    mock_ip_info_mgr.lookup_ip_info.return_value = None  # IPInfoManager returns None
    result = _parse_log_line(
        log_line, current_year, mock_logger, mock_ip_info_mgr, mock_reverse_lookup_func
    )
    assert result["country_code"] == "N/A"
    assert result["asn"] == "N/A"
    assert result["aso"] == "N/A"


def test_parse_log_line_ip_info_mgr_is_none(
    current_year, mock_logger, mock_reverse_lookup_func
):
    log_line = "Jan  1 12:00:00 server postfix/submission/smtpd[123]: client=unknown[1.2.3.4], sasl_method=PLAIN, sasl_username=user"
    mock_reverse_lookup_func.return_value = ("host.example.com", None)
    result = _parse_log_line(
        log_line, current_year, mock_logger, None, mock_reverse_lookup_func
    )  # Pass None for ip_info_mgr
    assert result["country_code"] == "N/A"
    assert result["asn"] == "N/A"
    assert result["aso"] == "N/A"


def test_parse_log_line_invalid_month(
    current_year, mock_logger, mock_ip_info_mgr, mock_reverse_lookup_func
):
    log_line = "Xxx  1 12:00:00 server postfix/submission/smtpd[123]: client=unknown[1.2.3.4], sasl_username=user"
    # This test implicitly relies on MONTHS from log_utils.py
    assert (
        _parse_log_line(
            log_line,
            current_year,
            mock_logger,
            mock_ip_info_mgr,
            mock_reverse_lookup_func,
        )
        is None
    )
    mock_logger.warning.assert_called_with(
        f"Invalid month abbreviation in log line: {log_line.strip()}"
    )


def test_parse_log_line_username_with_newline(
    current_year, mock_logger, mock_ip_info_mgr, mock_reverse_lookup_func
):
    log_line = "Jan  1 12:00:00 server postfix/submission/smtpd[123]: client=unknown[1.2.3.4], sasl_username=user\nname"
    mock_reverse_lookup_func.return_value = ("host.example.com", None)
    result = _parse_log_line(
        log_line, current_year, mock_logger, mock_ip_info_mgr, mock_reverse_lookup_func
    )
    assert result is not None
    assert result["user"] == "user name"  # Newline replaced with space
