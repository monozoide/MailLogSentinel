# tests/lib/maillogsentinel/test_progress.py
import unittest
from unittest.mock import patch
import io
import sys
from lib.maillogsentinel.progress import (
    ProgressTracker,  # Import the class
    GREEN,
    RED,
    ORANGE,
    RESET,
    CHECK_MARK,
    CROSS_MARK,
    TRIANGLE_MARK,
)


class TestProgressModule(unittest.TestCase):

    def setUp(self):
        # Redirect stdout to capture print statements
        self.held_stdout = sys.stdout
        sys.stdout = io.StringIO()
        # Instantiate ProgressTracker for each test
        self.tracker = ProgressTracker()

    def tearDown(self):
        # Restore stdout
        sys.stdout = self.held_stdout

    @patch("lib.maillogsentinel.progress.get_terminal_width", return_value=80)
    def test_start_step(self, mock_width):
        self.tracker.start_step("Test Step")
        output = sys.stdout.getvalue()
        self.assertIn("- Test Step... ", output)

    @patch("lib.maillogsentinel.progress.get_terminal_width", return_value=80)
    def test_complete_step_success(self, mock_width):
        self.tracker.start_step("Test Step For Success")  # Need a current step
        sys.stdout.truncate(0)  # Clear previous output from start_step
        sys.stdout.seek(0)
        self.tracker.complete_step("Test Step For Success", True, details="Done well")
        output = sys.stdout.getvalue()
        self.assertIn("- Test Step For Success:", output)
        self.assertIn(f"{GREEN}{CHECK_MARK}{RESET} Completed", output)
        self.assertIn("(Done well)\n", output)

    @patch("lib.maillogsentinel.progress.get_terminal_width", return_value=80)
    def test_complete_step_failure(self, mock_width):
        self.tracker.start_step("Test Step For Failure")  # Need a current step
        sys.stdout.truncate(0)
        sys.stdout.seek(0)
        self.tracker.complete_step("Test Step For Failure", False, details="Oh no")
        output = sys.stdout.getvalue()
        self.assertIn("- Test Step For Failure:", output)
        self.assertIn(f"{RED}{CROSS_MARK}{RESET} Failed", output)
        self.assertIn("(Oh no)\n", output)

    @patch("lib.maillogsentinel.progress.get_terminal_width", return_value=80)
    def test_update_progress_determinate(self, mock_width):
        self.tracker.start_step("Progressing")
        sys.stdout.truncate(0)
        sys.stdout.seek(0)
        self.tracker.update_progress(1, 2, length=10)  # 50%
        output = sys.stdout.getvalue()
        self.assertTrue(output.startswith("\r- Progressing... "))
        self.assertIn("[█████-----] 50%", output)

    @patch("lib.maillogsentinel.progress.get_terminal_width", return_value=80)
    def test_update_indeterminate_progress(self, mock_width):
        self.tracker.start_step("Indeterminate Progress")
        sys.stdout.truncate(0)
        sys.stdout.seek(0)
        self.tracker.update_indeterminate_progress("Working...")
        output = sys.stdout.getvalue()
        self.assertIn("\r- Indeterminate Progress... Working...", output)

    @patch("lib.maillogsentinel.progress.get_terminal_width", return_value=80)
    def test_print_message_warning(self, mock_width):
        self.tracker.print_message("A warning message", level="warning")
        output_no_step = sys.stdout.getvalue()
        self.assertIn(
            f"{ORANGE}{TRIANGLE_MARK}{RESET} {ORANGE}A warning message{RESET}\n",
            output_no_step,
        )

        sys.stdout.truncate(0)
        sys.stdout.seek(0)
        self.tracker.start_step("Ongoing Task")
        current_output_before_print = (
            sys.stdout.getvalue()
        )  # Capture output of start_step
        self.tracker.print_message("Another warning", level="warning")
        output_with_step = sys.stdout.getvalue()

        self.assertIn(
            f"{ORANGE}{TRIANGLE_MARK}{RESET} {ORANGE}Another warning{RESET}\n",
            output_with_step,
        )
        cleaned_prompt = current_output_before_print.strip().replace("\r", "")
        lines = output_with_step.strip().split("\n")
        last_line_content = ""
        if lines:
            last_line_content = lines[-1].strip()
        self.assertEqual(last_line_content, cleaned_prompt)

    @patch("lib.maillogsentinel.progress.get_terminal_width", return_value=80)
    def test_finalize_success(self, mock_width):
        self.tracker.finalize(True, "All good.")
        output = sys.stdout.getvalue()
        self.assertIn(
            f"\n{GREEN}{CHECK_MARK} All steps succeeded. All good.{RESET}\n",
            output,
        )

    @patch("lib.maillogsentinel.progress.get_terminal_width", return_value=80)
    def test_finalize_failure(self, mock_width):
        self.tracker.finalize(False, "Not good.")
        output = sys.stdout.getvalue()
        self.assertIn(
            f"\n{RED}{CROSS_MARK} Some steps failed. Not good.{RESET}\n",  # Adjusted expectation
            output,
        )


if __name__ == "__main__":
    unittest.main()
