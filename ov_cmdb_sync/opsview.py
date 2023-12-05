#!/usr/bin/env python3
"""This module contains functions to interact with Opsview."""

import logging

from pprint import pformat
from urllib.parse import urljoin
from typing import List, ForwardRef

import re
import sys

from requests.exceptions import RequestException

import requests

from ov_cmdb_sync import util


class Session(requests.Session):
    """A session with an Opsview instance."""

    def __init__(self, url, username, password):
        self.url = util.with_https(url)
        self.username = username
        self.password = password

        self.auth_response = requests.post(
            urljoin(self.url, "/rest/login"),
            json={"username": self.username, "password": self.password},
        )

        if self.auth_response.status_code != 200:
            logging.error("Error: '%s'", self.auth_response.text)
            return

        self.token = self.auth_response.json()["token"]

        self.client = requests.Session()
        self.client.headers.update(
            {
                "X-Opsview-Username": self.username,
                "X-Opsview-Token": self.token,
                "Content-Type": "application/json",
            }
        )

    def handle_pending_changes(self, force):
        """Check if there are pending changes in Opsview and act accordingly."""
        if self.changes_to_apply() and not force:
            logging.error("There are pending changes in Opsview. Aborting.")
            sys.exit(1)

        if self.changes_to_apply() and force:
            logging.warning(
                "There are pending changes in Opsview, but we are ignoring them"
                + " because of the --force option."
            )
            logging.warning("Pending changes will be included when applying changes.")

    def populate_known_entities(
        self,
        entity_set_attribute,
        entity_list_attribute,
        entity_key,
        get_entities_function,
    ):
        """Generic method to populate sets and lists of known entities."""
        setattr(self, entity_set_attribute, set())
        setattr(self, entity_list_attribute, [])

        entities = get_entities_function(self)

        for entity in entities:
            if entity[entity_key] not in getattr(self, entity_set_attribute):
                getattr(self, entity_set_attribute).add(entity[entity_key])
                getattr(self, entity_list_attribute).append(entity)

                logging.debug(f"Known {entity_key}s:")
                logging.debug(pformat(getattr(self, entity_list_attribute)))

    def populate_known_bsm_services(self):
        """Populate the set of known bsm service entities."""
        logging.debug("Getting all BSM services from Opsview")
        self.populate_known_entities(
            "known_bsm_service_names", "known_bsm_services", "name", get_bsm_services
        )

    def populate_known_bsm_components(self):
        """Populate the set of known bsm component entities."""
        logging.debug("Getting all BSM components from Opsview")
        self.populate_known_entities(
            "known_bsm_component_names",
            "known_bsm_components",
            "name",
            get_bsm_components,
        )

    def populate_known_hashtags(self):
        """Populate the set of known hashtag entities."""
        logging.debug("Getting all hashtags from Opsview")
        self.populate_known_entities(
            "known_hashtag_names", "known_hashtags", "name", get_hashtags
        )

    def populate_known_host_check_commands(self):
        """Populate the set of known host check command entities."""
        logging.debug("Getting all host check commands from Opsview")
        self.populate_known_entities(
            "known_host_check_command_names",
            "known_host_check_commands",
            "name",
            get_host_check_commands,
        )

    def populate_known_hosticons(self):
        """Populate the set of known hosticon entities."""
        logging.debug("Getting all hosticons from Opsview")
        self.populate_known_entities(
            "known_hosticon_names", "known_hosticons", "name", get_hosticons
        )

    def populate_known_hosts(self):
        """Populate the set of known host entities."""
        logging.debug("Getting all hosts from Opsview")
        self.populate_known_entities(
            "known_host_names", "known_hosts", "name", get_hosts
        )

    def populate_known_hostgroups(self):
        """Populate the set of known hostgroup entities."""
        logging.debug("Getting all hostgroups from Opsview")
        self.populate_known_entities(
            "known_hostgroup_matpaths", "known_hostgroups", "matpath", get_hostgroups
        )

    def populate_known_hosttemplates(self):
        """Populate the set of known hosttemplate entities."""
        logging.debug("Getting all hosttemplates from Opsview")
        self.populate_known_entities(
            "known_hosttemplate_names",
            "known_hosttemplates",
            "name",
            get_hosttemplates,
        )

    def populate_known_servicechecks(self):
        """Populate the set of known servicecheck entities."""
        logging.debug("Getting all servicechecks from Opsview")
        self.populate_known_entities(
            "known_servicecheck_names",
            "known_servicechecks",
            "name",
            get_servicechecks,
        )

    def populate_known_servicegroups(self):
        """Populate the set of known servicegroup entities."""
        logging.debug("Getting all servicegroups from Opsview")
        self.populate_known_entities(
            "known_servicegroup_names",
            "known_servicegroups",
            "name",
            get_servicegroups,
        )

    def populate_known_timeperiods(self):
        """Populate the set of known timeperiod entities."""
        logging.debug("Getting all timeperiods from Opsview")
        self.populate_known_entities(
            "known_timeperiod_names", "known_timeperiods", "name", get_timeperiods
        )

    def populate_known_variables(self):
        """Populate the set of known variable entities."""
        logging.debug("Getting all variables from Opsview")
        self.populate_known_entities(
            "known_variable_names", "known_variables", "name", get_variables
        )

    def get(self, url):
        """Send a GET request to Opsview."""
        return self.client.get(urljoin(self.url, url))

    def post(self, url, json):
        """Send a POST request to Opsview."""
        return self.client.post(urljoin(self.url, url), json=json)

    def delete(self, url):
        """Send a DELETE request to Opsview."""
        return self.client.delete(urljoin(self.url, url))

    def close(self):
        """Log out and close the session."""
        # Also logout from Opsview to invalidate the token
        logout_response = self.client.post(urljoin(self.url, "/rest/logout"))

        if logout_response.status_code != 200:
            logging.error("Error: '%s'", logout_response.text)
            return

        self.client.close()

    def changes_to_apply(self) -> bool:
        """Check if there are pending changes in Opsview."""
        response = self.get("/rest/reload")

        if response.status_code != 200:
            error_msg = f"Error checking for pending changes: '{response.text}'"
            logging.error(error_msg)
            raise RequestException(error_msg)

        status = response.json()["configuration_status"]

        if status == "uptodate":
            return False

        if status == "pending":
            return True

        error_msg = f"Unexpected response from Opsview: '{status}'"
        logging.error(error_msg)
        raise RequestException(error_msg)

    def apply_changes(self):
        """Apply pending changes in Opsview."""
        if not self.changes_to_apply():
            return None

        logging.info("Applying changes in Opsview")
        response = self.post("/rest/reload", json={})

        if response.status_code != 200:
            error_msg = f"Error applying changes: '{response.text}'"
            logging.error(error_msg)
            raise RequestException(error_msg)

        return response.json()


class Object:
    """An Opsview Object."""

    name: str
    url: str

    def as_minimal_json(self):
        """Return the object as a minimal JSON object."""
        return {"name": self.name}

    def as_json(self, shallow=False):
        """Return the object as a JSON object."""
        d = self.__dict__.copy()

        if shallow:
            d = {key: value for key, value in d.items() if value and value != "0"}

        for key, value in d.items():
            if isinstance(value, Object):
                d[key] = value.as_json(shallow=shallow)
            if isinstance(value, ObjectList):
                d[key] = value.as_json(shallow=shallow)["list"]
            elif isinstance(value, int):
                d[key] = str(value)
            elif isinstance(value, float):
                d[key] = str(value)

        return d

    def delete(self, session: Session):
        """Delete the object in Opsview."""
        logging.info("Deleting %s '%s' in Opsview", type(self).__name__, self.name)

        # DELETE /rest/config/{object_type}/{id} The API only support deleting
        # one object at a time, except for hosts. We need to get the ID of the
        # object first if it doesn't exist. Using urljoin() here would result in
        # a URL like https://opsview.example.com/rest/config/attribute?id=1 if
        # the object type is Variable.

        if not self.exists(session):
            logging.debug(
                "%s '%s' does not exist in Opsview", type(self).__name__, self.name
            )
            return None

        self.refresh_id(session)
        response = session.delete(urljoin(self.url, self.id))

        self.handle_response(response)

        return response

    def exists(self, session: Session) -> bool:
        """Check if the object exists in Opsview."""
        return object_exists(session, self.url, self.name)

    def handle_response(self, response):
        """Handle the response from Opsview."""
        if response.status_code != 200:
            logging.error("Failed to create, delete, or change object in Opsview")
            logging.error(response.text)
            raise RequestException("Opsview API request failed")

    def refresh_id(self, session: Session):
        """Refresh the ID of the object from Opsview."""
        self.id = get_object_id(session, self)


class ObjectList:
    """A list of Opsview Objects."""

    objects: List[Object]
    url: str

    def __init__(self, objects=None):
        """Initialize the list of objects."""
        if objects is None:
            self.objects = []
        elif isinstance(objects, type(self)):
            self.objects = objects.objects.copy()
        elif not isinstance(objects, list) and isinstance(objects, Object):
            self.objects = [objects]
        elif not all(isinstance(obj, type(objects[0])) for obj in objects):
            raise TypeError(
                f"Cannot create list of objects of different types: "
                f"{[type(obj).__name__ for obj in objects]}"
            )
        else:
            self.objects = objects

    def __iter__(self):
        """Return an iterator over the objects in the list."""
        return iter(self.objects)

    def __getitem__(self, index):
        """Return the object at the given index."""
        return self.objects[index]

    def __len__(self):
        """Return the number of objects in the list."""
        return len(self.objects)

    def append_object(self, obj):
        """Append an object to the list."""
        self.objects.append(obj)

    def as_json(self, shallow=False):
        return {"list": [obj.as_json(shallow=shallow) for obj in self.objects]}

    def create(self, session: Session):
        """Create the objects in Opsview."""
        return self.create_objects(session, self.url)

    def copy(self):
        """Return a copy of the list of objects."""
        return type(self)(self.objects.copy())

    def create_objects(self, session: Session, object_url):
        """Create the objects in Opsview."""
        if not self.process(session):
            return None

        # If the method is run on a HostList, first create the HostGroups and
        # Variables, needed, then create the hosts.

        if isinstance(self, HostList):
            hostgroups = HostGroupList()
            variables = VariableList()

            for host in self.objects:
                hostgroups.append_object(host.hostgroup)
                for variable in host.hostattributes:
                    variables.append_object(Variable(variable.name, ""))

            hostgroups.create(session)
            variables.create(session)

        data = self.as_json(shallow=True)

        if isinstance(self, HostList):
            logging.info("Creating %s hosts in Opsview", len(self.objects))
            for host in self.objects:
                logging.info("Creating host '%s'", host.name)
        elif isinstance(self, HostGroupList):
            logging.info("Creating %s hostgroups in Opsview", len(self.objects))
            for hostgroup in self.objects:
                logging.info("Creating hostgroup '%s'", hostgroup.name)
        elif isinstance(self, VariableList):
            logging.info("Creating %s variables in Opsview", len(self.objects))
            for variable in self.objects:
                logging.info("Creating variable '%s'", variable.name)
        else:
            logging.info(
                "Creating %s objects of type '%s' in Opsview",
                len(self.objects),
                type(self).__name__,
            )
            for obj in self.objects:
                logging.info("Creating object '%s'", obj.name)

        if util.is_debug():
            logging.debug("Sending data to Opsview:")
            logging.debug(pformat(data))

        response = session.post(object_url, data)
        self.handle_response(response)

        return response

    def log_objects(self, message):
        """Log a message and a list of objects."""
        if util.is_debug():
            logging.debug(message)
            for obj in self.objects:
                logging.debug(pformat(obj))

    def handle_response(self, response):
        """Handle the response from Opsview."""
        if response.status_code != 200:
            logging.error("Failed to create, delete, or change objects in Opsview")
            logging.error(response.json())
            raise RequestException("Opsview API request failed")

    def __merge_single(self, other):
        """Merge a single list of objects into this list."""
        if not isinstance(other, type(self)):
            error_msg = (
                f"Cannot merge object of type {type(self).__name__} "
                f"with object of type {type(other).__name__}"
            )
            raise TypeError(error_msg)

        seen_names = set()
        joined_list = []

        # Objects in the other list take precedence.
        for obj in other.objects:
            seen_names.add(obj.name)
            joined_list.append(obj)

        # Append objects from self that are not in other.
        for obj in self.objects:
            if obj.name not in seen_names:
                joined_list.append(obj)

        self.objects = joined_list

    def merge(self, *other):
        """Merge one or more lists of objects into this list."""
        for other_list in other:
            if not isinstance(other_list, type(self)):
                raise TypeError(
                    f"Cannot merge object of type {type(self).__name__} "
                    f"with object of type {type(other).__name__}"
                )

            self.__merge_single(other_list)

    def process(self, session: Session):
        """Process the list of objects before creating them in Opsview."""
        logging.debug(
            "Processing objects of type '%s' for creation.", type(self).__name__
        )

        if isinstance(self, HostGroupList):
            matpaths = set(hostgroup.matpath for hostgroup in self.objects)
            self.add_hostgroups_from_matpaths(*matpaths)
            self.sort_by_depth()
            for hostgroup in self.objects:
                hostgroup.lookup_ref(session)

        if isinstance(self, HostList):
            for host in self.objects:
                host.hostgroup.lookup_ref(session)

        self.without_duplicates()
        self.without_existing(session)

        if not self.objects:
            if isinstance(self, HostList):
                logging.info("No hosts to create after processing.")
            elif isinstance(self, HostGroupList):
                logging.info("No hostgroups to create after processing.")
            elif isinstance(self, VariableList):
                logging.info("No variables to create after processing.")
            else:
                logging.info(
                    "No objects of type '%s' to create after processing",
                    type(self).__name__,
                )

            return False

        return True

    def remove(self, obj):
        """Remove an object from the list."""
        self.objects.remove(obj)

    def without_duplicates(self):
        """Remove duplicate objects from the list based on names."""
        unique_names = set(obj.name for obj in self.objects)

        if len(unique_names) == len(self.objects):
            logging.debug("No duplicate objects found")
            return

        logging.debug("Found duplicate objects")

        unique_objects = []

        for obj in self.objects:
            if obj.name in unique_names:
                unique_objects.append(obj)
                unique_names.remove(obj.name)
            else:
                logging.debug("Removing duplicate object '%s'", obj.name)

        self.objects = unique_objects

    def without_existing(self, session: Session):
        """Remove objects that already exist in Opsview."""
        self.objects = [obj for obj in self.objects if not obj.exists(session)]


class BSMComponent(Object):
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

    url = "/rest/config/bsmcomponent"

    def __init__(
        self,
        name: str,
        has_icon=False,
        host_template=None,
        host_template_id=None,
        hosts=None,
        id=None,
        quorum_pct=None,
        ref=None,
        uncommitted=False,
    ):
        if not name:
            raise ValueError("The 'name' attribute is missing or empty.")

        self.name = name
        self.has_icon = "1" if has_icon else "0"

        if isinstance(host_template, HostTemplate):
            self.host_template = host_template
        elif isinstance(host_template, str):
            self.host_template = HostTemplate(host_template)
        elif host_template is None:
            self.host_template = None
        else:
            raise TypeError(
                f"Invalid type for 'host_template' attribute: "
                f"'{type(host_template).__name__}'"
            )

        self.host_template_id = host_template_id
        self.hosts = HostList(hosts)
        self.id = id
        self.ref = ref
        self.uncommitted = "1" if uncommitted else "0"

        self.__validate_and_set_quorum_pct(quorum_pct)

    def __validate_and_set_quorum_pct(self, quorum_pct):
        """Validate the quorum_pct attribute."""

        if quorum_pct is None:
            self.quorum_pct = None
            return

        # Convert string to float, if necessary.
        if isinstance(quorum_pct, str):
            try:
                quorum_pct = float(quorum_pct)
            except ValueError:
                raise ValueError(
                    f"Invalid string format for 'quorum_pct': '{quorum_pct}'"
                )

            # Validate float type.
            if not isinstance(quorum_pct, float):
                raise TypeError(
                    f"Invalid type for 'quorum_pct' attribute: '{type(quorum_pct).__name__}'"
                )

            # Validate quorum percentage value.
            if not valid_quorum_pct(quorum_pct, len(self.hosts)):
                raise ValueError(
                    f"The quorum_pct value '{quorum_pct}' is invalid for "
                    f"{len(self.hosts)} hosts."
                )

            # Set the quorum percentage with formatted string.
            self.quorum_pct = f"{quorum_pct:.2f}"


def valid_quorum_pct(quorum_pct: float, number_of_hosts: int):
    """Check if a quorum_pct value is valid for a given number of hosts."""
    if quorum_pct < 0 or quorum_pct > 100:
        return False

    for n in range(0, number_of_hosts + 1):
        ratio_pct = (n / number_of_hosts) * 100
        # Using a tolerance for floating-point comparison
        if (
            abs(quorum_pct - ratio_pct) < 0.01
        ):  # Adjusted the tolerance to 0.01 for percentage precision
            return True

    return False


class BSMService(Object):
    """An Opsview BSMService.

    Example from the Opsview API:
    {'components': [{'name': 'Component 1',
                      'ref': '/rest/config/businesscomponent/1'},
                     {'name': 'Component 2',
                      'ref': '/rest/config/businesscomponent/2'}],
     'id': '1',
     'name': 'BSM 1',
     'ref': '/rest/config/bsmservice/1',
     'uncommitted': '0'}"""

    url = "/rest/config/bsmservice"

    def __init__(
        self, name: str, components=None, id=None, ref=None, uncommitted=False
    ):
        if not name:
            raise ValueError("The 'name' attribute is missing or empty.")

        self.name = name
        self.components = BSMComponentList(components)
        self.id = id
        self.ref = ref
        self.uncommitted = "1" if uncommitted else "0"


class Hashtag(Object):
    """An Opsview Hashtag.

    Example from the Opsview API:
    {'all_hosts': '0',
     'all_servicechecks': '0',
     'calculate_hard_states': '0',
     'description': '',
     'enabled': '0',
     'exclude_handled': '0',
     'hosts': [{'name': 'opsview', 'ref': '/rest/config/host/1'}],
     'id': '6',
     'name': 'opsview-distributed',
     'public': '0',
     'ref': '/rest/config/keyword/6',
     'roles': [],
     'servicechecks': [],
     'show_contextual_menus': '1',
     'style': None,
     'uncommitted': '0'}"""

    url = "/rest/config/keyword"

    def __init__(
        self,
        name: str,
        all_hosts=False,
        all_servicechecks=False,
        calculate_hard_states=False,
        description=None,
        enabled=True,
        exclude_handled=False,
        hosts=None,
        id=None,
        public=False,
        ref=None,
        roles=None,
        servicechecks=None,
        show_contextual_menus=True,
        style=None,
        uncommitted=False,
    ):
        if not name:
            raise ValueError("The 'name' attribute is missing or empty.")

        # The name of the hashtag must be ASCII-only.
        if name != name.encode("ascii", "ignore").decode("ascii"):
            raise ValueError(
                f"The name '{name}' contains non-ASCII characters. "
                + "Hashtag names must be ASCII-only."
            )

        # The name of the hashtag may only contain alphanumeric characters,
        # underscores, and hyphens.
        name_regex = re.compile(r"^[a-zA-Z0-9_-]+$")

        if not name_regex.match(name):
            raise ValueError(
                f"The name '{name}' contains invalid characters. "
                + "Hashtag names may only contain alphanumeric characters, "
                + "underscores, and hyphens."
            )

        self.name = name

        self.all_hosts = "1" if all_hosts else "0"
        self.all_servicechecks = "1" if all_servicechecks else "0"
        self.calculate_hard_states = "1" if calculate_hard_states else "0"
        self.description = (
            "Created by Opsview CMDB Sync" if description is None else description
        )
        self.enabled = "1" if enabled else "0"
        self.exclude_handled = "1" if exclude_handled else "0"
        self.hosts = HostList(hosts)
        self.id = id
        self.public = "1" if public else "0"
        self.ref = ref
        self.roles = [] if roles is None else roles
        self.servicechecks = ServiceCheckList(servicechecks)
        self.show_contextual_menus = "1" if show_contextual_menus else "0"
        self.style = style
        self.uncommitted = "1" if uncommitted else "0"


class HostCheckCommand(Object):
    """An Opsview CheckCommand.

    Example from the Opsview API:
    {'args': '-H $HOSTADDRESS$ -t 3 -w 500.0,80% -c 1000.0,100%',
    'hosts': [{'name': 'Amer-Finance-Environment', 'ref': '/rest/config/host/10'}],
    'id': '15',
    'name': 'ping',
    'plugin': {'name': 'check_icmp', 'ref': '/rest/config/plugin/check_icmp'},
    'priority': '2',
    'ref': '/rest/config/hostcheckcommand/15',
    'uncommitted': '0'}"""

    url = "/rest/config/hostcheckcommand"

    def __init__(
        self,
        name: str,
        args=None,
        hosts=None,
        id=None,
        plugin=None,
        priority=None,
        ref=None,
        uncommitted=False,
    ):
        if not name:
            raise ValueError("The 'name' attribute is missing or empty.")

        self.name = name

        if isinstance(plugin, Plugin):
            self.plugin = plugin
        elif isinstance(plugin, str):
            self.plugin = Plugin(plugin)
        elif plugin is None:
            self.plugin = None
        else:
            raise TypeError(
                f"Invalid type for 'plugin' attribute: '{type(plugin).__name__}'"
            )

        self.args = args if args is not None else ""
        self.hosts = HostList(hosts)
        self.id = id
        self.priority = priority
        self.ref = ref
        self.uncommitted = "1" if uncommitted else "0"


class HostIcon(Object):
    """An Opsview HostIcon.

    Example from the Opsview API:
    {'img_prefix': '/static/images/logos/linux',
     'name': 'LOGO - Linux Penguin',
     'ref': '/rest/config/hosticons/LOGO%20-%20Linux%20Penguin'}"""


class HostTemplate(Object):
    """An Opsview HostTemplate.

    Example from the Opsview API (abbreviated):
    {'description': 'Monitor an ESXi Resource Pool (supports vMotion)',
     'has_icon': '0',
     'hosts': [{'name': 'localhost.ny.us.itrs', 'ref': '/rest/config/host/3'}],
     'id': '152',
     'managementurls': [],
     'name': 'OS - VMware vSphere ESXi Resource Pool',
     'ref': '/rest/config/hosttemplate/152',
     'servicechecks': [{'event_handler': None,
                        'exception': None,
                        'name': 'vSphere - Resource Pool - CPU Used',
                        'ref': '/rest/config/servicecheck/838',
                        'timed_exception': None}]"""

    url = "/rest/config/hosttemplate"

    def __init__(
        self,
        name: str,
        description=None,
        has_icon=False,
        hosts=None,
        id=None,
        managementurls=None,
        ref=None,
        servicechecks=None,
        uncommitted=False,
    ):
        if not name:
            raise ValueError("The 'name' attribute is missing or empty.")

        self.name = name
        self.description = description if description is not None else ""
        self.has_icon = "1" if has_icon else "0"
        self.hosts = HostList(hosts)
        self.id = id
        self.managementurls = [] if managementurls is None else managementurls
        self.ref = ref
        self.servicechecks = ServiceCheckList(servicechecks)
        self.uncommitted = "1" if uncommitted else "0"


class Host(Object):
    """An Opsview Host.

    Example from the Opsview API:
    {'alias': '',
     'business_components': [{'name': 'Component 1',
                              'ref': '/rest/config/businesscomponent/1'}], # This should actually be '/rest/config/bsmcomponent/1'
     'check_attempts': '2',
     'check_command': {'name': 'ping', 'ref': '/rest/config/hostcheckcommand/15'},
     'check_interval': '300',
     'check_period': {'name': '24x7', 'ref': '/rest/config/timeperiod/1'},
     'enable_snmp': '0',
     'event_handler': '',
     'event_handler_always_exec': '0',
     'flap_detection_enabled': '1',
     'hostattributes': [{'arg1': None,
                         'arg2': None,
                         'arg3': None,
                         'arg4': None,
                         'id': '728',
                         'name': 'SERVICENOW_INSTANCE',
                         'value': 'dev85142.service-now.com'},
                        {'arg1': None,
                         'arg2': None,
                         'arg3': None,
                         'arg4': None,
                         'id': '727',
                         'name': 'SERVICENOW_SYS_ID',
                         'value': 'e1542e842ff67110dd4dad6df699b607'}],
     'hostgroup': {'name': 'cmdb_ci_server', 'ref': '/rest/config/hostgroup/343'},
     'hosttemplates': [{'name': 'Network - Base',
                        'ref': '/rest/config/hosttemplate/117'}],
     'icon': {'name': 'LOGO - Opsview',
              'path': '/static/images/logos/opsview.png'},
     'id': '341',
     'ip': '192.168.2.85',
     'keywords': [{'name': 'dev85142_service_now_com',
                   'ref': '/rest/config/keyword/102'},
                  {'name': 'Geneos', 'ref': '/rest/config/keyword/105'}],
     'last_updated': '1701592975',
     'monitored_by': {'name': 'collectors-ny',
                      'ref': '/rest/config/monitoringcluster/2'},
     'name': 'GeneosGatewayLab01',
     'notification_options': None,
     'notification_period': {'name': '24x7', 'ref': '/rest/config/timeperiod/1'},
     'other_addresses': '',
     'parents': [],
     'rancid_autoenable': '0',
     'rancid_connection_type': 'ssh',
     'rancid_username': None,
     'rancid_vendor': None,
     'ref': '/rest/config/host/341',
     'retry_check_interval': '60',
     'servicechecks': [],
     'snmp_extended_throughput_data': '0',
     'snmp_max_msg_size': '0',
     'snmp_port': '161',
     'snmp_use_getnext': '0',
     'snmp_use_ifname': '0',
     'snmp_version': '2c',
     'snmpv3_authprotocol': None,
     'snmpv3_privprotocol': None,
     'snmpv3_username': '',
     'tidy_ifdescr_level': '0',
     'uncommitted': '0',
     'use_rancid': '0'}"""

    url = "/rest/config/host"

    def __init__(
        self,
        name: str,
        ip: str,
        hostgroup: ForwardRef("HostGroup"),
        hostattributes: ForwardRef("VariableList"),
        collector_cluster: str,
        hashtags=None,
        host_id=None,
        host_check_command_name: str = "ping",
        host_templates: ForwardRef("HostTemplateList") = None,
    ):
        self.name = name
        self.ip = ip
        self.host_check_command = HostCheckCommand(host_check_command_name)
        self.hostgroup: HostGroup = hostgroup
        self.hostattributes = VariableList(hostattributes)
        self.collector_cluster = collector_cluster

        self.id = host_id

        self.hashtags = HashtagList(hashtags)

        if not host_templates:
            host_templates = HostTemplateList()
            host_templates.append_object(HostTemplate("Network - Base"))

        self.host_templates = HostTemplateList(host_templates)

    def lookup_id(self, session: Session):
        """Get the ID of the host from Opsview."""
        self.id = get_host_id(session, self.name)

    def as_json(self, shallow=False):
        logging.debug("Creating JSON for host '%s'", self.name)
        logging.debug("%s", pformat(getattr(self, "__dict__")))
        return {
            "name": self.name,
            "id": self.id,
            "ip": self.ip,
            "check_command": self.host_check_command.as_json(shallow=True),
            "hostgroup": {"matpath": self.hostgroup.matpath},
            "hosttemplates": [
                host_template.as_json(shallow=True)
                for host_template in self.host_templates
            ],
            "hostattributes": [
                attr.as_json(shallow=True) for attr in self.hostattributes
            ],
            "monitored_by": {"name": self.collector_cluster},
            "keywords": [hashtag.as_json(shallow=True) for hashtag in self.hashtags],
        }

    def exists(self, session):
        if not hasattr(session, "known_host_names") or not session.known_host_names:
            session.populate_known_hosts()

        if self.name in session.known_host_names:
            logging.debug("Host with name '%s' already exists", self.name)
            return True

        logging.debug("Host with name '%s' does not exist", self.name)
        return False


class HostGroup(Object):
    """An Opsview HostGroup.

    Example from the Opsview API:
    {'children': [{'name': '192.168.2.88 - ESXi',
                   'ref': '/rest/config/hostgroup/5'},
                  {'name': '192.168.2.88 - VMs',
                   'ref': '/rest/config/hostgroup/6'}],
     'hosts': [],
     'id': '4',
     'is_leaf': '0',
     'matpath': 'Opsview,Automonitor,VMware vSphere Express Scan,',
     'name': 'VMware vSphere Express Scan',
     'parent': {'matpath': 'Opsview,Automonitor,',
                'name': 'Automonitor',
                'ref': '/rest/config/hostgroup/3'},
     'ref': '/rest/config/hostgroup/4',
     'uncommitted': '0'}"""

    url = "/rest/config/hostgroup"

    def __init__(
        self,
        name: str,
        children=None,
        hosts=None,
        id=None,
        is_leaf=False,
        matpath=None,
        parent=None,
        ref=None,
        uncommitted=False,
    ):
        if not name:
            raise ValueError("The 'name' attribute is missing or empty.")

        self.name = name
        self.children = HostGroupList(children)
        self.hosts = HostList(hosts)
        self.id = id
        self.is_leaf = "1" if is_leaf else "0"

        # If no parent is given, assume that the hostgroup is a child of the
        # root hostgroup.
        if parent:
            self.parent = parent
        # TODO: At some point, it might be worth considering actually looking up
        #       the name of the root hostgroup in Opsview since the name might
        #       have been changed.
        elif name != "Opsview":
            self.parent = HostGroup(
                name="Opsview", parent=None, ref="/rest/config/hostgroup/1"
            )
        else:
            self.parent = None

        self.matpath = self.__with_matpath() if matpath is None else matpath
        self.ref = ref
        self.uncommitted = "1" if uncommitted else "0"

    def __with_matpath(self):
        if self.parent:
            return f"{self.parent.matpath}{self.name},"

        return f"{self.name},"

    def lookup_ref(self, session: Session):
        """Get the ref of the hostgroup from Opsview."""
        if self.exists(session):
            self.ref = get_host_group_ref(session, self.matpath)

    def as_json(self, shallow=False):
        parent_entry = {
            "matpath": self.parent.matpath,
            "name": self.parent.name,
        }

        if self.parent and self.parent.ref:
            parent_entry["ref"] = self.parent.ref

        hostgroup_json = {
            "children": [child.as_json(shallow=True) for child in self.children]
            if self.children
            else [],
            "hosts": [host.as_json(shallow=True) for host in self.hosts]
            if self.hosts
            else [],
            "id": self.id,
            "is_leaf": self.is_leaf,
            "matpath": self.matpath,
            "name": self.name,
            # "parent": self.parent.as_json(shallow=True) if self.parent else None,
            "parent": parent_entry if self.parent else None,
            "ref": self.ref,
            "uncommitted": self.uncommitted,
        }

        if shallow:
            optional_keys = [
                "children",
                "hosts",
                "id",
                "is_leaf",
                "name",
                "parent",
                "ref",
                "uncommitted",
            ]
            for key in optional_keys:
                attr = getattr(self, key)
                if not attr or attr == "0":
                    del hostgroup_json[key]

        return hostgroup_json

    def exists(self, session: Session):
        if not hasattr(session, "known_hostgroups") or not session.known_hostgroups:
            session.populate_known_hostgroups()

        if self.matpath in session.known_hostgroup_matpaths:
            logging.debug("Hostgroup with matpath '%s' already exists", self.matpath)
            return True

        logging.debug("Hostgroup with matpath '%s' does not exist", self.matpath)
        return False


class Plugin(Object):
    """An Opsview Plugin.

    Example from the Opsview API:
    {"envvars" : "",
     "name" : "check_snmp_linkstatus",
     "servicechecks" : [
        {
           "name" : "Discards",
           "ref" : "/rest/config/servicecheck/101"
        },
        {
           "name" : "Errors",
           "ref" : "/rest/config/servicecheck/100"
        },
        {
           "name" : "Interface",
           "ref" : "/rest/config/servicecheck/95"
        }
     ],
     "hostcheckcommands" : [],
     "uncommitted": "1"}"""

    url = "/rest/config/plugin"

    def __init__(
        self,
        name: str,
        envvars=None,
        servicechecks=None,
        hostcheckcommands=None,
        uncommitted=False,
    ):
        if not name:
            raise ValueError("The 'name' attribute is missing or empty.")

        self.name = name
        self.envvars = envvars if envvars is not None else ""
        self.servicechecks = ServiceCheckList(servicechecks)
        self.hostcheckcommands = HostCheckCommandList(hostcheckcommands)
        self.uncommitted = "1" if uncommitted else "0"


class ServiceCheck(Object):
    """An Opsview ServiceCheck.

    Example from the Opsview API:
    {'alert_from_failure': '1',
     'args': '--IgnoreMyOutDatedPerlModuleVersions -H $HOSTADDRESS$ --u '
             '%WINCREDENTIALS:1% -p %WINCREDENTIALS:2% -m checkiis -s errors -a '
             "'%WEB_SERVER_INSTANCE_NAME%'",
     'attribute': {'name': 'WEB_SERVER_INSTANCE_NAME',
                   'ref': '/rest/config/attribute/149'},
     'calculate_rate': None,
     'cascaded_from': None,
     'check_attempts': '3',
     'check_freshness': '1',
     'check_interval': '300',
     'check_period': None,
     'checktype': {'name': 'Active Plugin', 'ref': '/rest/config/checktype/1'},
     'critical_comparison': None,
     'critical_value': None,
     'dependencies': [],
     'description': 'Check IIS web server errors using WMI',
     'event_handler': '',
     'event_handler_always_exec': '0',
     'flap_detection_enabled': '1',
     'hosts': [],
     'hosttemplates': [{'name': 'OS - Windows WMI - IIS Server Agentless',
                        'ref': '/rest/config/hosttemplate/201'}],
     'id': '1137',
     'invertresults': '0',
     'keywords': [],
     'label': None,
     'markdown_filter': '0',
     'name': 'Windows WMI - IIS Server Agentless - Web server errors',
     'notification_options': 'w,c,r,u,f',
     'notification_period': None,
     'oid': None,
     'plugin': {'name': 'check_wmi_plus.pl',
                'ref': '/rest/config/plugin/check_wmi_plus.pl'},
     'ref': '/rest/config/servicecheck/1137',
     'retry_check_interval': '60',
     'sensitive_arguments': '1',
     'servicegroup': {'name': 'OS - Windows WMI - IIS Server Agentless',
                      'ref': '/rest/config/servicegroup/179'},
     'snmptraprules': [],
     'stale_state': '3',
     'stale_text': 'UNKNOWN: Service results are stale',
     'stale_threshold_seconds': '1800',
     'stalking': None,
     'uncommitted': '0',
     'volatile': '0',
     'warning_comparison': None,
     'warning_value': None}"""

    url = "/rest/config/servicecheck"

    def __init__(
        self,
        name: str,
        alert_from_failure=True,
        args="",
        attribute=None,
        calculate_rate=None,
        cascaded_from=None,
        check_attempts=3,
        check_freshness=True,
        check_interval=300,
        check_period=None,
        checktype=None,
        critical_comparison=None,
        critical_value=None,
        dependencies=None,
        description=None,
        event_handler=None,
        event_handler_always_exec=False,
        flap_detection_enabled=True,
        hosts=None,
        hosttemplates=None,
        id=None,
        invertresults=False,
        keywords=None,
        label=None,
        markdown_filter=False,
        notification_options="w,c,r,u,f",
        notification_period=None,
        oid=None,
        plugin=None,
        ref=None,
        retry_check_interval=60,
        sensitive_arguments=True,
        servicegroup=None,
        snmptraprules=None,
        stale_state=3,
        stale_text="UNKNOWN: Service results are stale",
        stale_threshold_seconds=1800,
        stalking=None,
        uncommitted=False,
        volatile=False,
        warning_comparison=None,
        warning_value=None,
    ):
        if not name:
            raise ValueError("The 'name' attribute is missing or empty.")

        self.name = name

        if isinstance(servicegroup, ServiceGroup):
            self.servicegroup = servicegroup
        elif servicegroup is None:
            self.servicegroup = None
        elif isinstance(servicegroup, str):
            self.servicegroup = ServiceGroup(servicegroup)
        else:
            raise TypeError(
                f"Invalid type for 'servicegroup' attribute: {type(servicegroup).__name__}"
            )

        if isinstance(attribute, Variable):
            self.attribute = attribute
        elif attribute is None:
            self.attribute = None
        elif isinstance(attribute, str):
            self.attribute = Variable(attribute)
        else:
            raise TypeError(
                f"Invalid type for 'attribute' attribute: {type(attribute).__name__}"
            )

        if isinstance(plugin, Plugin):
            self.plugin = plugin
        elif plugin is None:
            self.plugin = None
        elif isinstance(plugin, str):
            self.plugin = Plugin(plugin)
        else:
            raise TypeError(
                f"Invalid type for 'plugin' attribute: {type(plugin).__name__}"
            )

        self.alert_from_failure = "1" if alert_from_failure else "0"
        self.args = args if args is not None else ""
        self.calculate_rate = calculate_rate
        self.cascaded_from = cascaded_from
        self.check_attempts = check_attempts
        self.check_freshness = "1" if check_freshness else "0"
        self.check_interval = check_interval
        self.check_period = check_period
        self.checktype = checktype
        self.critical_comparison = critical_comparison
        self.critical_value = critical_value
        self.dependencies = [] if dependencies is None else dependencies
        self.description = description if description is not None else ""
        self.event_handler = event_handler if event_handler is not None else ""
        self.event_handler_always_exec = "1" if event_handler_always_exec else "0"
        self.flap_detection_enabled = "1" if flap_detection_enabled else "0"
        self.hosts = HostList(hosts)
        self.hosttemplates = HostTemplateList(hosttemplates)
        self.id = id
        self.invertresults = "1" if invertresults else "0"
        self.keywords = HashtagList(keywords)
        self.label = label
        self.markdown_filter = "1" if markdown_filter else "0"
        self.notification_options = notification_options
        self.notification_period = notification_period
        self.oid = oid
        self.ref = ref
        self.retry_check_interval = retry_check_interval
        self.sensitive_arguments = "1" if sensitive_arguments else "0"
        self.snmptraprules = [] if snmptraprules is None else snmptraprules
        self.stale_state = stale_state
        self.stale_text = stale_text
        self.stale_threshold_seconds = stale_threshold_seconds
        self.stalking = stalking
        self.uncommitted = "1" if uncommitted else "0"
        self.volatile = "1" if volatile else "0"
        self.warning_comparison = warning_comparison
        self.warning_value = warning_value


class ServiceGroup(Object):
    """An Opsview Servicegroup.

    Example from the Opsview API:
    {'id': '160',
     'name': 'Service Provider - Amazon',
     'ref': '/rest/config/servicegroup/160',
     'servicechecks': [{'name': 'Amazon EC2 Instances',
                        'ref': '/rest/config/servicecheck/1028'},
                       {'name': 'Amazon EC2 Status',
                        'ref': '/rest/config/servicecheck/1027'},
                       {'name': 'Amazon S3 Bucket',
                        'ref': '/rest/config/servicecheck/1026'}],
     'uncommitted': '0'}"""

    url = "/rest/config/servicegroup"

    def __init__(
        self, name: str, id=None, ref=None, servicechecks=None, uncommitted=False
    ):
        if not name:
            raise ValueError("The 'name' attribute is missing or empty.")

        self.name = name
        self.id = id
        self.ref = ref
        self.servicechecks = ServiceCheckList(servicechecks)
        self.uncommitted = "1" if uncommitted else "0"


class TimePeriod(Object):
    """An Opsview TimePeriod.

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

    url = "/rest/config/timeperiod"

    def __init__(
        self,
        name: str,
        alias=None,
        monday=None,
        tuesday=None,
        wednesday=None,
        thursday=None,
        friday=None,
        saturday=None,
        sunday=None,
        host_check_periods=None,
        host_notification_periods=None,
        servicecheck_check_periods=None,
        servicecheck_notification_periods=None,
        id=None,
        ref=None,
        object_locked=True,
        uncommitted=False,
        zone={"name": "SYSTEM", "ref": "/rest/config/timezone/1"},
    ):
        if not name:
            raise ValueError("The 'name' attribute is missing or empty.")

        self.__validate_time(
            monday, tuesday, wednesday, thursday, friday, saturday, sunday
        )

        self.name = name
        self.alias = alias if alias is not None else ""
        self.friday = friday if friday is not None else ""
        self.monday = monday if monday is not None else ""
        self.saturday = saturday if saturday is not None else ""
        self.sunday = sunday if sunday is not None else ""
        self.thursday = thursday if thursday is not None else ""
        self.tuesday = tuesday if tuesday is not None else ""
        self.wednesday = wednesday if wednesday is not None else ""
        self.host_check_periods = HostList(host_check_periods)
        self.host_notification_periods = HostList(host_notification_periods)
        self.id = id
        self.ref = ref
        self.servicecheck_check_periods = ServiceCheckList(servicecheck_check_periods)
        self.servicecheck_notification_periods = ServiceCheckList(
            servicecheck_notification_periods
        )
        self.object_locked = "1" if object_locked else "0"
        self.uncommitted = "1" if uncommitted else "0"
        self.zone = zone

    def __validate_time(self, *time_strings):
        """Check if the time is in the correct format."""
        # Could be something like this:
        # 'saturday': '00:00-24:00',
        # 'wednesday': '00:00-09:00,17:00-24:00',
        # 'thursday': '00:00-09:00,17:00-21:00,22:10-23:05',
        time_regex = re.compile(r"^\d{2}:\d{2}-\d{2}:\d{2}(,\d{2}:\d{2}-\d{2}:\d{2})*$")

        for t in time_strings:
            if t is None:
                continue
            if not time_regex.match(t):
                raise ValueError(
                    f"The time '{t}' is not in the correct format. "
                    + "Correct format is '00:00-24:00' or "
                    + "'00:00-09:00,17:00-24:00'."
                )

        return True


class Variable(Object):
    """An Opsview Variable."""

    url = "/rest/config/attribute"

    def __init__(self, name: str, value="", id=None, ref=None):
        if not name:
            raise ValueError("The 'name' attribute is missing or empty.")

        if len(value) > 63:
            raise ValueError(
                f"The value '{value}' is too long. Maximum length is 63 "
                + "characters. Actual length is {len(value)} characters."
            )

        self.name = name
        self.value = value
        self.id = id
        self.ref = ref

    def as_json(self, shallow=False):
        return {
            "name": self.name,
            "value": self.value,
        }

    def exists(self, session: Session):
        if (
            not hasattr(session, "known_variables_names")
            or not session.known_variable_names
        ):
            session.populate_known_variables()

        if self.name in session.known_variable_names:
            logging.debug("Variable with name '%s' already exists", self.name)
            return True

        logging.debug("Variable with name '%s' does not exist", self.name)
        return False


class BSMComponentList(ObjectList):
    """A list of Opsview BSMComponents."""

    objects: List[BSMComponent]
    url = "/rest/config/bsmcomponent"


class BSMServiceList(ObjectList):
    """A list of Opsview BSMComponents."""

    objects: List[BSMService]
    url = "/rest/config/bsmservice"


class HashtagList(ObjectList):
    """A list of Opsview Hashtags."""

    objects: List[Hashtag]
    url = "/rest/config/keyword"


class HostCheckCommandList(ObjectList):
    """A list of Opsview HostCheckCommands."""

    objects: List[HostCheckCommand]
    url = "/rest/config/hostcheckcommand"


class HostTemplateList(ObjectList):
    """A list of Opsview HostTemplates."""

    objects: List[HostTemplate]
    url = "/rest/config/hosttemplate"


class HostList(ObjectList):
    """A list of Opsview Hosts."""

    objects: List[Host]
    url = "/rest/config/host"

    def delete(self, session: Session):
        """Delete the hosts in Opsview."""
        if not self.objects:
            return

        for host in self.objects:
            logging.info("Deleting host '%s'", host.name)

        # DELETE /rest/config/OBJECTTYPE?id=X&id=Y&id=Z
        # The API only supports deleting multiple objects of the host type by
        # providing a list of IDs. We need to get the IDs of the hosts first.
        # Using urljoin() here would result in a URL like
        # https://opsview.example.com/rest/config/host?id=1&id=2&id=3

        url = f"{self.url}?id=" + "&id=".join(str(host.id) for host in self.objects)

        response = session.delete(url)

        self.handle_response(response)

        return response

    def from_snow_instance(self, session: Session, instance: str):
        """Get all hosts from Opsview that come from a specific ServiceNow instance."""
        if not instance:
            raise ValueError("The 'instance' attribute is missing or empty.")

        logging.debug(
            "Getting hosts from Opsview that come from instance '%s'", instance
        )

        all_hosts = get_hosts(session)
        # Use list comprehension to filter out all hosts that have a hostattribute
        # named SERVICENOW_INSTANCE AND where the value of that hostattribute is
        # equal to the instance we are looking for.
        instance_hosts = [
            host
            for host in all_hosts
            if any(
                attr["name"] == "SERVICENOW_INSTANCE" and attr["value"] == instance
                for attr in host["hostattributes"]
            )
        ]

        logging.debug("Found %s hosts", len(instance_hosts))
        self.objects = [
            Host(
                host["name"],
                host["ip"],
                HostGroup(host["hostgroup"]["name"]),
                VariableList(
                    [
                        Variable(attr["name"], attr["value"])
                        for attr in host["hostattributes"]
                    ]
                ),
                host["monitored_by"]["name"],
                host["keywords"],
                host["id"],
            )
            for host in instance_hosts
        ]
        self.log_objects("Found hosts:")

    def sync_from_snow_instance(
        self,
        session: Session,
        snow_hosts: ForwardRef("HostList"),
        instance: str,
        dry_run=False,
        force=False,
    ):
        """Sync the list of Opsview hosts with a list of ServiceNow hosts."""
        logging.debug("Syncing Opsview hosts with ServiceNow objects")

        if not instance:
            raise ValueError("The 'instance' attribute is missing or empty.")
        else:
            instance = util.snow_instance_from_url(util.with_https(instance))

        # This scenario handles the case where ServiceNow reports no hosts to
        # monitor. In this case, we want to remove all Opsview hosts that
        # originate from the ServiceNow instance.
        if not snow_hosts:
            logging.debug(
                f"No ServiceNow hosts found, "
                f"removing all Opsview hosts from the instance '{instance}'"
            )

            if dry_run:
                logging.info("Dry run: Would have removed ALL Opsview hosts")
                return
            else:
                if not force:
                    answer = input(
                        f"Are you sure you want to remove ALL Opsview hosts from the "
                        f"instance '{instance}'? [y/N] "
                    )
                    if answer.lower() != "y":
                        logging.info("Aborting")
                        return

                purge_snow_hosts(session, instance, force)
                return

        # Build up the list of Opsview hosts that originate from the ServiceNow
        # instance.
        self.from_snow_instance(session, instance)

        logging.info(
            f"Number of hosts from instance '{instance}' found in Opsview: {len(self)}"
        )

        existing_host_names = [host.name for host in self.objects]

        hosts_to_delete = HostList(
            [
                host
                for host in self.objects
                if host.name not in [snow_host.name for snow_host in snow_hosts]
            ]
        )

        hosts_to_create = HostList(
            [
                snow_host
                for snow_host in snow_hosts
                if snow_host.name not in existing_host_names
            ]
        )

        if not hosts_to_delete and not hosts_to_create:
            logging.info("No hosts to delete or create")
        elif hosts_to_delete:
            logging.info(
                "Number of hosts to delete in Opsview: %s", len(hosts_to_delete)
            )
            if not dry_run:
                hosts_to_delete.delete(session)
        else:
            logging.info(
                "Number of hosts to create in Opsview: %s", len(hosts_to_create)
            )
            if not dry_run:
                hosts_to_create.create(session)

        prune_snow_hashtags(session)


class HostGroupList(ObjectList):
    """A list of Opsview HostGroups."""

    objects: List[HostGroup]
    url = "/rest/config/hostgroup"

    def add_hostgroups_from_matpaths(self, *matpaths: str):
        """Add hostgroups from matpaths."""
        # Given a list of matpaths, add all hostgroups that are not already in
        # the HostGroupList.
        # If a hostgroup is already in the list, but has a different parent,
        # it is considered a different HostGroup and will be added to the list.
        logging.debug("Processing the following matpaths: '%s'", pformat(matpaths))
        for matpath in matpaths:
            logging.debug("Adding hostgroups from matpath '%s'", matpath)
            hostgroup_names = matpath.split(",")
            hostgroup_names.pop()  # Remove the last empty string
            logging.debug("Hostgroup names: '%s'", pformat(hostgroup_names))

            for i, hostgroup_name in enumerate(hostgroup_names):
                parent = None

                if i == 1:
                    parent = HostGroup(hostgroup_names[i - 1], parent=None)

                if i > 1:
                    parent = HostGroup(
                        hostgroup_names[i - 1], parent=HostGroup(hostgroup_names[i - 2])
                    )

                hostgroup = HostGroup(hostgroup_name, parent=parent)

                if hostgroup not in self.objects:
                    self.objects.append(hostgroup)

    def sort_by_depth(self):
        """Sort the list of hostgroups by depth with the shortest first."""
        self.objects.sort(key=lambda hostgroup: hostgroup.matpath.count(","))

    def without_duplicates(self):
        """Remove duplicate hostgroups from the list based on matpaths."""
        # We need a SubClass specific method to remove duplicates, since
        # HostGroups are compared by matpath, not by name.
        seen_matpaths = set()
        unique_hostgroups = []

        for hostgroup in self.objects:
            if hostgroup.matpath not in seen_matpaths:
                seen_matpaths.add(hostgroup.matpath)
                unique_hostgroups.append(hostgroup)
            else:
                logging.debug("Removing duplicate hostgroup '%s'", hostgroup.name)

        if len(unique_hostgroups) == len(self.objects):
            logging.debug("No duplicate hostgroups found")
        else:
            logging.debug("Found duplicate hostgroups")

        self.objects = unique_hostgroups


class ServiceCheckList(ObjectList):
    """A list of Opsview ServiceChecks."""

    objects: List[ServiceCheck]
    url = "/rest/config/servicecheck"


class VariableList(ObjectList):
    """A list of Opsview Variables."""

    objects: List[Variable]
    url = "/rest/config/attribute"


def get_object(session: Session, object_type: str, object_name: str) -> dict:
    """Get an object of a certain type from Opsview."""
    logging.debug("Getting %s from Opsview: '%s'", object_type, object_name)
    response = session.get(f"/rest/config/{object_type}/{object_name}")

    if response.status_code != 200:
        error_msg = f"Error fetching {object_type}: '{response.text}'"
        logging.error(error_msg)
        raise RequestException(error_msg)

    return response.json()


def get_objects(session: Session, object_url):
    """Get all objects of a certain type from Opsview, handling pagination."""
    all_objects = []
    page_number = 1

    while True:
        logging.debug(
            "Getting objects from Opsview at %s, page %s", object_url, page_number
        )
        paginated_url = f"{object_url}?page={page_number}"
        response = session.get(paginated_url)

        # logging.debug("Response from Opsview: '%s'", response.text)

        if response.status_code != 200:
            error_msg = f"Error fetching objects: '{response.text}'"
            logging.error(error_msg)
            raise RequestException(error_msg)

        data = response.json()
        objects = data["list"]
        all_objects.extend(objects)

        if util.is_debug():
            logging.debug("Found %s objects on page %s", len(objects), page_number)
            for obj in objects:
                logging.debug("Found object: '%s'", obj["name"])

        # Check if there are more pages
        if data.get("summary", {}).get("page", "0") == data.get("summary", {}).get(
            "totalpages", "0"
        ):
            break

        page_number += 1

    return all_objects


def get_variable(session: Session, variable_name):
    """Get a variable from Opsview."""
    return get_object(session, "attribute", variable_name)


def get_variables(session: Session):
    """Get all variables from Opsview."""
    return get_objects(session, "/rest/config/attribute")


def get_host(session: Session, host_name):
    """Get a host from Opsview."""
    return get_object(session, "host", host_name)


def get_hosts(session: Session):
    """Get all hosts from Opsview."""
    return get_objects(session, "/rest/config/host")


def get_host_id(session: Session, host_name):
    """Get the ID of a host from Opsview."""
    host = get_host(session, host_name)

    if host:
        return host["id"]

    return None


def get_host_group_by_name(session: Session, host_group_name):
    """Get a host group from Opsview."""
    all_host_groups = get_hostgroups(session)

    for host_group in all_host_groups:
        if host_group["name"] == host_group_name:
            return host_group

    return None


def get_host_group_by_matpath(session: Session, host_group_matpath):
    """Get a host group from Opsview."""
    if not session.known_hostgroups:
        session.populate_known_hostgroups()

    for host_group in session.known_hostgroups:
        if host_group["matpath"] == host_group_matpath:
            return host_group

    return None


def get_host_group_ref(session: Session, host_group_matpath):
    """Get a host group ref from Opsview."""
    host_group = get_host_group_by_matpath(session, host_group_matpath)

    if host_group:
        return host_group["ref"]

    return None


def get_hostgroups(session: Session):
    """Get all host groups from Opsview."""
    return get_objects(session, "/rest/config/hostgroup")


def get_hosttemplate(session: Session, host_template_name):
    """Get a host template from Opsview."""
    return get_object(session, "hosttemplate", host_template_name)


def get_hosttemplates(session: Session):
    """Get all host templates from Opsview."""
    return get_objects(session, "/rest/config/hosttemplate")


def get_bsm_component(session, bsm_component_name):
    """Get a BSM component from Opsview."""
    return get_object(session, "bsmcomponent", bsm_component_name)


def get_bsm_components(session: Session):
    """Get all BSM components from Opsview."""
    return get_objects(session, "/rest/config/bsmcomponent")


def get_bsm_service(session: Session, bsm_service_name):
    """Get a BSM service from Opsview."""
    return get_object(session, "bsmservice", bsm_service_name)


def get_bsm_services(session: Session):
    """Get all BSM services from Opsview."""
    return get_objects(session, "/rest/config/bsmservice")


def get_hashtag(session: Session, hashtag_name):
    """Get a hashtag from Opsview."""
    return get_object(session, "keyword", hashtag_name)


def get_hashtags(session: Session):
    """Get all hashtags from Opsview."""
    return get_objects(session, "/rest/config/keyword")


def get_host_check_commands(session: Session):
    """Get all host check commands from Opsview."""
    return get_objects(session, "/rest/config/hostcheckcommand")


def get_hosticon(session: Session, hosticon_name):
    """Get a hosticon from Opsview."""
    return get_object(session, "hosticons", hosticon_name)


def get_hosticons(session: Session):
    """Get all hosticons from Opsview."""
    return get_objects(session, "/rest/config/hosticons")


def get_servicechecks(session: Session):
    """Get all service check commands from Opsview."""
    return get_objects(session, "/rest/config/servicecheck")


def get_servicegroups(session: Session):
    """Get all service groups from Opsview."""
    return get_objects(session, "/rest/config/servicegroup")


def get_timeperiods(session: Session):
    """Get all timeperiods from Opsview."""
    return get_objects(session, "/rest/config/timeperiod")


def purge_snow_variables(session: Session):
    """Delete all variables in Opsview that come from ServiceNow."""
    if not hasattr(session, "known_variables") or not session.known_variables:
        session.populate_known_variables()

    variables_to_delete = []
    ids_to_delete = []

    for variable in session.known_variables:
        if (
            variable["name"].startswith("SERVICENOW_")
            and variable["name"] != "SERVICENOW_SETTINGS"
        ):
            variables_to_delete.append(variable["name"])
            ids_to_delete.append(variable["id"])

    if not ids_to_delete:
        logging.info("Number of variables to delete in Opsview: 0")
        return

    logging.info("Number of variables to delete in Opsview: %s", len(ids_to_delete))

    for variable in variables_to_delete:
        logging.info("Deleting variable '%s'", variable)

    for variable_id in ids_to_delete:
        url = f"/rest/config/attribute/{variable_id}"
        response = session.delete(url)

        if response.status_code != 200:
            error_msg = f"Error deleting variables: '{response.text}'"
            logging.error(error_msg)
            raise RequestException(error_msg)


def purge_root_snow_hostgroup(session: Session):
    """If no hostgroups are left in Opsview that come from ServiceNow, delete the
    root ServiceNow hostgroup.
    """
    # Always refresh since this is run after the hostgroups have been deleted.
    session.populate_known_hostgroups()

    service_now_hostgroups = [
        hostgroup
        for hostgroup in session.known_hostgroups
        if hostgroup["matpath"].startswith("Opsview,ServiceNow,")
    ]

    if not service_now_hostgroups:
        logging.debug("No ServiceNow hostgroups left in Opsview")
        return

    if len(service_now_hostgroups) > 1:
        logging.debug(
            "More than one ServiceNow hostgroup left in Opsview. Not deleting the root hostgroup."
        )
        return

    if (
        len(service_now_hostgroups) == 1
        and service_now_hostgroups[0]["name"] == "ServiceNow"
    ):
        logging.info("Deleting root hostgroup 'ServiceNow'")
        url = f"/rest/config/hostgroup/{service_now_hostgroups[0]['id']}"
        response = session.delete(url)

        if response.status_code != 200:
            error_msg = f"Error deleting root ServiceNow hostgroup: '{response.text}'"
            logging.error(error_msg)
            raise RequestException(error_msg)


def purge_snow_hostgroups(session: Session, instance: str):
    """Removing all hostgroups from Opsview that come from ServiceNow."""
    # If the hostgroup matpath starts with "Opsview,ServiceNow,{instance},",
    # then it comes from the ServiceNow instance that we're purging. We need to
    # get all hostgroups first, then filter out the ones that come from the
    # ServiceNow instance, then delete them.
    if not hasattr(session, "known_hostgroups") or not session.known_hostgroups:
        session.populate_known_hostgroups()

    hostgroups_to_delete = []
    ids_to_delete = []

    for hostgroup in session.known_hostgroups:
        if hostgroup["matpath"].startswith(f"Opsview,ServiceNow,{instance},"):
            hostgroups_to_delete.append(hostgroup["name"])
            ids_to_delete.append(hostgroup["id"])

    if not hostgroups_to_delete:
        logging.info("Number of hostgroups to delete in Opsview: 0")
        return

    logging.info(
        "Number of hostgroups to delete in Opsview: %s",
        len(hostgroups_to_delete),
    )

    for hostgroup in hostgroups_to_delete:
        logging.info("Deleting hostgroup '%s'", hostgroup)

    # Hostgroups cannot be deleted as a list, so we need to delete them one by
    # one using the id.
    for hostgroup_id in ids_to_delete:
        url = f"/rest/config/hostgroup/{hostgroup_id}"
        response = session.delete(url)

        if response.status_code != 200:
            error_msg = f"Error deleting hostgroups: '{response.text}'"
            logging.error(error_msg)
            raise RequestException(error_msg)


def prune_snow_hashtags(session: Session):
    """Remove all hashtags from Opsview that are empty or that represent a
    specific instance."""
    if not hasattr(session, "known_hashtags") or not session.known_hashtags:
        session.populate_known_hashtags()

    hashtags_to_delete = []
    ids_to_delete = []

    for hashtag in session.known_hashtags:
        if (
            hashtag["description"].startswith("Created by Opsview CMDB Sync")
            and hashtag["hosts"] == []
            and hashtag["servicechecks"] == []
        ):
            hashtags_to_delete.append(hashtag["name"])
            ids_to_delete.append(hashtag["id"])

    if not hashtags_to_delete:
        logging.info("Number of hashtags to delete in Opsview: 0")
        return

    logging.info("Number of hashtags to delete in Opsview: %s", len(hashtags_to_delete))

    for hashtag in hashtags_to_delete:
        logging.info("Deleting hashtag '%s'", hashtag)

    # Hashtags cannot be deleted as a list, so we need to delete them one by
    # one using the id.
    for hashtag_id in ids_to_delete:
        url = f"/rest/config/keyword/{hashtag_id}"
        response = session.delete(url)

        if response.status_code != 200:
            error_msg = f"Error deleting hashtags: '{response.text}'"
            logging.error(error_msg)
            raise RequestException(error_msg)


def purge_snow_hosts(session: Session, instance: str, force=False):
    """Remove all hosts from Opsview that come from a ServiceNow instance."""
    hosts = HostList()

    hosts.from_snow_instance(session, instance)

    if hosts:
        response = hosts.delete(session)

        if response and response.status_code != 200:
            logging.error("Failed to delete hosts in Opsview")
            logging.error(response.json())
            sys.exit(1)

    else:
        logging.info("Number of hosts to delete in Opsview: 0")

    if not force:
        answer = input(
            f"Are you sure you want to delete ALL objects "
            f"from the ServiceNow instance '{instance}'? [y/N] "
        )
        if answer.lower() != "y":
            logging.info("Aborting")
            return

    prune_snow_hashtags(session)
    purge_snow_hostgroups(session, instance)
    purge_root_snow_hostgroup(session)

    # Only purge variables if there are no more hosts left in Opsview that come
    # from any ServiceNow instance.

    session.populate_known_hosts()

    if not any(
        (attr["name"] == "SERVICENOW_INSTANCE" or attr["name"] == "SERVICENOW_SYS_ID")
        for host in session.known_hosts
        for attr in host["hostattributes"]
    ):
        purge_snow_variables(session)
    else:
        logging.info(
            "Not purging ServiceNow variables, since there are still hosts "
            + "in Opsview that come from other ServiceNow instances"
        )


def object_exists(session: Session, object_url, object_name) -> bool:
    """Check if an object exists in Opsview."""
    response = session.get(urljoin(object_url, "exists", object_name))

    if response.status_code != 200:
        error_msg = f"Error fetching object: '{response.text}'"
        logging.error(error_msg)
        raise RequestException(error_msg)

    exists = response.json()["exists"]

    if exists == 1:
        return True

    return False


def get_object_id(session: Session, obj: Object):
    """Get the ID of an object from Opsview."""
    response = session.get(urljoin(obj.url, obj.name))

    if response.status_code != 200:
        error_msg = f"Error fetching object: '{response.text}'"
        logging.error(error_msg)
        raise RequestException(error_msg)

    object_id = response.json()["id"]

    if object_id:
        return object_id

    return None
