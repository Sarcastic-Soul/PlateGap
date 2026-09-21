#!/usr/bin/env python3
"""Export the coding agent's AWS calls from CloudTrail, with secrets removed.

The hackathon asks for documented proof that a coding agent was connected to
the AWS account. A chat screenshot proves nothing. CloudTrail does: every call
that built this stack is in the account's own event history, timestamped, with
the user agent that made it.

Three user agents appear in the build window and they tell the whole story:

  aws-cli/...            Claude Code driving the AWS CLI directly
  APN/1.0 HashiCorp/...  Terraform, run by the agent's bootstrap script
  aws-cli/... as a role  GitHub Actions, deploying over OIDC with no stored key

Run it with credentials that can read CloudTrail:

    uv run python scripts/export_cloudtrail.py --since 2026-09-19T00:00:00Z

Output goes to docs/hackathon/evidence/. Anything that could be a credential
or locate a person is dropped before anything is written -- see REDACT. The
file is committed to a public repository, so this is not optional.
"""

import argparse
import collections
import json
import os
import pathlib
import subprocess
import sys

# Fields that either are a credential, or identify where a person was sitting.
REDACT = ("accessKeyId", "sourceIPAddress", "sessionIssuer", "webIdFederationData",
          "attributes", "principalId", "arn", "accountId", "recipientAccountId",
          "sharedEventID", "userName")

# Calls that changed something. Reads are noise here -- the claim being
# evidenced is that an agent *built* the stack, not that it looked at it.
WRITE_PREFIXES = ("Create", "Update", "Put", "Delete", "Add", "Attach", "Tag",
                  "Remove", "Set", "Publish", "Invalidate")

# AWS talking to itself. The SSM agent on the hackathon EC2 box alone heartbeats
# a few hundred UpdateInstanceInformation calls a day, which would bury the
# handful of calls that actually mean something.
MACHINE_NOISE = ("amazon-ssm-agent", "awslambda-worker", ".amazonaws.com",
                 "Go-http-client")

# One row per client, not one per patch version of its user agent string.
CLIENTS = (
    ("aws-cli/", "AWS CLI, driven by Claude Code"),
    ("HashiCorp/1.0 Terraform", "Terraform, run by the agent's bootstrap script"),
    ("aws-sdk-js/", "GitHub Actions deploying over OIDC"),
    ("Mozilla/", "A browser (the AWS console)"),
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "hackathon" / "evidence"


def fetch(since, limit):
    out = subprocess.run(
        ["aws", "cloudtrail", "lookup-events", "--start-time", since,
         "--max-items", str(limit), "--query", "Events[].CloudTrailEvent",
         "--output", "json"],
        capture_output=True, text=True, check=True).stdout
    return [json.loads(e) for e in json.loads(out)]


def account_id():
    return subprocess.run(
        ["aws", "sts", "get-caller-identity", "--query", "Account", "--output", "text"],
        capture_output=True, text=True, check=True).stdout.strip()


def scrub(value, account):
    """Drop credential-ish keys, and blank the account number wherever it

    appears -- it is threaded through hundreds of ARNs inside
    requestParameters, so dropping whole keys is not enough on its own."""
    if isinstance(value, dict):
        return {k: scrub(v, account) for k, v in value.items() if k not in REDACT}
    if isinstance(value, list):
        return [scrub(v, account) for v in value]
    if isinstance(value, str) and account in value:
        return value.replace(account, "ACCOUNT")
    return value


def client_of(event):
    agent = event.get("userAgent", "unknown")
    # The user agent alone cannot tell the agent's CLI from the deploy
    # workflow's, because the workflow shells out to the same AWS CLI. The
    # identity can: the workflow holds a role assumed over OIDC, and the
    # account setup before the build ran as root.
    kind = event.get("userIdentity", {}).get("type")
    if kind == "AssumedRole" and "aws-cli/" in agent:
        return "GitHub Actions deploying over OIDC"
    if kind == "Root" and "aws-cli/" in agent:
        return "AWS CLI as the root user, creating the IAM user"
    for marker, label in CLIENTS:
        if marker in agent:
            return label
    return agent[:60]


def interesting(event):
    name = event.get("eventName", "")
    agent = event.get("userAgent", "")
    # CloudTrail marks sign-in token grants such as CreateOAuth2Token as reads
    # although their names start with Create.
    if event.get("readOnly") is True:
        return False
    if any(marker in agent for marker in MACHINE_NOISE):
        return False
    return any(name.startswith(prefix) for prefix in WRITE_PREFIXES)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="2026-09-19T00:00:00Z")
    parser.add_argument("--limit", type=int, default=3000)
    args = parser.parse_args()

    account = account_id()
    events = fetch(args.since, args.limit)
    writes = sorted((e for e in events if interesting(e)),
                    key=lambda e: e["eventTime"])
    if not writes:
        sys.exit("no write events in the window -- widen --since")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cloudtrail-build-window.json").write_text(
        json.dumps([scrub(e, account) for e in writes], indent=1, sort_keys=True) + "\n")

    by_agent = collections.Counter(client_of(e) for e in writes)
    by_call = collections.Counter(e["eventName"] for e in writes)
    lines = [
        "# CloudTrail: what the coding agent did to this account",
        "",
        "Generated by `scripts/export_cloudtrail.py`. Every mutating API call in",
        "the build window, straight out of the account's own event history.",
        "Access key ids, IP addresses, ARNs and the account number are stripped",
        "before the file is written, and AWS-internal chatter (the SSM agent on the",
        "EC2 box, Lambda's own workers) is left out -- the full record is in",
        "CloudTrail itself.",
        "",
        "| | |",
        "| --- | --- |",
        "| Window | %s to %s |" % (writes[0]["eventTime"], writes[-1]["eventTime"]),
        "| Mutating calls | %d |" % len(writes),
        "| Distinct API calls | %d |" % len(by_call),
        "",
        "## Who made the calls",
        "",
        "| Calls | Client |",
        "| --- | --- |",
    ]
    lines += ["| %d | %s |" % (n, agent) for agent, n in by_agent.most_common()]
    lines += ["", "## What was called", "", "| Calls | API |", "| --- | --- |"]
    lines += ["| %d | %s |" % (n, name) for name, n in by_call.most_common(40)]
    lines += ["", "Raw events: `cloudtrail-build-window.json`.", ""]
    (OUT / "README.md").write_text("\n".join(lines))

    print("wrote %d events to %s" % (len(writes), OUT))


if __name__ == "__main__":
    main()
