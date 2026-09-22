# Zero to Shipped: the brief and the field

My working summary of the hackathon: the facts, what an entry must have, how it
is scored, and what the other entries look like so far. It is for me and for
anyone deciding where PlateGap stands. The rules themselves are in
[RULES.md](RULES.md) and the public brief in [ABOUT.md](ABOUT.md); the plan
that follows from this is [PROJECT-PLAN.md](PROJECT-PLAN.md).

Source: <https://builder.aws.com/build/hackathons/e83e84e5-4f4c-383b-bbe9-4a15ac195d55/zero-to-shipped>.
Pulled from the Builder Center API on 2026-09-22
(`GET https://api.builder.aws.com/sms/hackathons/{entityId}` and
`GET https://api.builder.aws.com/cs/submissions/parent/{entityId}?parentContentType=HACKATHON`,
paginated on `cursor`). No auth needed — both are public. The raw JSON is in
[raw/](raw/), and every count below can be checked against it.

## Facts

| Field | Value |
| --- | --- |
| Title | Zero to Shipped |
| Entity ID | e83e84e5-4f4c-383b-bbe9-4a15ac195d55 |
| Status | LIVE |
| Type | Virtual, "build on your own AWS account" |
| Opens | 2026-09-18, 09:00 PT |
| Submissions due | 2026-10-02, 23:59 PT (2026-10-03 06:59 UTC) |
| Registrations | 1,594 on 2026-09-22 (1,253 on 2026-09-21, 769 on 2026-09-20) |
| Submitted projects | 55 on 2026-09-22 (40 on 2026-09-21, 19 on 2026-09-20) |
| Prize pool | $28,000 |
| Winners | 5 projects |
| Per winner | $5,000 AWS promotional credits, a swag bundle (jacket, backpack, keyboard, about $600), a certificate and a digital badge |
| Entry limit | One entry per person |
| Judges (Builder Center aliases) | bhavinjp, karamen, raghuramg, manubel, hamzalfa |

### Timeline

| Milestone | Date |
| --- | --- |
| Launch | Sep 18 |
| Projects due | Oct 2 |
| Gate 1: AI and human scoring | Week of Oct 5 |
| Gate 2: human judging panel | Week of Oct 12 |
| Winners announced | Week of Oct 19 |

## Eligibility

- 18 or older, with a Builder Center profile.
- Excluded countries: Argentina, Australia, Brazil, Hong Kong, Indonesia,
  Italy, the Philippines, Vietnam, Singapore, Russia, Cuba, Iran, North Korea,
  Syria, Belarus, Crimea, DNR, LNR and the UAE. **India is not excluded.**
- Amazon and AWS employees and their households are excluded.
- Eligibility is checked at the finalist stage against public profiles
  (Builder Center, LinkedIn). Disqualification is possible even after the
  winners are announced.

## Hard requirements

All six are mandatory.

1. A coding agent **connected to the AWS console**, with documented proof of
   the connection in the write-up.
2. A **live application running on AWS**, publicly reachable by URL, with no
   login wall for judges.
3. One **app category tag**: `#workplace-efficiency`,
   `#daily-life-enhancement`, `#commercial-potential`, `#social-good` or
   `#personal-expression`.
4. One **lane tag**: `#startup` or `#community`.
5. An original app, not previously published.
6. A project write-up published on Builder Center covering the app, the
   development process, how the coding agent helped, the AWS services used,
   the category and lane, and a link to the live app.

### The ship gate

Pass or fail, no exceptions. An app that is not live and reachable by both the
AI scorer and the human judges at evaluation time is eliminated, however good
the idea. This is the highest-risk item: keep the app up from Oct 2 through at
least Oct 20.

## Scoring

The same rubric at both gates, 25% each:

- Technical Innovation & Originality
- Implementation Quality
- Community / Market Impact
- Creativity & Storytelling

Gate 1 (AI and human) cuts to the **top 100**. The Gate 2 panel picks 5
winners **across the app categories**, so the category matters: a crowded one
means competing head to head, an empty one is a wider lane.

Half the rubric (Impact, Storytelling) is about the write-up rather than the
code, and Gate 1 is largely an AI reading the markdown. The write-up is as much
the product as the app is.

## The field so far

55 projects on 2026-09-22, counted from each project's tags in
[raw/submissions-2026-09-22.json](raw/submissions-2026-09-22.json). Over half
carry no category tag at all, and PlateGap is not among them yet.

| Category tag | Projects |
| --- | --- |
| `workplace-efficiency` | 7 |
| `social-good` | 7 |
| `commercial-potential` | 6 |
| `daily-life-enhancement` | 3 |
| `personal-expression` | 1 |
| none | 32 |

The three `daily-life-enhancement` entries so far (a garden planner, a legal-
document reader built on Google Gemini rather than AWS, and an ASL sign
detector) are all thin — 0–1 likes or comments, one to three short paragraphs.
None runs a real audit against real field data the way PlateGap's does.

| Lane tag | Projects |
| --- | --- |
| `startups` (plural, not the tag the rules name) | 11 |
| `community` | 9 |
| `startup` | 0 |
| none | 35 |

## Categories

- **Workplace efficiency**: task automation, team dashboards, workflow
  engines.
- **Daily life enhancement**: smart home, personal assistants, habit trackers.
- **Commercial potential**: SaaS, marketplaces, vertical solutions.
- **Personal expression**: art generators, music tools, content platforms.
- **Social good**: measurable impact for underserved populations in
  education, health or climate resilience. Run with the AWS Skilling and
  Social Impact team; qualifying organisations may also apply for AWS Social
  Impact Credits.

## Lanes

- **Startup**: pushed toward a product, with a story about product-market fit,
  first users and a path to a business.
- **Community**: helps a group you belong to, such as a class, a meetup or an
  open-source project.
