# NAME

maillogsentinel - monitor Postfix SASL authentication failures

# SYNOPSIS

```shell
    maillogsentinel [options]
    maillogsentinel --setup [--config FILE]
```

# DESCRIPTION

MailLogSentinel parses Postfix SASL authentication logs, records failed login attempts, and emails daily reports. The utility keeps persistent CSV and state files so subsequent runs only process new log lines.

Normal operation must be executed as an unprivileged service user; root access is only required for the initial setup workflow.

The program reads configuration values from an INI file (see Configuration). When invoked without command options, it processes the configured mail log, updates the persistent dataset, and generates progress messages on stdout. Dedicated subcommands are available for reporting, state resets, SQL export/import, and non-interactive setup.

# OPTIONS

**`--config FILE`**
Override the default configuration file path (`/etc/maillogsentinel.conf`). When combined with `--setup` the supplied file is treated as the source template for automated provisioning.

**`--setup`**
Create or refresh configuration, directories, and systemd units. Run this command with root privileges. Without `--config` the setup wizard runs interactively and writes `/etc/maillogsentinel.conf`. When `--config` is supplied, the wizard performs an automated deployment using that template.

**`--report`**
Send the email summary immediately using the currently persisted dataset. Requires mail transport configuration in the config file.

**`--reset`**
Back up the CSV, operational log, and offset state into `~/maillogsentinel_backup_XXXXXX`, then remove the originals so the next execution reprocesses all historical logs. Cron/systemd timers must be managed manually afterwards.

**`--purge`**
Perform the same archival workflow as `--reset` but is intended for complete environment refreshes. All persisted artefacts are moved into a timestamped directory beneath the invoking user's home.

**`--sql-export`**
Append newly discovered events to SQL files located in the configured s`ql_export_dir`. Use this for long-term storage or downstream analytics systems that ingest SQL statements.

**`--sql-import`**
Read .sql files from `sql_export_dir` and replay them against the database described in the `[database\]` section of the configuration.

# PREREQUISITES

- Python 3.10 or later.
- Access to the Postfix log files defined in the configuration.
- A functional local mail transfer agent for dispatching summary emails.
- Root privileges for the setup command; day-to-day execution should use a
dedicated service account.

# CONFIGURATION

Settings are stored in an INI file (default `etc/maillogsentinel.conf`).
Only keys that persist between executions or affect operations are
documented below. Developer-oriented tuning options are described in the
project documentation.

## `[paths]`

**`working_dir`**
Location for the persistent CSV (`maillogsentinel.csv`) and operational log (`maillogsentinel.log`). Ensure the service account can read and write this directory.

**`state_dir`**
Directory containing `tate.offset`, which tracks the last processed position within the mail log.

**`mail_log`**
Absolute path to the mail log file to monitor, typically `/var/log/mail.log`.

## `[report]`

**`email`**
Recipient address for the daily summary email. The message body lists top sources, usernames, and other aggregated indicators derived from the CSV.

## `[general]`

**`log_level`**
Logging verbosity for maillogsentinel.log. Accepts `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`.

## `[dns_cache]`

**`enabled`**
Toggle cached reverse DNS lookups to reduce latency and repeated resolver traffic.

**`size`**
Maximum number of entries retained in the DNS cache.

**ttl_seconds**
Expiration time for cached DNS entries.

## `[ipinfo]`

**`country_db_path`**
Path to the country database used for IP geolocation.

**`asn_db_path`**
Path to the ASN database used for enrichment.

**`db_update_url_country`**
Download URL for refreshing the country database.

**`db_update_url_asn`**
Download URL for refreshing the ASN database.

## `[database]`

**`sql_export_dir`**
Directory that stores generated SQL export files and the source material for `--sql-import`.

**`db_type`**
Database backend used for imports (for example postgresql or mysql).

**`db_host`**
Hostname or address of the database service.

**`db_name`**
Target database schema.

**`db_user`**
Credential name for database access.

**`db_password`**
Password used by db_user. Protect this file with restrictive permissions.

# FILES

**`/etc/maillogsentinel.conf`**
Primary configuration file created by `--setup`.

**`<working_dir`>/maillogsentinel.csv`**
Persistent datastore containing failed authentication events.

**`<working_dir>/maillogsentinel.log`**
Operational log capturing runtime diagnostics.

**`<state_dir>/state.offset`**
Offset tracker that prevents reprocessing of previously parsed log lines.

**`<sql_export_dir>/*.sql`**
Incremental SQL export batches generated by `--sql-export`.

**`./maillogsentinel_setup.log`**
Transcript of the last setup session, useful for troubleshooting provisioning issues.

# DIAGNOSTICS

Runtime messages are written to stdout and to maillogsentinel.log using the configured log level. When deployed as a systemd service, inspect progress with:

```shell
    journalctl -u maillogsentinel.service
    journalctl -u maillogsentinel-report.service
```

Failures during setup are documented in maillogsentinel_setup.log. SQL import/export issues are logged alongside the operational log file.

# SYSTEMD INTEGRATION

The setup wizard installs sample units named maillogsentinel.service, maillogsentinel-extract.timer, maillogsentinel-report.service, and maillogsentinel-report.timer. Review and adjust the User= directive and paths before copying them to /etc/systemd/system, then reload systemd and enable the timers.

# SECURITY

Do not run the main extraction workflow as root. Grant the service user read access to mail logs and write access to the working/state directories. Protect `/etc/maillogsentinel.conf` because it may contain SMTP credentials and database passwords. Network downloads performed by `ipinfo.py` should be executed with appropriate firewalls and TLS validation in place.

# AUXILIARY UTILITIES

**`bin/log_anonymizer.py`**
Redacts sensitive fields within mail logs to support troubleshooting without leaking credentials or addresses.

**`bin/ipinfo.py`**
Maintains the geolocation databases referenced by `[ipinfo]` settings and can query IP metadata on demand. Use `bin/ipinfo.py --update` to refresh the datasets.

# EXAMPLES

Initial interactive deployment

```shell
sudo python3 maillogsentinel.py --setup
```

Automated deployment from a prepared configuration

```shell
sudo python3 maillogsentinel.py --config /opt/bootstrap/maillogsentinel.conf --setup
```

Daily processing from a custom configuration

```shell
python3 maillogsentinel.py --config /srv/maillogsentinel/maillogsentinel.conf
```

Force immediate email delivery for the accumulated dataset

```shell
python3 maillogsentinel.py --report
```

Archive existing state and restart ingestion

```shell
python3 maillogsentinel.py --reset
```

# EXIT STATUS

**`0`**
Successful execution.

**`1`**
A recoverable error occurred (for example missing configuration, permission errors, or setup cancellation). Inspect maillogsentinel.log or maillogsentinel_setup.log for details.

# REPORTING BUGS

Report issues at https://github.com/monozoide/MailLogSentinel/issues.

# AUTHOR

Written by monozoide. Project home page: https://github.com/monozoide/MailLogSentinel.

# SEE ALSO

**`fail2ban(1)`**

**`journalctl(1)`**

**`systemd.service(5)`**

**`systemd.timer(5)`**

**`rsyslog.conf(5)`**

**`syslog-ng.conf(5)`**
