#!/usr/bin/env python3
"""This package contains functions to sync objects from ServiceNow to Opsview."""
from __future__ import print_function

import logging
import sys
from pprint import pformat

import pysnow

from ov_cmdb_sync import util, opsview, servicenow


def main():
    """Main module."""

    args = util.parse_args()

    ### LOGGING ###
    # Set up logging. By default, we log to stdout and to a logfile at
    # /var/log/opsview/opsview.log, if no other logfile is specified with the
    # --logfile option.

    if args.logfile:
        # Try to create the file, if it doesn't exist
        # This will fail if the user doesn't have write permissions
        # to the directory
        try:
            with open(args.logfile, "a", encoding="utf-8") as _:
                pass
        except IOError:
            print(f"Unable to write to logfile {args.logfile}")
            sys.exit(1)
    util.setup_logging(args.debug, args.logfile)
    logging.debug("Debug output enabled")

    ### OPSVIEW SESSION ###
    util.test_connection(util.with_https(args.ov_url))
    # Create an Opsview session object. This will be used to interact with
    # Opsview.

    logging.debug("Initializing Opsview session at %s", args.ov_url)
    ov = opsview.Session(
        url=args.ov_url, username=args.ov_username, password=args.ov_password
    )
    logging.info("Connected to the Opsview instance at %s", args.ov_url)

    ### DEBUG ###
    # ov.populate_known_hosticons()
    # sys.exit(0)

    ov.handle_pending_changes(args.force)

    ### PURGE SNOW INSTANCE ###
    # If the --purge-snow-hosts-from-instance option is specified, purge all
    # hosts that come from the ServiceNow CMDB and exit.

    if args.purge_snow_instance:
        opsview.purge_snow_hosts(ov, args.purge_snow_instance)
        ov.apply_changes()
        ov.close()
        sys.exit(0)

    ### SERVICENOW SESSION ###
    util.test_connection(args.snow_url)

    # Create a ServiceNow session object. This will be used to interact with
    # ServiceNow.

    logging.debug("Initializing ServiceNow session at %s", args.snow_url)
    snow = pysnow.Client(
        host=util.without_https(args.snow_url),
        user=args.snow_username,
        password=args.snow_password,
    )
    logging.info("Connected to the ServiceNow instance at %s", args.snow_url)

    ### Parse ServiceNow CMDB ###
    logging.debug("Getting all hosts from ServiceNow")
    ov_hosts_in_snow = servicenow.opsview_host_list(snow)
    logging.info("Found %s Opsview Hosts in ServiceNow", len(ov_hosts_in_snow))

    if util.is_debug():
        logging.debug("Opsview Hosts in ServiceNow:")
        for host in ov_hosts_in_snow:
            logging.debug(pformat(host.as_json()))

    ### Execute changes in Opsview ###
    # Now that we have all the hosts from ServiceNow, we can create them in
    # Opsview.

    ov.populate_known_hosts()
    opsview.HostList().sync_from_snow_instance(
        session=ov,
        snow_hosts=ov_hosts_in_snow,
        instance=servicenow.instance_from_url(util.with_https(args.snow_url)),
        dry_run=args.dry_run,
    )

    if args.dry_run:
        logging.info("Not applying changes.")
        sys.exit(0)

    # if response and response.status_code != 200:
    #     logging.error("Failed to create hosts in Opsview")
    #     logging.error(response.json())
    #     sys.exit(1)

    ov.apply_changes()

    ### Close sessions and exit ###

    snow.session.close()
    ov.close()
    sys.exit(0)


if __name__ == "__main__":
    main()
