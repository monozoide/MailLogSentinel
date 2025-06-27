# Getting Started

This section guides you through the initial steps to get MailLogSentinel up and running.

## Prerequisites

Before installing MailLogSentinel, ensure your system meets the following requirements:

*   **Python 3.x:** MailLogSentinel is written in Python 3. You can check your Python version by running `python3 --version`.
*   **Postfix Mail Server:** MailLogSentinel is designed to monitor Postfix logs. You need a functional Postfix installation.
*   **Standard Unix Utilities:** Basic command-line utilities like `chmod`, `cp`, `mkdir`, `sudo` are required for installation and setup.
*   **Systemd (Optional but Recommended):** For running MailLogSentinel as a service, Systemd is the preferred method. Most modern Linux distributions use Systemd.

## Installation

Follow these steps to install MailLogSentinel:

1.  **Clone the Repository:**
    Open your terminal and clone the MailLogSentinel GitHub repository:
    ```bash
    git clone https://github.com/monozoide/MailLogSentinel.git
    cd MailLogSentinel
    ```

2.  **Make Scripts Executable and Copy to System Path:**
    ```bash
    chmod +x bin/*.py
    sudo cp bin/maillogsentinel.py /usr/local/bin/
    sudo cp bin/ipinfo.py /usr/local/bin/
    ```

3.  **Install the Library:**
    To make the MailLogSentinel library accessible to the scripts, you can install it system-wide.
    ```bash
    # Create the directory if it doesn't exist
    sudo mkdir -p /usr/local/lib/maillogsentinel
    # Copy the library files
    sudo cp lib/maillogsentinel/*.py /usr/local/lib/maillogsentinel/
    # Copy the entire library directory (some configurations might rely on this structure)
    sudo cp -r lib/maillogsentinel /usr/local/lib/
    ```
    Alternatively, you can adjust your `PYTHONPATH` environment variable to include the `lib` directory within the cloned repository. However, the system-wide installation is generally more robust for services.

## Initial Setup

MailLogSentinel includes a setup routine within the main script (`maillogsentinel.py`). This routine helps configure essential parameters, set up directories, and install Systemd service files if desired.

There are two primary modes for the initial setup:

### Interactive Setup (Recommended for First-Time Users)

This mode guides you through the configuration process step-by-step, prompting you for necessary information.

*   **Command:**
    ```bash
    sudo /usr/local/bin/maillogsentinel.py --setup --interactive
    ```
*   **Process:**
    *   The script will ask for paths (e.g., Postfix log files, report storage), email addresses for notifications, and scheduling preferences for log scanning and reporting.
    *   Progress messages are displayed directly in the console for each major step (e.g., "Saving configuration file...", "Creating directories...", "Installing Systemd unit files...").
    *   A detailed log of the setup process is saved to `maillogsentinel_setup.log` in the directory where you run the command. This log can be helpful for troubleshooting if any issues arise.

### Automated/Silent Setup

This mode uses a pre-existing configuration file to set up MailLogSentinel. It's useful for deployments across multiple servers or when you have a standard configuration.

*   **Prerequisite:** You need a source configuration file.
    *   You can generate one by running the interactive setup on a reference machine.
    *   Alternatively, you can manually create it. The structure and required parameters can be found by examining the `bin/maillogsentinel_setup.py` script or referring to the [Configuration](Configuration) section of this wiki.
*   **Command:**
    ```bash
    sudo /usr/local/bin/maillogsentinel.py --setup --automated /path/to/your/source_maillogsentinel.conf
    ```
    Replace `/path/to/your/source_maillogsentinel.conf` with the actual path to your configuration file.
*   **Process:**
    *   The script will apply the settings from the specified configuration file.
    *   Console output is minimal, primarily showing critical errors if they occur.
    *   Detailed progress and any issues are logged to `maillogsentinel_setup.log` in the directory where the command is executed.

> [!WARNING]
> Before running the setup for the first time, it's highly recommended to review the [Configuration](Configuration) options and understand the prerequisites to ensure a smooth installation.

After completing these steps, MailLogSentinel should be installed and configured on your system. The next step is to understand its [Usage](Usage) and how to interpret its output.
