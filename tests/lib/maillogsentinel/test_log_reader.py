"""
Unit tests for the log_reader module.

This module tests the LogReader abstraction, including autodetection logic,
SyslogReader, and JournaldReader implementations.
"""

import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
import pytest
import logging

from lib.maillogsentinel.log_reader import (
    SyslogReader,
    JournaldReader,
    detect_log_source,
    create_log_reader,
)


@pytest.fixture
def mock_logger():
    """Create a mock logger for testing."""
    return Mock(spec=logging.Logger)


@pytest.fixture
def sample_log_files(tmp_path):
    """Create sample log files for testing SyslogReader."""
    main_log = tmp_path / "mail.log"
    rotated_log = tmp_path / "mail.log.1"
    
    main_log.write_text(
        "Nov  1 10:00:01 server1 postfix/smtpd[1234]: connect from unknown[192.168.1.100]\n"
        "Nov  1 10:00:02 server1 postfix/smtpd[1234]: NOQUEUE: reject: RCPT from unknown[192.168.1.100]: "
        "554 5.7.1 Service unavailable; Client host [192.168.1.100] blocked using test; sasl_username=testuser\n"
    )
    
    rotated_log.write_text(
        "Oct 31 23:59:59 server1 postfix/smtpd[5678]: connect from attacker[10.0.0.1]\n"
        "Oct 31 23:59:59 server1 postfix/smtpd[5678]: NOQUEUE: reject: RCPT from attacker[10.0.0.1]: "
        "554 5.7.1 Service unavailable; Client host [10.0.0.1] blocked using test; sasl_username=baduser\n"
    )
    
    return [rotated_log, main_log], main_log


class TestSyslogReader:
    """Tests for SyslogReader class."""
    
    def test_init(self, sample_log_files, mock_logger):
        """Test SyslogReader initialization."""
        filepaths, maillog_path = sample_log_files
        
        def mock_is_gzip(path):
            return False
        
        reader = SyslogReader(filepaths, maillog_path, mock_is_gzip, mock_logger)
        
        assert reader.filepaths == filepaths
        assert reader.maillog_path == maillog_path
        assert reader.is_gzip_func == mock_is_gzip
        assert reader.logger == mock_logger
        assert reader.new_offset == 0
    
    def test_read_entries_basic(self, sample_log_files, mock_logger):
        """Test basic log entry reading."""
        filepaths, maillog_path = sample_log_files
        
        def mock_is_gzip(path):
            return False
        
        reader = SyslogReader(filepaths, maillog_path, mock_is_gzip, mock_logger)
        
        entries = list(reader.read_entries(offset=0))
        
        # Should read from both files
        assert len(entries) == 4  # 2 lines from each file
        
        # Check that entries contain expected content
        assert "192.168.1.100" in entries[2]  # From main log
        assert "sasl_username=testuser" in entries[3]  # From main log
        assert "10.0.0.1" in entries[0]  # From rotated log
        assert "sasl_username=baduser" in entries[1]  # From rotated log
    
    def test_read_entries_with_offset(self, sample_log_files, mock_logger):
        """Test reading entries with a file offset."""
        filepaths, maillog_path = sample_log_files
        
        def mock_is_gzip(path):
            return False
        
        reader = SyslogReader([maillog_path], maillog_path, mock_is_gzip, mock_logger)
        
        # First, read all entries to get the total content length
        all_entries = list(reader.read_entries(offset=0))
        first_offset = reader.get_new_offset()
        
        # Read only the first line by calculating its byte length properly
        file_content = maillog_path.read_text()
        lines = file_content.splitlines(keepends=True)
        first_line_byte_length = len(lines[0].encode('utf-8'))
        
        partial_entries = list(reader.read_entries(offset=first_line_byte_length))
        
        # Filter out empty entries
        non_empty_entries = [entry for entry in partial_entries if entry.strip()]
        
        # Should only get the second line
        assert len(non_empty_entries) == 1
        assert "sasl_username=testuser" in non_empty_entries[0]
    
    def test_get_new_offset(self, sample_log_files, mock_logger):
        """Test that get_new_offset returns the correct offset."""
        filepaths, maillog_path = sample_log_files
        
        def mock_is_gzip(path):
            return False
        
        reader = SyslogReader([maillog_path], maillog_path, mock_is_gzip, mock_logger)
        
        # Read all entries
        list(reader.read_entries(offset=0))
        
        # New offset should be the file size
        expected_offset = maillog_path.stat().st_size
        assert reader.get_new_offset() == expected_offset


class TestJournaldReader:
    """Tests for JournaldReader class."""
    
    def test_init(self, mock_logger):
        """Test JournaldReader initialization."""
        reader = JournaldReader("postfix.service", mock_logger)
        
        assert reader.unit == "postfix.service"
        assert reader.logger == mock_logger
        assert reader.since_timestamp is None
        assert reader.last_timestamp is None
    
    def test_init_with_timestamp(self, mock_logger):
        """Test JournaldReader initialization with timestamp."""
        timestamp = "2023-11-01T10:00:00"
        reader = JournaldReader("postfix.service", mock_logger, timestamp)
        
        assert reader.since_timestamp == timestamp
        assert reader.last_timestamp == timestamp
    
    @patch('subprocess.Popen')
    def test_read_entries_basic(self, mock_popen, mock_logger):
        """Test basic journalctl reading."""
        # Mock journalctl output
        mock_process = MagicMock()
        mock_process.stdout = [
            json.dumps({
                "__REALTIME_TIMESTAMP": "1698840000000000",
                "_HOSTNAME": "server1",
                "SYSLOG_IDENTIFIER": "postfix/smtpd",
                "_PID": "1234",
                "MESSAGE": "connect from unknown[192.168.1.100]"
            }),
            json.dumps({
                "__REALTIME_TIMESTAMP": "1698840001000000",
                "_HOSTNAME": "server1", 
                "SYSLOG_IDENTIFIER": "postfix/smtpd",
                "_PID": "1234",
                "MESSAGE": "NOQUEUE: reject: RCPT from unknown[192.168.1.100]: sasl_username=testuser"
            })
        ]
        mock_process.stderr.read.return_value = ""
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process
        
        reader = JournaldReader("postfix.service", mock_logger)
        entries = list(reader.read_entries(offset=0))
        
        assert len(entries) == 2
        assert "server1" in entries[0]
        assert "postfix/smtpd[1234]" in entries[0]
        assert "connect from unknown[192.168.1.100]" in entries[0]
        assert "sasl_username=testuser" in entries[1]
        
        # Check that journalctl was called with correct arguments
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args[0][0]
        assert "journalctl" in call_args
        assert "-u" in call_args
        assert "postfix.service" in call_args
        assert "--output=json" in call_args
        assert "--no-pager" in call_args
    
    @patch('subprocess.Popen')
    def test_read_entries_with_since(self, mock_popen, mock_logger):
        """Test reading entries with since timestamp."""
        mock_process = MagicMock()
        mock_process.stdout = []
        mock_process.stderr.read.return_value = ""
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process
        
        # Test with Unix timestamp offset
        reader = JournaldReader("postfix.service", mock_logger)
        timestamp = 1698840000  # Unix timestamp
        list(reader.read_entries(offset=timestamp))
        
        # Check that --since was included in the command
        call_args = mock_popen.call_args[0][0]
        assert "--since" in call_args
        # The timestamp should be converted to ISO format
        since_index = call_args.index("--since") + 1
        assert "2023-11-01" in call_args[since_index]  # Should contain the date
    
    def test_convert_to_syslog_format(self, mock_logger):
        """Test conversion of journald entries to syslog format."""
        reader = JournaldReader("postfix.service", mock_logger)
        
        entry = {
            "__REALTIME_TIMESTAMP": "1698840000000000",
            "_HOSTNAME": "server1",
            "SYSLOG_IDENTIFIER": "postfix/smtpd",
            "_PID": "1234",
            "MESSAGE": "connect from unknown[192.168.1.100]"
        }
        
        result = reader._convert_to_syslog_format(entry)
        
        assert result is not None
        assert "server1" in result
        assert "postfix/smtpd[1234]" in result
        assert "connect from unknown[192.168.1.100]" in result
        # Should contain a timestamp in syslog format (e.g., "Nov 01 09:00:00")
        assert len(result.split()) >= 5  # timestamp + hostname + process + message
    
    def test_convert_to_syslog_format_minimal(self, mock_logger):
        """Test conversion with minimal journald entry."""
        reader = JournaldReader("postfix.service", mock_logger)
        
        entry = {
            "MESSAGE": "test message"
        }
        
        result = reader._convert_to_syslog_format(entry)
        
        assert result is not None
        assert "test message" in result
        assert "localhost" in result  # Default hostname
        assert "unknown" in result  # Default process name
    
    def test_get_new_offset(self, mock_logger):
        """Test getting new offset after reading."""
        reader = JournaldReader("postfix.service", mock_logger)
        
        # Initially should return current timestamp
        offset1 = reader.get_new_offset()
        assert isinstance(offset1, int)
        assert offset1 > 0
        
        # After setting last_timestamp
        reader.last_timestamp = "1698840000"
        offset2 = reader.get_new_offset()
        assert offset2 == 1698840000


class TestDetectLogSource:
    """Tests for log source detection functionality."""
    
    @patch('subprocess.run')
    def test_detect_journald_available_with_entries(self, mock_run, mock_logger):
        """Test detection when journald is available and has entries."""
        # Mock successful journalctl --version
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="systemd 249 (249.11)"),
            MagicMock(returncode=0, stdout="Nov 01 10:00:00 server1 postfix/smtpd[1234]: test")
        ]
        
        result = detect_log_source(mock_logger)
        
        assert result == "journald"
        assert mock_run.call_count == 2
        
        # Check first call was for version check
        first_call_args = mock_run.call_args_list[0][0][0]
        assert "journalctl" in first_call_args
        assert "--version" in first_call_args
        
        # Check second call was for entries check
        second_call_args = mock_run.call_args_list[1][0][0]
        assert "journalctl" in second_call_args
        assert "-u" in second_call_args
        assert "postfix.service" in second_call_args
    
    @patch('subprocess.run')
    def test_detect_journald_available_no_entries(self, mock_run, mock_logger):
        """Test detection when journald is available but has no entries."""
        # Mock successful version check but no entries
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="systemd 249 (249.11)"),
            MagicMock(returncode=0, stdout="")  # No entries
        ]
        
        result = detect_log_source(mock_logger)
        
        assert result == "syslog"
    
    @patch('subprocess.run')
    def test_detect_journald_not_available(self, mock_run, mock_logger):
        """Test detection when journalctl is not available."""
        mock_run.side_effect = FileNotFoundError()
        
        result = detect_log_source(mock_logger)
        
        assert result == "syslog"
    
    @patch('subprocess.run')
    def test_detect_journald_version_fails(self, mock_run, mock_logger):
        """Test detection when journalctl version check fails."""
        mock_run.return_value = MagicMock(returncode=1)
        
        result = detect_log_source(mock_logger)
        
        assert result == "syslog"
    
    @patch('subprocess.run')
    def test_detect_with_custom_unit(self, mock_run, mock_logger):
        """Test detection with custom mail service unit."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="systemd 249 (249.11)"),
            MagicMock(returncode=0, stdout="test entry")
        ]
        
        result = detect_log_source(mock_logger, "mail.service")
        
        assert result == "journald"
        
        # Check that custom unit was used
        second_call_args = mock_run.call_args_list[1][0][0]
        assert "mail.service" in second_call_args


class TestCreateLogReader:
    """Tests for the log reader factory function."""
    
    def test_create_syslog_reader(self, sample_log_files, mock_logger):
        """Test creating a SyslogReader."""
        filepaths, maillog_path = sample_log_files
        
        def mock_is_gzip(path):
            return False
        
        reader = create_log_reader(
            "syslog",
            filepaths=filepaths,
            maillog_path=maillog_path,
            is_gzip_func=mock_is_gzip,
            logger=mock_logger
        )
        
        assert isinstance(reader, SyslogReader)
        assert reader.filepaths == filepaths
        assert reader.maillog_path == maillog_path
    
    def test_create_journald_reader(self, mock_logger):
        """Test creating a JournaldReader."""
        reader = create_log_reader(
            "journald",
            logger=mock_logger,
            unit="postfix.service"
        )
        
        assert isinstance(reader, JournaldReader)
        assert reader.unit == "postfix.service"
        assert reader.logger == mock_logger
    
    def test_create_reader_invalid_type(self, mock_logger):
        """Test creating reader with invalid type."""
        with pytest.raises(ValueError, match="Unsupported log source type"):
            create_log_reader("invalid", logger=mock_logger)
    
    def test_create_syslog_reader_missing_params(self, mock_logger):
        """Test creating SyslogReader with missing parameters."""
        with pytest.raises(ValueError, match="SyslogReader requires"):
            create_log_reader("syslog", logger=mock_logger)
    
    def test_create_journald_reader_missing_logger(self):
        """Test creating JournaldReader without logger."""
        with pytest.raises(ValueError, match="JournaldReader requires logger"):
            create_log_reader("journald")