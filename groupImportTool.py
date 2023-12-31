#!/usr/bin/env python3

import sys
import argparse
import requests
import json
from csv import reader, writer
from ratelimit import limits, sleep_and_retry

# Command line argument parsing
parser = argparse.ArgumentParser()
parser.add_argument("-x", "--quiet", help = "reduces output verbosity", action = "store_false")
parser.add_argument("-e", "--environment", help = "<REQUIRED> the ID of the environment in which the users you wish to delete are stored", required = True)
parser.add_argument("-c", "--client", help = "<REQUIRED> the ID of an app configured with the ability to delete users", required = True)
parser.add_argument("-s", "--secret", help = "<REQUIRED> the corresponding secret of an app configured with the ability to delete users", required = True)
parser.add_argument("-p", "--population", help = "the ID of the population in which the users you wish to delete are stored")
parser.add_argument("-q", "--query", nargs="+", help = "a SCIM 2.0 filter")
parser.add_argument("-w", "--skip", nargs="+", help = "user IDs to be skipped during deletion")
parser.add_argument("-u", "--users", nargs="+", help = "userIDs to process")
parser.add_argument("-g", "--groups", nargs="+", help = "groups to add users to")
args = parser.parse_args()

ENVIRONMENT_ID = args.environment
CLIENT_ID = args.client
CLIENT_SECRET = args.secret
POPULATION_ID = args.population
SKIP_USER_IDS_ARRAY = args.skip
USERS_TO_ADD = args.users
GROUPS_TO_UPDATE = args.groups
QUERY = ""

if POPULATION_ID:
    QUERY = "(population.id eq \"{}\")".format(POPULATION_ID)

if POPULATION_ID and args.query:
    QUERY = QUERY + " and (" + " ".join(args.query) + ")"
elif args.query:
    QUERY = " ".join(args.query)

if SKIP_USER_IDS_ARRAY:
    SKIP_USER_IDS = set(SKIP_USER_IDS_ARRAY)
else:
    SKIP_USER_IDS = []

VERBOSE = args.quiet
MAX_ATTEMPTS = 3

# Log failures
def log_error(description, r):
    print("[ERROR] " + description + " ({}):".format(str(r.status_code)))
    print("[ERROR] Request: " + r.request.url)
    if r.request.body:
        print("[ERROR] " + r.request.body)
    print("[ERROR] " + r.text)

# Constructs the users URL with the given query, if any
def build_query_url():
    global QUERY
    url = "https://api.pingone.com/v1/environments/{}/users".format(ENVIRONMENT_ID)
    if QUERY:
        url += "?filter={}".format(QUERY)
    return url

# Constructs the users URL with the parameter
def build_user_url(user_id):
    url = "https://api.pingone.com/v1/environments/{}/users".format(ENVIRONMENT_ID)
    if QUERY:
        url += "?filter={} eq".format(user_id)
    return url

# Request a token with client credentials
def get_token():
    global token, BEARER_HEADER
    token_url = "https://auth.pingone.com/{}/as/token?grant_type=client_credentials".format(ENVIRONMENT_ID)

    try:
        r = requests.post(
            token_url,
            headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            auth = (CLIENT_ID, CLIENT_SECRET))
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        log_error("Error requesting access token", r)
        sys.exit()

    token = r.json()["access_token"]
    BEARER_HEADER = {"Authorization": "Bearer {}".format(token)}

# TODO:  change to a function that will look over the group json file to find the group id
@sleep_and_retry
@limits(calls = 95, period = 1)
def find_group(groupid):


# Add user to group
@sleep_and_retry
@limits(calls = 95, period = 1)
def add_user(user):
    user_id = user["id"]
    group_url = "https://api.pingone.com/v1/environments/{}/users/{}".format(ENVIRONMENT_ID, user_id)
    attempt = 1
    while (attempt <= MAX_ATTEMPTS):
        try:
            r = requests.delete(group_url, headers = BEARER_HEADER, timeout=5)
            r.raise_for_status()
            if VERBOSE:
                print("Adding user {} ({}) to group".format(user["username"], user_id))
            break
        except requests.exceptions.HTTPError as e:
            # If the status code is 401, refresh token and retry
            if e.response.status_code == 401:
                if VERBOSE:
                    print("Refreshing token...")
                get_token()
            else:
                log_error("Error adding user {}".format(user_id), r)
        if VERBOSE:
            print("Retrying... attempt {}/{}".format(attempt, MAX_ATTEMPTS))
        attempt += 1

# Main
get_token()

line = 0
with open(USERS_TO_ADD, 'r') as read_obj:
    csv_reader = reader(read_obj)
    header = next(csv_reader)
    # Check file as empty
    if header is not None:
        # Iterate over each row after the header in the csv
        for row in csv_reader:
            if len(row) > 2:
                # increment our line
                line += 1
                # Row is a list that represents a row in csv.
                username = row[0]
                groups = row[34]
                users_url = build_user_url(username)

                attempt = 1
                while (attempt <= MAX_ATTEMPTS):
                    try:
                        r = requests.get(users_url, headers = BEARER_HEADER)
                        r.raise_for_status()
                        msg = "{} user(s) found in environment {}".format(str(r.json()["count"]), ENVIRONMENT_ID)
                        if QUERY:
                            msg += " matching {}".format(QUERY)
                        print(msg)
                        add_user(r.json())
                        break
                    except requests.exceptions.HTTPError as e:
                        # If the status code is 401, refresh token and retry
                        if e.response.status_code == 401:
                            if VERBOSE:
                                print("Refreshing token...")
                            get_token()
                        else:
                            log_error("Error fetching users", r)
                    if VERBOSE:
                        print("Retrying... attempt {}/{}".format(attempt, MAX_ATTEMPTS))
                    attempt += 1

print("Done")