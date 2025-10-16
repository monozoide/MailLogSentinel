# MailLogSentinel - Frequently Asked Questions (FAQ)

## Table of Contents

- [🚀 Installation and Configuration](#-installation-and-configuration)
- [⚙️ Daily Usage](#-daily-usage)
- [🔧 Maintenance and Administration](#-maintenance-and-administration)
- [🔗 Advanced Integrations](#-advanced-integrations)
- [🚨 Troubleshooting and Errors](#-troubleshooting-and-errors)
- [📊 Data and Reports](#-data-and-reports)
- [🔐 Security and Permissions](#-security-and-permissions)
- [🛠️ Development](#-development)

***

## 🚀 Installation and Configuration

### Q1: How to install MailLogSentinel on Debian 12/13?

**Step-by-step installation:**

```bash
# 1. Clone the repository
git clone https://github.com/monozoide/MailLogSentinel.git
cd MailLogSentinel

# 2. Copy binaries to system
chmod +x bin/*.py
sudo cp bin/*.py /usr/local/bin/

# 3. Copy libraries
sudo cp -r lib/ /usr/local/bin/

# 4. Run interactive setup
sudo python3 /usr/local/bin/maillogsentinel.py --setup --interactive
```

**📖 Reference:** [Getting Started Guide](../wiki/)

### Q2: What's the difference between `--setup --interactive` and `--setup --automated`?

| Mode | Usage | When to use |
| :-- | :-- | :-- |
| `--interactive` | Asks questions step by step | First installation, custom config |
| `--automated` | Uses existing config file | Multiple deployments, CI/CD |

```bash
# Interactive mode (recommended for first time)
sudo python3 /usr/local/bin/maillogsentinel.py --setup --interactive

# Automated mode (uses /etc/maillogsentinel.conf)
sudo python3 /usr/local/bin/maillogsentinel.py --setup --automated
```

### Q3: How to disable email reports?

Simply stop & disable `maillogsentinel-report.timer` and `maillogsentinel-report.service` :

```bash
systemctl list-timers --all |grep maillogsentinel
Mon 2025-10-13 16:20:00 CEST 3min 33s Mon 2025-10-13 16:16:17 CEST       8s ago maillogsentinel-sql-export.timer maillogsentinel-sql-export.service
Mon 2025-10-13 16:20:00 CEST 3min 33s Mon 2025-10-13 16:15:09 CEST 1min 16s ago maillogsentinel-sql-import.timer maillogsentinel-sql-import.service
Mon 2025-10-13 17:00:00 CEST    43min Mon 2025-10-13 16:00:18 CEST    16min ago maillogsentinel-extract.timer    maillogsentinel.service
Mon 2025-10-13 23:59:59 CEST       7h Mon 2025-10-13 00:00:18 CEST       8h ago maillogsentinel-report.timer     maillogsentinel-report.service
```

```bash
sudo systemctl stop maillogsentinel-report.timer && sudo systemctl stop maillogsentinel-report.service
sudo systemctl disable maillogsentinel-report.service && sudo systemctl disable maillogsentinel-report.timer

```

```bash
systemctl list-timers --all |grep maillogsentinel
Mon 2025-10-13 16:25:00 CEST      10s Mon 2025-10-13 16:20:09 CEST 4min 40s ago maillogsentinel-sql-import.timer maillogsentinel-sql-import.service
Mon 2025-10-13 16:28:00 CEST 3min 10s Mon 2025-10-13 16:24:01 CEST      48s ago maillogsentinel-sql-export.timer maillogsentinel-sql-export.service
Mon 2025-10-13 17:00:00 CEST    35min Mon 2025-10-13 16:00:18 CEST    24min ago maillogsentinel-extract.timer    maillogsentinel.service
```

## ⚙️ Daily Usage

### Q4: How does MailLogSentinel manage sending reports by email?

MailLogSentinel requires the Postfix MTA to be installed and configured to send reports via email with the CSV attachment.

Command line utilities such as mailx do not support sending attachments.

### Q5: How to check if MailLogSentinel is working?

```bash
# Check service status
systemctl status maillogsentinel.service

# View recent logs
journalctl -u maillogsentinel.service -f

# Check data files
ls -la /var/log/maillogsentinel/
tail -20 /var/log/maillogsentinel/maillogsentinel.csv
```


### Q6: How to generate a manual report?

```bash
# Generate and send report immediately
python3 /usr/local/bin/maillogsentinel-report.py --report
```


### Q7: Where are the data and log files stored?

| File Type | Location | Description |
| :-- | :-- | :-- |
| CSV Data | `/var/log/maillogsentinel/maillogsentinel.csv` | Parsed email logs |
| Application Logs | `/var/log/maillogsentinel/maillogsentinel.log` | Service logs |
| State File | `/var/lib/maillogsentinel/maillogsentinel.state` | Processing state |
| Configuration | `/etc/maillogsentinel.conf` | Main config file |

## 🔧 Maintenance and Administration

### Q8: How to backup MailLogSentinel data?

```bash
#!/bin/bash
# Complete backup script
BACKUP_DIR="$HOME/backup/maillogsentinel/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

# Backup data files
cp /var/log/maillogsentinel/* $BACKUP_DIR/

# Backup configuration
cp /etc/maillogsentinel.conf $BACKUP_DIR/

# Backup state
cp /var/lib/maillogsentinel/* $BACKUP_DIR/

# Create archive
tar -czf $BACKUP_DIR.tar.gz $BACKUP_DIR
```


### Q9: How to setup log rotation?

Create `/etc/logrotate.d/maillogsentinel`:

```bash
/var/log/maillogsentinel/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    postrotate
        systemctl reload maillogsentinel.service
    endscript
}

/var/log/maillogsentinel/*.csv {
    weekly
    rotate 52
    compress
    delaycompress
    missingok
    notifempty
}
```


### How to update MailLogSentinel?

```bash
# 1. Stop service
sudo systemctl stop maillogsentinel.service

# 2. Backup current installation
BACKUP_DIR="$HOME/backup/maillogsentinel/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR
sudo cp -r /usr/local/bin/maillogsentinel* $BACKUP_DIR/

# 3. Update from Git
cd MailLogSentinel
git pull origin main

# 4. Update installation
chmod +x bin/*.py
sudo cp bin/*.py /usr/local/bin/

# 3. Copy libraries
sudo cp -r lib/ /usr/local/bin/

# 5. Restart service
sudo systemctl start maillogsentinel.service
```


### How to migrate data to a new server?

```bash
# On old server - Export data
python3 /usr/local/bin/maillogsentinel.py --sql-export --output=/tmp/maillog_export.sql

# Transfer files to new server
scp /tmp/maillog_export.sql newserver:/tmp/
scp /etc/maillogsentinel.conf newserver:/tmp/

# On new server - Import data
python3 /usr/local/bin/maillogsentinel.py --sql-import --input=/tmp/maillog_export.sql
sudo cp /tmp/maillogsentinel.conf /etc/
```


***

## 🔗 Advanced Integrations

### How to integrate with Metabase?

**1. Export data to SQL format:**

```bash
python3 /usr/local/bin/maillogsentinel.py --sql-export --output=/tmp/maillog_data.sql
```

**2. Import into PostgreSQL/MySQL:**

```sql
-- PostgreSQL example
CREATE DATABASE maillogsentinel;
\c maillogsentinel
\i /tmp/maillog_data.sql
```

**3. Connect Metabase:**

- Database type: PostgreSQL/MySQL
- Host: localhost
- Database: maillogsentinel
- Username/Password: your DB credentials

**4. Example Metabase queries:**

```sql
-- Top domains by email volume
SELECT domain, COUNT(*) as email_count 
FROM mail_logs 
WHERE timestamp >= NOW() - INTERVAL '30 days'
GROUP BY domain 
ORDER BY email_count DESC;

-- SASL authentication failures
SELECT COUNT(*) as failures, DATE(timestamp) as day
FROM mail_logs 
WHERE message LIKE '%SASL%authentication%failed%'
GROUP BY DATE(timestamp)
ORDER BY day DESC;
```

**📖 Reference:** [Metabase Integration Guide](https://github.com/monozoide/MailLogSentinel/wiki/metabase-integration-guide)

### How to setup automated SQL exports?

There are two ways to do this:

1. The native method:
   - Install SQLite3 `sudo apt install sqlite3`
   - Enable the `maillogsentinel-sql-import.service` and `maillogsentinel-sql-import.timer` services

And that's it, the service takes care of everything!

2. The manual method: you must:
   - Install, configure and secure an SQL Server (Mariadb, PostgreSQL)
   - Create a script to import the SQL file into your database

You can find the [SQL column mapping file](https://github.com/monozoide/MailLogSentinel/blob/main/config/maillogsentinel_sql_column_mapping.json)

**📖 Reference:**: 
   - [Using MailLogSentinel's native SQL tools](https://github.com/monozoide/MailLogSentinel/wiki/maillogsentinel-and-sqlite3)
   - [Using RDBMS with MailLogSentinel](https://github.com/monozoide/MailLogSentinel/wiki/maillogsentinel-and-rdbms)

## 🚨 Troubleshooting and Errors

### Error "Permission denied" on /var/log/mail.log

**Problem:** MailLogSentinel can't read mail logs.

**Solution:**

```bash
# Add user to syslog group
sudo usermod -a -G syslog $USER

# Or add maillogsentinel user to adm group
sudo usermod -a -G adm maillogsentinel

# Alternative: Change log file permissions
sudo chmod 644 /var/log/mail.log

# Restart service
sudo systemctl restart maillogsentinel.service
```


### Service fails to start

**Check service status:**

```bash
sudo systemctl status maillogsentinel.service -l
journalctl -u maillogsentinel.service --no-pager
```

**Common issues and solutions:**


| Error | Cause | Solution |
| :-- | :-- | :-- |
| `Config file not found` | Missing configuration | Run `sudo maillogsentinel.py --setup --interactive` |
| `Python module not found` | Incomplete installation | Reinstall libraries: `sudo cp -r lib/ /usr/local/bin/` |

### No emails in reports

**Diagnostic steps:**

```bash
# 1. Check if parsing is working
tail -50 /var/log/maillogsentinel/maillogsentinel.csv

# 2. Check mail log format
tail -20 /var/log/mail.log

# 3. Test email sending
echo "Test" | mail -s "Test Report" admin@domain.com

# 5. Check or occurrences of authentication failures
grep -hoP 'sasl_username=\K[^, ]+' /var/log/mail.log | sort | uniq -c | sort -nr | awk '{print $2 " : " $1}'
```

## 📊 Data and Reports

### How to analyze CSV data manually?

**Basic analysis with command-line tools:**

```bash
# Count total emails
wc -l /var/log/maillogsentinel/maillogsentinel.csv

# Top 10 senders
awk -F',' '{print $4}' /var/log/maillogsentinel/maillogsentinel.csv | sort | uniq -c | sort -nr | head -10

# Emails by hour
awk -F',' '{print substr($1,12,2)}' /var/log/maillogsentinel/maillogsentinel.csv | sort | uniq -c

# SASL failures
grep -i "sasl.*fail" /var/log/mail.log | wc -l
```

## 🔐 Security and Permissions

### What are the recommended security settings?

**File permissions:**

```bash
# Configuration file (sensitive data)
sudo chmod 600 /etc/maillogsentinel.conf
sudo chown root:root /etc/maillogsentinel.conf

# Data directory
sudo chmod 750 /var/log/maillogsentinel/
sudo chown maillogsentinel:syslog /var/log/maillogsentinel/

# State files
sudo chmod 640 /var/lib/maillogsentinel/
sudo chown maillogsentinel:maillogsentinel /var/lib/maillogsentinel/
```

### How to run with minimal privileges?

**Create dedicated user:**

```bash
# Create system user
sudo useradd --system --no-create-home --shell /bin/false maillogsentinel

# Add to necessary groups
sudo usermod -a -G syslog maillogsentinel

# Update service file
sudo systemctl edit maillogsentinel.service
```

**Service configuration:**

```ini
[Service]
User=maillogsentinel
Group=syslog
# Remove sudo requirements
ExecStart=/usr/local/bin/maillogsentinel.py --no-root
```

## 🛠️ Development

### How to contribute to MailLogSentinel?

**Development setup:**

```bash
# Fork and clone
git clone https://github.com/monozoide/MailLogSentinel.git
cd MailLogSentinel

# Create development environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install in development mode
pip install -e .

# Run tests
python -m pytest tests/
```

**Code style:**

```bash
# Format code
black .
isort .

# Lint code  
flake8 .
pylint .

# Type checking
mypy .
```

**📖 Reference:** [Contributing Guide](../CONTRIBUTING.md)

## 🆘 Getting More Help

- **📚 Documentation:** [Project Wiki](https://github.com/monozoide/MailLogSentinel/wiki)
- **🐛 Bug Reports:** [GitHub Issues](https://github.com/monozoide/MailLogSentinel/issues)
- **💬 Discussions:** [GitHub Discussions](https://github.com/monozoide/MailLogSentinel/discussions)
- **📧 Contact:** [Project Maintainer](https://github.com/monozoide)

**Before asking for help:**

1. ✅ Check this FAQ
2. ✅ Search existing [GitHub issues](https://github.com/monozoide/MailLogSentinel/issues)
3. ✅ Run diagnostic commands from this FAQ
4. ✅ Include relevant logs and configuration (sanitized)

***

*This FAQ is maintained by the community. [Contribute improvements](https://github.com/monozoide/MailLogSentinel/blob/main/docs/wiki/FAQ.md) to help other users!*

***