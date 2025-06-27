from pathlib import Path
import logging  # Required for logger mocking or type hinting
from unittest.mock import MagicMock

# Adjust the import path based on how pytest will discover your modules.
# If 'tests' is at the same level as 'lib', and pytest runs from the root,
# you might need to ensure 'lib' is in sys.path or use relative imports if
# structured as a package.
# For now, assuming direct import works or will be adjusted by pytest's path handling.
from lib.maillogsentinel.utils import is_gzip, read_state, write_state, STATE_FILENAME


def test_is_gzip():
    """Test the is_gzip function."""
    assert is_gzip(Path("file.txt.gz"))
    assert not is_gzip(Path("file.txt"))
    assert is_gzip(Path("archive.tar.gz"))
    assert not is_gzip(Path("directory.gz/file"))  # Checks filename, not part of path
    assert not is_gzip(Path("gz.file"))
    assert is_gzip(Path(".gz"))  # A file named just .gz


def test_read_state_file_not_exists(tmp_path: Path):
    """Test read_state when the state file does not exist."""
    # tmp_path is a pytest fixture providing a temporary directory unique to the test invocation
    statedir = tmp_path
    assert read_state(statedir) == 0


def test_read_state_file_exists(tmp_path: Path):
    """Test read_state when the state file exists with a valid offset."""
    statedir = tmp_path
    state_file = statedir / STATE_FILENAME
    state_file.write_text("12345")
    assert read_state(statedir) == 12345


def test_read_state_invalid_content(tmp_path: Path):
    """Test read_state when the state file contains invalid content."""
    statedir = tmp_path
    state_file = statedir / STATE_FILENAME
    state_file.write_text("not_an_integer")
    # Mock logger to check warning, or ensure it handles gracefully
    mock_logger = MagicMock(spec=logging.Logger)
    assert read_state(statedir, logger=mock_logger) == 0
    mock_logger.warning.assert_called_once()  # Check that a warning was logged


def test_read_state_empty_file(tmp_path: Path):
    """Test read_state when the state file is empty."""
    statedir = tmp_path
    state_file = statedir / STATE_FILENAME
    state_file.write_text("")
    mock_logger = MagicMock(spec=logging.Logger)
    assert read_state(statedir, logger=mock_logger) == 0
    mock_logger.warning.assert_called_once()


def test_write_state(tmp_path: Path):
    """Test write_state correctly writes the offset to the state file."""
    statedir = tmp_path
    offset = 98765
    mock_logger = MagicMock(spec=logging.Logger)

    write_state(statedir, offset, logger=mock_logger)

    state_file = statedir / STATE_FILENAME
    assert state_file.is_file()
    assert state_file.read_text().strip() == "98765"
    mock_logger.error.assert_not_called()  # Ensure no error was logged


def test_write_state_overwrite(tmp_path: Path):
    """Test write_state correctly overwrites an existing state file."""
    statedir = tmp_path
    state_file = statedir / STATE_FILENAME
    state_file.write_text("11111")  # Pre-existing content

    offset = 22222
    mock_logger = MagicMock(spec=logging.Logger)

    write_state(statedir, offset, logger=mock_logger)

    assert state_file.read_text().strip() == "22222"
    mock_logger.error.assert_not_called()


# Placeholder for test_placeholder, or remove if all other tests cover discovery
# def test_placeholder():
#    assert True
