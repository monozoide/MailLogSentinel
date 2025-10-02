import pytest
from lib.maillogsentinel import log_utils

class DummyLogger:
    def warning(self, msg):
        pass
    def error(self, msg, *args, **kwargs):
        pass
    def info(self, msg):
        pass
    def debug(self, msg):
        pass

def dummy_reverse_lookup(ip, logger):
    return ("dummyhost.example.com", None)

class DummyIPInfoMgr:
    def lookup_ip_info(self, ip):
        return {"country_code": "US", "asn": "AS12345", "aso": "ExampleOrg"}

def test_postfix_parser_happy_path():
    """Test parsing a valid Postfix log line with SASL authentication (happy path)"""
    log_line = "Oct  2 12:34:56 mail postfix/smtpd[12345]: 0123456789AB: client=example.com[192.0.2.1], sasl_method=PLAIN, sasl_username=user@example.com"
    result = log_utils._parse_log_line(
        log_line,
        2025,
        DummyLogger(),
        DummyIPInfoMgr(),
        dummy_reverse_lookup,
    )
    assert result is not None, "Parser should return a result for a valid log line"
    assert result.get('date_s').endswith('12:34'), f"Unexpected date_s: {result.get('date_s')}"
    assert result.get('ip') == '192.0.2.1'
    assert result.get('user') == 'user@example.com'
    assert result.get('server') == 'mail'
    assert result.get('hostn') == 'dummyhost.example.com'
    assert result.get('country_code') == 'US'
    assert result.get('asn') == 'AS12345'
    assert result.get('aso') == 'ExampleOrg'

def test_postfix_parser_sasl_auth_failure():
    """Test parsing a SASL authentication failure log line"""
    log_line = "Oct  2 12:35:00 mail postfix/smtpd[12345]: warning: unknown[203.0.113.5]: SASL PLAIN authentication failed: authentication failure, sasl_username=baduser@example.com"
    result = log_utils._parse_log_line(
        log_line,
        2025,
        DummyLogger(),
        DummyIPInfoMgr(),
        dummy_reverse_lookup,
    )
    assert result is not None, "Parser should return a result for SASL auth failure log line"
    assert result.get('ip') == '203.0.113.5'
    assert result.get('user') == 'baduser@example.com'
    assert result.get('server') == 'mail'

def test_postfix_parser_garbled_line():
    """Test parsing a garbled/unexpected log line that doesn't match expected format"""
    log_line = "GARBLED LOG DATA WITHOUT EXPECTED FORMAT"
    try:
        result = log_utils._parse_log_line(
            log_line,
            2025,
            DummyLogger(),
            DummyIPInfoMgr(),
            dummy_reverse_lookup,
        )
        # Should return None for unmatched lines, not raise exception
        assert result is None, f"Expected None for garbled input, got: {result}"
    except Exception as e:
        pytest.fail(f"Parser raised an exception on garbled input: {e}")

def test_postfix_parser_no_sasl_username():
    """Test parsing a log line that matches the log format but has no sasl_username"""
    log_line = "Oct  2 12:34:56 mail postfix/smtpd[12345]: 0123456789AB: client=example.com[192.0.2.1], sasl_method=PLAIN"
    result = log_utils._parse_log_line(
        log_line,
        2025,
        DummyLogger(),
        DummyIPInfoMgr(),
        dummy_reverse_lookup,
    )
    # Should return None because PAT regex won't match without sasl_username
    assert result is None, f"Expected None for log line without sasl_username, got: {result}"

def test_postfix_parser_invalid_date():
    """Test parsing a log line with invalid date format"""
    log_line = "XYZ 32 25:99:99 mail postfix/smtpd[12345]: client=example.com[192.0.2.1], sasl_username=user@example.com"
    result = log_utils._parse_log_line(
        log_line,
        2025,
        DummyLogger(),
        DummyIPInfoMgr(),
        dummy_reverse_lookup,
    )
    # Should return None due to invalid month or day
    assert result is None, f"Expected None for invalid date format, got: {result}"

def test_postfix_parser_reverse_dns_failure():
    """Test parsing when reverse DNS lookup fails"""
    def failing_reverse_lookup(ip, logger):
        return (None, "DNS lookup failed")
    
    log_line = "Oct  2 12:34:56 mail postfix/smtpd[12345]: client=example.com[192.0.2.1], sasl_username=user@example.com"
    result = log_utils._parse_log_line(
        log_line,
        2025,
        DummyLogger(),
        DummyIPInfoMgr(),
        failing_reverse_lookup,
    )
    assert result is not None
    assert result.get('hostn') == 'null'
    assert result.get('reverse_dns_status') == 'DNS lookup failed'
