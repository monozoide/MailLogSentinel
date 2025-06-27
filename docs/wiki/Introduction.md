# Introduction

## What is MailLogSentinel?

MailLogSentinel is a simple yet powerful monitoring tool specifically designed for Postfix mail servers. If you're running your own mail server, you understand the challenges: from initial setup and security hardening to ongoing maintenance and the constant barrage of brute-force authentication attacks.

MailLogSentinel automates the analysis of your Postfix logs to detect these intrusion attempts in near real-time. It operates without relying on complex frameworks, using only Python 3 and standard libraries, alongside your existing Postfix setup.

## Key Features

MailLogSentinel offers a range of features to help you keep your mail server secure:

*   **Log Scanning:** It diligently scans your Postfix logs, including rotated archives, to ensure no suspicious activity is missed.
*   **Failed Authentication Detection:** The tool is adept at identifying failed SASL (Simple Authentication and Security Layer) authentications, which are common indicators of brute-force attacks.
*   **Detailed Information Extraction:** When an intrusion attempt is detected, MailLogSentinel extracts crucial details such as:
    *   Date and time of the attempt
    *   Server hostname or IP address
    *   Source IP address of the attacker
    *   Username targeted
    *   Hostname of the attacking machine (if available via reverse DNS)
*   **IP Geolocation:** It looks up IP address information, including:
    *   Country of origin
    *   ASN (Autonomous System Number)
    *   ASO (Autonomous System Organization)
*   **CSV Reporting:** Findings are appended to a structured CSV (Comma Separated Values) file (`reports/intrusions.csv` by default). This allows for easy storage, searching, and further analysis of intrusion data.
*   **Email Summaries:** MailLogSentinel can be configured to send concise email summaries of detected activities on a schedule you define. These reports provide a quick overview of the security status of your mail server.
*   **Lightweight and Efficient:** Built with Python 3 and standard libraries, it's designed to be resource-friendly and easy to integrate into existing systems.

By automating these critical monitoring tasks, MailLogSentinel helps you stay informed about potential threats and maintain a more secure mail server environment.
