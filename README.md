# MailLogSentinel

<p align="center">
  <img src="img/banner-logo.png" alt="MailLogSentinel Banner" height="90">
</p>

MailLogSentinel watches Postfix authentication activity, enriches IPs with geo/ASN data, stores events in CSV, and prepares daily email digests. This README gives a concise but complete walkthrough for first-time users, sysadmins, and testers (≈260 lines).

---

## 1. Quick Install (90 seconds)

```bash
git clone https://github.com/monozoide/MailLogSentinel.git && \
cd MailLogSentinel && \
sudo PYTHONPATH="$(pwd):$(pwd)/bin" bin/maillogsentinel.py --setup --interactive && \
sudo PYTHONPATH="$(pwd):$(pwd)/bin" bin/ipinfo.py --update --config /etc/maillogsentinel.conf && \
sudo PYTHONPATH="$(pwd):$(pwd)/bin" bin/maillogsentinel.py --config /etc/maillogsentinel.conf --report
```

Expected results
- Interactive setup completes and writes `/etc/maillogsentinel.conf`
- IP country/ASN databases download
- CSV appears at `/var/log/maillogsentinel/maillogsentinel.csv`
- Daily email sample is delivered to the configured inbox

If something fails
- Check `/var/log/maillogsentinel/maillogsentinel.log`
- Ensure the Postfix log (default `/var/log/mail.log`) is readable by the configured user
- Retry the IP database update (network hiccups are common)
- Consult docs/wiki/Troubleshooting.md for targeted fixes

---

## 2. Requirements & Defaults

| Component | Default / Expectation |
| --- | --- |
| OS | Linux with Postfix logs available (systemd recommended but optional) |
| Python | 3.10 or newer (uses only stdlib + bundled modules) |
| Privileges | `sudo` for setup, file installation, timers |
| Config file | `/etc/maillogsentinel.conf` (created during setup) |
| CSV output | `/var/log/maillogsentinel/maillogsentinel.csv` |
| App log | `/var/log/maillogsentinel/maillogsentinel.log` |
| State | `/var/lib/maillogsentinel/state.offset` |
| Timers/Services | `maillogsentinel.service`, `maillogsentinel-extract.timer`, `maillogsentinel-report.timer`, `ipinfo-update.timer` |

Need to customise? Run the interactive setup again, or edit the config file and restart timers.

---

## 3. Choose Your Flow

### A. Manual / on-demand processing
- Run the Quick Install command set whenever you need a report
- Works well for lab environments or when systemd is unavailable
- Reuse the repo “as-is” by keeping the `PYTHONPATH="$(pwd):$(pwd)/bin"` prefix

### B. Systemd automation (safe defaults)

```bash
sudo PYTHONPATH="$(pwd):$(pwd)/bin" bin/maillogsentinel.py --setup --interactive  # answer “yes” to systemd
sudo systemctl daemon-reload
sudo systemctl enable --now maillogsentinel-extract.timer maillogsentinel-report.timer ipinfo-update.timer
systemctl list-timers | grep maillogsentinel
```

Services installed by setup
- `maillogsentinel.service`: one-shot log extraction
- `maillogsentinel-extract.timer`: periodic extraction (default hourly)
- `maillogsentinel-report.service/.timer`: daily summary email (default 23:59)
- `ipinfo-update.service/.timer`: refresh IP databases (default weekly)

To customise schedules, edit the timer files in `/etc/systemd/system/` and run `sudo systemctl daemon-reload` followed by `sudo systemctl restart <timer>`.

---

## 4. What Happens Under the Hood

```
Postfix log → Parser extracts SASL failures → Geo/ASN enrichment → CSV append
                                                      ↘ optional SQL export
CSV + templates → Mail composer → Daily email report
```

- **Extraction**: incremental read with offset tracking to avoid reprocessing rotated logs
- **Enrichment**: reverse DNS plus local ASN/Country lookups via `ipinfo.py`
- **Storage**: CSV for quick inspection, optional SQL export for long-term archiving
- **Reporting**: plaintext email summarising top IPs, usernames, countries, ASNs, reverse lookup failures

---

## 5. Configuration Cheat Sheet (`/etc/maillogsentinel.conf`)

| Section | Key options (defaults in parentheses) |
| --- | --- |
| `[paths]` | `working_dir` (`/var/log/maillogsentinel`), `state_dir` (`/var/lib/maillogsentinel`), `mail_log` (`/var/log/mail.log`), `csv_filename` (`maillogsentinel.csv`) |
| `[report]` | `email`, `subject_prefix` (`[MailLogSentinel]`), `sender_override` (empty → auto) |
| `[geolocation]` | `country_db_path`, `country_db_url` (sapics CC0 data) |
| `[ASN_ASO]` | `asn_db_path`, `asn_db_url` |
| `[general]` | `log_level` (`INFO`), `log_file`, `log_file_max_bytes`, `log_file_backup_count` |
| `[dns_cache]` | `enabled` (`True`), `size` (`128`), `ttl_seconds` (`3600`) |
| `[database]` | Optional SQL export/import settings (`db_type`, `sql_export_dir`, credentials) |
| `[systemd]` | `extraction_schedule`, `report_schedule`, `ip_update_schedule` (populated by setup) |

Edit the file with sudo, then rerun `sudo systemctl restart maillogsentinel-extract.timer` (or the relevant timer) to apply changes.

---

## 6. File & Directory Layout

| Path | Purpose |
| --- | --- |
| `/etc/maillogsentinel.conf` | Main configuration |
| `/var/log/maillogsentinel/maillogsentinel.csv` | Incremental CSV store |
| `/var/log/maillogsentinel/maillogsentinel.log` | Application log (rotated) |
| `/var/lib/maillogsentinel/state.offset` | Last processed byte offset |
| `/var/lib/maillogsentinel/country_aside.csv` | Country DB (downloaded) |
| `/var/lib/maillogsentinel/asn.csv` | ASN/ASO DB (downloaded) |
| `/usr/local/bin/maillogsentinel.py` | Optional installed entry point |
| `/usr/local/lib/maillogsentinel/` | Optional library copy when installing system-wide |

Keep backups of CSV and configuration as part of your normal server backup policy.

---

## 7. Command Reference (extended)

| Task | Command | Notes |
| --- | --- | --- |
| Interactive setup | `sudo PYTHONPATH="$(pwd):$(pwd)/bin" bin/maillogsentinel.py --setup --interactive` | Creates config, optional systemd units |
| Automated/setup replay | `sudo bin/maillogsentinel.py --setup --automated /path/to/conf` | Use previously saved config for scripted installs |
| Single extraction | `sudo PYTHONPATH="$(pwd):$(pwd)/bin" bin/maillogsentinel.py --config /etc/maillogsentinel.conf` | Processes new log entries only |
| Send report | `sudo PYTHONPATH="$(pwd):$(pwd)/bin" bin/maillogsentinel.py --config /etc/maillogsentinel.conf --report` | Uses collected CSV data |
| Reset state | `sudo maillogsentinel.py --config /etc/maillogsentinel.conf --reset` | Archives CSV/log, resets offset |
| Purge | `sudo maillogsentinel.py --config /etc/maillogsentinel.conf --purge` | Full archive/reset (fresh start) |
| SQL export | `sudo maillogsentinel.py --config /etc/maillogsentinel.conf --sql-export` | Requires `[database]` section |
| SQL import | `sudo maillogsentinel.py --config /etc/maillogsentinel.conf --sql-import` | Replays `.sql` files into DB |
| Update IP DBs | `sudo PYTHONPATH="$(pwd):$(pwd)/bin" bin/ipinfo.py --update --config /etc/maillogsentinel.conf` | Run manually or via timer |
| IP lookup | `PYTHONPATH="$(pwd):$(pwd)/bin" bin/ipinfo.py 8.8.8.8` | Works without sudo |
| Log anonymizer | `python3 bin/log_anonymizer.py --input mail.log --output redacted.log` | CLI also accepts stdin/stdout |

For unattended operation, install binaries to `/usr/local/bin/` and omit the `PYTHONPATH` prefix.

---

## 8. Outputs & Examples

### CSV snapshot

```
server,date,ip,user,hostname,reverse_dns_status,country_code,asn,aso
srv01,"2025-05-17 12:05",81.30.107.24,contribute,mail.example.com,OK,US,9808,"China Mobile"
srv01,"2025-05-17 13:45",192.0.2.45,admin,host.example.org,OK,BR,18881,"Celcom Axiata Berhad"
srv01,"2025-05-17 14:10",205.177.40.1,user@example.com,null,Errno 1,US,5650,"Frontier Communications"
```

### Email summary (collapsed)

<details>
<summary>Sample daily email</summary>

```
##################################################
### MailLogSentinel v1.0.5-A                     ###
### Extraction interval : hourly                 ###
### Report at 2025-05-28 10:30                   ###
### Server: mail.example.com                     ###
##################################################

Total attempts today: 55

Top 10 failed authentications today:
 1. user@example.com   111.222.11.22  host.attacker.cn   CN  5
 2. admin@example.com  22.33.44.55    another.host.ru    RU  4
 ...

Top 10 countries today: CN, RU, MY, AU, AE, BR, US, MD
Top 10 ASNs today: 4837, 134810, 25513, ...

Reverse DNS failures: 26 (Errno 1: 24, Errno 2: 2)
Attached CSV: maillogsentinel.csv
```

</details>

---

## 9. Maintenance Tasks

- **Rotate or archive CSV**: use `--reset` (keeps backups in your home dir) or schedule your own archival job
- **Upgrade MailLogSentinel**: pull latest git tag, rerun setup to refresh timers if required, and review CHANGELOG on releases page
- **Refresh IP databases**: timers handle it weekly; manually run `ipinfo.py --update` after network outages
- **Verify timers**: `systemctl list-timers 'maillogsentinel*'`
- **Check disk usage**: CSV grows with activity; consider exporting to SQL and purging periodically for high-volume servers
- **Log anonymisation before sharing**: `bin/log_anonymizer.py` removes user/IP details per configurable patterns

---

## 10. Troubleshooting Playbook

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| No email received | Mail relay blocked or SMTP misconfigured | Check `/var/log/maillogsentinel/maillogsentinel.log`, verify `report.email`, ensure outbound mail works |
| CSV empty | No matching SASL failures or wrong log path | Confirm `mail_log` path, run `tail -n50 /var/log/mail.log`, rerun extraction |
| Permission denied reading logs | User not in `adm` (Debian/Ubuntu) or lacks access | `sudo usermod -aG adm <run_as_user>` then logout/login, rerun setup |
| Timers inactive | Systemd not enabled or `daemon-reload` missing | `sudo systemctl daemon-reload`, then enable timers as shown above |
| IP DB update fails | Network issue or GitHub rate limit | Retry later, or host DB files internally and update URLs in config |
| Reverse DNS slow | DNS cache disabled or TTL too short | Enable `[dns_cache]`, adjust `ttl_seconds` |

More detailed recipes live in docs/wiki/Troubleshooting.md.

---

## 11. Testing & Validation Guide

For two new testers verifying a fresh install:
1. Provision a clean VM (Debian/Ubuntu preferred) with Postfix logging enabled
2. Follow section **1. Quick Install (90 seconds)**
3. Confirm email delivery and CSV contents
4. Enable systemd timers (section 3B) and check `systemctl list-timers`
5. Run `sudo journalctl -u maillogsentinel.service --since=-1h` to ensure no errors
6. Document any unclear prompts or failures and feed back into README/docs

Optional checks: run `pytest` (unit tests use sample logs) and `flake8` to ensure environment meets dev requirements (`pip install -r requirements.txt`).

---

## 12. Documentation Map

- **Overview & walkthrough**: docs/wiki/Getting-Started.md
- **Configuration reference**: docs/wiki/Configuration.md
- **Usage scenarios & CLI appendix**: docs/wiki/Usage.md
- **Scripts & utilities**: docs/wiki/Scripts-and-Utilities.md
- **API docs (HTML)**: docs/api/index.html
- **Roadmap & project status**: docs/Roadmap.md

Bookmark these pages for deeper administration tasks.

---

## 13. Contributing & Community

We welcome bug reports, feature ideas, and pull requests.

1. Fork and clone the repository
2. Create a branch: `git checkout -b feature/your-feature`
3. Run tests: `pytest` (uses fixtures under `tests/`)
4. Format/lint (optional but encouraged): `flake8`
5. Commit with a descriptive message, push, and open a PR

Good-first issues are labelled in GitHub Issues. Please read docs/CONTRIBUTING.md for code style, DCO instructions, and review expectations.

<p align="center">
  <img src="https://img.shields.io/github/actions/workflow/status/monozoide/MailLogSentinel/python-app.yml?branch=main" alt="CI Status" />
  <img src="https://img.shields.io/badge/Issues-Welcome-brightgreen" alt="Issues Welcome" />
  <img src="https://img.shields.io/badge/Hacktoberfest-2025-FF8AE2?style=flat-square&logo=github" alt="Hacktoberfest" />
</p>

---

## 14. License & Support

- License: GNU GPL v3 (see LICENSE)
- Code of Conduct: CODE_OF_CONDUCT.md
- Security policy: SECURITY.md
- Financial support: https://liberapay.com/Zoide (30% redistributed to other OSS projects)
- Contact: open an issue or start a discussion on GitHub

Thank you for helping keep MailLogSentinel effective and accessible.

