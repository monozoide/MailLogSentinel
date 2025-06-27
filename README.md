# MailLogSentinel

<p align="center">
  <img src="img/banner-logo.png" alt="MailLogSentinel Banner" height="100">
</p>

<p align="center">
A simple monitoring tool for Postfix mail servers.
</p>

<p align="center">
  <img src="https://img.shields.io/github/actions/workflow/status/monozoide/MailLogSentinel/python-app.yml?branch=main" alt="GitHub Actions Status" />
  <img src="https://img.shields.io/github/languages/top/monozoide/MailLogSentinel" alt="GitHub top language" /> 
  <img src="https://img.shields.io/badge/python-3.x-brightgreen" alt="Python 3.x" /> 
  <img src="https://img.shields.io/badge/Issues-Welcome-brightgreen" alt="Issues Welcome" />
  <img src="https://img.shields.io/liberapay/receives/Zoide.svg?logo=liberapay">
  <img src="https://img.shields.io/liberapay/gives/Zoide.svg?logo=liberapay">
</p>



---

## Table of Contents

- [Introduction](#introduction)
- [Quick Start](#quick-start)
- [Architecture & Visuals](#architecture--visuals)
- [Generated email](#generated-email)
- [Generated CSV Structure](#generated-csv-structure)
- [Generated logs](#generated-logs)
- [Additional features](#additional-features)
- [Full documentation](#full-documentation)
- [Contributing](#contributing)
- [Roadmap](#roadmap)
- [License](#license)
- [Support](#support)

---

## Introduction

Running your own mail server (Postfix) can feel like playing with fire: initial setup, securing, maintenance – and then daily brute-force attacks on your authentication.

**MailLogSentinel** automates log analysis to detect intrusion attempts in real time. It:

- Scans Postfix logs (including rotated archives)
- Identifies failed SASL authentications
- Extracts key details (date, server, IP, username, hostname)
- Look up IP address information, such as country, ASN and ASO
- Appends findings to a CSV file
- Sends concise email summaries on schedule

No complex frameworks—just Python 3 and standard libraries, plus your existing Postfix mail server.

---

## Quick Start

1. **Clone the repository**
 ```bash
git clone https://github.com/monozoide/MailLogSentinel.git
cd MailLogSentinel
```

2. **Install the script**
```bash
chmod +x bin/*.py 
sudo cp bin/maillogsentinel.py /usr/local/bin/
sudo cp bin/ipinfo.py /usr/local/bin/
# Ensure the library is accessible, e.g., by installing it or adjusting PYTHONPATH
# For a simple system-wide install of the library (adjust paths as needed):
sudo mkdir -p /usr/local/lib/maillogsentinel
sudo cp lib/maillogsentinel/*.py /usr/local/lib/maillogsentinel/
sudo cp -r lib/maillogsentinel /usr/local/lib/
```
The main script `maillogsentinel.py` includes a setup routine.

3. **Run Initial Setup**

MailLogSentinel offers two primary setup modes:

*   **Interactive Setup (Recommended for first-time users):**
    This mode guides you through the configuration process step-by-step, asking for necessary paths, email addresses, and scheduling preferences. Progress is displayed directly in the console.
    ```bash
    sudo /usr/local/bin/maillogsentinel.py --setup --interactive
    ```
    During this process, a detailed log is also saved to `maillogsentinel_setup.log` in the directory where you run the command.

*   **Automated/Silent Setup:**
    This mode uses a pre-configured file for setup. It's useful for deployments or when you have a standard configuration.
    First, you'll need a source configuration file. You can generate one by running the interactive setup on a machine or by manually creating it based on the required parameters (see `bin/maillogsentinel_setup.py` or the Wiki for details on the config structure).
    ```bash
    sudo /usr/local/bin/maillogsentinel.py --setup --automated /path/to/your/source_maillogsentinel.conf
    ```
    Progress for automated setup is primarily logged to `maillogsentinel_setup.log`. Console output is minimal, mainly for critical errors.

> [!WARNING]
> Read the [Wiki](https://github.com/monozoide/MailLogSentinel/wiki) for detailed information on configuration options and prerequisites before the first run.

## Progress Display

*   **Setup:**
    *   **Interactive:** Progress messages are printed to the console at each major step (e.g., "Saving configuration file...", "Creating directories...", "Installing Systemd unit files..."). A detailed log is kept in `maillogsentinel_setup.log`.
    *   **Automated:** Minimal console output. Detailed progress is logged in `maillogsentinel_setup.log`.
*   **Log Extraction & Reporting:**
    *   When run directly (e.g., for testing or manual execution), progress and errors are printed to the console based on the configured log level.
    *   When run as a Systemd service (the typical production setup), all output (stdout and stderr) is directed to the Systemd journal. You can view these logs using `journalctl -u maillogsentinel.service` (for extraction) or `journalctl -u maillogsentinel-report.service` (for reporting).
    *   Detailed operational logs are also written to the file specified in the configuration (default: `/var/log/maillogsentinel/maillogsentinel.log`).

## Architecture & Visuals

```mermaid
graph LR
  A[Postfix logs] --> B[MailLogSentinel] --> C[IpInfo]
  C --> D[CSV File]
  C --> E[Email Report]
```

## Generated email
The email report provides a summary of failed login attempts. Here's an example:
```
##################################################
### MailLogSentinel v1.0.5-A                     ###
### Extraction interval : hourly                 ###
### Report at 2025-05-28 10:30                   ###
### Server: 192.168.1.10   (mail.example.com)    ###
##################################################

Total attempts today: 55

Top 10 failed authentications today:
   1. user@example.com     111.222.11.22  host.attacker.cn   CN  5 times
   2. admin@example.com    22.33.44.55    another.host.ru    RU  4 times
   3. testuser             123.123.1.2    unknown.host.br    BR  3 times
   4. support@example.com  99.88.77.6     some.server.us     US  3 times
   5. webmaster            10.20.30.40    dynamic.isp.de     DE  2 times
   6. info@example.com     5.15.25.35     mail.other.net     GB  2 times
   7. user.1@domain.tld    220.182.17.122 null               N/A 1 times
   8. user.1               81.189.180.120 null               N/A 1 times
   9. qijoxuli@domain.tld  31.25.31.12    host.example.ru    RU  1 times
  10. info@domain.com      73.197.194.98  c-73-197-194-98... US  1 times

Top 10 Usernames today:
   1. user@example.com         10 times
   2. user.1@domain.tld		6 times
   3. contact@domain.com	3 times
   4. user2@domain.tld		2 times
   5. user2			2 times
   6. info@domain.com		2 times
   7. contact			2 times
   8. other			2 times
   9. qijoxuli@domain.tld	1 times
  10. qijoxuli			1 times
  
Top 10 countries today:
   1. CN             6 times
   2. RU             1 times
   3. MY             1 times
   4. AU             1 times
   5. AE             1 times
   6. BR             1 times
   7. US             1 times
   8. MD             1 times

Top 10 ASO today:
   1. CHINA UNICOM China169 Backbone                                                2 times
   2. China Mobile Communications Corporation                                       2 times
   3. PJSC Moscow city telephone network                                            1 times
   4. China Unicom IP network China169 Guangdong province                           1 times
   5. China Mobile                                                                  1 times
   6. Celcom Axiata Berhad                                                          1 times
   7. AAPT Limited                                                                  1 times
   8. Hulum Almustakbal Company for Communication Engineering and Services Ltd      1 times
   9. TELEFONICA BRASIL S.A                                                         1 times
  10. Frontier Communications of America, Inc.                                      1 times

Top 10 ASN today:
   1. 4837        2 times
   2. 134810      2 times
   3. 25513       1 times
   4. 17816       1 times
   5. 9808        1 times
   6. 10030       1 times
   7. 2764        1 times
   8. 203214      1 times
   9. 18881       1 times
  10. 5650        1 times

--- Reverse DNS Lookup Failure Summary ---
Total failed reverse lookups today: 26
Breakdown by error type:
  Errno 1 : 24
  Errno 2 :  2

Total CSV file size: 241.1K
Total CSV lines:     3613

Please see attached: maillogsentinel.csv

For more details and documentation, visit: https://github.com/monozoide/MailLogSentinel/blob/main/README.md
```

## Generated CSV Structure
`reports/intrusions.csv` columns:
|server|date|ip|user|hostname|reverse_dns_status|country_code|asn|aso|
|--------|--------------------|-----------------|--------------|--------------------|---------|----|----------------------|---------|
| srv01  | 2025-05-17 11:13   | 105.73.190.126  | office@me    | null               | Errno 1 | CN | AAPT Limited         | 134810  |
| srv01  | 2025-05-17 12:05   | 81.30.107.24    | contribute   | mail.example.com   | OK      | US | China Mobile         | 9808    |
| srv01  | 2025-05-17 13:45   | 192.0.2.45      | admin        | host.example.org   | OK      | BR | Celcom Axiata Berhad | 18881   |

Each new intrusion record is appended automatically.

## Generated logs
```
2025-05-29 00:00:00,315 INFO === Start of MailLogSentinel v1.0.4-B ===
2025-05-28 23:50:04,990 DEBUG Read CSV line: Server='srv', Date='01/05/2025 02:28', IP='188.255.34.171', User='admin@libranet.fr', Hostname='broadband-188-255-34-171.ip.moscow.rt.ru', DNS Status='OK'. Comparing Date with '28/05/2025'.
2025-05-29 00:00:00,315 DEBUG Files to process: [PosixPath('/var/log/mail.log')], starting from offset: 1198314
2025-05-29 00:00:00,315 INFO Processing /var/log/mail.log (gzip: False)
2025-05-29 00:00:00,316 INFO Incremental read of /var/log/mail.log from 1198314
2025-05-29 00:00:00,351 DEBUG Using valid cached DNS entry for 206.231.72.34 (timestamp: 1748469600.351121).
2025-05-29 00:00:00,351 DEBUG Reverse lookup failed for IP 206.231.72.34: Errno 4
2025-05-29 00:00:00,353 DEBUG Using valid cached DNS entry for 120.157.82.240 (timestamp: 1748469600.3531048).
2025-05-29 00:00:00,353 DEBUG Reverse lookup failed for IP 120.157.82.240: Errno 1
2025-05-29 00:00:00,685 DEBUG Using valid cached DNS entry for 47.91.88.67 (timestamp: 1748469600.685305).
2025-05-29 00:00:00,685 DEBUG Reverse lookup failed for IP 47.91.88.67: Errno 2
2025-05-29 00:00:00,924 DEBUG Using valid cached DNS entry for 36.135.62.103 (timestamp: 1748469600.9245389).
2025-05-28 23:50:05,205 INFO Report sent from admin@my_server.fqdn to admin@my_server.fqdn
2025-05-29 00:00:01,938 INFO === End of MailLogSentinel execution ===
```

## Additional features

### Log Anonymizer Script

The `bin/log_anonymizer.py` script is a utility designed to anonymize sensitive data within log files, with a particular focus on Postfix mail logs. This is useful for sharing log excerpts for troubleshooting purposes or for archiving logs while minimizing privacy concerns.

> [!WARNING]
> Read the [Wiki](https://github.com/monozoide/MailLogSentinel/wiki) for more informations about this feature.

### IP Information Utility (`ipinfo.py`)

`ipinfo.py` is a command-line tool and library to look up IP address information, such as country, ASN (Autonomous System Number), and ASO (Autonomous System Organization), using local databases. It also includes functionality to download and update these databases. The default IP geolocation databases used by this utility are sourced from the `sapics/ip-location-db` project on GitHub by user 'sapics' and are licensed under [Creative Commons Zero (CC0)](https://creativecommons.org/publicdomain/zero/1.0/deed). You can find the repository at [https://github.com/sapics/ip-location-db](https://github.com/sapics/ip-location-db).

Basic CLI usage examples:
```bash
# Update databases
bin/ipinfo.py --update

# Lookup an IP address
bin/ipinfo.py 8.8.8.8
```
The script can be configured via `maillogsentinel.conf` to specify paths for the databases, or it will use default paths if not configured.

## Full documentation
> [!IMPORTANT]
> This is just an overview of how it works and features. For full user and administrator documentation, please visit the [MailLogSentinel Wiki](https://github.com/monozoide/MailLogSentinel/wiki).

### API Documentation
For developers interested in the internal workings or wanting to contribute to the codebase, API documentation generated from the source code is available:
- [API Documentation](docs/api/maillogsentinel.html)

## Contributing
All contributions are welcome—code, docs, ideas, bug reports!
1. Fork 🖐️
2. Create branch: `git checkout -b feature/YourFeature`
3. Commit: `git commit -m "Add feature"`
4. Push: `git push origin feature/YourFeature`
5. Open a Pull Request 📬

## 🐣 Good First Issue Template

```
🐛 Bug or ✨ Feature Request

**Description**: _Short description of the issue or feature._

**Steps to Reproduce**:
1. ...
2. ...

**Expected Behavior**: _What you expected._

**Environment**:
- MailLogSentinel vX.Y.Z
- Python 3.x
- OS: e.g. Debian 11

**Additional Context**: _Screenshots, logs, etc._
```

## Roadmap
You can consult the [Roadmap.md](docs/Roadmap.md)  file for more information

## License
This project is licensed under the GNU GPL v3. See [LICENSE](LICENSE) for details.

## Support
> [!TIP]
> As a free software enthusiast, I have devoted a large part of my life to using, promoting, and defending free and open source culture in all its forms. I develop these tools as a hobby, at my own pace, but I couldn’t accomplish anything without the extraordinary OSS ecosystem that inspires me every day.
> 
> To support the community, **30% of every donation** will be transparently redistributed to other open source projects. You can track the progress of these contributions and the breakdown of your support in the Wiki section of this repository, via a monthly financial report.
 > 
> Thank you for your trust and support! :sparkling_heart: 

> [!IMPORTANT]
> I chose [Liberapay](https://liberapay.com/) for several reasons:
>
> - Non-profit association based in France :clap:
> - Funding of donation-related fees through user donations ^^
> - Association publishing its source code on [GitHub](https://github.com/liberapay/liberapay.com) under the [CC0](https://fr.wikipedia.org/wiki/Licence_CC0) license :heart_eyes:
> - Ability for donors to make secret, private, or public donations :ghost:
> - Opportunity for everyone to contribute to the life of the association and/or the platform :construction_worker:
> 
> <noscript><a href="https://liberapay.com/Zoide/donate"><img alt="Donate using Liberapay" src="https://liberapay.com/assets/widgets/donate.svg"></a></noscript>

