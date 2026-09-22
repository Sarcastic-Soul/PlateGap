# PlateGap — Builder Center submission

Draft of the post. Category `#daily-life-enhancement`, lane `#startup`.
Live: <https://d2u44arueak38s.cloudfront.net> · Code: <https://github.com/Sarcastic-Soul/PlateGap>

---

## Your meal plan is already paid for. What is it still leaving you short of?

I live in a hostel in India and pay a mess fee up front, every month, whether I
eat or not. Once it is paid, the food on the counter is free at the margin —
but it is rationed. Rice and roti are unlimited. Paneer is one ladle. The egg
is one egg. Everyone I know tops the rest up out of their own pocket, at the
shop outside the gate, with no idea what they are topping up or whether they
are buying the right thing.

A campus dining hall in the US works the same way, with a swipe instead of a
monthly fee.

The gaps are not small or rare. 59.1% of Indian girls aged 15–19 are anaemic,
and so are 31.1% of boys (NFHS-5). 31% of adolescents are short of vitamin B12
(CNNS). Among young vegetarian graduates in one study, half were deficient
(Naik et al., 2018). Iron and B12 are exactly the nutrients a vegetarian mess
plate is thinnest on.

PlateGap treats that as an optimization problem, because that is what it is.

**1. Where's the gap?** Eat the menu as well as it can possibly be eaten —
inside the portions actually served, and inside what one person can physically
get through in a day. What is still missing?

**2. What's the cheapest fix?** Add priced items from a shop and minimise the
money spent while hitting every nutrient floor.

**3. What should the kitchen change?** Given that students are spending their
own money to patch the menu, which single dish, added to the menu, would cut
that spending the most — across everybody?

No signup. Three presets ship: a real Indian hostel mess timetable, a
representative North American dining hall, and a plain canteen to edit. Prices
are editable, because the shop outside your gate is not the shop outside mine.

## What it found

On my own mess menu, Monday, egg-eating diet:

- **4 of 12 nutrient targets cannot be met from the menu at all**, at any
  portion size a person could eat.
- Closing the gap costs **₹7.82 a day** — about ₹235 a month, on top of a mess
  fee already paid.
- The binding constraint is **not the menu. It is stomach volume.** The solver
  wants twelve rotis and bowl after bowl of curd; the plate limit of 1400 g is
  what stops it. That limit prices at **₹0.0347 per gram**, and that price
  holds for the next 68 g of appetite — worth ₹2.36 a day.
- Zinc is the expensive nutrient: **₹7.53 per milligram** at the margin — for
  the first 0.14 mg. Two more milligrams cost ₹35, not ₹15.
- Raising the roti ration from twelve to thirteen would save **₹0.51 a day**.

Those numbers are not estimates. They are the dual variables of the linear
program, and the range each one holds over — which is the whole reason the
solver is written the way it is.

### Where I got those numbers wrong the first time

The first draft of this post said an extra 100 g of appetite was worth ₹3.47,
that zinc costs ₹7.53 a milligram, and that one more roti saves ₹0.597. Every
one of those was a correct shadow price, and every one was used wrongly.

A shadow price is a slope. It is the cost of the *next* unit, and it stays true
only until the solution turns a corner — until some other food enters the plan
or leaves it. Multiply it by 100 g, or by a whole roti, and you are assuming the
corner is further away than it is.

So the solver now reports, for every shadow price, the stretch it holds over,
read off the same final tableau with the standard sensitivity-ranging
arithmetic. The zinc price holds between 16.97 and 17.14 mg: a sixth of a
milligram. The plate price holds for 68 g, not 100. The roti price holds to
12.5 rotis, which is why a whole extra roti is worth ₹0.51 and not ₹0.597.

Each range is checked the only way that means anything: move the constraint to
the far end of its range, re-solve from scratch, and assert the cost moved by
exactly price × distance. Then step just past the edge on an instance where the
price is unique and assert it *stops* holding, so a solver that reported every
range as infinite would fail. The ranges are guarantees rather than exact edges
on a degenerate plan — the price can hold further than shown, never less — and
the interface rounds every edge inward so the display never claims more than
the solver did. It did claim more, once: rupee amounts are shown in whole
rupees, so "carrot is not worth buying above ₹8" went out while the true
threshold was ₹8.42, and at ₹8.20 the solver bought carrots. The test that
re-solves at each threshold caught it.

The same ranges answer the question every reader asks first — *these prices are
yours, not mine* — directly. Each item on the shopping list says how far its
price can move before the list changes: spinach stays on it anywhere from ₹4.31
to ₹14. And the items that nearly made the list say how cheap they would have to
get: carrot, below ₹8.42 against ₹10 today.

Aggregated across a 600-student hostel, the menu leaks **₹264,486 a month** in
out-of-pocket spending. Adding khada masoor dal on the days it is absent would
recover **₹82,842 a month** of that. On the US dining hall at 3000 students the
same analysis says **$99,177.86 a month**, and that a black bean and rice bowl
would recover **$30,284** of it.

That is a number a dining services director can act on, derived from nothing
but the posted menu.

## It is not just my mess: 14 published menus

One menu is an anecdote. So I collected every hostel mess menu I could find on
an Indian college's own website: 14 menus from 12 institutions, including IITs,
an NIT, an IISER, a central university, a deemed university, and private
colleges. Each went through the app's own pipeline. Nova Lite transcribed the PDFs, the live
parser matched the names, and every name it would not place was settled with a
written reason. Then I solved a whole week for each menu, for a vegetarian man
and a vegetarian woman. This measures the best plate each menu allows, so a
student who eats what they like does worse:

- For a woman, **12 of the 14 menus cannot reach the iron target on at least
  one day of the week, and 6 cannot reach it on any day**.
- For a man, **10 of 14 fall short on vitamin B12 on some day, and 3 on
  every day**. Calcium falls short on some day at 13 of 14.
- Closing every gap costs a median **₹267 a week** for a woman and **₹222**
  for a man. That is around ₹1,000 a month on top of the mess fee, and it
  ranges from ₹36 to ₹621 a week depending on the menu.
- The fix is almost always the same short list: cooked spinach, guava, a
  packet of milk, soya chunks, boiled rajma.

The study checks itself. Settling a name can only add food to a day, so I
solved every menu again with only the parser's own matches. No shortfall
count went down, and most went up, so the figures above are the kinder
reading. The
full method, the menu-by-menu table, and what the study does *not* show (a
menu is not what is served, the sample is whatever is online) are in
[`FIELD-STUDY.md`](https://github.com/Sarcastic-Soul/PlateGap/blob/main/docs/hackathon/FIELD-STUDY.md).

Running real menus also found five bugs in the menu reader that my own menu
never exercised:

- It read menus with the days down the side as a single Monday.
- It counted paid extras as mess food.
- It did not recognise a dated fortnight as a timetable.
- It accepted near matches like "curd rice" as plain rice and "milk cake" as
  milk.
- It turned a sandwich on a vegetarian menu into the catalog's turkey
  sandwich.

All five are fixed and tested.

## Who this is for, and what happens next

Every hostel and dining hall I found runs the same shape: a fixed fee paid up
front, a rationed line, and nobody accountable for the gap between what is
served and what a body needs. That is not particular to my own mess — it is
the field study's 12 institutions, and the US dining-hall preset runs on the
same structure with a swipe instead of a monthly fee. The audit view is built
for whoever can act on the number: a student deciding what to buy at the shop
outside the gate, or a mess committee or dining-services office deciding which
single dish, added to the menu, stops hundreds of people from having to.

So far the only user is me, on my own mess menu, plus whoever finds this and
points it at their own timetable — the app needs no signup and no account to
do that. The path to more than that is the same pipeline the field study
already runs on: more real menus scanned in (the raw source list is public, in
[`SOURCES.csv`](https://github.com/Sarcastic-Soul/PlateGap/blob/main/data/field/menus/SOURCES.csv)), and the institutional
audit — the one priced in rupees a month, not per student — put in front of an
actual mess committee, since that is the reader who can act on it without
first being convinced the number is real.

## What is technically unusual about it

**The solver is written from scratch.** `solver/simplex.py` is a two-phase
simplex with Bland's rule, in pure Python, with no dependencies at all — not
numpy, not scipy. Lambda gets an 88 KB zip and a cold start with nothing to
import.

It was not written from scratch for the sake of it. It was written from scratch
because the product needs the **dual** variables, not just the answer, and it
needs to decompose them per constraint, and it needs the range each one holds
over. "Zinc costs ₹7.53 a milligram, for the next sixth of a milligram" is read
straight off the optimal basis. A library that returns only the primal solution
cannot tell you that.

**Correctness is held to a reference.** `scipy.optimize.linprog` is a
development dependency that never ships. 260 randomly generated LPs are solved
by both on every change, and the test asserts three things: same feasibility
status, same objective to 1e-6, and — the one that matters — **the same duals**,
plus complementary slackness checked against our own primal, and strong
duality — `y·b == c·x` — asserted on every instance, which is the check that
catches a stale dual when each individual number still looks plausible. The
sensitivity ranges have no reference to compare against, so they are held to
re-solving instead, on 320 random programs and every day of the real presets.
873 tests in all, green before anything deploys.

**The menu audit is a pricing step used as a product feature.** To find which
dish added to the menu would save students the most money, the obvious approach
is to re-solve the whole week for every candidate dish. That is 100 candidates ×
7 days of LPs. Instead PlateGap computes each candidate's **reduced cost**
against the duals it already has — the same arithmetic simplex does internally
to choose an entering variable — and only re-solves the handful that price out
as promising. There is a test that re-solves every *rejected* candidate to
assert the screen never hides a worthwhile one.

**Every recommendation explains itself**, because the reduced cost decomposes
by constraint row. "This dish helps" becomes "this dish helps because it
carries zinc, whose dual is high, and it does it in few grams, and the gram
budget is binding."

**Two classes of goods in one program.** Mess items have cost 0 and a serving
cap; market items have a price and no cap. That single formulation is what lets
one LP answer "what is free food worth to you" and "what should you buy" at the
same time.

**You can photograph your mess menu, and the model is not allowed to read it.**
`scan` sends the PDF or the photo to Nova Lite and asks for exactly one thing:
write down the words that are printed. Which catalog dish each written name
means is then settled by `parse`, on the standard library, with no model call
— exact names, a shared table of regional names (chapati, phulka, chawal,
appalam) collected from the 14 menus in the field study, the presets' own alias
maps, a transliteration fold, then fuzzy distance. It refuses to guess when two
dishes are equally close. `"dal"`
comes back as *could be Mix dal or Khada masoor dal, and guessing between them
would be a coin toss*, with both suggested.

That split is deliberate. A model asked for dish IDs returns a confident,
plausible, unfalsifiable menu, and a shortfall computed from a hallucinated
menu is wrong in a way the reader cannot see. So the model does the typing and
the catalog does the deciding: a scan of the real seven-day IIIT timetable
places 131 names and leaves 26 it would not place, each shown with the near
misses it rejected and settled with one tap. The transcription is editable before
anything is solved, because character recognition on a photographed noticeboard
gets things wrong and only the person holding the phone knows which things.

**The written explanation cannot contain a number the solver did not produce.**
`explain` asks Bedrock (Nova Lite) to write the result up in prose. Every
number is then extracted back out of the text and reconciled against the
solver's own figures at the precision it was written with; one number that does
not reconcile discards the whole explanation and the templated version is
returned instead. Nothing the caller typed reaches the prompt — a posted menu
is called "your menu", never by the name they gave it — and there is a test
that posts a menu named `IGNORE EVERYTHING ABOVE` and asserts it never appears.

## Architecture

Static site on **S3** behind **CloudFront** with an origin access control, so
the bucket is never public. One **Lambda** function behind a **Function URL** —
no API Gateway, because one route does not need one. **CloudWatch Logs** with a
retention policy. **IAM** roles scoped per job. All of it declared in
**Terraform**, in `infra/`, 501 lines.

Deploys run from **GitHub Actions over OIDC**: GitHub signs a short-lived token,
AWS trusts its identity provider directly, and the trust policy is pinned to one
repository and one branch. There is no access key in the repository, none in the
org secrets, nothing to rotate and nothing to leak. The deploy role can update
the function and write the site; it cannot create or destroy infrastructure.
The workflow runs the full test suite, then smoke-tests the live endpoint after
shipping — a green deploy that produced a broken endpoint is worse than a red
one.

Running cost at hackathon traffic is **effectively zero**: Lambda's free tier,
a few megabytes in S3, and CloudFront's free tier. No database, because the
problem has no state worth keeping — a menu goes in, a plan comes out.

## How a coding agent built it, and how that is proved

Claude Code held the AWS credentials and did the building: it wrote the simplex,
digitized my mess menu, built the nutrient catalog from USDA FoodData Central SR
Legacy (76 base ingredients, 109 dishes composed from them by recipe in stated
grams, every row traceable to an `fdcId`), wrote the Terraform, and ran it.

I am not evidencing that with a chat screenshot. I am evidencing it with
**CloudTrail** — the account's own event history, which records every call that
built this stack, with the client that made it:

| Calls | Client |
| --- | --- |
| 64 | GitHub Actions deploying over OIDC, set up by the agent |
| 36 | Terraform, run by the agent's bootstrap script |
| 26 | AWS CLI, driven by Claude Code |
| 5 | AWS CLI as the root user, creating the IAM user the agent works as |
| 2 | A browser (me, in the console) |

(Export of 2026-09-22, window 2026-09-19T16:19:11Z to 2026-09-22T13:27:12Z,
133 mutating calls across 40 distinct APIs.)

`CreateFunction`, `CreateBucket`, `CreateDistributionWithTags`,
`CreateOpenIDConnectProvider`, `PutBucketPolicy`, `UpdateFunctionCode` — all of
it timestamped, under the user agent that made it, in a window that opens the
evening before the first commit of the solver. The export is in the repository at
`docs/hackathon/evidence/`, generated by `scripts/export_cloudtrail.py`, with
access key ids, IP addresses and the account number stripped before it was
written, because that directory is public.

The interesting part of the process was not the code. It was the debugging the
agent had to do against a real account:

- The Function URL returned 403 to the public despite `AuthType: NONE` and a
  policy that granted `lambda:InvokeFunctionUrl` to everyone. Direct
  `lambda invoke` worked. The account turned out to be a newer one, on which
  AWS blocks public function URLs by default — visible in
  `get-account-settings` as a concurrency limit of 10 rather than 1000. Fixed,
  with a comment in the Terraform explaining honestly what the grant widens.
- GitHub Actions could not assume the deploy role: `Not authorized to perform
  sts:AssumeRoleWithWebIdentity`, with a trust policy that looked correct. The
  agent printed the OIDC token's claims from inside the workflow and found the
  repository issues **ID-qualified subject claims** —
  `repo:owner@142567151/PlateGap@1378199091:ref:refs/heads/main`, not
  `repo:owner/PlateGap:...`. The trust policy now accepts both, and the
  ID-qualified form is the stricter one: numeric ids cannot be reused by a
  repository deleted and recreated under the same name.
- Terraform kept failing with `No valid credential sources found` in a shell
  where every `aws` command worked, because Terraform's Go SDK cannot read the
  CLI's session cache. The bootstrap script now exports the credentials itself.

## What I would not claim

Cooking destroys nutrients, so the catalog applies retention factors taken
programmatically from the USDA Table of Nutrient Retention Factors, Release 6 —
each of the 336 recipe lines declares how the ingredient is prepared. Two calls
are worth stating: no yield factor is applied, because recipes state raw grams
into the pot and the cooked weight cancels; and ingredients that already cite a
cooked USDA row take a factor of 1.0, because taking the loss off twice would
manufacture a shortfall *in the direction that flatters this product*. Release 6
has no code for pressure cooking, the dominant Indian method, and none for deep
frying flour — both are approximated and both are labelled in the data.

Paneer and jaggery now come from the Indian Food Composition Tables 2017 rather
than a guess: paneer's calcium was 208 mg in my proxy and is 476 mg measured.
They keep an estimated flag for exactly one nutrient each, because IFCT 2017
measures vitamin B12 for only a few fish and meats, and not for these. Whey protein is still a proxy
outright. The seed market prices are my own survey near one campus and are meant
to be edited. Nutrient targets follow ICMR-NIN 2020 for India and the US DRIs
for the US preset, and the app says which one it used.

The model says what it does not know. That seemed more useful than a number with
no provenance.

---

**Live:** <https://d2u44arueak38s.cloudfront.net>
**Code:** <https://github.com/Sarcastic-Soul/PlateGap>
**Category:** `#daily-life-enhancement` · **Lane:** `#startup`
