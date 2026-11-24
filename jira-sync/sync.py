#!/usr/bin/python3
"""One-way sync of Jira tickets assigned to me into the Todoist "tickets" project.

- Open assigned tickets missing from Todoist are added.
- Each task sits in a section named after its Jira status (lowercased).
- Tasks whose ticket is Done are completed.
- Empty sections are removed.

Tokens come from the macOS Keychain (services: todoist-api, jira-api).
"""
import base64
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime

JIRA_SITE = "https://tripadvisor.atlassian.net"
JIRA_EMAIL = "jbradbeer@tripadvisor.com"
TODOIST = "https://api.todoist.com/api/v1"
PROJECT = "tickets"
KEY_RE = re.compile(r"/browse/([A-Z][A-Z0-9]+-\d+)")


def keychain(service):
    return subprocess.run(
        ["/usr/bin/security", "find-generic-password", "-s", service, "-w"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def request(url, headers, body=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
    for k, v in headers.items():
        req.add_header(k, v)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


class Todoist:
    def __init__(self, token):
        self.h = {"Authorization": f"Bearer {token}"}

    def get_all(self, path, **params):
        out, cursor = [], None
        while True:
            q = dict(params, limit=200, **({"cursor": cursor} if cursor else {}))
            page = request(f"{TODOIST}/{path}?{urllib.parse.urlencode(q)}", self.h)
            out += page["results"]
            cursor = page.get("next_cursor")
            if not cursor:
                return out

    def post(self, path, body=None, method=None):
        return request(f"{TODOIST}/{path}", self.h, body if body is not None else {}, method)

    def delete(self, path):
        return request(f"{TODOIST}/{path}", self.h, method="DELETE")


def jira_search(auth, jql):
    h = {"Authorization": f"Basic {auth}", "Accept": "application/json"}
    issues, token = [], None
    while True:
        body = {"jql": jql, "fields": ["summary", "status"], "maxResults": 100}
        if token:
            body["nextPageToken"] = token
        page = request(f"{JIRA_SITE}/rest/api/3/search/jql", h, body)
        issues += page["issues"]
        token = page.get("nextPageToken")
        if not token:
            return issues


def main():
    td = Todoist(keychain("todoist-api"))
    auth = base64.b64encode(f"{JIRA_EMAIL}:{keychain('jira-api')}".encode()).decode()
    # Jira answers searches with bad credentials as anonymous (empty results), so check auth explicitly.
    request(f"{JIRA_SITE}/rest/api/3/myself", {"Authorization": f"Basic {auth}"})

    project_id = next(p["id"] for p in td.get_all("projects") if p["name"] == PROJECT)
    tasks = {}
    for t in td.get_all("tasks", project_id=project_id):
        m = KEY_RE.search(t["content"])
        if m:
            tasks[m.group(1)] = t

    issues = {i["key"]: i for i in jira_search(auth, "assignee = currentUser() AND statusCategory != Done")}
    if tasks:
        keys = ",".join(k for k in tasks if k not in issues)
        if keys:
            issues.update({i["key"]: i for i in jira_search(auth, f"key in ({keys})")})

    sections = {s["name"]: s["id"] for s in td.get_all("sections", project_id=project_id)}

    def section_for(status):
        name = status.lower()
        if name not in sections:
            sections[name] = td.post("sections", {"name": name, "project_id": project_id})["id"]
            log(f"created section '{name}'")
        return sections[name]

    for key, issue in issues.items():
        status = issue["fields"]["status"]
        done = status["statusCategory"]["key"] == "done"
        task = tasks.get(key)
        if task is None:
            if done:
                continue
            content = f"[{key.lower()}]({JIRA_SITE}/browse/{key}) {issue['fields']['summary'].lower()}"
            td.post("tasks", {"content": content, "project_id": project_id,
                              "section_id": section_for(status["name"])})
            log(f"added {key}")
        elif done:
            td.post(f"tasks/{task['id']}/close")
            log(f"completed {key}")
        else:
            target = section_for(status["name"])
            if task.get("section_id") != target:
                td.post(f"tasks/{task['id']}/move", {"section_id": target})
                log(f"moved {key} to '{status['name'].lower()}'")

    used = {t["section_id"] for t in td.get_all("tasks", project_id=project_id)}
    for name, sid in sections.items():
        if sid not in used:
            td.delete(f"sections/{sid}")
            log(f"removed empty section '{name}'")


def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M} {msg}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"error: {e}")
        sys.exit(1)
