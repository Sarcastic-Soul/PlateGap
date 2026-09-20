# What this project actually costs

Checked against account 905543840246 on 2026-09-20, not assumed.

`aws freetier get-free-tier-usage` returns seven rows for this account and
**every one is `Always Free`**. There are no `12 Months Free` rows. The old
12-month EC2 / RDS / S3 allowances do not apply here. Month-to-date net
amortized cost is $0.00 — credits are absorbing the EC2 instance.

So the only two things that matter: the Always Free allowances, which never
expire and apply to every account, and the $50 of credits expiring next month.

## Always Free — never expires, applies to us

| Service | Allowance per month | What we'd use |
| --- | --- | --- |
| Lambda | 1,000,000 requests + 400,000 GB-seconds | a few thousand requests |
| Lambda Function URL | no additional charge — part of Lambda | 1 endpoint |
| DynamoDB | 25 GB storage; on-demand 2.5 M read + 1 M write request units | a few MB, a few thousand ops |
| CloudFront | 1 TB out + 10 M requests + 2 M Functions invocations | well under a GB |
| CloudWatch Logs | 5 GB ingestion | a few MB |
| SNS / SQS | 1 M requests each | unused |

A hackathon demo does not come within three orders of magnitude of any of these.

## Not free — and what it actually comes to

| Service | Rate | Our usage | Cost |
| --- | --- | --- | --- |
| S3 | ~$0.023/GB-month + request charges | a ~20 MB static site | **under $0.01/month** |
| Bedrock Nova Lite | $0.06 / $0.24 per M tokens in/out | one `explain` call measured at 732 in, ~130 out; 2,000 of them | **~$0.15 total** |
| Bedrock Nova Lite, `scan` | same rate | one uploaded menu measured at 1,862 in, ~1,100 out; 200 of them | **~$0.08 total** |
| DynamoDB, on-demand | ~$0.625–1.25 per M writes | one write per scan, capped at 500/day | **under $0.02/month** |
| Bedrock Nova Micro | $0.035 / $0.14 per M tokens | same volume | ~$0.09 total |
| Bedrock Claude Haiku 4.5 | $1 / $5 per M tokens | same volume | ~$2.76 total |
| EC2 t4g.medium | ~$0.0336/hr | already running, by choice | ~$24/month, paid from credits |

**The whole project, excluding the EC2 you're deliberately burning credits on,
costs under one dollar for the entire hackathon.**

## The backstop

Every other control in this project bounds spending where the spending
happens: reserved concurrency bounds the request rate, `scan_daily_cap` bounds
the only action that pays a model, the Always Free allowances cover the rest.
`infra/budget.tf` is for the case none of those anticipated, and it is a $5 a
month AWS Budget that emails on a forecast breach and again at 80% and 100% of
actual.

The one setting that makes it work is `include_credit = false`. By default a
budget subtracts credits before comparing against the threshold, so an account
carrying $50 of them reads $0.00 no matter what it is doing, and the first
email arrives once the credits are already gone. Excluding them makes the alert
measure usage, which is the thing worth hearing about while it can still be
stopped.

The address is not in this repository. It is a real inbox and the repository is
public, so `budget_alert_email` has no default and is passed at apply time;
unset, the budget is simply not created, and nothing in CI runs Terraform so
nothing breaks. Budgets are free for the first two per account.

## The actual insight

Money is not the constraint. The constraint is that **$50 expires next month**,
and expiring credits are worth nothing.

That inverts one decision in principle: Bedrock is the only line item here
that costs real money and the only one that affects output quality, so the
instinct should be to economize on servers rather than on the model. Three
dollars against a balance that evaporates regardless is not a saving.

In practice it did not come to that, for two reasons.

The first is that Anthropic models on Bedrock need a one-time use-case form
submitted from the console before they answer at all. Without it the call
fails with `ResourceNotFoundException: Model use case details have not been
submitted for this account`, which is an entitlement, not a quota — the quotas
page cheerfully shows Haiku 4.5 at 5 M TPM while every invocation is refused.
Amazon's own models need no form.

The second is that the quality gap did not show up. The same `explain` prompt
was put to Nova Lite and Nova Micro: both produced a correct, readable
paragraph and both passed the reconciliation check that throws an explanation
away when a number in it does not match the solve. There was nothing to buy.

So `explain` runs on Nova Lite, at about $0.075 per thousand calls, and the
form is not worth filling for this project. `PLATEGAP_EXPLAIN_MODEL` makes it
one environment variable to revisit.

There are no menu-parsing calls to economize on: `solver/menutext.py` matches
pasted text against the catalog with string normalisation and containment
scoring, and never invokes a model.

## Correction on the EC2 box

Last turn I suggested stopping it. That was wrong given your situation — the
credits expire next month whether or not you spend them, so running the
instance converts something worthless into something useful. Keep it.

It stays out of the request path for a different reason, which still holds: the
ship gate is evaluated from Oct 2 through the week of Oct 19, and an instance
in the critical path is the likeliest way to lose the entire submission. The
judged URL is CloudFront and Lambda. The box is yours for whatever else you want
— building, video rendering, other hackathons.

## Final stack

```
S3 + CloudFront          static frontend, HTTPS          ~$0.01/mo
Lambda + Function URL    solve · frontier · audit · parse · scan · explain    free
DynamoDB (on-demand)     shared menu library + usage counters          free
Bedrock                  Nova Lite: the explanation, and reading an    ~$0.15 total
                         uploaded menu
DynamoDB                 one row a day, capping what scan may spend   <$0.02/month
CloudWatch Logs          structured logs, Logs Insights for metrics    free
AWS Budgets              $5/month alert on gross usage, as a backstop   free
```

DynamoDB earns its place only because of the shared menu library — strangers
landing on the site pick from menus other people already added, which is the
feature that makes the product generic rather than personal. If that feature is
cut, the table goes with it and the app still works from bundled presets.

Five services. No API Gateway, no Textract, no Step Functions, no EC2 in the
request path — each omission justified in the write-up.

## Sources

- [AWS Free Tier now offers $200 in credits and 6-month free plan](https://aws.amazon.com/about-aws/whats-new/2025/07/aws-free-tier-credits-month-free-plan/)
- [AWS Free Tier in 2026 — what actually stays free](https://dev.to/aiunplugged/aws-free-tier-in-2026-what-actually-stays-free-5bcp)
- [AWS Free Tier Explained: What's Actually Free in 2026](https://spot.rackspace.com/blog/aws-free-tier)
- [Amazon CloudFront pricing](https://aws.amazon.com/cloudfront/pricing/)
- [Amazon Bedrock pricing in 2026](https://www.cloudzero.com/blog/amazon-bedrock-pricing/)
