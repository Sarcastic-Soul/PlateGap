"""A hard daily ceiling on what the public endpoint may spend.

Every other action in this project is arithmetic on our own Lambda, so the
worst a stranger can do with them is use up a free tier. `scan` is different:
it calls Bedrock, and Bedrock bills per call. The Function URL is public and
unauthenticated by design -- a tool anyone should be able to try without
signing up -- which means "anyone may use this" and "anyone may spend my
money" are the same sentence unless something counts.

Reserved concurrency already bounds the *rate*: ten executions, each holding
its slot for the ten seconds a page of PDF takes, is about one scan a second.
That is roughly $34 a day, which is more than this project's whole budget.
So the rate limit is not the control. This is.

Why a counter and not a rate limit per caller
---------------------------------------------

There is no caller to count. A Function URL has no API keys and no usage
plans, and per-IP limiting would mean WAF, whose monthly minimum is several
times the loss it would be preventing. Counting the spend itself is both
cheaper and a better fit: what matters is not who is calling but how much has
been spent today.

Why the number lives in DynamoDB
--------------------------------

It has to be one number, and Lambda has nowhere to put one. A counter held in
a module global is per warm container, so the real ceiling becomes that
number times however many containers are alive, resetting whenever AWS
recycles one -- an approximation, when the thing being approximated is money.
`UpdateItem` with an `ADD` is a single atomic round trip that returns the new
total, so ten containers racing get ten different numbers and exactly one of
them is the five hundredth.

This is the only shared, durable state in the project. The catalog is static,
the metrics are logs, and a menu someone built travels in the URL fragment.
It is worth a table for the one thing that genuinely cannot be recomputed.

The cap is per day and not per lifetime
---------------------------------------

A lifetime cap eventually trips and then the feature is gone, possibly at
three in the morning with nobody watching, and it never comes back without a
person. A daily cap bounds the loss to one day of it and then heals itself.

Failing closed
--------------

If the count cannot be read or written, the scan is refused. The alternative
reads better -- do not let the accounting break the feature -- but it means
anything that breaks DynamoDB also removes the ceiling, which is the one
thing this file exists to hold up. Refusing costs a person the upload and
leaves the paste box, which does the same job. Being wrong the other way
costs money that cannot be got back.
"""

import datetime
import os

# Empty means no ceiling, which is what a checkout and the test suite want:
# neither of them can reach Bedrock in the first place. Terraform always sets
# this on the deployed function, so "unset" never happens in production.
TABLE = os.environ.get("PLATEGAP_SCAN_TABLE", "")

REGION = os.environ.get("AWS_REGION", "us-east-1")

DEFAULT_DAILY_CAP = 500

# Yesterday's row is of no further use, but keeping a week of them means the
# question "how much did this actually get used" has an answer.
KEEP_DAYS = 7

_TABLE = None


def daily_cap():
    try:
        cap = int(os.environ.get("PLATEGAP_SCAN_DAILY_CAP", DEFAULT_DAILY_CAP))
    except (TypeError, ValueError):
        return DEFAULT_DAILY_CAP
    return cap if cap > 0 else DEFAULT_DAILY_CAP


def today():
    """UTC, so the day the ceiling resets is the same day everywhere."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _table():
    global _TABLE
    if _TABLE is None:
        import boto3
        _TABLE = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
    return _TABLE


def _refusal(used, cap):
    return ("this has already read %d menus today, which is the daily limit "
            "on what a free public endpoint will spend. It resets at midnight "
            "UTC. Paste the menu as text instead -- that runs here and has no "
            "limit at all." % cap)


def take(count=None):
    """Claim one scan against today's budget.

    Returns `None` when the scan may go ahead, or a sentence explaining why
    not. The claim happens before Bedrock is called and is not given back if
    the call then fails: a refused scan costs nothing, and undercounting what
    has been spent is the only error worth avoiding here.

    `count` is the seam the tests use: anything callable that takes the day
    and returns the running total for it.
    """
    if not TABLE and count is None:
        return None

    cap = daily_cap()
    try:
        used = (count or _count)(today())
    except Exception as problem:
        # Fail closed. See the module docstring: the ceiling is the point.
        return ("the daily limit on reading menus could not be checked, so "
                "this one was not attempted (%s). Paste the menu as text "
                "instead." % type(problem).__name__)

    if used > cap:
        return _refusal(used, cap)
    return None


def _count(day):
    """Add one to today's tally and hand back the new total.

    One round trip, atomic, and it returns the value it wrote, so two
    containers incrementing at the same instant get two different numbers
    rather than both reading the same one and both deciding they are under.
    """
    answer = _table().update_item(
        Key={"day": day},
        UpdateExpression=("ADD scans :one "
                          "SET expires = if_not_exists(expires, :ttl)"),
        ExpressionAttributeValues={
            ":one": 1,
            ":ttl": int(datetime.datetime.now(datetime.timezone.utc).timestamp())
                    + KEEP_DAYS * 86400,
        },
        ReturnValues="UPDATED_NEW")
    return int(answer["Attributes"]["scans"])
