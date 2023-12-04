#!/usr/bin/env python3
"""This module contains common utility functions."""

import argparse
import logging
import logging.handlers
import sys
import os
import socket
from datetime import datetime

import requests


def mixed_to_upper_underscore(mixed_str):
    """Convert a mixed case string to upper case with underscores."""
    words = []
    start = 0

    for i in range(1, len(mixed_str)):
        if mixed_str[i].isupper() and mixed_str[i - 1].islower():
            words.append(mixed_str[start:i])
            start = i
        elif mixed_str[i] == "_":
            words.append(mixed_str[start:i])
            start = i + 1

    words.append(mixed_str[start:])
    return "_".join(words).upper()


def snake_to_pascal(snake_str):
    """Convert a snake case string to Pascal case."""
    return "".join(word.capitalize() for word in snake_str.split("_"))


class CustomFileFormatter(logging.Formatter):
    """Custom logging formatter for the log file."""

    hostname = socket.gethostname()
    script_name = "ov_cmdb_sync"
    process_id = os.getpid()

    def format(self, record):
        current_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        formatted_message = (
            f"{self.hostname} {self.script_name}[{self.process_id}]: "
            f"[{current_time}] [{record.name}] [{record.levelname}] "
            f"{record.getMessage()}"
        )
        return formatted_message


class ColoredFormatter(logging.Formatter):
    """Custom logging formatter for the terminal that adds color."""

    COLORS = {
        "WARNING": "\033[93m",
        "INFO": "\033[94m",
        "DEBUG": "\033[92m",
        "CRITICAL": "\033[91m",
        "ERROR": "\033[91m",
    }

    def format(self, record):
        color = self.COLORS.get(record.levelname, "\033[0m")
        record.msg = f"{color}{record.msg}\033[0m"
        return super().format(record)


def setup_logging(debug=False, logfile=None):
    """Setup logging to a file and the terminal."""
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Setting the File Handler up first is important, because otherwise the
    # record.msg will be overwritten by the ColoredFormatter and the log file
    # will contain ANSI escape sequences, which is not what we want.

    # File Handler
    if logfile:
        file_handler = logging.FileHandler(logfile)
        file_handler.setFormatter(CustomFileFormatter())
        logger.addHandler(file_handler)

    # Terminal Handler with Colored Output
    terminal_handler = logging.StreamHandler(sys.stdout)
    terminal_handler.setFormatter(ColoredFormatter("%(message)s"))
    logger.addHandler(terminal_handler)


def is_debug():
    """Return True if debug output is enabled."""
    return logging.getLogger().getEffectiveLevel() == logging.DEBUG


def with_https(url):
    """Add https:// to the URL if it is not already there."""
    if not url.startswith("https://"):
        return "https://" + url

    return url


def without_https(url):
    """Remove https:// from the URL if it is there."""
    if url.startswith("https://"):
        return url[8:]

    return url


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Sync Opsview with ServiceNow", prog="ov_cmdb_sync"
    )
    parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable debug output"
    )
    parser.add_argument("-n", "--dry-run", action="store_true", help="Dry run")
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Don't stop if there are pending changes in Opsview",
    )
    parser.add_argument(
        "-l",
        "--logfile",
        help="Logfile to write to",
        default="/var/log/opsview/opsview.log",
    )
    parser.add_argument(
        "--purge-snow-instance",
        help="Purge Salesforce hosts that come from the ServiceNow CMDB",
    )
    parser.add_argument("--ov-url", help="Opsview URL", required=True)
    parser.add_argument("--ov-username", help="Opsview username", required=True)
    parser.add_argument("--ov-password", help="Opsview password", required=True)

    parser.add_argument(
        "--snow-url",
        help="ServiceNow URL",
        required="--purge-snow-instance" not in sys.argv,
    )
    parser.add_argument(
        "--snow-username",
        help="ServiceNow username",
        required="--purge-snow-instance" not in sys.argv,
    )
    parser.add_argument(
        "--snow-password",
        help="ServiceNow password",
        required="--purge-snow-instance" not in sys.argv,
    )

    return parser.parse_args()


def test_connection(url):
    """Test the connection to a URL."""
    logging.debug("Testing connection to %s", url)
    response = requests.get(url=with_https(url))

    if response.status_code != 200:
        logging.error("Failed to connect to %s", url)
        logging.error(response.json())
        sys.exit(1)
