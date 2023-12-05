#!/usr/bin/env pipenv
import pytest

from ov_cmdb_sync import util


def test_instance_from_url():
    assert (
        util.snow_instance_from_url("https://dev85142.service-now.com")
        == "dev85142.service-now.com"
    )
    assert (
        util.snow_instance_from_url("http://dev85142.service-now.com/")
        == "dev85142.service-now.com"
    )
