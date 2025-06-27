# -*- coding: utf-8 -*-
"""
Provides utility functions for displaying progress indicators in the terminal.

This module includes functions to:
- Start and complete steps with status icons (check mark, cross mark).
- Display determinate progress bars with percentage.
- Display indeterminate progress messages.
- Print general messages with different levels (info, warning, error).
- Finalize the overall process with a success or failure message.

It uses ANSI escape codes for colors and special characters for icons to enhance
the visual feedback of command-line tools. Terminal width is considered for
properly clearing lines.
"""
import sys
import shutil

# ANSI escape codes for colors
GREEN = "\033[92m"
RED = "\033[91m"
ORANGE = "\033[93m"
RESET = "\033[0m"

# Icons
CHECK_MARK = "✓"
CROSS_MARK = "✗"
TRIANGLE_MARK = "▲"

# Store the current step name to manage overwriting lines correctly
# _current_step_message = "" # Replaced by instance variable


def get_terminal_width():
    return shutil.get_terminal_size((80, 20)).columns


class ProgressTracker:
    def __init__(self):
        self.current_step_message = ""

    def start_step(self, step_name: str) -> None:
        """
        Prints the start message for a new step.

        This function clears any previous progress line and prints the name of the
        current step being executed, followed by "...". It stores the step message
        in an instance variable to allow `update_progress` to prepend it.

        Args:
            step_name: The name of the step to display.
        """
        # Clear any previous step's lingering progress bar line
        if self.current_step_message:
            sys.stdout.write("\r" + " " * len(self.current_step_message) + "\r")

        self.current_step_message = f"- {step_name}... "
        sys.stdout.write(self.current_step_message)
        sys.stdout.flush()

    def update_progress(
        self, current_value: int, total_value: int, length: int = 40
    ) -> None:
        """
        Updates and displays a determinate progress bar.

        Calculates the percentage of completion and draws a progress bar
        of the specified length. The progress bar is prefixed by the current
        step message. The line is overwritten on subsequent calls.

        Args:
            current_value: The current progress value.
            total_value: The total value representing 100% completion.
            length: The character length of the progress bar itself (excluding
                    percentage and step message). Defaults to 40.
        """
        if total_value == 0:  # Avoid division by zero for indeterminate progress
            progress_text = "In progress..."
        else:
            percentage = int((current_value / total_value) * 100)
            filled_length = int(length * current_value // total_value)
            bar = "█" * filled_length + "-" * (length - filled_length)
            progress_text = f"[{bar}] {percentage}%"

        # Ensure the full line is overwritten
        terminal_width = get_terminal_width()
        full_line = "\r" + self.current_step_message + progress_text
        # Pad with spaces to clear the rest of the line if the new message is shorter
        padding = (
            " " * (terminal_width - len(full_line) - 1)
            if terminal_width > len(full_line)
            else ""
        )
        sys.stdout.write(full_line + padding + "\r")
        sys.stdout.flush()

    def update_indeterminate_progress(self, message: str = "Processing...") -> None:
        """
        Updates and displays an indeterminate progress message.

        This is used when the total number of items is unknown. It displays
        the current step message followed by the provided message.
        The line is overwritten on subsequent calls.

        Args:
            message: The message to display for indeterminate progress.
                     Defaults to "Processing...".
        """
        # Ensure the full line is overwritten
        terminal_width = get_terminal_width()
        full_line = "\r" + self.current_step_message + message
        # Pad with spaces to clear the rest of the line
        padding = (
            " " * (terminal_width - len(full_line) - 1)
            if terminal_width > len(full_line)
            else ""
        )
        sys.stdout.write(full_line + padding + "\r")
        sys.stdout.flush()

    def complete_step(self, step_name: str, success: bool, details: str = "") -> None:
        """
        Marks a step as completed, displaying its status.

        Clears the current progress line and prints the step name followed by
        a success (✓) or failure (✗) icon and status text.
        Optional details can be appended.

        Args:
            step_name: The name of the step that was completed.
            success: Boolean indicating whether the step was successful.
            details: Optional string providing additional details about the
                     step's completion.
        """
        leader_message = f"- {step_name}: "

        status_icon = (
            f"{GREEN}{CHECK_MARK}{RESET}" if success else f"{RED}{CROSS_MARK}{RESET}"
        )
        status_text = "Completed" if success else "Failed"

        output_message = f"{leader_message}{status_icon} {status_text}"
        if details:
            output_message += f" ({details})"

        # Clear the current line
        terminal_width = get_terminal_width()
        sys.stdout.write("\r" + " " * terminal_width + "\r")  # Clear the line

        sys.stdout.write(output_message + "\n")
        sys.stdout.flush()
        self.current_step_message = ""  # Reset for the next step

    def print_message(self, message: str, level: str = "info") -> None:
        """
        Prints a message to the console with an optional level indicator.

        If a progress step is active, it clears that line before printing
        the message, then restores the progress step message.

        Args:
            message: The message string to print.
            level: The level of the message ('info', 'warning', 'error').
                   Defaults to 'info'.
        """
        if self.current_step_message:
            sys.stdout.write(
                "\r" + " " * (len(self.current_step_message) + 50) + "\r"
            )  # 50 for progress bar
            sys.stdout.flush()

        icon = ""
        color = RESET
        if level == "warning":
            icon = f"{ORANGE}{TRIANGLE_MARK}{RESET} "
            color = ORANGE
        elif level == "error":
            icon = f"{RED}{CROSS_MARK}{RESET} "
            color = RED
        elif level == "info":
            icon = f"{ORANGE}{TRIANGLE_MARK}{RESET} "

        sys.stdout.write(f"{icon}{color}{message}{RESET}\n")
        sys.stdout.flush()

        if self.current_step_message:
            sys.stdout.write(self.current_step_message)
            sys.stdout.flush()

    def finalize(self, success: bool, final_message: str) -> None:
        """
        Prints a final summary message for the overall process.

        Clears any ongoing progress line and prints a message indicating overall
        success or failure, followed by the `final_message`.

        Args:
            success: Boolean indicating the overall success of the process.
            final_message: The final message to display.
        """
        if self.current_step_message:  # Clear any ongoing step message
            sys.stdout.write("\r" + " " * (len(self.current_step_message) + 50) + "\r")
            sys.stdout.flush()
            self.current_step_message = ""

        if success:
            sys.stdout.write(
                f"\n{GREEN}{CHECK_MARK} All steps succeeded. {final_message}{RESET}\n"
            )
        else:
            sys.stdout.write(
                f"\n{RED}{CROSS_MARK} Some steps failed. {final_message}{RESET}\n"
            )
        sys.stdout.flush()
