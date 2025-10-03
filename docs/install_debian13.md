# MailLogSentinel - Debian 12/13 Installation Guide

**Time:** ≤ 15 minutes  
**System:** Debian 12 (Bookworm) / Debian 13 (Trixie)

## 1. Prerequisites

Verify requirements:

```bash
cat /etc/debian_version    # Should be 12.x or 13.x
python3 --version          # Python 3.9+
systemctl status postfix   # Should be active
sudo whoami                # Should return 'root'
```

---

## 2. System Preparation

Update and install dependencies:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-venv python3-pip git
```

---

## 3. Installation

### Create directory and clone repository

```bash
sudo mkdir -p /opt/maillogsentinel
sudo chown $USER:$USER /opt/maillogsentinel
cd /opt/maillogsentinel
git clone https://github.com/monozoide/MailLogSentinel.git .
```

### Setup Python virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 4. Configuration

### Create configuration file

```bash
mkdir -p config
cat > config/config.ini << 'EOF'
[paths]
log_file = /var/log/mail.log
output_csv = /var/log/maillogsentinel/mail_report.csv

[email]
smtp_server = localhost
smtp_port = 25
from_address = maillogsentinel@localhost
to_address = admin@localhost
send_email = false

[processing]
time_range = 24h
EOF
```

### Create output directory and set permissions

```bash
sudo mkdir -p /var/log/maillogsentinel
sudo chown $USER:$USER /var/log/maillogsentinel
sudo usermod -aG adm $USER
```

> **Note:** Logout and login again or use `newgrp adm`

---

## 5. Systemd Configuration

### Create service

```bash
sudo tee /etc/systemd/system/maillogsentinel.service > /dev/null << 'EOF'
[Unit]
Description=MailLogSentinel - Postfix Log Analyzer
After=network.target postfix.service

[Service]
Type=oneshot
User=maillogsentinel
Group=maillogsentinel
WorkingDirectory=/opt/maillogsentinel
Environment="PATH=/opt/maillogsentinel/venv/bin:/usr/local/bin:/usr/bin"
ExecStart=/opt/maillogsentinel/venv/bin/python main.py
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
```

### Create timer (runs hourly)

```bash
sudo tee /etc/systemd/system/maillogsentinel.timer > /dev/null << 'EOF'
[Unit]
Description=MailLogSentinel Hourly Timer
Requires=maillogsentinel.service

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
Persistent=true

[Install]
WantedBy=timers.target
EOF
```

### Create system user

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin maillogsentinel
sudo usermod -aG adm maillogsentinel
sudo chown -R maillogsentinel:maillogsentinel /opt/maillogsentinel
sudo chown -R maillogsentinel:maillogsentinel /var/log/maillogsentinel
```

---

## 6. Enable and Start

```bash
sudo systemctl daemon-reload
sudo systemctl enable maillogsentinel.timer
sudo systemctl start maillogsentinel.timer
sudo systemctl start maillogsentinel.service  # Manual test
```

---

## 7. Verification

### Service status

```bash
systemctl status maillogsentinel.service
```

### Timer status

```bash
systemctl list-timers | grep maillogsentinel
```

### Service logs

```bash
journalctl -u maillogsentinel.service --no-pager | tail -n 50
```

### Check generated CSV file

```bash
ls -lh /var/log/maillogsentinel/
head -n 10 /var/log/maillogsentinel/mail_report.csv
```

---

## 8. Troubleshooting

### Service fails to start

```bash
# View error logs
journalctl -u maillogsentinel.service -n 100 --no-pager

# Common issues:
# - Permission denied: add user to 'adm' group
# - Module not found: reinstall dependencies in venv
# - Config missing: verify /opt/maillogsentinel/config/config.ini exists
```

### Timer not triggering

```bash
systemctl status maillogsentinel.timer
systemctl list-timers --all | grep maillogsentinel
```

### No output generated

```bash
# Check if Postfix is logging
sudo tail -f /var/log/mail.log

# Check log path in config
grep log_file /opt/maillogsentinel/config/config.ini
```

---

## 9. Customization

### Run daily instead of hourly

```bash
sudo systemctl edit --full maillogsentinel.timer
# Change: OnUnitActiveSec=1h to OnUnitActiveSec=1d
sudo systemctl daemon-reload
sudo systemctl restart maillogsentinel.timer
```

### Analyze last 7 days

```bash
sudo nano /opt/maillogsentinel/config/config.ini
# Change: time_range = 24h to time_range = 7d
```

### Enable email sending

```bash
sudo nano /opt/maillogsentinel/config/config.ini
# Change: send_email = false to send_email = true
# Configure from_address and to_address
sudo systemctl restart maillogsentinel.service
```

---

## 10. Maintenance

### Log rotation

```bash
sudo tee /etc/logrotate.d/maillogsentinel > /dev/null << 'EOF'
/var/log/maillogsentinel/*.csv {
    weekly
    rotate 12
    compress
    missingok
}
EOF
```

### Update MailLogSentinel

```bash
cd /opt/maillogsentinel
sudo -u maillogsentinel git pull
sudo -u maillogsentinel venv/bin/pip install --upgrade -r requirements.txt
sudo systemctl restart maillogsentinel.service
```

---

## 11. Uninstallation

```bash
sudo systemctl stop maillogsentinel.timer maillogsentinel.service
sudo systemctl disable maillogsentinel.timer maillogsentinel.service
sudo rm /etc/systemd/system/maillogsentinel.{service,timer}
sudo systemctl daemon-reload
sudo rm -rf /opt/maillogsentinel /var/log/maillogsentinel
sudo userdel maillogsentinel
```

---

## Validation Checklist

- [ ] `systemctl status maillogsentinel.service` - no errors
- [ ] `systemctl list-timers | grep maillogsentinel` - shows next run
- [ ] `journalctl -u maillogsentinel.service` - execution logs
- [ ] CSV exists at `/var/log/maillogsentinel/mail_report.csv`
- [ ] CSV contains valid Postfix data

---

## Additional Resources

- **Repository:** https://github.com/monozoide/MailLogSentinel.git
- **Postfix Docs:** http://www.postfix.org/documentation.html
- **Systemd Timers:** https://wiki.archlinux.org/title/Systemd/Timers

---

**Version:** 1.0  
**Tested on:** Debian 13 (Trixie)
