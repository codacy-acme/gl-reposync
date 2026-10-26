#!/usr/bin/env python3
"""Add GitLab Cloud repositories to Codacy, skipping archived and already-synced ones."""
import argparse
import os
import sys
import time
from urllib.parse import quote

import requests

GITLAB_API = "https://gitlab.com/api/v4"
CODACY_API = "https://api.codacy.com/api/v3"


def request(method, url, retries=5, **kwargs):
    """HTTP call that backs off on rate limits (429) and transient 5xx errors."""
    for attempt in range(retries):
        r = requests.request(method, url, timeout=60, **kwargs)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(int(r.headers.get("Retry-After", 2 ** attempt)))
            continue
        return r
    return r


def gitlab_projects(group, token):
    """Yield all non-archived projects in a GitLab group (incl. subgroups) or user namespace."""
    headers = {"PRIVATE-TOKEN": token}
    url = f"{GITLAB_API}/groups/{quote(group, safe='')}/projects"
    params = {"include_subgroups": "true", "archived": "false", "simple": "true", "per_page": 100}
    r = request("GET", url, headers=headers, params=params)
    if r.status_code == 404:  # not a group, try a personal namespace
        u = request("GET", f"{GITLAB_API}/users", headers=headers, params={"username": group})
        u.raise_for_status()
        if not u.json():
            sys.exit(f"GitLab: '{group}' is not a group or user visible to this token")
        url = f"{GITLAB_API}/users/{u.json()[0]['id']}/projects"
        params = {"archived": "false", "simple": "true", "per_page": 100}
        r = request("GET", url, headers=headers, params=params)
    while True:
        r.raise_for_status()
        for p in r.json():
            if not p.get("archived"):  # second guard, in case the API filter is ignored
                yield p["path_with_namespace"]
        nxt = r.headers.get("X-Next-Page")
        if not nxt:
            return
        params["page"] = nxt
        r = request("GET", url, headers=headers, params=params)


def codacy_existing(org, token):
    """Return the set of repo full paths already in Codacy for this organization."""
    headers = {"api-token": token}
    url = f"{CODACY_API}/organizations/gl/{quote(org, safe='')}/repositories"
    params = {"filter": "AllSynced", "limit": 100}
    existing = set()
    while True:
        r = request("GET", url, headers=headers, params=params)
        if r.status_code in (401, 403):
            sys.exit("Codacy: access denied. The API token must belong to an organization admin.")
        r.raise_for_status()
        body = r.json()
        existing.update(repo["fullPath"].lower() for repo in body["data"] if repo.get("fullPath"))
        cursor = (body.get("pagination") or {}).get("cursor")
        if not cursor:
            return existing
        params["cursor"] = cursor


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--group", required=True,
                    help="GitLab group (subgroups included) or username, e.g. my-group or my-group/team")
    ap.add_argument("--apply", action="store_true", help="Add repositories (default is a dry run)")
    args = ap.parse_args()

    gl_token = os.environ.get("GITLAB_TOKEN")
    codacy_token = os.environ.get("CODACY_API_TOKEN")
    if not gl_token or not codacy_token:
        sys.exit("Set GITLAB_TOKEN and CODACY_API_TOKEN environment variables.")

    org = args.group.strip("/").split("/")[0]  # Codacy org = top-level GitLab namespace
    existing = codacy_existing(org, codacy_token)
    projects = sorted(gitlab_projects(args.group.strip("/"), gl_token))
    to_add = [p for p in projects if p.lower() not in existing]

    print(f"GitLab (non-archived): {len(projects)} | already in Codacy: {len(projects) - len(to_add)} "
          f"| to add: {len(to_add)}")
    if not args.apply:
        for p in to_add:
            print(f"  would add: {p}")
        print("Dry run only. Re-run with --apply to add them.")
        return

    failed = 0
    for p in to_add:
        r = request("POST", f"{CODACY_API}/repositories", headers={"api-token": codacy_token},
                    json={"provider": "gl", "repositoryFullPath": p})
        if r.ok:
            print(f"  added: {p}")
        else:
            failed += 1
            print(f"  FAILED: {p} ({r.status_code} {r.text[:200]})", file=sys.stderr)
    print(f"Done. Added {len(to_add) - failed}, failed {failed}.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
