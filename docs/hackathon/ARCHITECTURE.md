# PlateGap — architecture and technical design

Category `#daily-life-enhancement` · Lane `#startup` · Account 905543840246 · us-east-1

## The insight the product is named after

You pre-pay for a campus meal plan. The menu is fixed and posted weekly — you
never chose it. Nobody tells you what it actually delivers nutritionally, and
when it falls short you pay to close that gap out of your own pocket without
ever seeing the number.

PlateGap computes that number, tells you the cheapest way to close it, and then
tells the institution how to stop the gap existing.

## The optimization core

This is the part that is not a language model, and the part the write-up leads with.

### Variables

- `m_i ≥ 0` — servings of mess item *i* eaten today. **Cost 0** (already paid for).
  Bounded `0 ≤ m_i ≤ cap_i` by what is actually served and what a person will
  realistically eat.
- `x_j ≥ 0` — units of outside item *j* bought with your own money. **Cost `c_j` > 0**.

### Program

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

### Why the dual solution is the whole product

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

### Institution mode — inverse optimization

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

## Solver implementation

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

## Where the language model is used, and where it is not

| Job | Tool | Constrained how |
| --- | --- | --- |
| Menu photo → text | Textract `DetectDocumentText` | deterministic |
| Menu text → canonical food IDs | Bedrock Nova Lite | output restricted to IDs that exist in our catalog; anything unmapped is surfaced to the user, never invented |
| Solver output → English | Bedrock Nova Lite | receives only numbers; prompt forbids introducing any figure not supplied |
| Choosing what to eat | **the simplex solver** | — |
| Computing nutrition | **the food composition table** | — |
| Deciding quantities | **the simplex solver** | — |

Claude Haiku 4.5 is available on this account via the `us.anthropic.*` inference
profile if Nova Lite's explanation quality proves insufficient.

## Nutrition data

Composite Indian dishes are **recipe-decomposed into base ingredients** rather
than guessed at dish level — dal becomes lentils + oil + spices at standard
ratios, and the nutrients come from the base ingredients. This is more defensible
than any dish-level estimate and is a detail worth stating in the write-up.

Base composition data: USDA FoodData Central (public domain, bulk download).
Indian-specific items that FDC lacks get a curated table with cited sources.

**Open risk:** nutrient data quality is the largest technical risk in the project.
Budget real time for it and cite every source in the repo.

## Prices

- Local survey — items sold near the hostel, collected by Anish. This is what
  makes the numbers real rather than illustrative.
- A national retail price feed for staples, if a fetchable one checks out.
  **Unverified — do not promise this until confirmed.**

## Who this is for — it is not my hostel

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
3. **Photograph the notice board** — the image goes straight to Nova Lite, which
   is multimodal, and comes back as canonical food IDs.

Prices work the same way: bundled regional defaults (₹ and $) that produce a
sensible answer immediately, with every single price editable inline. Somebody
in Ohio gets a real answer from the defaults, and a better one after thirty
seconds of editing.

My mess is the demo button and the story. It is not the schema.

## AWS architecture — deliberately small

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
         ├── parse      menu text or photo → canonical food IDs   (Nova Lite, multimodal)
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
| Textract | Nova Lite accepts images directly, so a separate OCR service would be one more dependency for a job one call already does |
| DynamoDB | Nothing here actually needs shared durable state. Catalog is static JSON, metrics are logs, shared plans ride in the URL fragment |
| Step Functions | There is no long-running workflow. The solve is single-digit milliseconds |
| EC2 | Nothing needs to be always-on, and an instance in the request path is the single most likely way to fail the ship gate between Oct 2 and Oct 19 |

The existing `t4g.medium` stays out of the project entirely. Stopping it while
it is unused also stops it consuming credits.

**Total running cost: inside the always-free tier, plus a few rupees of Bedrock.**
That number goes in the write-up.

## API shapes

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
