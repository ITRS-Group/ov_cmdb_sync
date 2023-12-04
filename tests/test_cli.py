#!/usr/bin/env python3

import os
import pytest
import subprocess

# Read ServiceNow and Opsview credentials from environment variables:
SNOW_URL = os.environ.get('SNOW_URL')
SNOW_USERNAME = os.environ.get('SNOW_USERNAME')
SNOW_PASSWORD = os.environ.get('SNOW_PASSWORD')
OV_URL = os.environ.get('OV_URL')
OV_USERNAME = os.environ.get('OV_USERNAME')
OV_PASSWORD = os.environ.get('OV_PASSWORD')

# Don't run any tests if the environment variables are not set. But still test
# for all environment variables to print all that are missing in a single
# error message.
missing_env_vars = []
if SNOW_URL is None:
    missing_env_vars.append('SNOW_URL')
if SNOW_USERNAME is None:
    missing_env_vars.append('SNOW_USERNAME')
if SNOW_PASSWORD is None:
    missing_env_vars.append('SNOW_PASSWORD')
if OV_URL is None:
    missing_env_vars.append('OV_URL')
if OV_USERNAME is None:
    missing_env_vars.append('OV_USERNAME')
if OV_PASSWORD is None:
    missing_env_vars.append('OV_PASSWORD')

if len(missing_env_vars) > 0:
    pytest.exit('Missing environment variables: ' + ', '.join(missing_env_vars))


# Run the main script using pipenv:

PIPENV_CMD = ["pipenv", "run", "python", "ov_cmdb_sync/main.py"]

def run_cmd_with_args(*args):
    """Run the main script with the given arguments."""
    cmd = PIPENV_CMD + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result


def run_cmd_with_env_and_args(*args):
    """Run the main script with the given arguments and environment variables."""
    result = run_cmd_with_args("--snow-url", SNOW_URL,
                               "--snow-username", SNOW_USERNAME,
                               "--snow-password", SNOW_PASSWORD,
                               "--ov-url", OV_URL,
                               "--ov-username", OV_USERNAME,
                               "--ov-password", OV_PASSWORD,
                               *args)

    return result


def test_cmd_fails_with_no_args():
    """Test that the command fails with no arguments."""
    result = run_cmd_with_args()

    assert result.returncode == 2
    assert 'usage: ov_cmdb_sync' in result.stderr


def test_pytest_help():
    """Test that the command shows the help message."""
    result = run_cmd_with_args("--help")

    assert result.returncode == 0
    assert 'usage: ov_cmdb_sync' in result.stdout


# def test_pytest_debug():
#     result = run_cmd_with_env_and_args("--debug")

#     assert 'Debug output enabled' in result.stdout


# def test_pytest_snow_full():
#     result = run_cmd_with_env_and_args()

#     assert result.returncode == 0
