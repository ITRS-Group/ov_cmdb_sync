#!/usr/bin/env python3

import os
import pytest
import random, string
from ov_cmdb_sync import opsview


def random_string(length=10):
    return "".join(random.choice(string.ascii_letters) for i in range(length))


def random_valid_ip():
    return ".".join(str(random.randint(0, 255)) for i in range(4))


def random_ov_host() -> opsview.Host:
    name = random_string()
    ip = random_valid_ip()
    hostgroup = opsview.HostGroup(random_string())
    hostattributes = opsview.VariableList(
        [
            opsview.Variable(random_string(), random_string()),
            opsview.Variable(random_string(), random_string()),
        ]
    )
    collector_cluster = random_string()
    hashtags = [random_string(), random_string(), random_string()]

    return opsview.Host(
        name, ip, hostgroup, hostattributes, collector_cluster, hashtags
    )


def random_ov_host_list(length=10) -> opsview.HostList:
    return opsview.HostList([random_ov_host() for i in range(length)])


@pytest.mark.skipif(os.getenv("OV_URL") is None, reason="OV_URL not set")
@pytest.mark.skipif(os.getenv("OV_USERNAME") is None, reason="OV_USERNAME not set")
@pytest.mark.skipif(os.getenv("OV_PASSWORD") is None, reason="OV_PASSWORD not set")
@pytest.mark.timeout(3)
def test_create_ov_session():
    session = opsview.Session(
        os.getenv("OV_URL"), os.getenv("OV_USERNAME"), os.getenv("OV_PASSWORD")
    )
    assert session.client is not None

    session.close()


def test_opsview_host():
    host = opsview.Host(
        "San_Diego_Gateway",
        "198.17.34.1",
        opsview.HostGroup(
            "cmdb_ci_netgear",
            parent=opsview.HostGroup(
                "dev85142.service-now.com",
                parent=opsview.HostGroup(
                    "ServiceNow", parent=opsview.HostGroup("Opsview")
                ),
            ),
        ),
        opsview.VariableList(
            [
                opsview.Variable(
                    "SERVICENOW_SYS_ID", "10884798c61122750108b095e21e4080"
                ),
                opsview.Variable("SERVICENOW_INSTANCE", "dev85142.service-now.com"),
                opsview.Variable("SERVICENOW_ASSET_TAG", "P1000082"),
            ]
        ),
        "Cluster01",
        ["foo", "bar"],
    )

    assert host is not None
    assert host.name == "San_Diego_Gateway"
    assert host.ip == "198.17.34.1"
    assert host.collector_cluster == "Cluster01"
    assert host.hashtags == ["foo", "bar"]
    assert host.hostgroup.name == "cmdb_ci_netgear"
    assert (
        host.hostgroup.matpath
        == "Opsview,ServiceNow,dev85142.service-now.com,cmdb_ci_netgear,"
    )
    assert host.hostattributes[0].name == "SERVICENOW_SYS_ID"
    assert host.hostattributes[0].value == "10884798c61122750108b095e21e4080"
    assert host.hostattributes[1].name == "SERVICENOW_INSTANCE"
    assert host.hostattributes[1].value == "dev85142.service-now.com"
    assert host.hostattributes[2].name == "SERVICENOW_ASSET_TAG"
    assert host.hostattributes[2].value == "P1000082"


def test_merge_opsview_hostlist_with_empty_list():
    hostlist = opsview.HostList()
    hostlist.merge(random_ov_host_list())

    assert len(hostlist) > 0

    hostlist.merge(opsview.HostList())

    assert len(hostlist) > 0


def test_merge_opsview_hostlist_with_nonempty_list():
    hostlist = random_ov_host_list()
    hostlist.merge(random_ov_host_list())

    assert len(hostlist) > 0


def test_merge_opsview_hostlist_with_duplicate_hosts():
    hostlist = random_ov_host_list(10)
    hostlist2 = hostlist.copy()

    hostlist.merge(hostlist2)

    assert len(hostlist) == 10


def test_merge_opsview_hostlist_with_single_duplicate_host():
    hostlist = random_ov_host_list(10)
    hostlist2 = opsview.HostList([hostlist[0]])
    hostlist3 = random_ov_host_list(10)

    hostlist.merge(hostlist2)
    hostlist.merge(hostlist3)

    assert len(hostlist) == 20


ROOT_HOSTGROUP = opsview.HostGroup(
    "Opsview", parent=None, ref="/rest/config/hostgroup/1"
)
CUSTOM_HOSTGROUP_1 = opsview.HostGroup("cmdb_ci_netgear")
CUSTOM_HOSTGROUP_2 = opsview.HostGroup("Routers", parent=CUSTOM_HOSTGROUP_1)
CUSTOM_HOSTGROUP_3 = opsview.HostGroup("Cisco", parent=CUSTOM_HOSTGROUP_2)


def test_hostgroup_matpaths():
    assert ROOT_HOSTGROUP.matpath == "Opsview,"
    assert CUSTOM_HOSTGROUP_1.matpath == "Opsview,cmdb_ci_netgear,"
    assert CUSTOM_HOSTGROUP_2.matpath == "Opsview,cmdb_ci_netgear,Routers,"
    assert CUSTOM_HOSTGROUP_3.matpath == "Opsview,cmdb_ci_netgear,Routers,Cisco,"


# TODO: Fix these tests once I've figured out exactly how the as_json() method
#       should work.


# def test_hostgroup_as_json():
#     assert ROOT_HOSTGROUP.as_json() == {
#         "name": "Opsview",
#         "parent": None,
#         "ref": "/rest/config/hostgroup/1",
#     }
#     assert CUSTOM_HOSTGROUP_1.as_json() == {
#         "name": "cmdb_ci_netgear",
#         "parent": {"name": "Opsview", "matpath": "Opsview,"},
#     }
#     assert CUSTOM_HOSTGROUP_2.as_json() == {
#         "name": "Routers",
#         "parent": {
#             "name": "cmdb_ci_netgear",
#             "matpath": "Opsview,cmdb_ci_netgear,",
#         },
#     }
#     assert CUSTOM_HOSTGROUP_3.as_json() == {
#         "name": "Cisco",
#         "parent": {
#             "name": "Routers",
#             "matpath": "Opsview,cmdb_ci_netgear,Routers,",
#         },
#     }


def test_variable_as_json():
    variable = opsview.Variable("SERVICENOW_SYS_ID", "10884798c61122750108b095e21e4080")

    assert variable.as_json() == {
        "name": "SERVICENOW_SYS_ID",
        "value": "10884798c61122750108b095e21e4080",
    }


def test_variable_with_value_larger_than_64_chars_raises_exception():
    with pytest.raises(ValueError, match="value"):
        opsview.Variable("SERVICENOW_SYS_ID", "1" * 65)


def test_new_hashtag():
    hashtag = opsview.Hashtag("foo", all_servicechecks=True)

    assert hashtag.name == "foo"
    assert hashtag.as_json() == {
        "all_hosts": "0",
        "all_servicechecks": "1",
        "calculate_hard_states": "0",
        "description": "Created by Opsview CMDB Sync",
        "enabled": "1",
        "exclude_handled": "0",
        "hosts": [],
        "id": None,
        "name": "foo",
        "public": "0",
        "ref": None,
        "roles": [],
        "servicechecks": [],
        "show_contextual_menus": "1",
        "style": None,
        "uncommitted": "0",
    }

    assert hashtag.as_json(shallow=True) == {
        "all_servicechecks": "1",
        "description": "Created by Opsview CMDB Sync",
        "enabled": "1",
        "name": "foo",
        "show_contextual_menus": "1",
    }

    assert hashtag.as_minimal_json() == {
        "name": "foo",
    }


def test_new_hostgroup():
    hostgroup1 = opsview.HostGroup("foo")
    hostgroup2 = opsview.HostGroup("bar", parent=hostgroup1)

    # Example from the Opsview API:
    # {'children': [{'name': '192.168.2.88 - ESXi',
    #                'ref': '/rest/config/hostgroup/5'},
    #               {'name': '192.168.2.88 - VMs',
    #                'ref': '/rest/config/hostgroup/6'}],
    #  'hosts': [],
    #  'id': '4',
    #  'is_leaf': '0',
    #  'matpath': 'Opsview,Automonitor,VMware vSphere Express Scan,',
    #  'name': 'VMware vSphere Express Scan',
    #  'parent': {'matpath': 'Opsview,Automonitor,',
    #             'name': 'Automonitor',
    #             'ref': '/rest/config/hostgroup/3'},
    #  'ref': '/rest/config/hostgroup/4',
    #  'uncommitted': '0'}"""

    assert hostgroup1.name == "foo"
    assert hostgroup1.parent.name == "Opsview"

    assert hostgroup2.name == "bar"
    assert hostgroup2.parent.name == "foo"

    assert hostgroup1.as_json() == {
        "children": [],
        "hosts": [],
        "id": None,
        "is_leaf": "0",
        "matpath": "Opsview,foo,",
        "name": "foo",
        "parent": {
            "matpath": "Opsview,",
            "name": "Opsview",
            "ref": "/rest/config/hostgroup/1",
        },
        "ref": None,
        "uncommitted": "0",
    }

    assert hostgroup2.as_json() == {
        "children": [],
        "hosts": [],
        "id": None,
        "is_leaf": "0",
        "matpath": "Opsview,foo,bar,",
        "name": "bar",
        "parent": {
            "matpath": "Opsview,foo,",
            "name": "foo",
        },
        "ref": None,
        "uncommitted": "0",
    }

    assert hostgroup1.as_json(shallow=True) == {
        "name": "foo",
        "parent": {
            "name": "Opsview",
            "matpath": "Opsview,",
            "ref": "/rest/config/hostgroup/1",
        },
        "matpath": "Opsview,foo,",
    }

    assert hostgroup2.as_json(shallow=True) == {
        "name": "bar",
        "parent": {"name": "foo", "matpath": "Opsview,foo,"},
        "matpath": "Opsview,foo,bar,",
    }


def test_new_host_check_command():
    host_check_command = opsview.HostCheckCommand(name="foo")

    assert host_check_command.name == "foo"
    assert host_check_command.as_json() == {
        "args": "",
        "hosts": [],
        "id": None,
        "name": "foo",
        "plugin": None,
        "priority": None,
        "ref": None,
        "uncommitted": "0",
    }

    assert host_check_command.as_json(shallow=True) == {
        "name": "foo",
    }


def test_new_service_check():
    service_check_command = opsview.ServiceCheck(name="foo")

    assert service_check_command.name == "foo"
    assert service_check_command.as_json() == {
        "alert_from_failure": "1",
        "args": "",
        "attribute": None,
        "calculate_rate": None,
        "cascaded_from": None,
        "check_attempts": "3",
        "check_freshness": "1",
        "check_interval": "300",
        "check_period": None,
        "checktype": None,
        "critical_comparison": None,
        "critical_value": None,
        "dependencies": [],
        "description": "",
        "event_handler": "",
        "event_handler_always_exec": "0",
        "flap_detection_enabled": "1",
        "hosts": [],
        "hosttemplates": [],
        "id": None,
        "invertresults": "0",
        "keywords": [],
        "label": None,
        "markdown_filter": "0",
        "name": "foo",
        "notification_options": "w,c,r,u,f",
        "notification_period": None,
        "oid": None,
        "plugin": None,
        "ref": None,
        "retry_check_interval": "60",
        "sensitive_arguments": "1",
        "servicegroup": None,
        "snmptraprules": [],
        "stale_state": "3",
        "stale_text": "UNKNOWN: Service results are stale",
        "stale_threshold_seconds": "1800",
        "stalking": None,
        "uncommitted": "0",
        "volatile": "0",
        "warning_comparison": None,
        "warning_value": None,
    }

    assert service_check_command.as_json(shallow=True) == {
        "alert_from_failure": "1",
        "name": "foo",
        "check_attempts": "3",
        "check_freshness": "1",
        "check_interval": "300",
        "flap_detection_enabled": "1",
        "notification_options": "w,c,r,u,f",
        "retry_check_interval": "60",
        "sensitive_arguments": "1",
        "stale_state": "3",
        "stale_text": "UNKNOWN: Service results are stale",
        "stale_threshold_seconds": "1800",
    }

    assert service_check_command.as_minimal_json() == {
        "name": "foo",
    }


def test_new_hosttemplate():
    host_template = opsview.HostTemplate(
        name="foo",
        servicechecks=opsview.ServiceCheckList(
            opsview.ServiceCheck(
                name="bar", plugin=opsview.Plugin(name="check_baz"), args="blah"
            )
        ),
    )

    assert host_template.name == "foo"
    assert host_template.as_json() == {
        "description": "",
        "has_icon": "0",
        "hosts": [],
        "id": None,
        "managementurls": [],
        "name": "foo",
        "ref": None,
        "servicechecks": [
            {
                "alert_from_failure": "1",
                "args": "blah",
                "check_attempts": "3",
                "check_freshness": "1",
                "check_interval": "300",
                "flap_detection_enabled": "1",
                "name": "bar",
                "notification_options": "w,c,r,u,f",
                "plugin": {
                    "name": "check_baz",
                },
                "retry_check_interval": "60",
                "sensitive_arguments": "1",
                "stale_state": "3",
                "stale_text": "UNKNOWN: Service results are stale",
                "stale_threshold_seconds": "1800",
            }
        ],
        "uncommitted": "0",
    }

    assert host_template.as_json(shallow=True) == {
        "name": "foo",
        "servicechecks": [
            {
                "alert_from_failure": "1",
                "args": "blah",
                "check_attempts": "3",
                "check_freshness": "1",
                "check_interval": "300",
                "flap_detection_enabled": "1",
                "name": "bar",
                "notification_options": "w,c,r,u,f",
                "retry_check_interval": "60",
                "sensitive_arguments": "1",
                "stale_state": "3",
                "stale_text": "UNKNOWN: Service results are stale",
                "stale_threshold_seconds": "1800",
                "plugin": {"name": "check_baz"},
            }
        ],
    }

    assert host_template.as_minimal_json() == {
        "name": "foo",
    }


def test_new_plugin():
    plugin = opsview.Plugin(name="check_foo")

    assert plugin.name == "check_foo"
    assert plugin.as_json() == {
        "envvars": "",
        "hostcheckcommands": [],
        "name": "check_foo",
        "servicechecks": [],
        "uncommitted": "0",
    }

    assert plugin.as_json(shallow=True) == {
        "name": "check_foo",
    }

    assert plugin.as_minimal_json() == {
        "name": "check_foo",
    }


def test_new_servicegroup():
    servicegroup = opsview.ServiceGroup(
        name="foo",
        servicechecks=[
            opsview.ServiceCheck(name="bar"),
            opsview.ServiceCheck(name="baz"),
        ],
    )

    assert servicegroup.name == "foo"

    assert servicegroup.as_json() == {
        "id": None,
        "name": "foo",
        "ref": None,
        "servicechecks": [
            {
                "alert_from_failure": "1",
                "check_attempts": "3",
                "check_freshness": "1",
                "check_interval": "300",
                "flap_detection_enabled": "1",
                "name": "bar",
                "notification_options": "w,c,r,u,f",
                "retry_check_interval": "60",
                "sensitive_arguments": "1",
                "stale_state": "3",
                "stale_text": "UNKNOWN: Service results are stale",
                "stale_threshold_seconds": "1800",
            },
            {
                "alert_from_failure": "1",
                "check_attempts": "3",
                "check_freshness": "1",
                "check_interval": "300",
                "flap_detection_enabled": "1",
                "name": "baz",
                "notification_options": "w,c,r,u,f",
                "retry_check_interval": "60",
                "sensitive_arguments": "1",
                "stale_state": "3",
                "stale_text": "UNKNOWN: Service results are stale",
                "stale_threshold_seconds": "1800",
            },
        ],
        "uncommitted": "0",
    }

    assert servicegroup.as_json(shallow=True) == {
        "name": "foo",
        "servicechecks": [
            {
                "alert_from_failure": "1",
                "check_attempts": "3",
                "check_freshness": "1",
                "check_interval": "300",
                "flap_detection_enabled": "1",
                "name": "bar",
                "notification_options": "w,c,r,u,f",
                "retry_check_interval": "60",
                "sensitive_arguments": "1",
                "stale_state": "3",
                "stale_text": "UNKNOWN: Service results are stale",
                "stale_threshold_seconds": "1800",
            },
            {
                "alert_from_failure": "1",
                "check_attempts": "3",
                "check_freshness": "1",
                "check_interval": "300",
                "flap_detection_enabled": "1",
                "name": "baz",
                "notification_options": "w,c,r,u,f",
                "retry_check_interval": "60",
                "sensitive_arguments": "1",
                "stale_state": "3",
                "stale_text": "UNKNOWN: Service results are stale",
                "stale_threshold_seconds": "1800",
            },
        ],
    }

    assert servicegroup.as_minimal_json() == {
        "name": "foo",
    }


def test_new_timeperiod():
    """
    Example from the Opsview API (abbreviated)):
    {'alias': '24 Hours A Day, 7 Days A Week',
     'friday': '00:00-24:00',
     'host_check_periods': [{'name': 'Amer-Finance-Environment',
                           'ref': '/rest/config/host/10'},
                          {'name': 'ubuntu-jammy-reference-host',
                           'ref': '/rest/config/host/30'},
                          {'name': 'VMWGW-NYC', 'ref': '/rest/config/host/21'}],
     'host_notification_periods': [{'name': 'Amer-Finance-Environment',
                                  'ref': '/rest/config/host/10'},
                                 {'name': 'VMWGW-NYC',
                                  'ref': '/rest/config/host/21'}],
     'id': '1',
     'monday': '00:00-24:00',
     'name': '24x7',
     'object_locked': '1',
     'ref': '/rest/config/timeperiod/1',
     'saturday': '00:00-24:00',
     'servicecheck_check_periods': [],
     'servicecheck_notification_periods': [],
     'sunday': '00:00-24:00',
     'thursday': '00:00-24:00',
     'tuesday': '00:00-24:00',
     'uncommitted': '0',
     'wednesday': '00:00-24:00',
     'zone': {'name': 'SYSTEM', 'ref': '/rest/config/timezone/1'}}"""

    timeperiod = opsview.TimePeriod(
        name="24x7",
        alias="24 Hours A Day, 7 Days A Week",
        sunday="00:00-24:00",
        monday="00:00-24:00",
        tuesday="00:00-24:00",
        wednesday="00:00-24:00",
        thursday="00:00-24:00",
        friday="00:00-24:00",
        saturday="00:00-24:00",
    )

    assert timeperiod.name == "24x7"
    assert timeperiod.as_json() == {
        "alias": "24 Hours A Day, 7 Days A Week",
        "friday": "00:00-24:00",
        "host_check_periods": [],
        "host_notification_periods": [],
        "id": None,
        "monday": "00:00-24:00",
        "name": "24x7",
        "object_locked": "1",
        "ref": None,
        "saturday": "00:00-24:00",
        "servicecheck_check_periods": [],
        "servicecheck_notification_periods": [],
        "sunday": "00:00-24:00",
        "thursday": "00:00-24:00",
        "tuesday": "00:00-24:00",
        "uncommitted": "0",
        "wednesday": "00:00-24:00",
        "zone": {"name": "SYSTEM", "ref": "/rest/config/timezone/1"},
    }


def test_new_bsm_component():
    """An Opsview BSMComponent.

    Example from the Opsview API:
    {'has_icon': '0',
     'host_template': {'name': 'Network - Base',
                       'ref': '/rest/config/hosttemplate/117'},
     'host_template_id': '117',
     'hosts': [{'name': 'GeneosGatewayLab01', 'ref': '/rest/config/host/341'},
               {'name': 'IP-Switch-1', 'ref': '/rest/config/host/338'},
               {'name': 'lnux100', 'ref': '/rest/config/host/339'}],
     'id': '1',
     'name': 'Component 1',
     'quorum_pct': '66.67',
     'ref': '/rest/config/bsmcomponent/1',
     'uncommitted': '0'}"""

    component = opsview.BSMComponent(
        name="Component 1",
        host_template=opsview.HostTemplate(name="Network - Base"),
        hosts=[
            opsview.Host(
                name="GeneosGatewayLab01",
                ip="127.0.0.1",
                hostgroup=opsview.HostGroup("Opsview"),
                hostattributes=None,
                collector_cluster=None,
                hashtags=None,
            ),
            opsview.Host(
                name="GeneosGatewayLab02",
                ip="127.0.0.1",
                hostgroup=opsview.HostGroup("Opsview"),
                hostattributes=None,
                collector_cluster=None,
                hashtags=None,
            ),
            opsview.Host(
                name="GeneosGatewayLab03",
                ip="127.0.0.1",
                hostgroup=opsview.HostGroup("Opsview"),
                hostattributes=None,
                collector_cluster=None,
                hashtags=None,
            ),
        ],
        quorum_pct="66.67",
    )

    assert component.name == "Component 1"
    assert component.as_json() == {
        "has_icon": "0",
        "host_template": {"name": "Network - Base"},
        "host_template_id": None,
        "hosts": [
            {
                "name": "GeneosGatewayLab01",
            },
            {
                "name": "GeneosGatewayLab02",
            },
            {
                "name": "GeneosGatewayLab03",
            },
        ],
        "id": None,
        "name": "Component 1",
        "quorum_pct": "66.67",
        "ref": None,
        "uncommitted": "0",
    }

    assert component.as_json(shallow=True) == {
        "name": "Component 1",
        "host_template": {"name": "Network - Base"},
        "hosts": [
            {
                "name": "GeneosGatewayLab01",
            },
            {
                "name": "GeneosGatewayLab02",
            },
            {
                "name": "GeneosGatewayLab03",
            },
        ],
        "quorum_pct": "66.67",
    }

    assert component.as_minimal_json() == {
        "name": "Component 1",
    }

    with pytest.raises(ValueError, match="is invalid for"):
        opsview.BSMComponent(
            quorum_pct="35.00",
            name="foo",
            hosts=[
                opsview.Host(
                    name="GeneosGatewayLab01",
                    ip="127.0.0.1",
                    hostgroup=opsview.HostGroup("Opsview"),
                    hostattributes=None,
                    collector_cluster=None,
                    hashtags=None,
                ),
                opsview.Host(
                    name="GeneosGatewayLab02",
                    ip="127.0.0.1",
                    hostgroup=opsview.HostGroup("Opsview"),
                    hostattributes=None,
                    collector_cluster=None,
                    hashtags=None,
                ),
                opsview.Host(
                    name="GeneosGatewayLab03",
                    ip="127.0.0.1",
                    hostgroup=opsview.HostGroup("Opsview"),
                    hostattributes=None,
                    collector_cluster=None,
                    hashtags=None,
                ),
            ],
        )


def test_valid_quorum_pct():
    pct1 = 0.0
    pct2 = 0.5
    pct3 = 1.0
    pct4 = 33.33
    pct5 = 66.67
    pct6 = 99.00
    pct7 = 100.00
    pct8 = 20.00

    assert opsview.valid_quorum_pct(pct1, 3) is True
    assert opsview.valid_quorum_pct(pct2, 3) is False
    assert opsview.valid_quorum_pct(pct3, 3) is False
    assert opsview.valid_quorum_pct(pct4, 3) is True
    assert opsview.valid_quorum_pct(pct5, 3) is True
    assert opsview.valid_quorum_pct(pct6, 3) is False
    assert opsview.valid_quorum_pct(pct7, 3) is True
    assert opsview.valid_quorum_pct(pct8, 3) is False

    assert opsview.valid_quorum_pct(pct1, 5) is True
    assert opsview.valid_quorum_pct(pct2, 5) is False
    assert opsview.valid_quorum_pct(pct3, 5) is False
    assert opsview.valid_quorum_pct(pct4, 5) is False
    assert opsview.valid_quorum_pct(pct5, 5) is False
    assert opsview.valid_quorum_pct(pct6, 5) is False
    assert opsview.valid_quorum_pct(pct7, 5) is True
    assert opsview.valid_quorum_pct(pct8, 5) is True

    assert opsview.valid_quorum_pct(pct1, 10) is True
    assert opsview.valid_quorum_pct(pct2, 10) is False
    assert opsview.valid_quorum_pct(pct3, 10) is False
    assert opsview.valid_quorum_pct(pct4, 10) is False
    assert opsview.valid_quorum_pct(pct5, 10) is False
    assert opsview.valid_quorum_pct(pct6, 10) is False
    assert opsview.valid_quorum_pct(pct7, 10) is True
    assert opsview.valid_quorum_pct(pct8, 10) is True


# def valid_quorum_pct(quorum_pct: float, number_of_hosts: int):
#     """Check if a quorum_pct value is valid for a given number of hosts."""
#     possible_quorum_decimals = []

#     for numerator in range(1, number_of_hosts + 1):
#         for denominator in range(1, number_of_hosts + 1):
#             if (
#                 f"{numerator / denominator * 100:.2f}" not in possible_quorum_decimals
#                 and (numerator / denominator <= 1)
#             ):
#                 possible_quorum_decimals.append(f"{numerator / denominator * 100:.2f}")

#     print(possible_quorum_decimals)

#     if quorum_pct < 0 or quorum_pct > 100:
#         return False

#     if f"{quorum_pct:.2f}" not in possible_quorum_decimals:
#         return False

#     return True
