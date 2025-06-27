# Troubleshooting

This section provides guidance on common issues you might encounter with MailLogSentinel and tips for debugging them.

## Common Issues

1.  **Configuration File Not Found or Incorrect:**
    *   **Symptom:** MailLogSentinel uses default settings, or errors appear during startup related to missing configuration values. The script might log warnings like "Default configuration ... not found or failed to load. Using internal defaults."
    *   **Solution:**
        *   Ensure `maillogsentinel.conf` exists at the expected location (e.g., `/etc/maillogsentinel.conf` or the path specified with `--config`).
        *   Verify the file has correct read permissions for the user running MailLogSentinel.
        *   Check the syntax of the configuration file. INI format is sensitive to section headers (`[section]`) and key-value pairs (`key = value`).
        *   Run `sudo /usr/local/bin/maillogsentinel.py --setup --interactive` to regenerate or create a new configuration file if you suspect corruption.

2.  **Permission Denied Errors:**
    *   **Symptom:** Errors related to reading log files, writing to the working directory (CSV, operational logs, state file), or creating directories.
    *   **Solution:**
        *   **Postfix Logs:** The user running MailLogSentinel needs read access to Postfix log files (e.g., `/var/log/mail.log`) and their rotated versions. Often, this means running MailLogSentinel as a user who is part of a group like `adm` or `syslog`, or adjusting log file permissions (less recommended for system logs).
        *   **Working/State Directories:** The user needs read/write access to the `working_dir` and `state_dir` specified in `maillogsentinel.conf`. These are typically `/var/log/maillogsentinel/` and `/var/lib/maillogsentinel/`. The setup script usually attempts to set appropriate permissions.
        *   **Running as Root (Setup vs. Operation):**
            *   The `--setup` process often requires `sudo` to install system files (Systemd units, copy binaries).
            *   Normal operation (log parsing, reporting) should ideally **not** run as root for security reasons. If it's run as a dedicated user, that user needs the necessary permissions.

3.  **Email Reports Not Being Sent:**
    *   **Symptom:** No email summaries are received.
    *   **Solution:**
        *   **Configuration:**
            *   Verify `email` in the `[report]` section of `maillogsentinel.conf` is set to a valid recipient address.
            *   Check `report_sender_override` if you're using it.
        *   **Mail Server (MTA):** MailLogSentinel uses `smtplib` which typically relies on a local MTA (like Postfix itself, Sendmail, or msmtp) being configured correctly to relay mail to `localhost:25` or as specified. Ensure your server can send emails from the command line (e.g., using `mail` or `sendmail` commands).
        *   **Firewall:** Ensure no firewall rules are blocking outgoing connections on port 25 (or the relevant SMTP port if your MTA is configured differently).
        *   **Logs:** Check MailLogSentinel's operational logs (`maillogsentinel.log`) and the system mail logs (e.g., `/var/log/mail.log`) for errors related to email sending. Look for SMTP errors (authentication, relay denied, connection refused).
        *   **Spam Filters:** Check if the reports are being caught by spam filters on the recipient's end.

4.  **GeoIP/ASN Databases Not Downloading or Updating:**
    *   **Symptom:** `ipinfo.py --update` fails, or logs show errors related to database downloads. Geolocation data in reports might be missing or outdated.
    *   **Solution:**
        *   **Internet Connectivity:** Ensure the server has internet access to reach the database URLs (specified in `maillogsentinel.conf` or `ipinfo.py` defaults).
        *   **Firewall/Proxy:** Check for firewall rules or proxy settings that might be blocking outgoing HTTPS connections to GitHub (where default databases are hosted).
        *   **Permissions:** The directory where databases are stored (e.g., `/var/lib/maillogsentinel/` or `~/.ipinfo/`) must be writable by the user running the update.
        *   **URLs:** Verify the `country_db_url` and `asn_db_url` in `maillogsentinel.conf` are correct and accessible.
        *   **Disk Space:** Ensure there's enough disk space.

5.  **Incorrect Log Parsing or No Intrusions Detected:**
    *   **Symptom:** Known intrusion attempts are not appearing in reports, or the CSV file is empty despite suspicious activity.
    *   **Solution:**
        *   **Log Path:** Double-check the `mail_log` path in `maillogsentinel.conf` points to the correct Postfix log file.
        *   **Log Format:** MailLogSentinel expects a standard Postfix SASL failure log format. If your Postfix logging is heavily customized, the parsing regex might not match.
            *   Example expected line: `postfix/submission/smtpd[<pid>]: warning: unknown[1.2.3.4]: SASL LOGIN authentication failed: UGFzc3dvcmQ6`
        *   **Offset Issues:**
            *   If the state file (containing the log offset) is corrupted or incorrect, MailLogSentinel might be skipping new entries or trying to re-parse very old data.
            *   Try `--reset` to clear the offset and re-process logs (be aware this might re-report old events if the CSV is not also cleared/managed).
        *   **Log Level:** Set `log_level = DEBUG` in `maillogsentinel.conf` and check `maillogsentinel.log` for detailed parsing activity. It will show lines being read and why they might be skipped.

6.  **Systemd Service/Timer Issues:**
    *   **Symptom:** The script doesn't run automatically, or `systemctl status` shows errors.
    *   **Solution:**
        *   **Installation:** Ensure the `.service` and `.timer` files were correctly installed by the `--setup` script (usually in `/etc/systemd/system/`).
        *   **Enable/Start:** Verify the timers are enabled and started:
            ```bash
            sudo systemctl list-unit-files | grep maillogsentinel
            sudo systemctl status maillogsentinel.timer maillogsentinel-report.timer
            sudo systemctl start maillogsentinel.timer maillogsentinel-report.timer # If not active
            sudo systemctl enable maillogsentinel.timer maillogsentinel-report.timer # To start on boot
            ```
        *   **Journal Logs:** Check the Systemd journal for errors:
            ```bash
            sudo journalctl -u maillogsentinel.service
            sudo journalctl -u maillogsentinel-report.service
            # Use -f to follow logs: sudo journalctl -f -u maillogsentinel.service
            ```
        *   **Paths in Service Files:** Ensure paths used in the `ExecStart=` lines of the service files are correct.

## Debugging Tips

1.  **Check Operational Logs:**
    *   The first place to look for errors is MailLogSentinel's own log file (default: `/var/log/maillogsentinel/maillogsentinel.log`).
    *   Increase verbosity by setting `log_level = DEBUG` in `maillogsentinel.conf`. This will provide much more detailed information about what the script is doing.

2.  **Run Manually:**
    *   Execute `/usr/local/bin/maillogsentinel.py` (and `/usr/local/bin/maillogsentinel.py --report`) directly from the command line as the user it normally runs as (or with `sudo` if testing permission-related issues). This allows you to see console output directly.

3.  **Verify Paths and Permissions:**
    *   Use `ls -l` and `namei -l` to meticulously check ownership and permissions for:
        *   Postfix log files.
        *   MailLogSentinel's working directory, state directory, and CSV file.
        *   GeoIP/ASN database files.
        *   The `maillogsentinel.py` and `ipinfo.py` scripts themselves.

4.  **Test Components Individually:**
    *   **IPInfo:** Run `ipinfo.py --update` to test database downloads. Run `ipinfo.py <IP_ADDRESS>` to test lookups.
    *   **Email:** Try sending a test email from your server using command-line tools to ensure the underlying mail system is working.

5.  **Simplify Configuration:**
    *   If you suspect a configuration issue, temporarily comment out optional settings in `maillogsentinel.conf` to revert to defaults and see if the problem resolves.

6.  **Examine the State File:**
    *   The state file (e.g., `/var/lib/maillogsentinel/maillogsentinel.state`) contains the byte offset of the last processed log entry. If it seems incorrect, you can delete it (or use `--reset`) to force MailLogSentinel to re-evaluate from the beginning of the logs (or based on its logic for initial runs).

7.  **Use `--reset` or `--purge` Carefully:**
    *   `--reset`: Resets the log offset and archives existing data. Useful if the offset is problematic.
    *   `--purge`: A more drastic reset, archiving all data and logs.
    *   **Backup first if you have important data in the CSV or logs that you haven't backed up elsewhere.** These commands move data to a backup directory in the user's home directory.

By systematically checking these areas, you can usually pinpoint the source of most problems with MailLogSentinel. When reporting issues, providing relevant log excerpts (especially DEBUG level) and your `maillogsentinel.conf` (with sensitive data redacted) is very helpful.
