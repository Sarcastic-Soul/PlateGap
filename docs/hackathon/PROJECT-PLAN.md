# PlateGap — build plan

Decided 2026-09-20. Due 2026-10-02 23:59 PT. Twelve days.
Category `#daily-life-enhancement` · Lane `#startup`

Design detail in `ARCHITECTURE.md`. Competitive position in `README.md` ("The field so far").

## Verified on the account already

- `905543840246` / `us-east-1` / IAM user `sarcastic-soul`
- EC2 `i-0ee8eb55a5eadba6c` "hackathon-box", t4g.medium, running, 44.211.149.117
- Bedrock: `amazon.nova-lite-v1:0`, `amazon.nova-micro-v1:0` and
  `us.anthropic.claude-haiku-4-5-20251001-v1:0` all invoke successfully
- Textract `DetectDocumentText` responds
- No existing S3 buckets, Lambdas or DynamoDB tables — clean slate
- Local: Terraform 1.9.0, Node 22, Python 3.12, Docker, Kiro 1.1.14

## Schedule

Two dates are immovable: **a live public URL by Sep 26**, and **real users by
Sep 30**. Everything else can slip.

| Day | Work | Done when |
| --- | --- | --- |
| **Sep 20–21** | Two-phase simplex with duals, pure Python. scipy differential test harness. LP model for the two-class formulation. | Several hundred random instances match scipy to 1e-6; duals satisfy complementary slackness |
| **Sep 22** | Nutrient table: USDA FDC base ingredients + recipe decomposition for composite dishes. Sources cited in-repo. Digitize the IIIT menu as the first preset. | ~150 foods with nutrients per 100g, every row traceable to a source |
| **Sep 23** | Regional default price sets (₹ and $), all editable in the UI. Anish's local survey fills the ₹ defaults. Build the dining-hall and generic presets. | Three presets each give a sensible answer with zero typing |
| **Sep 24–25** | Terraform stack: S3 + CloudFront + one Lambda behind a Function URL. `solve` and `frontier` live. | `terraform apply` from scratch produces a working endpoint |
| **Sep 26** | **Live public URL up.** Minimal but real frontend against `/solve`. | Ship gate satisfied, 6 days early |
| **Sep 27** | `/audit` — week aggregation + inverse-optimization search over menu additions. | Produces the institutional report for your real mess menu |
| **Sep 28** | `explain` and `parse` (both Nova Lite; multimodal handles the photo). Frontend: presets, budget slider, frontier chart, plate view, inline price editing. | A stranger can use it without you explaining anything |
| **Sep 29–30** | **Real users.** ~15 friends. Collect before/after nutrient coverage and out-of-pocket numbers. Quotes. | A results table with real numbers in it |
| **Oct 1** | Write-up. Architecture diagram. CloudTrail export as coding-agent proof. CloudWatch dashboard screenshot. | Draft done, read aloud once, trimmed |
| **Oct 2** | Buffer. Final ship-gate check from a machine that has never seen the site. Submit with both tags. | Submitted |

## Coding-agent proof

Claude Code holds the AWS credentials and does the building, so it qualifies as
a coding agent connected to the account. Do not evidence this with a chat
screenshot. Evidence it with **CloudTrail**: every `CreateFunction`,
`PutObject`, `CreateTable` and `Invoke` call lands under `user/sarcastic-soul`
with a timestamp. An event-history export covering the build window is harder
proof than anything else in the field will offer.

Optional ten-minute insurance: connect Kiro to the same account once and
screenshot it, so an AWS-first-party agent also appears in the record.

Collect this **as we go**. Evidence assembled on Oct 1 looks assembled on Oct 1.

## Submission checklist

- [x] Registered on Builder Center
- [x] Live public URL on AWS, no login wall, reachable by the AI scorer and judges
- [x] CloudTrail export documenting the coding agent's AWS calls
- [ ] Exactly one category tag: `#daily-life-enhancement`
- [ ] Exactly one lane tag: `#startup` — note `#startups` plural is wrong and several entrants got it wrong
- [ ] Write-up covers app, development process, coding-agent usage, AWS services, live link
- [ ] Original, not previously published
- [x] Three presets — Indian hostel mess, North American dining hall, generic cafeteria — each usable in one click
- [x] Works for a stranger with no Indian context and no signup
- [ ] Site stays up through the week of Oct 19
