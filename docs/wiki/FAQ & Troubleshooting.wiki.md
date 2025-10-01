# MailLogSentinel (MLS) FAQ & Troubleshooting

This page mirrors the [FAQ & Troubleshooting](./FAQ%20&%20Troubleshooting.md) from the codebase. For the latest version, always check the repository.

---

## Getting Started

### Supported Platforms
- **OS:** Debian 12/13 (Bookworm/Trixie)
- **Python:** 3.8+
- **Required Packages:**
  - `python3-pip`, `python3-systemd` (for journald), `sqlite3` (for SQL output), `mailutils` (for sending email reports)

### Postfix Log Sources
- **journald:** Modern Debian uses `systemd-journald` (logs in the journal, not files)
- **syslog:** Classic `/var/log/mail.log` (may require enabling in `/etc/rsyslog.d/`)

---

## Installation Paths

### Bare-metal (systemd) Quickstart
1. **Install dependencies:**
   ```sh
   sudo apt update
   sudo apt install python3-pip python3-systemd sqlite3 mailutils
   pip3 install -r requirements.txt
   ```
2. **Copy config:**
   ```sh
   cp config/maillogsentinel.conf /etc/maillogsentinel.conf
   ```
3. **Set up systemd service & timer:**
   See [Minimal systemd unit & timer](#minimal-systemd-unit--timer)
4. **Start MLS:**
   ```sh
   sudo systemctl start maillogsentinel.service
   sudo systemctl enable maillogsentinel.timer
   ```

### Verifying Ingestion
- **Tail logs:**
  ```sh
  sudo journalctl -u maillogsentinel.service -f
  ```
- **Check CSV growth:**
  ```sh
  watch wc -l /var/log/maillogsentinel/maillogsentinel.csv
  ```

---

## Configuration Essentials

- **Log path/journalctl selectors:**
  - Edit `/etc/maillogsentinel.conf`:
    - `log_source = journald` or `log_source = /var/log/mail.log`
    - For journald, set `journalctl_selector = _SYSTEMD_UNIT=postfix.service`
- **Output locations:**
  - Default CSV: `/var/log/maillogsentinel/maillogsentinel.csv`
  - SQL DB: `/var/log/maillogsentinel/maillogsentinel.db` (if enabled)
- **Email report:**
  - Configure SMTP in `maillogsentinel.conf` (`smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`)
  - Set `report_schedule = daily`
  - Sample email: see [Sample daily report](#sample-daily-report-redacted)

---

## Usage FAQ

### Where are CSV/SQL files stored?
- By default: `/var/log/maillogsentinel/`
- Change in config: `output_csv_path`, `output_sql_path`

### How to rotate logs and keep MLS in sync?
- Use `logrotate` for `/var/log/mail.log` and `/var/log/maillogsentinel/maillogsentinel.csv`
- MLS will pick up new logs on next run

### How to run multiple instances (multi-domain/host)?
- Copy config to `/etc/maillogsentinel_<instance>.conf`
- Duplicate systemd unit with different `--config` argument

### Performance tips for busy servers
- Increase systemd service `TimeoutSec`
- Use SQL output for large datasets
- Run MLS more frequently (adjust timer)

### Integrating with Metabase
- Point Metabase to the SQL DB or CSV file
- For CSV: use Metabase’s CSV upload or connect via a script
- For SQL: connect to SQLite DB directly
- [Metabase docs](https://www.metabase.com/docs/latest/)

---

## Troubleshooting

### Permission errors (journald access, file/dir perms)
- Ensure MLS runs as root or with `systemd-journal` group
- Check directory permissions: `/var/log/maillogsentinel/`

### Parser errors on unexpected log formats
- Check Postfix version and log format
- File an issue with sample log lines

### No email received (SMTP/auth/port, blocked by provider)
- Test SMTP settings with `mail` command
- Check spam/junk folder
- Use alternate SMTP provider if blocked

### Postfix log not found (distribution-specific paths)
- Confirm log path in config
- For journald: check `journalctl -u postfix`
- For syslog: check `/var/log/mail.log` exists

---

## Examples & Snippets

### Minimal systemd unit & timer
`/etc/systemd/system/maillogsentinel.service`:
```ini
[Unit]
Description=MailLogSentinel
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /path/to/maillogsentinel.py --config /etc/maillogsentinel.conf
User=root

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/maillogsentinel.timer`:
```ini
[Unit]
Description=Run MailLogSentinel daily

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

### Sample daily report (redacted)
```
Subject: [MLS] Daily Mail Report

Top senders:
user1@example.com: 120
user2@example.com: 98

Top recipients:
...
```

---

## References
- [README.md](../../README.md)
- [Wiki Home](./Home.md)
- [Configuration](./Configuration.md)
- [Contributing](./Contributing.md)
- [Troubleshooting](./Troubleshooting.md)
- [Related Issues](https://github.com/AnirudhPhophalia/MailLogSentinel/issues)

---

*For more, see the [full documentation](./Home.md) or open an issue if you’re stuck!*
