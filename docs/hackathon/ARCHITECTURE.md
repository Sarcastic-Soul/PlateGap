# PlateGap: architecture and technical design

How PlateGap is built and why: the linear program, the solver, where a
language model is and is not allowed, and the AWS stack. For judges and
engineers who want the reasoning behind the [README](../../README.md). Costs
are in [COST-AND-INFRA.md](COST-AND-INFRA.md); the evidence that a coding agent
built the stack is in [evidence/](evidence/README.md).

The document has two parts. [Part 1](#part-1-the-design-written-before-the-code)
is the design as I wrote it before any code existed, left as written; its
numbers are from that time. [Part 2](#what-actually-shipped-and-where-this-document-was-wrong)
records what shipped instead and where the design was wrong, which is where
most was learned. Current measurements are at the
[end](#measured-not-estimated).

Category `#daily-life-enhancement` · Lane `#startup` · Account 905543840246 · us-east-1

## Part 1: the design, written before the code

### The insight the product is named after

You pre-pay for a campus meal plan. The menu is fixed and posted weekly — you
never chose it. Nobody tells you what it actually delivers nutritionally, and
when it falls short you pay to close that gap out of your own pocket without
ever seeing the number.

PlateGap computes that number, tells you the cheapest way to close it, and then
tells the institution how to stop the gap existing.

### The optimization core

This is the part that is not a language model, and the part the write-up leads with.

#### Variables

- `m_i ≥ 0` — servings of mess item *i* eaten today. **Cost 0** (already paid for).
  Bounded `0 ≤ m_i ≤ cap_i` by what is actually served and what a person will
  realistically eat.
- `x_j ≥ 0` — units of outside item *j* bought with your own money. **Cost `c_j` > 0**.

#### Program

```
minimize    Σ_j c_j · x_j                        out-of-pocket rupees
subject to  Σ_i a_ik · m_i + Σ_j b_jk · x_j ≥ RDA_k      ∀ nutrient k   (floors)
            Σ_i a_ik · m_i + Σ_j b_jk · x_j ≤ UL_k       ∀ capped k     (sodium, sat fat)
            L ≤ total calories ≤ U                                      (two-sided band)
            Σ_i m_i ≤ maxServings                                       (realism)
            0 ≤ m_i ≤ cap_i,  x_j ≥ 0
```

The two-class structure — free-but-rationed goods alongside priced goods — is
what makes this a real modelling problem rather than the textbook diet problem.

#### Why the dual solution is the whole product

The dual variable `y_k` on nutrient *k*'s floor constraint is **rupees of
out-of-pocket spend per additional unit of nutrient k required**. That is
directly interpretable and directly checkable:

> `y_iron = 2.40 ₹/mg`, shortfall 5 mg → **iron is costing you ₹12/day, ₹360/month**

Reduced costs on non-basic foods answer the complementary question: how much
cheaper would peanuts have to get before they enter the optimal basket?

Every explanatory sentence in the UI is derived from these numbers. The language
model is handed `{binding: [iron, B12], duals: {...}, reduced_costs: {...}}` and
converts it to English. It cannot invent nutrition advice because it is never
asked to choose anything.

#### Institution mode — inverse optimization

Solve across all seven days of the posted menu, aggregate the duals, then search
candidate menu additions: for each candidate ingredient the mess could add within
its own budget, re-solve all seven days and measure the drop in total student
out-of-pocket spend.

```
best_addition = argmin_a  Σ_days  outOfPocket( menu_day ∪ {a} )
```

~100 candidates × 7 days × a few ms per solve = well under a second. The output
is an institutional report:

> "This menu delivers 86% of protein but 41% of iron. Students pay ₹360/month
>  each to cover the gap. Adding 40g of roasted chana on the four dal days
>  removes 71% of that cost."

Optimizing *the constraints* rather than within them is a genuinely higher-order
move than any submission currently in the field, and it is what turns a student
utility into a product an institution would buy.

### Solver implementation

Two-phase simplex, dense tableau, Bland's rule for anti-cycling. Pure Python,
**zero dependencies**, ~350 lines, runs in Lambda with no layer and no container.

Problem size is small, so a dense tableau is the right call. Measured on this
laptop, 30 random instances per row:

| Shape | Variables | Rows | Median | p95 | Pivots |
| --- | --- | --- | --- | --- | --- |
| one day — 20 mess, 30 market, 16 nutrients | 50 | 36 | **11 ms** | 15 ms | 83 |
| big day — 40 mess, 60 market, 22 nutrients | 100 | 62 | 51 ms | 63 ms | 149 |
| stress — 80 mess, 120 market, 25 nutrients | 200 | 105 | 143 ms | 174 ms | 182 |

A single day is the shape that actually runs on a slider drag, so 11 ms is the
number that matters and live re-solving is comfortable. A 30-point frontier is
30 solves, about a third of a second. The weekly audit is the expensive one:
candidate additions x 7 days, so 100 candidates is roughly 8 seconds and wants
either a trimmed candidate list or a progress indicator.

Duals are read off the final tableau's objective row in the slack/artificial
columns. Two-phase handling of `≥` constraints (surplus + artificial) is the
fiddly part and is where the tests earn their keep.

**Correctness discipline:** `tests/test_simplex.py` solves randomly generated
instances with both our simplex and `scipy.optimize.linprog`, asserting that
feasibility status agrees, objective values match to 1e-6, our duals match
scipy's marginals to 1e-5, and complementary slackness holds against our own
primal solution. scipy is a *development* dependency only — it never ships to
Lambda. **267 tests, all passing.** That differential test is worth a paragraph
in the write-up on its own.

The first run of it caught a real bug: rows whose right-hand side is negative
get negated during normalisation, and negating a row also negates its marginal.
A uniform sign convention silently produced duals of the wrong sign on exactly
the rows PlateGap cares about — the nutrient floors. Without the reference
implementation that would have shipped as confident, wrong advice.

### Where the language model is used, and where it is not

| Job | Tool | Constrained how |
| --- | --- | --- |
| Menu photo or PDF → text | Bedrock Nova Lite | asked to transcribe and nothing else. It never sees the catalog and never emits a food ID |
| Menu text → canonical food IDs | **`solver/menutext.py`** | string matching against a fixed catalog, offline. Anything it cannot place is surfaced with the near misses it rejected, never invented |
| Solver output → English | Bedrock Nova Lite | receives only numbers; prompt forbids introducing any figure not supplied |
| Choosing what to eat | **the simplex solver** | — |
| Computing nutrition | **the food composition table** | — |
| Deciding quantities | **the simplex solver** | — |

Claude Haiku 4.5 is available on this account via the `us.anthropic.*` inference
profile if Nova Lite's explanation quality proves insufficient.

### Nutrition data

Composite Indian dishes are **recipe-decomposed into base ingredients** rather
than guessed at dish level — dal becomes lentils + oil + spices at standard
ratios, and the nutrients come from the base ingredients. This is more defensible
than any dish-level estimate and is a detail worth stating in the write-up.

Base composition data: USDA FoodData Central (public domain, bulk download).
Indian-specific items that FDC lacks get a curated table with cited sources.

**Open risk:** nutrient data quality is the largest technical risk in the project.
Budget real time for it and cite every source in the repo.

### Prices

- Local survey — items sold near the hostel, collected by Anish. This is what
  makes the numbers real rather than illustrative.
- A national retail price feed for staples, if a fetchable one checks out.
  **Unverified — do not promise this until confirmed.**

### Who this is for — it is not my hostel

The product is generic. A hostel menu is an *input*, never a hardcoded
assumption. Anyone who lands on the page must reach a useful answer without
knowing anything about India, without signing up, and without typing much.

Three ways in, in order of effort:

1. **Pick a preset** — one click, instant result. Ships with an Indian hostel
   mess (my real IIIT menu, the authentic data), a North American university
   dining hall, and a generic cafeteria. The dining-hall preset exists so no
   judge has to imagine an unfamiliar situation; one of the five went to McGill
   and has personally lived the meal-plan problem.
2. **Paste your menu as text** — a week, a day, or a single meal.
3. **Photograph the notice board**, or drop in the PDF the mess sent round —
   Nova Lite transcribes it, the catalog matching happens here, and the text
   is shown to you to correct before anything is solved.

Prices work the same way: bundled regional defaults (₹ and $) that produce a
sensible answer immediately, with every single price editable inline. Somebody
in Ohio gets a real answer from the defaults, and a better one after thirty
seconds of editing.

My mess is the demo button and the story. It is not the schema.

### AWS architecture — deliberately small

Every service here earns its place, and the write-up states why the obvious
extras were left out. Right-sizing reads better to a panel of Solutions
Architects than a crowded diagram does.

```
        Browser — static, no signup, no login wall
                        │
        S3 (private) ───┴─── CloudFront + OAC        1 TB/mo always free, gives us HTTPS
                        │
        Lambda Function URL                           no extra cost, no API Gateway
                        │
        Lambda  Python 3.12  arm64                    1 M req/mo always free
         ├── solve      two-phase simplex → plan + duals + binding + reduced costs
         ├── frontier   N solves across a budget sweep → a real Pareto curve
         ├── audit      week aggregate + inverse-optimization over menu additions
         ├── parse      menu text → canonical food IDs            (no model, no network)
         ├── scan       menu photo or PDF → text, then parse      (Nova Lite, transcription only)
         └── explain    solver output → English                   (Nova Lite, grounded)
                        │
        Bedrock  amazon.nova-lite-v1:0                a few rupees at demo volume
                        │
        Food catalog + presets: JSON in the deployment package and S3
        Usage metrics: structured Lambda logs, counted with CloudWatch Logs Insights
        Shared plans: encoded in the URL fragment — stateless, no database
```

**Four services. Terraform, roughly a dozen resources.**

What was considered and deliberately cut, each for a stated reason:

| Cut | Why |
| --- | --- |
| API Gateway | A Lambda Function URL gives the same HTTPS endpoint with CORS at no cost, and API Gateway's free tier is 12-month rather than always-free |
| Textract | Nova Lite accepts an image or a PDF directly, so a separate OCR service would be one more dependency for a job one call already does. Measured: a page of PDF is about ten seconds and $0.0004 |
| DynamoDB, for data | Nothing that is *data* needs shared durable state. Catalog is static JSON, metrics are logs, shared plans ride in the URL fragment. **One table went in later and for a different reason:** a daily counter capping what `scan` may spend on Bedrock, which is the one number in the project that cannot be recomputed from anything else. See [Added: a spend cap](#added-a-spend-cap-and-the-one-table-in-the-project) below |
| Step Functions | There is no long-running workflow. The solve is single-digit milliseconds |
| EC2 | Nothing needs to be always-on, and an instance in the request path is the single most likely way to fail the ship gate between Oct 2 and Oct 19 |

The existing `t4g.medium` stays out of the project entirely. Stopping it while
it is unused also stops it consuming credits.

**Total running cost: inside the always-free tier, plus a few rupees of Bedrock.**
That number goes in the write-up.

### API shapes

```
POST /solve
  { menuDayId, profile: { age, sex, veg, allergies, kcalTarget },
    marketItems: [id], maxOutOfPocket? }
→ { messPlan: [{foodId, servings}], purchases: [{foodId, qty, cost}],
    outOfPocket, nutrients: {k: {got, floor, ul}},
    duals: {k: ₹/unit}, binding: [k], reducedCosts: {foodId: ₹},
    solveMs, iterations }

POST /audit
  { campusId, week }
→ { coverage: {k: pct}, perStudentMonthlyCost,
    bindingFrequency: {k: days}, bestAdditions: [{foodId, costToMess, studentSavings}] }
```

## What actually shipped, and where this document was wrong

Part 1 was written before the code. Keeping it as written and recording the
differences here is more useful than quietly rewriting it to match, because the
places the design was wrong are the places something was learned.

### Added: a limit on how much a person can eat

Not in the original design at all, and it turned out to be the constraint that
mattered most. Without it the solver meets every ICMR target from the mess
alone by prescribing twelve rotis and five servings of curd — arithmetically
perfect and useless as advice. With it, the binding constraint on a
well-stocked menu is stomach volume rather than the menu, and the shadow price
on that row (the money value of one more gram of appetite) is the most
interesting number the program produces.

The design assumed the gap would be structural — that the menu simply would
not contain enough calcium. On this menu it is not. The food is there; a
person cannot eat enough of it. That is a different and more honest finding.

### Added: dishes carry a cuisine

The menu audit was recommending a yogurt parfait for an Indian hostel mess.
Correct arithmetic, worthless advice. Every dish now belongs to a kitchen, and
the audit only suggests additions that belong on the menu it is auditing.

### Changed: the audit is a pricing step, not a search

The design described re-solving the week once per candidate. That is about ten
seconds. The shipped version prices every candidate against the duals from the
single solve we already did, which costs one dot product each, and re-solves
only the handful that price out negative. On Monday's IIIT menu, for the
default egg-eating profile, 56 candidates are screened and 8 price in; the
whole week's audit takes under a second.

The screen is only legitimate if it has no false negatives, so there is a test
that takes every rejected candidate, adds it for real and re-solves.

### Changed: the model transcribes, and the catalog matching is deterministic

The design had one endpoint turning a photograph straight into canonical food
IDs. That is not what shipped, and the split is the point.

`scan` sends the file — a PDF whole, as a Bedrock `document` block, with no
rasterising step — and asks Nova Lite for one thing: write down the words that
are printed, laid out as a table. `parse` then does the catalog matching in
`solver/menutext.py`, offline, with no model anywhere near it.

The reason is the failure mode. A model asked to emit dish IDs produces a
confident, plausible, unfalsifiable menu, and a shortfall computed from a
hallucinated menu is wrong in a way the reader cannot see. String matching
against a hundred fixed names has a right answer, and can say *"this could be
green chutney or imli chutney, and guessing would be a coin toss"* — which is
what the screen then asks you about, one tap per name.

Two things were measured on the way and both went against the design:

- Asking for the days down the side rather than across the top means asking a
  small model to transpose a grid. It dropped most of the cells and then
  repeated one row until it hit the token cap. `menutext` learned to read the
  layout a mess noticeboard is actually drawn in instead.
- Every instruction past "copy what is printed" cost transcription quality.
  A sentence asking it to keep the row of items served every day made it emit
  the row label and none of the contents, twice out of two.

Against the real seven-day IIIT timetable: 131 names placed across all seven
days, 26 it would not place, each reported with its near misses.

### Added: a spend cap, and the one table in the project

`scan` calls Bedrock, and the Function URL is public and unauthenticated by
design. That makes "anyone may try this" and "anyone may spend my money" the
same sentence unless something counts.

The account's concurrency limit is not the answer. Ten executions, each holding its slot
for the ten seconds a page of PDF takes, is about one scan a second — roughly
$34 a day, which is more than this project's whole budget. A per-caller rate
limit is not the answer either: a Function URL has no API keys to count, and
per-IP limiting means WAF, whose monthly minimum is several times the loss it
would prevent.

So the spend itself is counted. One DynamoDB row per day, `ADD` to increment,
TTL to sweep it up a week later; the 501st scan of a day comes back with
`read: false` and a sentence pointing at the paste box. The cap is per day
rather than per lifetime because a lifetime cap eventually trips and then the
feature is gone until a person notices — possibly at three in the morning,
mid-judging.

Two details worth defending:

- **`UpdateItem` with `ADD`, not read-then-write.** One atomic round trip that
  returns the value it wrote, so ten containers incrementing at the same
  instant get ten different numbers and exactly one of them is the five
  hundredth. A module global would have been free and wrong — it is per warm
  container, so the true ceiling becomes that number times however many
  containers are alive.
- **It fails closed.** If the tally cannot be read, the scan is refused.
  Failing open reads better until you notice that anything breaking DynamoDB
  also removes the ceiling, which is the only thing this exists to hold up.

On-demand billing rather than provisioned. One write unit is one write a
second, which is exactly the peak rate this is built to survive, so a
free-tier-sized provisioned table would throttle under the one load it exists
for. On-demand at the cap is about two cents a month.

### Changed: one action per request, not one path per endpoint

The Function URL takes a JSON body with an `action` field rather than routing
on a path. The actions are `presets`, `catalog`, `gap`, `solve`, `frontier`,
`week`, `audit`, `parse`, `scan` and `explain`. Same shapes as designed;
different envelope.

### Added: every shadow price says how far it holds

A shadow price is a slope, true only until the optimal basis changes. Early
versions of the write-up multiplied duals by 100 g or a whole roti as though
they held for ever. The simplex now reads sensitivity ranges off the final
tableau: for each binding row, the span of right-hand side its price holds
over; for each item bought, the price range over which the shopping list stays
the same. The interface shows both, rounded inward so it never claims more
than the solver did. There is no reference implementation for ranges, so
`tests/test_ranging.py` re-solves at and just past each edge instead.

### Changed: a ladle means a standard katori

Part 1 left serving weights to judgement. Every ladle is now one of the
standard katoris in ICMR-NIN's *Dietary Guidelines for Indians* (2024),
Annexure I: 155 ml for dal, curry, sabzi and rice, 115 ml for curd, raita and
sprouts, 200 ml for biryani. Only curd was outside that range; dahi and plain
curd are now 120 g. The weights are still estimates, not weighed. The reasoning
and the sources are in [DATA-SOURCES.md](DATA-SOURCES.md).

### Added: a field study

One menu is an anecdote. [FIELD-STUDY.md](FIELD-STUDY.md) runs the same
pipeline over menus other colleges publish, and fixed the parser bugs those
menus exposed.

### Measured, not estimated

Measured on 2026-09-21 on a laptop (x86_64, CPython 3.13) with
`uv run python scripts/benchmark_solver.py`, IIIT menu, Monday, median of 9
runs. The function runs on arm64 at 1769 MB, one vCPU, and has not been
benchmarked there.

| | |
| --- | --- |
| Deployment package | 88 KB (`scripts/package_lambda.sh`), no dependencies |
| The gap for one day (`gap`) | 3.5 ms |
| The cheapest top-up for one day (`cheapest`) | 18 ms |
| Frontier, 24 points | 194 ms |
| Whole-week audit | 774 ms |
| Tests | 873 passed, 40 skipped |
