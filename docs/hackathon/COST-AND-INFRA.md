# What this project costs

What PlateGap costs to run on this AWS account, and why each service is or is
not in the stack. For judges and for anyone sizing something similar. The
design reasoning is in [ARCHITECTURE.md](ARCHITECTURE.md); the README's
[infrastructure table](../../README.md#infrastructure-decisions-and-what-they-cost)
has the same decisions in short.

Checked against account 905543840246 on 2026-09-20, not assumed.

## What the account is entitled to

`aws freetier get-free-tier-usage` returns seven rows for this account and
**every one is `Always Free`**. There are no `12 Months Free` rows, so the old
12-month EC2, RDS and S3 allowances do not apply. Month-to-date net amortized
cost is $0.00, because credits are absorbing the EC2 instance.

So two things matter: the Always Free allowances, which never expire, and the
$50 of credits that expire next month.

## Always Free allowances

| Service | Allowance per month | What we use |
| --- | --- | --- |
| Lambda | 1,000,000 requests + 400,000 GB-seconds | a few thousand requests |
| Lambda Function URL | no additional charge; part of Lambda | 1 endpoint |
| DynamoDB | 25 GB storage; on-demand 2.5 M read + 1 M write request units | one small row a day |
| CloudFront | 1 TB out + 10 M requests + 2 M Functions invocations | well under a GB |
| CloudWatch Logs | 5 GB ingestion | a few MB |
| SNS / SQS | 1 M requests each | unused |

A hackathon demo does not come within three orders of magnitude of any of
these.

## What is not free, and what it comes to

| Service | Rate | Our usage | Cost |
| --- | --- | --- | --- |
| S3 | ~$0.023/GB-month + request charges | a static site of about 160 KB | **under $0.01/month** |
| Bedrock Nova Lite, `explain` | $0.06 / $0.24 per M tokens in/out | one call measured at 732 in, ~130 out; 2,000 of them | **~$0.15 total** |
| Bedrock Nova Lite, `scan` | same rate | one uploaded menu measured at 1,862 in, ~1,100 out; 200 of them | **~$0.08 total** |
| DynamoDB, on-demand | ~$0.625–1.25 per M writes | one write per scan, capped at 500 a day | **under $0.02/month** |
| Bedrock Nova Micro (not used) | $0.035 / $0.14 per M tokens | same volume as `explain` | ~$0.09 total |
| Bedrock Claude Haiku 4.5 (not used) | $1 / $5 per M tokens | same volume as `explain` | ~$2.76 total |
| EC2 t4g.medium | ~$0.0336/hr | already running, by choice, outside the app | ~$24/month, paid from credits |

**Leaving out the EC2 box, which I am running on credits by choice, the whole
project costs under one dollar for the entire hackathon.**

## The backstop: a $5 budget

Every other control bounds spending where it happens: the account's
concurrency limit of 10 bounds the request rate, `scan_daily_cap` bounds the
only action that pays for a model, and the Always Free allowances cover the
rest. `infra/budget.tf` is for the case none of those anticipated: a $5 a
month AWS Budget that emails on a forecast breach and again at 80% and 100% of
actual.

The one setting that makes it work is `include_credit = false`. By default a
budget subtracts credits before comparing against the threshold, so an account
carrying $50 of them reads $0.00 whatever it is doing, and the first email
arrives once the credits are gone. Excluding them makes the alert measure
usage, which is the thing worth hearing about while it can still be stopped.

The alert address is not in this repository. It is a real inbox and the
repository is public, so `budget_alert_email` has no default and is passed at
apply time. Unset, the budget is not created; nothing in CI runs Terraform, so
nothing breaks. The first two budgets on an account are free.

## Why the model is the cheap one anyway

Money is not the constraint. The constraint is that **$50 of credits expires
next month**, and expiring credits are worth nothing.

That inverts one decision in principle. Bedrock is the only line item that
costs real money and the only one that affects output quality, so the instinct
should be to economise on servers rather than on the model. Three dollars
against a balance that evaporates regardless is not a saving.

In practice it did not come to that, for two reasons.

1. **Haiku is not available without a form.** Anthropic models on Bedrock need
   a one-time use-case form submitted from the console before they answer.
   Without it the call fails with `ResourceNotFoundException: Model use case
   details have not been submitted for this account`. That is an entitlement,
   not a quota: the quotas page shows Haiku 4.5 at 5 M TPM while every
   invocation is refused. Amazon's own models need no form.
2. **The quality gap did not show up.** The same `explain` prompt was put to
   Nova Lite and Nova Micro. Both produced a correct, readable paragraph, and
   both passed the reconciliation check that throws an explanation away when a
   number in it does not match the solve. There was nothing to buy.

So `explain` runs on Nova Lite at about $0.075 per thousand calls, and the form
is not worth filling for this project. `PLATEGAP_EXPLAIN_MODEL` makes it one
environment variable to revisit.

Menu parsing costs nothing: `solver/menutext.py` matches pasted text against
the catalog with string normalisation and containment scoring, and never calls
a model. Only `scan`, which reads an uploaded file, uses one.

## The EC2 box stays, out of the request path

[ARCHITECTURE.md](ARCHITECTURE.md) suggested stopping the `t4g.medium` to save
credits. That was wrong for this account: the credits expire next month
whether or not they are spent, so running the instance turns something
worthless into something useful. It stays running.

It stays out of the request path for a reason that still holds. The ship gate
is evaluated from Oct 2 through the week of Oct 19, and an instance in the
critical path is the likeliest way to lose the submission. The judged URL is
CloudFront and Lambda. The box is for everything else: building, video
rendering, other hackathons.

## The stack as deployed

| Service | Job | Cost |
| --- | --- | --- |
| S3 + CloudFront | The static front end, over HTTPS | ~$0.01/month |
| Lambda + Function URL | Every API action: `solve`, `frontier`, `audit`, `parse`, `scan`, `explain` and the rest | free |
| Bedrock (Nova Lite) | Writing up a solve, and transcribing an uploaded menu | ~$0.23 for the hackathon, at the volumes above |
| DynamoDB (on-demand) | One row a day, counting what `scan` may spend | <$0.02/month |
| CloudWatch Logs | Structured logs, 7-day retention | free |
| AWS Budgets | $5/month alert on gross usage, as a backstop | free |

DynamoDB is there for one reason only: the daily `scan` counter, the one number
in the project that cannot be recomputed from anything else. The catalog ships
in the Lambda package and a shared menu travels in the URL fragment, so no
data needs a database.

No API Gateway, no Textract, no Step Functions and no EC2 in the request path.
[ARCHITECTURE.md](ARCHITECTURE.md#aws-architecture--deliberately-small) gives
the reason for each.

## Sources

- [AWS Free Tier now offers $200 in credits and 6-month free plan](https://aws.amazon.com/about-aws/whats-new/2025/07/aws-free-tier-credits-month-free-plan/)
- [AWS Free Tier in 2026 — what actually stays free](https://dev.to/aiunplugged/aws-free-tier-in-2026-what-actually-stays-free-5bcp)
- [AWS Free Tier Explained: What's Actually Free in 2026](https://spot.rackspace.com/blog/aws-free-tier)
- [Amazon CloudFront pricing](https://aws.amazon.com/cloudfront/pricing/)
- [Amazon Bedrock pricing in 2026](https://www.cloudzero.com/blog/amazon-bedrock-pricing/)
