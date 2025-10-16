# MailLogSentinel Installation and Configuration Guide

## 📋 Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [System Preparation](#system-preparation)
- [Installation Process](#installation-process)
- [Initial Configuration](#initial-configuration)
- [Verification and Testing](#verification-and-testing)
- [Service Configuration](#service-configuration)
- [Advanced Configuration](#advanced-configuration)
- [Troubleshooting](#troubleshooting)
- [Security Considerations](#security-considerations)

---

## 🔍 Overview

**MailLogSentinel** is a log monitoring and reporting tool designed for mail servers running on Debian-based systems. It extracts, processes, and reports mail log data, with support for SQL export/import functionality.

### Key Features
- **Real-time analysis** of Postfix logs (`/var/log/mail.log`)
- **SASL authentication failure detection** (LOGIN, PLAIN, CRAM-MD5, etc.)
- **Geographic IP enrichment** with ASN/ASO information
- **Automated email reporting** with CSV attachments
- **Systemd timer integration** for scheduled operations
- **SQL export capabilities** for data analysis

---

## 🛠 Prerequisites

### System Requirements

Before installing **MailLogSentinel**, ensure your system meets the following requirements:

| Requirement | Details |
|-------------|---------|
| **Operating System** | Fresh installation of Debian 12 or 13 |
| **Memory** | Minimum 4 GB RAM (for low-traffic production mail servers) |
| **System Tools** | `sudo`, `rsyslog`, `git` (optional, you can use the native wget tool) |
| **Mail Server** | Postfix (optional for testing) |

> [!IMPORTANT]
> This guide assumes a fresh Debian installation. Installing on an existing system may require additional configuration steps.

### Required Services

Before installing **MailLogSentinel**, ensure the following services are properly configured:

1. **Working Debian installation** (fresh recommended)
2. **rsyslog** installed and configured
3. **sudo** access configured
4. **Git** for repository cloning (optional)
5. **SMTP server access** for email reports (optional for testing)

---

## ⚙️ System Preparation

### Step 1: Install sudo

On a fresh Debian installation, `sudo` may not be available by default:

```bash
# Switch to root user
su -

# Update package index and install sudo
apt update && apt install sudo -y

# Add user to sudoers group (replace user by your username)
adduser user sudo

# Reboot to ensure proper initialization
reboot
```

### Step 2: Configure rsyslog

**MailLogSentinel** requires rsyslog for proper log handling:

```bash
# Install rsyslog if not present
sudo apt install rsyslog

# Start and enable rsyslog service
sudo systemctl start rsyslog
sudo systemctl enable --now rsyslog

# Verify rsyslog status
sudo systemctl status rsyslog
```

Configure systemd journal forwarding to syslog:

```bash
# Edit journald configuration
sudo vim /etc/systemd/journald.conf
```

Add or modify the following lines:

```ini
[Journal]
Storage=none
ForwardToSyslog=yes
```

Apply the configuration:

```bash
# Reload systemd daemon and restart services
sudo systemctl daemon-reexec
sudo systemctl restart systemd-journald
sudo systemctl restart rsyslog
```

---

## 📥 Installation Process

### Option 1: Using Debian native tools

```bash
# Download the latest release
wget https://github.com/monozoide/MailLogSentinel/archive/refs/tags/v5.14.15.zip -O MailLogSentinel.zip

# Unzip the archive in user home directory
python3 -m zipfile -e MailLogSentinel.zip ~/
```

Or

### Option 2: Clone the Repository with git

```bash
# Install git
sudo apt install git -y

# Clone MailLogSentinel repository
git clone https://github.com/monozoide/MailLogSentinel.git
cd MailLogSentinel
```

### Install Scripts and Libraries

```bash
# Make scripts executable
chmod +x bin/*.py && chmod +x lib/maillogsentinel/*.py

# Copy executables to system binary directory
sudo cp bin/*.py /usr/local/bin/

# Copy library modules to system library directory
sudo cp -r lib/maillogsentinel /usr/local/lib/
```

```bash
# Run initial installation
sudo python3 /usr/local/bin/maillogsentinel.py --setup --interactive
```

The `--setup --interactive` argument allows you to run an interactive step-by-step installation to install and configure:

```bash
# The main configuration file
/etc/maillogsentinel.conf

# Systemd units and timers
ipinfo-update.service
ipinfo-update.timer
maillogsentinel-extract.timer
maillogsentinel-report.service
maillogsentinel-report.timer
maillogsentinel.service
maillogsentinel-sql-export.service
maillogsentinel-sql-export.timer
maillogsentinel-sql-import.service
maillogsentinel-sql-import.timer

# Access rights & Directory creation
/var/log/maillogsentinel/
/var/lib/maillogsentinel/ 
Adding user to 'adm' group (if not already a member)
```
---

## 🔧 Initial Configuration

### Setup Configuration Files

**MailLogSentinel** uses a configuration-driven approach. 

The main configuration file is created in `/etc/maillogsentinel.conf` on first run with `--setup --interractive`.

**Basic configuration structure:**

```ini
[paths]
working_dir = /var/log/maillogsentinel
state_dir = /var/lib/maillogsentinel
mail_log = /var/log/mail.log

[report]
email = security-team@example.org
report_subject_prefix = [MailLogSentinel]

[geolocation]
country_db_path = /var/lib/maillogsentinel/country_aside.csv
asn_db_path = /var/lib/maillogsentinel/asn.csv

[general]
log_level = INFO
```

---

## ✅ Verification and Testing

### Check Service Status

After installation, verify that **MailLogSentinel** services are properly configured:

```bash
# List MailLogSentinel related systemd units
systemctl list-units --all "*maillogsentinel*" "*ipinfo-update*"
```

Expected output should show:
- `maillogsentinel-extract.timer` - Active/waiting
- `maillogsentinel-report.timer` - Active/waiting  
- `maillogsentinel-sql-export.timer` - Active/waiting
- `maillogsentinel-sql-import.timer` - Active/waiting
- `ipinfo-update.timer`- Active/waiting

> [!NOTE]
> It's normal for the service units to show as *failed* initially, as they haven't been triggered yet. The timers should be in "waiting" state.

### Verify Timer Configuration

```bash
# Check timer status and next execution times
systemctl list-timers --all '*maillogsentinel*' '*ipinfo-update*'
```

This command displays scheduled execution times for all **MailLogSentinel** timers.

### Initial Run

#### 1. Manual Log Extraction

Execute the first data extraction manually:

```bash
# Run initial log analysis
python3 /usr/local/bin/maillogsentinel.py
```

> [!NOTE]
> The first extraction may take a long time depending on the size of your log files. Subsequent extractions are much faster because the script does not reread the logs entirely.

Verify output generation:

```bash
# Check created files
ls -l /var/log/maillogsentinel/

# Monitor real-time CSV output
tail -f /var/log/maillogsentinel/maillogsentinel.csv
```

#### 2. Test Report Generation

For testing purposes (especially on systems without active Postfix), use sample data:

```bash
# Copy sample mail log for testing
sudo cp docs/dataset/sample.mail.log /var/log/mail.log && sudo chown root:adm /var/log/mail.log

# Generate test report
python3 /usr/local/bin/maillogsentinel.py --report
```

#### 3. Email Report Testing

If using local mail delivery for reports, install a mail client to verify output:

```bash
# Install neomutt for local email reading
sudo apt install neomutt -y
```

To read generated reports:

1. Launch `neomutt`
2. Confirm creation of `/home/$USER/Mail` folder
3. Select the **MailLogSentinel** email
4. Press `v` key to view attachments
5. Select `maillogsentinel.csv` to review the data

#### 4. SQL Export Testing

Test the SQL export functionality:

```bash
# Generate SQL export
python3 /usr/local/bin/maillogsentinel.py --sql-export
```

Verify the export file location:

```bash
# Check exported SQL files
ls -l /var/lib/maillogsentinel/
```

---

## ⏰ Service Configuration

### Timer Customization

**MailLogSentinel** uses `systemd` timers for automated operations. You can customize execution intervals:

#### 1. Log Extraction Timer

```bash
# Edit extraction timer
sudo vim /etc/systemd/system/maillogsentinel-extract.timer
```

Modify the `OnCalendar` value:
```ini
OnCalendar=hourly
```

#### 2. Email Reporting Timer

```bash
# Edit reporting timer  
sudo vim /etc/systemd/system/maillogsentinel-report.timer
```

Set daily execution:
```ini
OnCalendar=daily
```

#### 3. SQL Export Timer

```bash
# Edit SQL export timer
sudo vim /etc/systemd/system/maillogsentinel-sql-export.timer
```

Configure 4-minute intervals:
```ini
OnCalendar=*:0/4
```

#### 4. SQL Import Timer

```bash
# Edit SQL import timer
sudo vim /etc/systemd/system/maillogsentinel-sql-import.timer
```

Configure 5-minute intervals:
```ini
OnCalendar=*:0/5
```

### Applying Timer Changes

After modifying timer configurations:

```bash
# Reload systemd daemon
sudo systemctl daemon-reload

# Restart affected timers
sudo systemctl restart maillogsentinel-extract.timer
sudo systemctl restart maillogsentinel-report.timer
sudo systemctl restart maillogsentinel-sql-export.timer
sudo systemctl restart maillogsentinel-sql-import.timer
```

### Systemd Timer Syntax

The `OnCalendar` field uses standard systemd time syntax:

| Value | Description |
|-------|-------------|
| `hourly` | Run once per hour (at minute 0) |
| `daily` | Run once per day (at 00:00) |
| `*:0/5` | Run every 5 minutes |
| `Mon *-*-* 09:00:00` | Run every Monday at 9:00 AM |

For advanced timer configuration, refer to the [systemd/Timers documentation](https://wiki.archlinux.org/title/Systemd/Timers) for complete syntax options.

---

## 🔧 Advanced Configuration

### Geographic Database Updates

**MailLogSentinel** uses IP geolocation databases that require periodic updates:

The `ipinfo.py` script is executed daily via the `ipinfo-update.timer` and retrieves the databases from [ip-location-db](https://github.com/sapics/ip-location-db/tree/main), a project that provides IP to location databases in CSV and MMDB formats:

- [asn-country](https://github.com/sapics/ip-location-db/tree/main/asn-country) IP to country
- [asn](https://github.com/sapics/ip-location-db/tree/main/asn) IP to ASN/ASO

### Performance Tuning

For high-volume mail servers, consider the following optimizations:

- **Memory allocation**: Ensure adequate RAM for log processing
- **Timer intervals**: Adjust based on log volume and processing requirements
- **Database maintenance**: Regular cleanup of old CSV and SQL files

### Integration with Monitoring Systems

**MailLogSentinel** can be integrated with existing monitoring solutions:

- **Log aggregation**: Forward alerts to centralized logging systems
- **Metrics collection**: Export statistics to monitoring dashboards
- **Alerting**: Configure threshold-based notifications

---

## 🐛 Troubleshooting

### Common Issues

#### Service Startup Failures

If **MailLogSentinel** services fail to start:

1. Check service status:
   ```bash
   sudo systemctl status maillogsentinel-extract.service
   ```

2. Review logs:
   ```bash
   sudo journalctl -u maillogsentinel-extract.service
   ```

3. Verify file permissions:
   ```bash
   ls -l /usr/local/bin/maillogsentinel.py
   ls -l /usr/local/lib/maillogsentinel/
   ```

#### Log Processing Issues

If log analysis is not working:

1. Verify log file access:
   ```bash
   sudo ls -l /var/log/mail.log
   ```

2. Check rsyslog configuration:
   ```bash
   sudo systemctl status rsyslog
   ```

3. Test manual execution:
   ```bash
   python3 /usr/local/bin/maillogsentinel.py --debug
   ```

### Log Analysis

For debugging purposes, check MailLogSentinel's own logs:

```bash
# View application logs
sudo tail -f /var/log/mail.log
```

---

## 🔒 Security Considerations

### File Permissions

Ensure proper file permissions for security:

```bash
# Secure configuration files
sudo chmod 600 /etc/maillogsentinel.conf

# Verify log directory permissions
sudo ls -ld /var/log/maillogsentinel/
```

### Network Security

- **Firewall rules**: Ensure appropriate access controls
- **SMTP authentication**: Use secure credentials for email reporting
- **Log retention**: Implement appropriate log rotation and cleanup

### Data Privacy

**MailLogSentinel** processes potentially sensitive log data:

- **Access controls**: Limit access to authorized personnel only
- **Data retention**: Implement appropriate retention policies
- **Anonymization**: Consider log sanitization for compliance

### Production Deployment

For production environments:

1. **Backup configuration**: Maintain secure backups of configuration files
2. **Monitor resource usage**: Track CPU and memory consumption
3. **Regular updates**: Keep MailLogSentinel and dependencies updated
4. **Security audits**: Periodic review of access logs and configurations

---

## 📚 Additional Resources

### Documentation
- **API Reference**: [Programming interface documentation](https://github.com/monozoide/MailLogSentinel/tree/main/docs/api)
- **Configuration Guide**: [Advanced configuration options](https://github.com/monozoide/MailLogSentinel/wiki/Configuration)

### Support
- **GitHub Repository**: [MailLogSentinel Issues](https://github.com/monozoide/MailLogSentinel)
- **Community Forums**: [Discussions](https://github.com/monozoide/MailLogSentinel/discussions)

### Related Tools
- **Postfix Documentation**: [Official Postfix SASL Guide](https://www.postfix.org/SASL_README.html)
- **Systemd Timers**: [ArchWiki Systemd/Timers](https://wiki.archlinux.org/title/Systemd/Timers)

---

## 📝 Frequently Asked Questions

### Installation Questions

**Q: How do I install MailLogSentinel with a database backend?**
[Install MailLogSentinel with a database backend](https://github.com/monozoide/MailLogSentinel/wiki/database-backend)

**Q: Can MailLogSentinel work with journald instead of rsyslog?**
Currently, as of 10/15/2025, journald support is still in development. Stay tuned to be notified as soon as the feature is available.

**Q: How do I use MailLogSentinel on a production Postfix server?**
It all depends on the type of server you have and its configuration. Full documentation is currently being written.

For additional questions and answers, consult the project's [FAQ documentation.](https://github.com/monozoide/MailLogSentinel/wiki/FAQ.md)

## 📚 Additional Resources

- [Official Repository](https://github.com/monozoide/MailLogSentinel)
- [systemd Documentation](https://www.freedesktop.org/software/systemd/man/)
- [Debian Administrator's Handbook](https://www.debian.org/doc/)

---

**Last Updated**: October 2025  
**Version**: Compatible with Debian 12/13

*This guide provides comprehensive instructions for installing and configuring **MailLogSentinel** on Debian 12/13 systems. For the most current information and updates, always refer to the official project repository and documentation.*