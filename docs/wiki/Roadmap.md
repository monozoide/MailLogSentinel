# Roadmap

This page outlines the development roadmap for MailLogSentinel, including planned features, ongoing work, and completed items. This is adapted from the `docs/Roadmap.md` file in the repository.

## 🚀 Upcoming Features & Enhancements

These are features and improvements planned for future releases:

*   **Implement an RDBMS (Relational Database Management System) for Data Storage:**
    *   **Goal:** Move away from CSV files for storing intrusion data to a more robust and scalable RDBMS (e.g., SQLite, PostgreSQL, or MySQL).
    *   **Benefits:** Improved data querying capabilities, better performance for large datasets, enhanced data integrity, and easier integration with other analysis tools or web interfaces.
*   **Secure the CSV File (or Database):**
    *   **Goal:** Implement measures to protect the collected intrusion data, whether it's in a CSV file or an RDBMS.
    *   **Considerations:** File permissions, encryption (at rest or for backups), access controls if moving to a database.
*   **Draft "Use Cases" Documentation:**
    *   **Goal:** Create a new section in the documentation (or Wiki) that details various practical use cases and scenarios where MailLogSentinel can be effectively utilized.
    *   **Examples:** Setting up alerts for specific IP ranges, integrating with firewall scripts, long-term trend analysis.

## 🔄 In Progress

Tasks currently being actively worked on:

*   **Performance Testing:**
    *   **Goal:** Conduct thorough performance testing, especially with large log files and high volumes of intrusion attempts.
    *   **Focus Areas:** Log parsing speed, memory usage, efficiency of IP lookups and DNS caching, report generation time.
    *   **Outcome:** Identify bottlenecks and optimize code for better performance and scalability.

## ✔️ Completed Milestones

Key features and tasks that have been completed in previous versions:

*   **Finalize v5.14.13** (Internal versioning/milestone)
*   **Set up Unit Tests:**
    *   Initial framework for unit testing key components of the application.
*   **Configure CI/CD (Continuous Integration/Continuous Deployment):**
    *   Automated build, test, and potentially deployment pipelines (e.g., using GitHub Actions as seen in `.github/workflows/python-app.yml`).
*   **Implement IP Geolocation:**
    *   Integrated `ipinfo.py` for looking up country, ASN, and ASO information for IP addresses.
    *   Mechanism for downloading and updating local GeoIP/ASN databases.
*   **Write the Documentation:**
    *   Creation of the initial `README.md` and other core documentation files.
*   **Write the Wiki:**
    *   Development of this comprehensive Wiki for user and administrator documentation. (This task!)
*   **Anonymize Postfix Logs:**
    *   Developed the `tools/log_anonymizer.py` script to help users share log data safely.

This roadmap is subject to change based on community feedback and project priorities. If you have suggestions for new features or would like to contribute to existing items, please see the [Contributing](Contributing) page.
