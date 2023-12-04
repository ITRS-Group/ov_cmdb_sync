#!/usr/bin/env python3

import pytest

from ov_cmdb_sync import servicenow, opsview

EXAMPLE_SNOW_ASSET = {
    "attested_date": "",
    "skip_sync": "false",
    "operational_status": "1",
    "most_frequent_user": "",
    "sys_updated_on": "2023-10-10 23:21:22",
    "attestation_score": "",
    "discovery_source": "",
    "first_discovered": "",
    "sys_updated_by": "system",
    "due_in": "",
    "sys_created_on": "2005-05-24 21:07:43",
    "sys_domain": {
        "link": "https://dev85142.service-now.com/api/now/table/sys_user_group/global",
        "value": "global",
    },
    "install_date": "2022-11-24 08:00:00",
    "gl_account": "",
    "invoice_number": "",
    "sys_created_by": "glide.maint",
    "warranty_expiration": "",
    "asset_tag": "P1000082",
    "hardware_substatus": "",
    "fqdn": "",
    "change_control": "",
    "internet_facing": "false",
    "owned_by": "",
    "checked_out": "",
    "sys_domain_path": "/",
    "business_unit": "",
    "delivery_date": "",
    "maintenance_schedule": "",
    "hardware_status": "",
    "install_status": "1",
    "cost_center": "",
    "attested_by": "",
    "supported_by": "",
    "dns_domain": "",
    "name": "San Diego Gateway",
    "assigned": "2023-04-05 07:00:00",
    "life_cycle_stage": "",
    "purchase_date": "",
    "subcategory": "",
    "default_gateway": "",
    "short_description": "",
    "assignment_group": "",
    "managed_by": {
        "link": "https://dev85142.service-now.com/api/now/table/sys_user/d2826bf03710200044e0bfc8bcbe5dc9",
        "value": "d2826bf03710200044e0bfc8bcbe5dc9",
    },
    "managed_by_group": "",
    "can_print": "false",
    "last_discovered": "",
    "sys_class_name": "cmdb_ci_netgear",
    "manufacturer": {
        "link": "https://dev85142.service-now.com/api/now/table/core_company/31e83f333723100044e0bfc8bcbe5da7",
        "value": "31e83f333723100044e0bfc8bcbe5da7",
    },
    "sys_id": "10884798c61122750108b095e21e4080",
    "po_number": "",
    "checked_in": "",
    "sys_class_path": "/!!/!2/!!",
    "life_cycle_stage_status": "",
    "mac_address": "",
    "vendor": {
        "link": "https://dev85142.service-now.com/api/now/table/core_company/3efe8c4c37423000158bbfc8bcbe5d7d",
        "value": "3efe8c4c37423000158bbfc8bcbe5d7d",
    },
    "company": {
        "link": "https://dev85142.service-now.com/api/now/table/core_company/e7c1f3d53790200044e0bfc8bcbe5deb",
        "value": "e7c1f3d53790200044e0bfc8bcbe5deb",
    },
    "justification": "",
    "model_number": "",
    "department": "",
    "assigned_to": "",
    "start_date": "",
    "comments": "",
    "cost": "1952",
    "attestation_status": "",
    "sys_mod_count": "21",
    "monitor": "false",
    "serial_number": "",
    "ip_address": "198.17.34.1",
    "model_id": {
        "link": "https://dev85142.service-now.com/api/now/table/cmdb_model/0faa6b3f3763100044e0bfc8bcbe5d95",
        "value": "0faa6b3f3763100044e0bfc8bcbe5d95",
    },
    "duplicate_of": "",
    "sys_tags": "",
    "cost_cc": "USD",
    "order_date": "",
    "schedule": "",
    "support_group": "",
    "environment": "",
    "due": "",
    "attested": "false",
    "correlation_id": "",
    "unverified": "false",
    "attributes": "OpsviewCollectorCluster=Cluster-01;OpsviewHashtags=Foo,Bar;OpsviewHostTemplates='Network - Base','Application - Tomcat'",
    "location": {
        "link": "https://dev85142.service-now.com/api/now/table/cmn_location/f48b246e0a0a0ba700a6e9b44c99f102",
        "value": "f48b246e0a0a0ba700a6e9b44c99f102",
    },
    "asset": {
        "link": "https://dev85142.service-now.com/api/now/table/alm_asset/03c1ba8837f3100044e0bfc8bcbe5da8",
        "value": "03c1ba8837f3100044e0bfc8bcbe5da8",
    },
    "category": "Do not migrate to asset",
    "fault_count": "0",
    "lease_id": "",
}

HOST_TEMPLATE_LIST = opsview.HostTemplateList()
HOST_TEMPLATE_LIST.append_object(opsview.HostTemplate(name="Network - Base"))
HOST_TEMPLATE_LIST.append_object(opsview.HostTemplate(name="Application - Tomcat"))

HASH_TAG_LIST = opsview.HashtagList()
HASH_TAG_LIST.append_object(opsview.Hashtag(name="Foo", all_servicechecks=True))
HASH_TAG_LIST.append_object(opsview.Hashtag(name="Bar", all_servicechecks=True))
HASH_TAG_LIST.append_object(
    opsview.Hashtag(name="dev85142_service_now_com", all_servicechecks=True)
)


def test_snow_host():
    host = servicenow.Host(EXAMPLE_SNOW_ASSET)

    assert host is not None
    assert host.name == "San Diego Gateway"
    assert host.ip == "198.17.34.1"
    assert host.hostgroup.name == "cmdb_ci_netgear"
    assert (
        host.hostgroup.matpath
        == "Opsview,ServiceNow,dev85142.service-now.com,cmdb_ci_netgear,"
    )
    assert host.hostattributes[0].name == "SERVICENOW_SYS_ID"
    assert host.hostattributes[0].value == "10884798c61122750108b095e21e4080"
    assert host.hostattributes[1].name == "SERVICENOW_ASSET_TAG"
    assert host.hostattributes[1].value == "P1000082"
    assert host.hostattributes[2].name == "SERVICENOW_INSTANCE"
    assert host.hostattributes[2].value == "dev85142.service-now.com"
    assert host.collector_cluster == "Cluster-01"
    assert host.hashtags.as_json() == HASH_TAG_LIST.as_json()
    assert host.host_templates.as_json() == HOST_TEMPLATE_LIST.as_json()


def test_snow_host_without_name():
    with pytest.raises(ValueError, match="name"):
        servicenow.Host(
            {
                "ip_address": "127.0.0.1",
                "sys_id": "1234567890",
                "asset_tag": "P1000082",
                "name": "",
                "sys_class_name": "cmdb_ci_netgear",
                "asset": {
                    "link": "dev85142.service-now.com/api/now/table/alm_asset/03c1ba8837f3100044e0bfc8bcbe5da8",
                    "value": "03c1ba8837f3100044e0bfc8bcbe5da8",
                },
                "attributes": "OpsviewCollectorCluster=Cluster-01;OpsviewHashtags=Foo,Bar",
            }
        )


def test_snow_host_without_ip():
    with pytest.raises(ValueError, match="ip_address"):
        servicenow.Host(
            {
                "ip_address": "",
                "sys_id": "1234567890",
                "asset_tag": "P1000082",
                "name": "test",
                "sys_class_name": "cmdb_ci_netgear",
                "asset": {
                    "link": "dev85142.service-now.com/api/now/table/alm_asset/03c1ba8837f3100044e0bfc8bcbe5da8",
                    "value": "03c1ba8837f3100044e0bfc8bcbe5da8",
                },
                "attributes": "OpsviewCollectorCluster=Cluster-01;OpsviewHashtags=Foo,Bar",
            }
        )


def test_snow_host_without_sys_id():
    # Check that the error message contains the name of the missing attribute.
    with pytest.raises(ValueError, match="sys_id"):
        servicenow.Host(
            {
                "ip_address": "127.0.0.1",
                "sys_id": "",
                "asset_tag": "P1000082",
                "name": "test",
                "sys_class_name": "cmdb_ci_netgear",
                "asset": {
                    "link": "https://dev85142.service-now.com/api/now/table/alm_asset/03c1ba8837f3100044e0bfc8bcbe5da8",
                    "value": "03c1ba8837f3100044e0bfc8bcbe5da8",
                },
                "attributes": "OpsviewCollectorCluster=Cluster-01;OpsviewHashtags=Foo,Bar",
            }
        )


def test_snow_host_without_asset():
    with pytest.raises(ValueError, match="asset"):
        servicenow.Host(
            {
                "ip_address": "127.0.0.1",
                "sys_id": "1234567890",
                "name": "test",
                "asset_tag": "P1000082",
                "sys_class_name": "cmdb_ci_netgear",
                "attributes": "OpsviewCollectorCluster=Cluster-01;OpsviewHashtags=Foo,Bar",
            }
        )


def test_snow_host_without_asset_tag():
    host = servicenow.Host(
        {
            "ip_address": "127.0.0.1",
            "sys_id": "1234567890",
            "name": "test",
            "sys_class_name": "cmdb_ci_netgear",
            "asset": {
                "link": "https://dev85142.service-now.com/api/now/table/alm_asset/03c1ba8837f3100044e0bfc8bcbe5da8",
                "value": "03c1ba8837f3100044e0bfc8bcbe5da8",
            },
            "attributes": "OpsviewCollectorCluster=Cluster-01;OpsviewHashtags=Foo,Bar",
        }
    )

    # The host should be created without an asset tag attribute.
    # Assert that there is no attribute named "SERVICENOW_ASSET_TAG".

    for attribute in host.hostattributes:
        assert attribute.name != "SERVICENOW_ASSET_TAG"


def test_instance_from_url():
    assert (
        servicenow.instance_from_url("https://dev85142.service-now.com")
        == "dev85142.service-now.com"
    )
    assert (
        servicenow.instance_from_url("http://dev85142.service-now.com/")
        == "dev85142.service-now.com"
    )
