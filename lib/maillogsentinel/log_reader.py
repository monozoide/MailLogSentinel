"""
Log reading abstraction for MailLogSentinel.

This module provides an abstraction layer for reading log entries from different sources,
including traditional syslog files and systemd journald. It includes autodetection logic
to choose the best available log source.
"""

import subprocess
import logging
import json
import gzip
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator, Optional, Dict, Any, List
from datetime import datetime


class LogReader(ABC):
    """Abstract base class for log readers."""
    
    @abstractmethod
    def read_entries(self, offset: int = 0) -> Iterator[str]:
        """
        Read log entries starting from the given offset.
        
        Args:
            offset: The offset to start reading from (interpretation depends on implementation)
            
        Yields:
            str: Individual log line entries
        """
        pass
    
    @abstractmethod
    def get_new_offset(self) -> int:
        """
        Get the new offset after reading entries.
        
        Returns:
            int: The new offset for the next read operation
        """
        pass


class SyslogReader(LogReader):
    """Log reader for traditional syslog files."""
    
    def __init__(self, filepaths: List[Path], maillog_path: Path, 
                 is_gzip_func, logger: logging.Logger):
        """
        Initialize the syslog reader.
        
        Args:
            filepaths: List of log file paths to read
            maillog_path: The main mail log file path
            is_gzip_func: Function to determine if a file is gzipped
            logger: Logger instance
        """
        self.filepaths = filepaths
        self.maillog_path = maillog_path
        self.is_gzip_func = is_gzip_func
        self.logger = logger
        self.new_offset = 0
    
    def read_entries(self, offset: int = 0) -> Iterator[str]:
        """
        Read entries from syslog files.
        
        Args:
            offset: File offset to start reading from (for main log file only)
            
        Yields:
            str: Individual log line entries
        """
        self.new_offset = offset
        
        for path_obj in self.filepaths:
            self.logger.info(f"Processing syslog file: {path_obj.name}")
            
            try:
                path_size = path_obj.stat().st_size
            except OSError as e:
                self.logger.error(f"Could not get size of {path_obj}: {e}")
                continue
            
            # Initialize current file offset
            current_file_offset = 0
            if path_obj == self.maillog_path:
                current_file_offset = offset
                if path_size < current_file_offset:
                    self.logger.info(
                        f"Rotation detected for {path_obj.name}, "
                        f"resetting offset {current_file_offset} -> 0"
                    )
                    current_file_offset = 0
            
            is_gzipped_file = self.is_gzip_func(path_obj)
            file_open_mode = "rt"
            
            try:
                if is_gzipped_file:
                    with gzip.open(
                        path_obj, mode=file_open_mode, encoding="utf-8", errors="ignore"
                    ) as fobj:
                        for line in fobj:
                            yield line.rstrip('\n\r')
                else:
                    with path_obj.open(
                        mode=file_open_mode, encoding="utf-8", errors="ignore"
                    ) as fobj:
                        # Only seek if it's the main log file and being read incrementally
                        if path_obj == self.maillog_path:
                            self.logger.debug(
                                f"Incremental read of {path_obj.name} from offset {current_file_offset}"
                            )
                            fobj.seek(current_file_offset)
                        else:
                            self.logger.debug(
                                f"Reading rotated file {path_obj.name} from beginning"
                            )
                        
                        for line in fobj:
                            yield line.rstrip('\n\r')
                        
                        # Update offset only for the main log file
                        if path_obj == self.maillog_path:
                            self.new_offset = fobj.tell()
                            self.logger.debug(
                                f"Offset for {path_obj.name} updated to {self.new_offset}"
                            )
            
            except (IOError, OSError) as e:
                self.logger.error(f"Error processing file {path_obj.name}: {e}")
            except Exception as e:
                self.logger.error(
                    f"Unexpected error processing {path_obj.name}: {e}",
                    exc_info=True
                )
    
    def get_new_offset(self) -> int:
        """Get the new offset after reading entries."""
        return self.new_offset


class JournaldReader(LogReader):
    """Log reader for systemd journald using journalctl."""
    
    def __init__(self, unit: str, logger: logging.Logger, since_timestamp: Optional[str] = None):
        """
        Initialize the journald reader.
        
        Args:
            unit: The systemd unit to read logs from (e.g., 'postfix.service')
            logger: Logger instance
            since_timestamp: Optional timestamp to start reading from (ISO format)
        """
        self.unit = unit
        self.logger = logger
        self.since_timestamp = since_timestamp
        self.last_timestamp = since_timestamp
    
    def read_entries(self, offset: int = 0) -> Iterator[str]:
        """
        Read entries from journald using journalctl.
        
        Args:
            offset: For journald, this represents a timestamp offset (Unix timestamp)
            
        Yields:
            str: Individual log line entries in syslog format
        """
        # Convert offset (Unix timestamp) to ISO format if provided
        since_param = None
        if offset > 0:
            since_param = datetime.fromtimestamp(offset).isoformat()
        elif self.since_timestamp:
            since_param = self.since_timestamp
        
        cmd = ["journalctl", "-u", self.unit, "--output=json", "--no-pager"]
        
        if since_param:
            cmd.extend(["--since", since_param])
        
        self.logger.info(f"Running journalctl command: {' '.join(cmd)}")
        
        try:
            # Use subprocess to get journalctl output
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8'
            )
            
            latest_timestamp = None
            
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    # Parse JSON entry from journalctl
                    entry = json.loads(line)
                    
                    # Convert journald entry to syslog format
                    syslog_line = self._convert_to_syslog_format(entry)
                    if syslog_line:
                        yield syslog_line
                        
                        # Track the latest timestamp for next offset
                        if '__REALTIME_TIMESTAMP' in entry:
                            timestamp_us = int(entry['__REALTIME_TIMESTAMP'])
                            timestamp_s = timestamp_us // 1000000
                            latest_timestamp = timestamp_s
                
                except json.JSONDecodeError as e:
                    self.logger.warning(f"Failed to parse journald JSON entry: {e}")
                    continue
                except Exception as e:
                    self.logger.error(f"Error processing journald entry: {e}")
                    continue
            
            # Wait for process to complete and check for errors
            stderr_output = process.stderr.read()
            return_code = process.wait()
            
            if return_code != 0:
                self.logger.error(f"journalctl command failed with exit code {return_code}: {stderr_output}")
            
            # Update the last timestamp for next read
            if latest_timestamp:
                self.last_timestamp = str(latest_timestamp)
        
        except FileNotFoundError:
            self.logger.error("journalctl command not found. systemd is not available.")
            raise
        except subprocess.SubprocessError as e:
            self.logger.error(f"Error running journalctl: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error reading from journald: {e}")
            raise
    
    def _convert_to_syslog_format(self, entry: Dict[str, Any]) -> Optional[str]:
        """
        Convert a journald entry to syslog format.
        
        Args:
            entry: The journald entry as a dictionary
            
        Returns:
            str: The entry in syslog format, or None if conversion fails
        """
        try:
            # Extract timestamp
            if '__REALTIME_TIMESTAMP' in entry:
                timestamp_us = int(entry['__REALTIME_TIMESTAMP'])
                timestamp = datetime.fromtimestamp(timestamp_us / 1000000)
                timestamp_str = timestamp.strftime('%b %d %H:%M:%S')
            else:
                # Fallback to current time if no timestamp
                timestamp_str = datetime.now().strftime('%b %d %H:%M:%S')
            
            # Extract hostname
            hostname = entry.get('_HOSTNAME', 'localhost')
            
            # Extract process/service name  
            process_name = entry.get('SYSLOG_IDENTIFIER', entry.get('_COMM', 'unknown'))
            
            # Extract message
            message = entry.get('MESSAGE', '')
            
            # Extract PID if available
            pid = entry.get('_PID', '')
            pid_str = f"[{pid}]" if pid else ""
            
            # Construct syslog-style line
            # Format: MMM DD HH:MM:SS hostname process[pid]: message
            syslog_line = f"{timestamp_str} {hostname} {process_name}{pid_str}: {message}"
            
            return syslog_line
            
        except (KeyError, ValueError, TypeError) as e:
            self.logger.warning(f"Failed to convert journald entry to syslog format: {e}")
            return None
    
    def get_new_offset(self) -> int:
        """Get the new offset after reading entries (Unix timestamp)."""
        if self.last_timestamp:
            try:
                return int(self.last_timestamp)
            except (ValueError, TypeError):
                pass
        
        # Return current timestamp if no entries were processed
        return int(datetime.now().timestamp())


def detect_log_source(logger: logging.Logger, 
                     mail_service_unit: str = "postfix.service") -> str:
    """
    Autodetect the available log source.
    
    This function checks if journalctl is available and if it has entries for
    the mail service. If so, it prefers journald; otherwise, it falls back to syslog.
    
    Args:
        logger: Logger instance for reporting detection results
        mail_service_unit: The systemd unit name for the mail service
        
    Returns:
        str: Either 'journald' or 'syslog'
    """
    logger.info("Detecting available log source...")
    
    try:
        # Check if journalctl is available
        result = subprocess.run(
            ["journalctl", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            logger.info("journalctl not available, using syslog")
            return "syslog"
        
        logger.debug(f"journalctl version: {result.stdout.strip()}")
        
        # Check if there are entries for the mail service
        check_cmd = [
            "journalctl", "-u", mail_service_unit, 
            "--lines=1", "--no-pager", "--quiet"
        ]
        
        result = subprocess.run(
            check_cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 and result.stdout.strip():
            logger.info(f"Found journald entries for {mail_service_unit}, using journald")
            return "journald"
        else:
            logger.info(f"No journald entries found for {mail_service_unit}, using syslog")
            return "syslog"
    
    except subprocess.TimeoutExpired:
        logger.warning("journalctl detection timed out, falling back to syslog")
        return "syslog"
    except FileNotFoundError:
        logger.info("journalctl not found, using syslog")
        return "syslog"
    except Exception as e:
        logger.warning(f"Error during log source detection: {e}, falling back to syslog")
        return "syslog"


def create_log_reader(source_type: str, 
                     filepaths: List[Path] = None,
                     maillog_path: Path = None,
                     is_gzip_func = None,
                     logger: logging.Logger = None,
                     unit: str = "postfix.service",
                     since_timestamp: Optional[str] = None) -> LogReader:
    """
    Factory function to create the appropriate log reader.
    
    Args:
        source_type: Either 'syslog' or 'journald'
        filepaths: List of log file paths (for syslog)
        maillog_path: Main mail log file path (for syslog)
        is_gzip_func: Function to check if file is gzipped (for syslog)
        logger: Logger instance
        unit: Systemd unit name (for journald)
        since_timestamp: Optional timestamp to start from (for journald)
        
    Returns:
        LogReader: The appropriate log reader instance
        
    Raises:
        ValueError: If source_type is not supported or required parameters are missing
    """
    if source_type == "syslog":
        if not all([filepaths, maillog_path, is_gzip_func, logger]):
            raise ValueError("SyslogReader requires filepaths, maillog_path, is_gzip_func, and logger")
        return SyslogReader(filepaths, maillog_path, is_gzip_func, logger)
    
    elif source_type == "journald":
        if not logger:
            raise ValueError("JournaldReader requires logger")
        return JournaldReader(unit, logger, since_timestamp)
    
    else:
        raise ValueError(f"Unsupported log source type: {source_type}")