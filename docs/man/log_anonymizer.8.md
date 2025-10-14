# NAME

log_anonymizer - anonymize sensitive information in log files

# SYNOPSIS

```shell
log_anonymizer.py [-h] -i INPUT_FILE -o OUTPUT_FILE [-t TEMP_DIR] [--config CONFIG] [--log-level LEVEL] [--script-log-file SCRIPT_LOG_FILE]
```

# DESCRIPTION

**`log_anonymizer`** is a tool designed to anonymize sensitive information contained in email log files. It processes input log files and generates anonymized output files by applying configurable anonymization rules to protect private data while maintaining the utility of the logs for debugging and analysis purposes.

The tool supports customizable anonymization rules through configuration files and provides comprehensive logging capabilities to track the anonymization process.

# OPTIONS

**`-h`**, **`--help`**
Display help message and exit.

**`-i`**, **`-input-file`** **`INPUT_FILE`**
Specify the input log file to be anonymized. This option is mandatory.

**`-o`**, **`--output-file`** **`OUTPUT_FILE`**
Specify the output file where the anonymized log will be written. This option is mandatory.

**`-t`**, **`--temp-dir`** **`TEMP_DIR`**
Specify an optional temporary directory to use during processing. If not provided, the system default temporary directory will be used.

**`--config`** **`CONFIG`**
Specify a configuration file containing custom anonymization rules. This allows fine-tuning of the anonymization behavior to match specific requirements.

**`--log-level`** **`LEVEL`**
Set the logging level for the script execution. Valid values are: **`DEBUG`**, **`INFO`**, **`WARNING`**, **`ERROR`**, and **`CRITICAL`**. This controls the verbosity of diagnostic output during execution.

**`--script-log-file`** **`SCRIPT_LOG_FILE`**
Specify an optional path to a file where script execution logs will be saved. If not provided, logs are output to standard error only.

# EXAMPLES

Basic anonymization of a log file:

```shell
python3 log_anonymizer.py -i /var/log/mail.log -o /tmp/mail_anonymized.log
```

Anonymization with custom configuration and debug logging:

```shell
python3 log_anonymizer.py -i /var/log/mail.log -o /tmp/safe.log --config /etc/anonymizer/rules.conf --log-level DEBUG --script-log-file /var/log/anonymizer_execution.log
```

Using a custom temporary directory:

```shell
python3 log_anonymizer.py -i input.log -o output.log -t /tmp
```

# FILES

**`/etc/anonymizer/rules.conf`**
Default location for system-wide anonymization rules configuration (if applicable).

**`config/anonymizer/config`**
User-specific configuration file (if applicable).

# EXIT STATUS

**`0`**
Successful completion.

**`1`**
General error occurred during execution.

**`2`**
Invalid command-line arguments or missing required options.

# NOTES

The script requires Python3 to run. Ensure that all required Python3 dependencies are installed before execution.

Large log files may require significant temporary disk space during processing. Use the **-t** option to specify a temporary directory with adequate space if needed.

The quality of anonymization depends on the rules defined in the configuration file. Review and test your configuration thoroughly before processing sensitive production logs.

# SECURITY CONSIDERATIONS

While this tool anonymizes data according to configured rules, it is the administrator's responsibility to:

-   Verify that all sensitive data types are properly covered by anonymization rules
-   Securely handle both input and output files
-   Properly dispose of temporary files
-   Review anonymized output before sharing with untrusted parties

# BUGS

Report bugs at: https://github.com/monozoide/MailLogSentinel/issues

# AUTHOR

MailLogSentinel Project

# COPYRIGHT

This utility is part of the MailLogSentinel project.

# SEE ALSO

**`maillogsentinel`**(8), **`sed`**(1), **`awk`**(1), **`grep`**(1), **`logrotate`**(8)