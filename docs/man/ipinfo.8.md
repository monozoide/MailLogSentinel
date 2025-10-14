# NAME

ipinfo - IP address information lookup utility

# SYNOPSIS

```shell
ipinfo.py [-h] [--update] [--country-db-path PATH] [--asn-db-path PATH] [--country-db-url URL] [--asn-db-url URL] [--data-dir DIR] [--config FILE] [ip_address]
```

# DESCRIPTION

**`ipinfo.py`** is a command-line utility for looking up geographical and network information about IP addresses. It uses local databases for country and ASN (Autonomous System Number) information, providing fast offline lookups without requiring external API calls.

The utility can download and update its databases from public IP location repositories, making it suitable for integration into logging and monitoring systems like MailLogSentinel.

# OPTIONS

**`ip_address`**
IP address to look up (e.g., 8.8.8.8). If not provided, the utility displays usage information.

**`-h`**, **`--help`**
Display help message and exit.

**`--update`**
Download or update both IP databases (Country and ASN). This fetches the latest versions from the configured URLs and stores them in the appropriate locations.

**`--country-db-path`** `PATH`
Path to store or load the country database. Default: `ipinfo/country_aside.csv`

**`--asn-db-path`** `PATH`
Path to store or load the ASN database. Default: `ipinfo/ip2asn-lite.csv`

**`--country-db-url`** `URL`
URL for downloading the country database. Default: https://raw.githubusercontent.com/sapics/ip-location-db/main/asn-country/asn-country-ipv4-num.csv

**`--asn-db-url`** `URL`
URL for downloading the ASN database. Default: https://raw.githubusercontent.com/sapics/ip-location-db/refs/heads/main/asn/asn-ipv4-num.csv

**`--data-dir`** `DIR`
Directory to store or load all IP database files. If specified, this overrides the default directory component of **`--country-db-path` and **`--asn-db-path` unless they are specified as absolute paths.

**--config`** `FILE`
Path to maillogsentinel.conf configuration file. When specified, database paths and URLs can be read from the configuration file instead of using command-line options.

# FILES

`ipinfo/country_aside.csv`
Default location for the country database.

`ipinfo/ip2asn-lite.csv`
Default location for the ASN database.

`maillogsentinel.conf`
Optional configuration file for setting database paths and URLs.

# EXAMPLES

Look up information for a specific IP address:

```shell
ipinfo.py 8.8.8.8
```

Update both databases to their latest versions:

```shell
ipinfo.py --update
```

Look up an IP using a custom data directory:

```shell
ipinfo.py --data-dir /var/lib/ipinfo 1.1.1.1
```

Use a custom configuration file:

```shell
ipinfo.py --config /etc/maillogsentinel.conf 8.8.4.4
```

Specify custom database paths:

```shell
ipinfo.py --country-db-path /opt/db/country.csv --asn-db-path /opt/db/asn.csv 192.168.1.1
```

# EXIT STATUS

**`0`**
Successful execution.

**`1`**
General error (invalid IP address, database not found, network error during update).

# SEE ALSO

**`whois`**(1), **`dig`**(1), **`host`**(1), **`geoiplookup`**(1)

# BUGS

Report bugs at: https://github.com/monozoide/MailLogSentinel/issues

# AUTHOR

MailLogSentinel Project

# COPYRIGHT

This utility is part of the MailLogSentinel project.

Database sources: IP location databases by sapics https://github.com/sapics/ip-location-db