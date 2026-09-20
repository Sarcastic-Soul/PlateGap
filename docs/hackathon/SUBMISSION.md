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
  what stops it. That limit prices at **₹0.0347 per gram** — an extra 100 g of
  appetite is worth ₹3.47 a day.
- Zinc is the expensive nutrient: **₹7.53 per milligram** at the margin.
- One more roti in the ration would save **₹0.597 a day**.

Those last three numbers are not estimates. They are the dual variables of the
linear program, which is the whole reason the solver is written the way it is.

Aggregated across a 600-student hostel, the menu leaks **₹271,698 a month** in
out-of-pocket spending. Adding mutter paneer on the days it is absent would
recover **₹85,193 a month** of that. On the US dining hall at 3000 students the
same analysis says **$99,177.86 a month**, and that a black bean and rice bowl
would recover **$30,284** of it.

That is a number a dining services director can act on, derived from nothing
but the posted menu.

## What is technically unusual about it

**The solver is written from scratch.** `solver/simplex.py` is a two-phase
simplex with Bland's rule, in pure Python, with no dependencies at all — not
numpy, not scipy. Lambda gets a 51 KB zip and a cold start with nothing to
import.

It was not written from scratch for the sake of it. It was written from scratch
because the product needs the **dual** variables, not just the answer, and it
needs to decompose them per constraint. "Zinc costs ₹7.53 a milligram" and "one
more roti saves ₹0.597" are shadow prices read straight off the optimal basis.
A library that returns only the primal solution cannot tell you that.

**Correctness is held to a reference.** `scipy.optimize.linprog` is a
development dependency that never ships. 260 randomly generated LPs are solved
by both on every change, and the test asserts three things: same feasibility
status, same objective to 1e-6, and — the one that matters — **the same duals**,
plus complementary slackness checked against our own primal, and strong
duality — `y·b == c·x` — asserted on every instance, which is the check that
catches a stale dual when each individual number still looks plausible. 442
tests in all, green before anything deploys.

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
— exact names, the presets' own alias maps, a transliteration fold, then fuzzy
distance — and it refuses to guess when two dishes are equally close. `"dal"`
comes back as *could be Dal makhani or Mix dal, and guessing between them would
be a coin toss*, with both suggested.

That split is deliberate. A model asked for dish IDs returns a confident,
plausible, unfalsifiable menu, and a shortfall computed from a hallucinated
menu is wrong in a way the reader cannot see. So the model does the typing and
the catalog does the deciding: on the real seven-day IIIT timetable that is 127
dishes read and 20 names it would not place, each shown with the near misses it
rejected and settled with one tap. The transcription is editable before
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
| 48 | AWS CLI, driven by Claude Code |
| 23 | Terraform, run by the agent's bootstrap script |
| 1 | A browser (me, once, in the console) |

(Numbers as of the last export; re-run the script before posting and copy the
table it writes.)

`CreateFunction`, `CreateBucket`, `CreateDistributionWithTags`,
`CreateOpenIDConnectProvider`, `PutBucketPolicy`, `UpdateFunctionCode` — all of
it under the agent's user agent, timestamped, in a window that starts hours
before the first line of the solver existed. The export is in the repository at
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
measures vitamin B12 for no food in the book. Whey protein is still a proxy
outright. The seed market prices are my own survey near one campus and are meant
to be edited. Nutrient targets follow ICMR-NIN 2020 for India and the US DRIs
for the US preset, and the app says which one it used.

The model says what it does not know. That seemed more useful than a number with
no provenance.

---

**Live:** <https://d2u44arueak38s.cloudfront.net>
**Code:** <https://github.com/Sarcastic-Soul/PlateGap>
**Category:** `#daily-life-enhancement` · **Lane:** `#startup`
