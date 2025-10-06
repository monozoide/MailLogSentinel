# MailLogSentinel - systemd/journald Support

MailLogSentinel now supports reading mail logs from both traditional syslog files and systemd journald. The system will automatically detect the best available log source, or you can configure it explicitly.

## Log Source Autodetection

By default, MailLogSentinel will automatically detect the best log source:

1. **journald** is preferred if:
   - `journalctl` command is available
   - journald has entries for the mail service (default: `postfix.service`)

2. **syslog** is used as fallback if:
   - journalctl is not available
   - No journald entries found for the mail service

## Configuration

Add the following section to your `/etc/maillogsentinel.conf`:

```ini
[log_source]
# Options: auto, syslog, journald (default: auto)
source_type = auto

# systemd unit for journald reading (default: postfix.service)
journald_unit = postfix.service
```

### Configuration Options

- **source_type**: 
  - `auto` - Automatic detection (recommended)
  - `syslog` - Force traditional syslog file reading
  - `journald` - Force journald reading

- **journald_unit**: The systemd unit to monitor when using journald (e.g., `postfix.service`, `mail.service`)

## Manual Testing

### Test journald availability

```bash
# Check if journalctl is available
journalctl --version

# Check for Postfix entries in journald
journalctl -u postfix.service --since today | head -10
```

### Force syslog mode

```ini
[log_source]
source_type = syslog
```

### Force journald mode

```ini
[log_source]
source_type = journald
journald_unit = postfix.service
```

## Example journalctl Commands

MailLogSentinel uses commands similar to these when reading from journald:

```bash
# Basic journald reading
journalctl -u postfix.service --output=json --no-pager

# Reading since a specific time
journalctl -u postfix.service --output=json --no-pager --since "2023-11-01 10:00:00"

# Reading recent entries only
journalctl -u postfix.service --output=json --no-pager --since "1 hour ago"
```

## Troubleshooting

### Permission Issues

If you encounter permission issues with journalctl:

```bash
# Add user to systemd-journal group (Ubuntu/Debian)
sudo usermod -a -G systemd-journal maillogsentinel

# Or use adm group (some distributions)
sudo usermod -a -G adm maillogsentinel
```

### No Entries Found

If autodetection falls back to syslog:

1. Check if your mail service uses a different unit name:
   ```bash
   systemctl list-units | grep -i mail
   systemctl list-units | grep -i postfix
   ```

2. Update the configuration:
   ```ini
   [log_source]
   source_type = journald
   journald_unit = your-mail-service.service
   ```

### Verify Log Parsing

The journald reader converts journald entries to syslog format internally. You can verify the format by running:

```bash
journalctl -u postfix.service --output=json --lines=1 | jq
```

This shows the raw journald format that gets converted to syslog format for processing.

## Backward Compatibility

- Existing configurations continue to work without changes
- Syslog file reading remains the default on non-systemd systems
- All existing features (rotation detection, gzip support, etc.) work with both sources