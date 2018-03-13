#!/usr/bin/python
import argparse
import ConfigParser
import getpass
import json
import logging
import os
import requests
import sys
import time

from datetime import datetime
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class PasswordPrompt(argparse.Action):
    def __call__(self, parser, args, values, option_string):
        if values is None:
            values = getpass.getpass()
        setattr(args, self.dest, values)
        
# Version
VERSION = "1.2.1"

# Default configuration (overwritten by errata2cv.ini if exist values and command line arguments)
URL = "https://satellite.default/" 
USERNAME = "admin"
PASSWORD = "password"
ORG_NAME = "Default Organization"

# Logging default level
LOGGING_LEVEL = logging.INFO

# API Information
SATELLITE_API = URL + "api/"
KATELLO_API = URL + "katello/api/"
TASKS_API = URL + "foreman_tasks/api/"

# API Settings
POST_HEADERS = {'content-type': 'application/json', 'accept': 'application/json;version=2'}
SSL_VERIFY = False

# Helper functions for GET/POST API methods
#TODO: use some library to improve error handling/logging
def get_json(location, json_data = ""):
    logging.debug("Request: GET %s" % location)
    if json_data: logging.debug("Request data: " + json.dumps(json_data))
    result = requests.get(location,
                            params = json_data,
                            auth = (USERNAME, PASSWORD),
                            verify = SSL_VERIFY)
    logging.debug("Request result: " + json.dumps(result.json()))
    return result.json()

def post_json(location, json_data):
    logging.debug("Request: POST %s" % location)
    if json_data: logging.debug("Request data: " + json.dumps(json_data))
    result = requests.post(location,
                            data = json.dumps(json_data),
                            auth = (USERNAME, PASSWORD),
                            verify = SSL_VERIFY,
                            headers = POST_HEADERS)
    logging.debug("Request result: " + json.dumps(result.json()))
    return result.json()

def main():
    global URL, USERNAME, PASSWORD, ORG_NAME, SATELLITE_API, KATELLO_API, TASKS_API, LOGGING_LEVEL

    # Setup arguments from command line
    parser = argparse.ArgumentParser(description = "Satellite 6 - Content View Errata Updater v%s" % VERSION)
    parser.add_argument("--cv", help = "Comma-separated list of Content View names to update. If keyword all is specified, all existing content views in the organization will be updated", required = True)
    parser.add_argument("--type", type = str.lower, help = "Comma-separated list of errata types to include (bugfix, enhancement or security). Default: Security.", default = "security")
    parser.add_argument("--severity", type = str.lower, help = "Comma-separated list of errata severity level to include (critical, important, moderate or low). Default: Critical.", default = "critical")
    parser.add_argument("--from-date", help = "Date to use as a referente instead of Content View publishing date (YYYY/MM/DD).", default = "")
    parser.add_argument("--to-date", help = "Date to use as a referente to stop including erratas (YYYY/MM/DD).", default = "")
    parser.add_argument("--propagate", action = "store_true", help = "Propagate incremental version to Composite Content Views. Default: False.", default = False)
    parser.add_argument("--update-hosts", help = "Comma-separated list of lifecycle environments to update hosts with the included erratas.", default = "")
    parser.add_argument("--dry-run", action = "store_true", help = "Check for erratas but don't update Content Views nor update hosts.", default = False)
    parser.add_argument("-s", "--server-url", "--url", help = "Satellite base URL with trailing slash. Default: %s," % URL)
    parser.add_argument("-o", "--organization", "--org_name", help = "Satellite Organization to work with. Default: %s, " % ORG_NAME)
    parser.add_argument("-u", "--username", help = "Username to authenticate with. Default: %s," % USERNAME)
    parser.add_argument("-p", "--password", action = PasswordPrompt, nargs='?', help = "Password to be used. Prompt if no password is provided,", dest="password")
    parser.add_argument("-d", "--debug", action = "store_true", help = "Show debug information (including GET/POST requests).", default = False)
    parser.add_argument("-V", "--version", action = "version", version = "%(prog)s " + VERSION)
    args = vars(parser.parse_args())

    # Override configuration with args values if present in command line or config file if available
    # TODO: Do all this configuration stuff it better than global variables, someday.
    config = ConfigParser.ConfigParser()
    config.read('%s/errata2cv.ini' % os.path.abspath(os.path.dirname(sys.argv[0])))

    if args["username"]:
        USERNAME = args["username"]
    elif config.has_option('config', 'username'):
        USERNAME = config.get('config', 'username')

    if args["password"]:
        PASSWORD = args["password"]
    elif config.has_option('config', 'password'):
        PASSWORD = config.get('config', 'password')

    if args["server_url"]:
        URL = args["server_url"]
    elif config.has_option('config', 'url'):
        URL = config.get('config', 'url')
    SATELLITE_API = URL + "api/" 
    KATELLO_API = URL + "katello/api/"
    TASKS_API = URL + "foreman_tasks/api/"

    if args["organization"]:
        ORG_NAME = args["organization"]
    elif config.has_option('config', 'org_name'):
        ORG_NAME = config.get('config', 'org_name')

    if args["debug"] is True:
        LOGGING_LEVEL = logging.DEBUG
 
    # Setup logging
    logging.getLogger("requests").setLevel(logging.WARNING)
    log = logging.getLogger(__name__)
    logging.basicConfig(level = LOGGING_LEVEL,
                    stream = sys.stdout,
                    format = "%(asctime)s %(levelname)s: %(message)s",
                    handlers = [logging.StreamHandler()])

    # Get organization
    logging.debug("Looking for organization information.")
    org = get_json(KATELLO_API + "organizations/" + ORG_NAME)

    # Compose search strings using input arguments
    severity_search = "(severity = " + ' or severity = '.join([x.capitalize() for x in args["severity"].split(',')]) + ")"
    type_search = "(type = " + ' or type = '.join(args["type"].split(',')) + ")"

    # If cv param is set to all, get all existing contentviews
    if args["cv"].lower() == "all":
        logging.info("Getting list of all existing content views in organization %s.", ORG_NAME)
        get_params = {
                "noncomposite": 1,
                "nondefault": 1,
                "per_page": 9999
        }
        all_cvs = get_json(KATELLO_API + "organizations/%s/content_views" % org["id"], get_params)["results"]
        cv_list = ",".join(i["name"] for i in all_cvs)
    else:
        cv_list = args["cv"]

    # Loop over content-views to find any new errata in their repositories
    for cv_name in cv_list.split(","):
        logging.info("Processing content-view %s." % cv_name)
        errata_ids = []
        try:
            # Compose GET parameters to get given content view
            get_params = {
                "noncomposite": 1,
                "nondefault": 1,
                "search": "name=%s" % cv_name
            }
            cv = get_json(KATELLO_API + "organizations/%s/content_views" % org["id"], get_params)["results"][0]
        except:
            logging.warning("Skipping non existing content-view %s." % cv_name)
            continue

        # Calculate from-date acording to parameters and last version published
        if args["from_date"] == "":
            last_published = cv["last_published"]
            if last_published is None:
                last_published = "1970-01-01 00:00:00 UTC"
            from_date = datetime.strptime(last_published, "%Y-%m-%d  %X %Z").strftime('%Y/%m/%d')
        else:
            from_date = args["from_date"]
        logging.debug("Using %s as start date." % from_date)

        # Compose GET parameters to search errata
        get_params = {
            "repository_id": '',
            "paged": False,
            "errata_restrict_applicable": False,
            "errata_restrict_installable": False,
            "search": "%s and %s and updated > '%s'" % (type_search, severity_search, from_date)
        }

        # Append to-date if parameter was provided
        if args["to_date"]:
            get_params ["search"] += " and updated < '%s'" % args["to_date"]
            logging.debug("Using %s as end date." % from_date)

        need_publish = False
        # Get erratas matching criteria for each repository
        for repo in cv["repositories"]:
            logging.info("Searching for erratas in repository %s" % repo["name"])
            get_params["repository_id"] = repo["id"]
            errata_in_repo = get_json(KATELLO_API + "errata", get_params)

            # Save errata id in an array and warn if any suggests a reboot
            for errata in errata_in_repo["results"]:
                logging.info("Found %s (%s - %s) errata. Reboot suggested: %s." % (errata["errata_id"], errata["type"].capitalize(), errata["severity"], "Yes" if errata["reboot_suggested"] else "No"))
                errata_ids.append(errata["errata_id"])

        # Publish incremental version if there are any errata in the array
        errata_ids = list(set(errata_ids))
        if len(errata_ids) > 0:
            # Get CV version in Library environment only
            for version in cv["versions"]:
                if 1 in version["environment_ids"]:
                    logging.info("Selected content-view %s (version %s) as baseline to include %s erratas. Skipping any other existing content-view version." % (cv["name"], version["version"], len(errata_ids)))
                    break
                else:
                    logging.debug("Skipping content-view %s (version %s): Not in Library." % (cv["name"], version["version"]))

            # Compose POST parameters to publish incremental version
            post_params = {
                "resolve_dependencies": 1,
                "add_content": { "errata_ids": errata_ids },
                "content_view_version_environments": [ {
                    "content_view_version_id": version["id"],
                    "environment_ids": [ 1 ]
                } ]
            }
            if args["propagate"] == True:
                post_params["propagate_all_composites"] = 1 

            # If no dry-run execution publish an incremental version and propagate it to all composite content views
            if args["dry_run"] == False:
                logging.info("Publishing incremental content-view version.")
                incremental_update = post_json(KATELLO_API + "content_view_versions/incremental_update", post_params)

                # Loop until task is finished
                progress = 0
                while(incremental_update["pending"] != False):
                    logging.info("Waitting for publishing task to complete: %i%%." % progress)
                    time.sleep(60)
                    incremental_update = get_json(TASKS_API + "tasks/" + incremental_update["id"])
                    # Progress is returned like 0.05 = 5%
                    progress = float(incremental_update["progress"]) * 100 

                if incremental_update["result"] != "success":
                    logging.error("Error publishing incremental content-view version. Skipping installation in hosts.")
                    continue

                # Apply erratas to hosts using remote execution "Install Errata - Katello SSH Default" job if environments were provided
                if args["update_hosts"]:
                    logging.info("Installing errata in hosts (if applicable).")

                    # Compose search query for hosts in given lifecycle environments and erratas are applicable
                    environments_search = "(lifecycle_environment=" + " or lifecycle_environment=".join(args["update_hosts"].split(",")) + ")"
                    applicable_search = "(applicable_errata=" + " or applicable_errata=".join(errata_ids) + ")"
                    search_query = environments_search + " and " + applicable_search

                    # Get template id
                    template_json = get_json(SATELLITE_API + 'job_templates', {"search": 'name = "Install Errata - Katello SSH Default"'})
                    if len(template_json["results"]) > 0:
                        template_id = template_json["results"][0]["id"]

                        # Compose POST parameters to invoke the job
                        post_params = {
                            "job_invocation": {
                                "job_template_id": template_id,
                                "inputs": {
                                    "errata": ",".join(errata_ids)
                                },
                                "search_query": search_query,
                                "targeting_type": "static_query"
                            }
                        }

                        # Invoke job execution and continue with another CV in the list (if any)
                        job_execution = post_json(SATELLITE_API + 'job_invocations', post_params)
                    else:
                        logging.info("Remote execution job \"Install Errata - Katello SSH Default\" not found. Skipping errata installation.")
                else:
                    logging.debug("Skipping errata installation as no host lifecycle environments were provided.")
            else:
                logging.info("Skipping incremental content-view and/or installation in hosts as dry-run was specified.")
            logging.info("Finished processing CV %s." % cv_name)
        else:
            logging.info("No new existing erratas for %s CV." % cv["name"])

if __name__ == "__main__":
    main()
