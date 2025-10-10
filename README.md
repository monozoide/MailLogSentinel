# MailLogSentinel

<p align="center">
  <img src="img/banner-logo.png" alt="MailLogSentinel Banner" height="100">
</p>

<p align="center">
Lightweight Postfix authentication watchdog - Monitor failed SASL attempts, get daily email reports, export to database.
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


<!-- 🎃 Hacktoberfest 2025 — Badges compacts -->
<p align="center">
  <a href="https://hacktoberfest.com/"><img alt="Hacktoberfest 2025" src="https://img.shields.io/badge/Hacktoberfest-2025-FF8AE2?style=flat-square&logo=github"></a>
  <a href="https://github.com/monozoide/MailLogSentinel/issues?q=is%3Aopen+is%3Aissue+label%3A%22good+first+issue%22"><img alt="good first issue" src="https://img.shields.io/github/issues-search?query=repo%3Amonozoide%2FMailLogSentinel%20label%3A%22good%20first%20issue%22%20state%3Aopen&label=good%20first%20issue&style=flat-square"></a>
  <a href="https://github.com/monozoide/MailLogSentinel/issues?q=is%3Aopen+is%3Aissue+label%3A%22help+wanted%22"><img alt="help wanted" src="https://img.shields.io/github/issues-search?query=repo%3Amonozoide%2FMailLogSentinel%20label%3A%22help%20wanted%22%20state%3Aopen&label=help%20wanted&style=flat-square"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-3776AB?style=flat-square&logo=python&logoColor=white">
  <a href="https://github.com/monozoide/MailLogSentinel/releases"><img alt="release" src="https://img.shields.io/github/v/release/monozoide/MailLogSentinel?display_name=tag&sort=semver&style=flat-square"></a>
</p>

---

## Table of Contents

- [🎯 What it does](#-what-it-does)
- [📋 Prerequisites](#-prerequisites)
- [⚡ Quick Start](#-quick-start)
- [📊 Sample Output](#-sample-output)
- [💣 Basic Commands](#-basic-commands)
- [📚 Documentation](#-documentation)
- [🤝 Contributing](#-contributing)
- [⛑ Roadmap](#roadmap)
- [📄 License](#-license)
- [💖 Support](#-support)

---

## 🎯 What it does

**MailLogSentinel** monitors your **Postfix** server for authentication failures in real-time:
- 📊 **Tracks** failed login attempts with IP geolocation
- 📧 **Sends** daily email summaries with top offenders
- 💾 **Stores** events in CSV (+ optional SQL export)
- 🚀 **Runs** as lightweight systemd service

Perfect for small to medium mail servers wanting simple, effective monitoring without complex SIEM solutions.

## 📋 Prerequisites

- Linux with systemd and syslog
- Python 3.10+
- Postfix with SASL authentication
- `sudo` access for installation

## ⚡ Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/monozoide/MailLogSentinel.git
cd MailLogSentinel

# Install scripts and libraries
chmod +x bin/*.py && chmod +x lib/maillogsentinel/*.py
sudo cp bin/*.py /usr/local/bin/
sudo cp -r lib/maillogsentinel /usr/local/lib/
```

### 2. Run Interactive Setup

```bash
sudo python3 /usr/local/bin/maillogsentinel.py --setup --interactive
```

The setup wizard will:
- ✅ Configure paths and email settings
- ✅ Install systemd services
- ✅ Set up daily reporting schedule
- ✅ Initialize geolocation databases

### 3. Verify Installation

```bash
# Check service status
systemctl status maillogsentinel.service

# View live logs
journalctl -fu maillogsentinel.service
```

### 4. First time run
```bash
python3 /usr/local/bin/maillogsentinel.py
```bash


### 5. Test email report manually
```bash
python3 /usr/local/bin/maillogsentinel.py --report
```

## 📊 Sample Output

[Daily email report example](docs/dataset/sample_email_report_output.txt)

## 💣 Basic Commands

| Command | Description |
|---------|------------|
| `maillogsentinel --report` | Send email report now |
| `maillogsentinel --reset` | Archive data & restart monitoring |
| `maillogsentinel --version` | Show version |
| `maillogsentinel --help` | Show all options |

## 📚 Documentation

- **[Installation Guide](../../../wiki/Setup)** - Detailed setup instructions
- **[Configuration](../../../wiki/Configuration)** - All config options explained
- **[Advanced Features](../../../wiki/Features)** - SQL export, log anonymization, custom reports
- **[Troubleshooting](../../../wiki/Troubleshooting)** - Common issues and solutions
- **[API Documentation](../../../tree/main/docs/api)** - For developers

## 🤝 Contributing

Contributions welcome! Please check our [Contributing Guide](https://github.com/monozoide/MailLogSentinel/wiki/How-can-I-contribute%3F).

> [!CAUTION]
> The use of AI tools is permitted, provided that the contributor uses them in a reasonable manner. 

## Roadmap

You can follow the MailLogSentinel roadmap on the project page: [MailLogSentinel Roadmap](https://github.com/users/monozoide/projects/6)

## 📄 License

GNU GPL v3 - See [LICENSE](LICENSE) file.

## 💖 Support

If you find this useful, consider supporting development:

[![Liberapay receiving](https://img.shields.io/liberapay/receives/Zoide)](https://liberapay.com/Zoide/)

*30% of donations are redistributed to other open source projects.*

---

**Quick Links:** [Issues](https://github.com/monozoide/MailLogSentinel/issues) · [Wiki](https://github.com/monozoide/MailLogSentinel/wiki) · [Releases](https://github.com/monozoide/MailLogSentinel/releases)

---

> _We have no right to believe that freedom can be won without a struggle._

Che Guevara