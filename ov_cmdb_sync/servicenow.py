#!/usr/bin/env python3
"""This module contains functions to interact with ServiceNow."""

import logging
import re
from urllib.parse import urlsplit
from pprint import pformat

from pysnow import QueryBuilder
from tqdm import tqdm

from ov_cmdb_sync import opsview, util


def assert_values(asset, *values, require_all=True, debug=False) -> bool:
    """Assert that the asset has all or any of the values, based on either_or."""
    missing_values = [value for value in values if not asset.get(value)]

    def log_or_raise(message):
        if debug:
            logging.debug(message)
        else:
            raise ValueError(message)

    if not require_all and not any(asset.get(value) for value in values):
        value_str = ", ".join(missing_values)
        value_label = "value is" if len(missing_values) == 1 else "values are"
        log_or_raise(
            f"The following {value_label} missing for asset "
            f"with name {asset['name']}: {value_str}"
        )
    elif require_all and not all(asset.get(value) for value in values):
        value_str = ", ".join(missing_values)
        value_label = "value is" if len(missing_values) == 1 else "values are"
        log_or_raise(
            f"The following {value_label} missing for asset "
            f"with name {asset['name']}: {value_str}"
        )

    return True


def get_snow_services(client):
    """Get all Services from ServiceNow."""
    logging.debug("Getting all Services from ServiceNow")
    query = QueryBuilder().field("name").is_not_empty()

    services_resource = client.resource(api_path="/table/cmdb_ci_service")
    response = services_resource.get(query=query, stream=True)
    number_of_services = 0
    services = []

    for service in tqdm(response.all(), desc="Getting ServiceNow Services"):
        number_of_services += 1
        logging.debug("Found service: %s", service.get("name"))
        services.append(service)

    logging.debug("Found %s services", number_of_services)

    return services


def get_hosts(client):
    """Get all hosts from ServiceNow."""
    logging.debug("Getting all hosts from ServiceNow")
    query = QueryBuilder().field("attributes").contains("OpsviewCollectorCluster")

    hosts_resource = client.resource(api_path="/table/cmdb_ci")
    response = hosts_resource.get(query=query, stream=True)
    number_of_units = 0
    hosts = []
    no_ip_or_fqdn = []

    for unit in tqdm(
        response.all(),
        desc="Processing ServiceNow Hosts",
        total=response.count,
        unit="host",
    ):
        # logging.debug("Found unit: %s", unit.get("name"))
        if unit.get("ip_address") or unit.get("fqdn"):
            hosts.append(unit)
            number_of_units += 1
        else:
            no_ip_or_fqdn.append(unit.get("name"))
            # logging.warning(
            #     "Host %s has no IP address or FQDN. Skipping.", unit.get("name")
            # )

    logging.debug("Found %s units", number_of_units)
    if no_ip_or_fqdn:
        for unit in no_ip_or_fqdn:
            logging.warning("Skipped host '%s' as it has no IP address or FQDN.", unit)
    if util.is_debug():
        logging.debug("Units:")
        logging.debug(pformat(hosts))

    return hosts


class Host:
    """A host in ServiceNow."""

    def __init__(self, asset):
        assert_values(asset, "fqdn", "ip_address", require_all=False)
        assert_values(asset, "name", "sys_id", "sys_class_name", require_all=True)
        assert_values(asset, "asset", "sys_domain", require_all=True, debug=True)

        self.name = asset["name"]
        self.ip = asset["ip_address"] if asset.get("ip_address") else asset["fqdn"]
        self.hostattributes = self.__hostattributes_from_asset(asset)
        self.hostgroup = self.__hostgroup_from_asset(asset)
        self.__attributes = self.__parse_attributes(asset)
        self.collector_cluster = self.__collector_cluster_from_attributes()
        self.hashtags: opsview.HashtagList = self.__hashtags_from_attributes()
        self.host_templates = self.__host_templates_from_attributes()
        self.__with_instance_hashtag(asset)

    def __hostgroup_from_asset(self, asset):
        instance = self.__instance_from_asset(asset)
        root_hostgroup = opsview.HostGroup("Opsview", parent=None)
        snow_parent = opsview.HostGroup("ServiceNow", parent=root_hostgroup)
        instance_parent = opsview.HostGroup(instance, parent=snow_parent)
        return opsview.HostGroup(asset["sys_class_name"], parent=instance_parent)

    def __parse_attributes(self, asset) -> dict:
        attributes = asset["attributes"]
        logging.debug("Attributes: %s", attributes)
        regex = re.compile(r"([^;=]+)=([^;=]+(?:,[^;=]+)*)")
        attributes_dict = {}
        for match in regex.finditer(attributes):
            key = match.group(1)
            value = match.group(2)
            # Remove surrounding quotes from the value.
            if "," in value:
                value = [v.strip("'\"") for v in value.split(",")]
            else:
                value = [value.strip("'\"")]
            attributes_dict[key] = value

        logging.debug("Attributes dict: %s", attributes_dict)
        return attributes_dict

    def __collector_cluster_from_attributes(self) -> str:
        if not self.__attributes.get("OpsviewCollectorCluster"):
            raise ValueError(
                "The 'OpsviewCollectorCluster' attribute is missing or empty."
            )

        if len(self.__attributes["OpsviewCollectorCluster"]) > 1:
            logging.warning(
                "Host {self.name} has more than one OpsviewCollectorCluster."
                + " Using the first one."
            )

        return self.__attributes["OpsviewCollectorCluster"][0]

    def __hashtags_from_attributes(self) -> opsview.HashtagList:
        hashtags = opsview.HashtagList()

        if self.__attributes.get("OpsviewHashtags"):
            for name in self.__attributes["OpsviewHashtags"]:
                hashtag = opsview.Hashtag(
                    name=name, all_servicechecks=True, enabled=True
                )
                hashtags.append_object(hashtag)

        return hashtags

    def __host_templates_from_attributes(self) -> opsview.HostTemplateList:
        templates = opsview.HostTemplateList()

        if self.__attributes.get("OpsviewHostTemplates"):
            for name in self.__attributes["OpsviewHostTemplates"]:
                template = opsview.HostTemplate(name)
                templates.append_object(template)

        return templates

    def __instance_from_link(self, link):
        return urlsplit(link).netloc

    def __instance_from_asset(self, asset):
        if asset.get("asset") and asset["asset"].get("link"):
            return self.__instance_from_link(asset["asset"]["link"])
        if asset.get("sys_domain") and asset["sys_domain"].get("link"):
            return self.__instance_from_link(asset["sys_domain"]["link"])

        raise ValueError(
            f"Could not determine the instance for asset with name {asset['name']}."
        )

    def __with_instance_hashtag(self, asset):
        instance = self.__instance_from_asset(asset)

        # Replace all non-alphanumeric characters with underscores
        cleaned_instance = re.sub(r"[^a-zA-Z0-9]", "_", instance)

        if cleaned_instance == "":
            raise ValueError("After processing, the instance name is empty.")

        self.hashtags.append_object(
            opsview.Hashtag(name=cleaned_instance, all_servicechecks=True, enabled=True)
        )

    def __hostattributes_from_asset(self, asset):
        hostattributes = [
            opsview.Variable("SERVICENOW_SYS_ID", asset["sys_id"]),
        ]

        if asset.get("asset_tag"):
            hostattributes.append(
                opsview.Variable("SERVICENOW_ASSET_TAG", asset["asset_tag"])
            )

        instance = self.__instance_from_asset(asset)
        hostattributes.append(opsview.Variable("SERVICENOW_INSTANCE", instance))

        return hostattributes

    def as_opsview_host(self):
        """Return an Opsview Host object."""
        logging.debug("Generating Opsview Host from ServiceNow Asset: %s", self.name)
        return opsview.Host(
            name=self.name.replace(" ", "_"),
            ip=self.ip,
            hostgroup=self.hostgroup,
            hostattributes=self.hostattributes,
            collector_cluster=self.collector_cluster,
            hashtags=self.hashtags,
            host_id=None,
            hosttemplates=self.host_templates,
        )


def opsview_host_list(snow_client, ov_client, instance_url) -> opsview.HostList:
    """Return a list of Opsview Hosts from ServiceNow."""
    import pprint

    logging.debug("Generating Opsview Host List from ServiceNow CMDB")

    snow_assets = get_hosts(snow_client)
    ov_hosts = opsview.HostList(
        [Host(asset).as_opsview_host() for asset in snow_assets]
    )

    logging.info(
        "Valid Opsview hosts found in ServiceNow instance '%s': %s",
        instance_url,
        len(ov_hosts),
    )

    return ov_hosts
