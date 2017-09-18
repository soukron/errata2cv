#!/usr/bin/python
import json
import sys
import time
from datetime import datetime
import logging
import argparse
import getpass
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


class PasswordPrompt(argparse.Action):
    def __call__(self, parser, args, values, option_string):
        password = getpass.getpass()
        setattr(args, self.dest, password)
        

# Version
VERSION = "1.1.1"

# API Settings
POST_HEADERS = {'content-type': 'application/json'}
SSL_VERIFY = False

# Helper functions for GET/POST API methods
#TODO: use some library to improve error handling/logging
def get_json(location, username, password, json_data = ""):
    logging.debug("Request: GET %s" % location)
    if json_data: logging.debug("Request data: " + json.dumps(json_data))
    result = requests.get(location,
                            data = json_data,
                            auth = (username, password),
                            verify = SSL_VERIFY)
    logging.debug("Request result: " + json.dumps(result.json()))
    return result.json()

def post_json(location, json_data, username, password):
    logging.debug("Request: POST %s" % location)
    if json_data: logging.debug("Request data: " + json.dumps(json_data))
    result = requests.post(location,
                            data = json_data,
                            auth = (username, password),
                            verify = SSL_VERIFY,
                            headers = POST_HEADERS)
    logging.debug("Request result: " + json.dumps(result.json()))
    return result.json()

def main():
    # Read arguments from command line
    parser = argparse.ArgumentParser(description = "Satellite 6 - Content View Errata Updater v%s" % VERSION)
    parser.add_argument("--cv", help = "Comma-separated list of Content View names to update.", required = True)
    parser.add_argument("--type", type = str.lower, help = "Comma-separated list of errata types to include (bugfix, enhancement or security). Default: Security.", default = "security")
    parser.add_argument("--severity", type = str.lower, help = "Comma-separated list of errata severity level to include (critical, important, moderate or low). Default: Critical.", default = "critical")
    parser.add_argument("--from-date", help = "Date to use as a referente instead of Content View publishing date (YYYY/MM/DD).", default = "")
    parser.add_argument("--to-date", help = "Date to use as a referente to stop including erratas (YYYY/MM/DD).", default = "")
    parser.add_argument("--propagate", action = "store_true", help = "Propagate incremental version to Composite Content Views. Default: False.", default = False)
    parser.add_argument("--update-hosts", help = "Comma-separated list of lifecycle environments to update hosts with the included erratas.", default = "")
    parser.add_argument("--dry-run", action = "store_true", help = "Check for erratas but don't update Content Views nor update hosts.", default = False)
    parser.add_argument("-o", "--organization", help = "Satellite Organization to work with", default = "Default Organization")
    parser.add_argument("-u", "--username", help = "Username to authenticate with", required = True)
    parser.add_argument('-p', "--password", action = PasswordPrompt, nargs=0, help = "Prompt password to be used alongside with username", required=True)
    parser.add_argument('-e', "--endpoint", help = "Satellite base URL. Eg: https://satellite.default/", required = True)
    parser.add_argument("-d", "--debug", action = "store_true", help = "Show debug information (including GET/POST requests)", default = False)
    parser.add_argument("-V", "--version", action = "version", version = "%(prog)s " + VERSION)
    args = vars(parser.parse_args())

    # Calculate logging level for main program
    logging.getLogger("requests").setLevel(logging.WARNING)
    if args["debug"] is True:
        LOGGING_LEVEL = logging.DEBUG
    else:
        LOGGING_LEVEL = logging.INFO

    # Setup logging
    log = logging.getLogger(__name__)
    logging.basicConfig(level = LOGGING_LEVEL,
                    stream = sys.stdout,
                    format = "%(asctime)s %(levelname)s: %(message)s",
                    handlers = [logging.StreamHandler()])

    # API information
    endpoint = args["endpoint"]
    username = args["username"]
    password = args["password"]
    organization = args["organization"]
    satellite_api = endpoint + "api/v2/"
    katello_api = endpoint + "katello/api/v2/"
    tasks_api = endpoint + "foreman_tasks/api/"


    # Get organization
    logging.debug("Looking for organization information.")
    org = get_json(katello_api + "organizations/" + organization, username, password)

    # Compose search strings using input arguments
    severity_search = "(severity = " + ' or severity = '.join([x.capitalize() for x in args["severity"].split(',')]) + ")"
    type_search = "(type = " + ' or type = '.join(args["type"].split(',')) + ")"

    # Loop over content-views to find any new errata in their repositories
    for cv_name in args["cv"].split(","):
        logging.info("Processing content-view %s." % cv_name)
        errata_ids = []
        try:
            # Compose GET parameters to get given content view
            get_params = {
                "noncomposite": 1,
                "nondefault": 1,
                "search": "name=%s" % cv_name
            }
            cv = get_json(katello_api + "organizations/%s/content_views" % org["id"], username, password, get_params)["results"][0]
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
            errata_in_repo = get_json(katello_api + "errata", username, password, get_params)

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
                    logging.info("Selected content-view %s (version %s) as baseline to include %s erratas." % (cv["name"], version["version"], len(errata_ids)))
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
                incremental_update = post_json(katello_api + "content_view_versions/incremental_update", json.dumps(post_params), username, password)

                # Loop until task is finished
                while(incremental_update["pending"] != False):
                    logging.info("Waitting for publishing task to complete.")
                    time.sleep(60)
                    incremental_update = get_json(tasks_api + "tasks/" + incremental_update["id"], username, password)

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
                    template_json = get_json(satellite_api + 'job_templates', username, password, {"search": 'name = "Install Errata - Katello SSH Default"'})
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
                        job_execution = post_json(satellite_api + 'job_invocations', json.dumps(post_params), username, password)
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
