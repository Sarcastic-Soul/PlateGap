# PlateGap

**Your meal plan is already paid for. This works out what it still leaves you
short of, and the cheapest thing you can buy to fix it.**

A hostel mess fee or a campus meal plan is a sunk cost. Once it is paid, the
food on the counter is free at the margin — but it is rationed: unlimited
rice and roti, one ladle of paneer, one boiled egg. Students top the rest up
out of their own pockets without ever knowing what they are topping up, or
whether they are buying the right thing.

**Live:** <https://d2u44arueak38s.cloudfront.net> — no sign-up, nothing to
install. The API behind it is a single Lambda Function URL:
<https://j3h24i4cnnjhwwxyoenqibxene0yrrju.lambda-url.us-east-1.on.aws/>, which
takes a JSON body such as `{"action": "solve", "menuId": "iiit", "day": "mon"}`.

PlateGap answers three questions, each of which is a linear program:

1. **Where's the gap?** Eat the menu as well as it can possibly be eaten,
   inside the portions actually served and inside what a person can actually
   get through in a day. What is still missing?
2. **What's the cheapest fix?** Add priced items from a shop and minimise the
   money spent while hitting every nutrient floor. The shadow price on a
   binding floor is literally *what the last milligram of zinc costs you*.
3. **What should the kitchen change?** Given that students are spending their
   own money to patch the menu, which single addition would cut that spending
   the most — across everybody?

Three presets ship: a real Indian hostel mess timetable, a representative
North American dining hall, and a deliberately plain canteen to edit. You can
also build a menu of your own — start from a preset or from nothing, pick
dishes per meal per day — paste one in as text and have it matched to the
catalog, or share the one you built as a link. The whole menu travels in the
URL fragment, so there is nothing stored anywhere and nothing to sign into.

## What's interesting about it

**The solver is written from scratch.** `solver/simplex.py` is a two-phase
simplex with dual extraction, in pure Python, with no dependencies — the
Lambda runtime provides boto3 and the function needs nothing else. It is held
to `scipy.optimize.linprog` on a few hundred random instances every time the
code changes, and the tests check the *duals*, not just the objective,
because the duals are what the product actually shows.

That test caught the bug that mattered. Normalising a constraint with a
negative right-hand side negates the row, and negating a row negates its
marginal. With one uniform sign convention, 90 of 267 tests failed: objectives
were right and duals were sign-flipped — on exactly the nutrient-floor rows
this product exists to display. Tracking a per-row sign fixed it.

**The menu audit is the simplex pricing step used as a feature.** Searching
for the best dish to add by re-solving the week once per candidate is slow. At
the optimum, a variable left out of the program improves the objective only if
its reduced cost is negative, and pricing a candidate against the duals we
already have costs one dot product. On Monday's menu that screens 56
candidates down to 11 before any extra solve runs. There is a test that takes
every *rejected* candidate, adds it for real and re-solves, because a screen
with a false negative would silently drop the best recommendation and still
look like a working feature.

The same arithmetic explains itself: the reduced cost is a sum of one term per
constraint, so it decomposes into *why* — "add matar chola, mainly because it
is a cheap route to the zinc floor".

**The constraint that turned out to matter was a physical one.** Without a cap
on how much food a person can eat in a day, the solver meets every ICMR target
from the mess alone by prescribing twelve rotis and five servings of curd.
Arithmetically perfect, useless. With the cap in place, the binding constraint
on a well-stocked menu is *stomach volume*, not the menu — and the shadow
price on that row is the money value of one more gram of appetite. It is the
most interesting number the program produces and it only exists because the
first answer was obviously wrong.

## Where the numbers come from

Ingredients are USDA FoodData Central SR Legacy foods, cited by `fdcId`.
Dishes are computed from ingredient recipes in stated grams, not estimated at
dish level, so any single assumption can be argued with directly rather than
having to take the whole table on faith.

**Cooking is charged for.** Every recipe line says how the ingredient is
prepared, and the USDA Table of Nutrient Retention Factors (Release 6, 2007)
decides how much of each nutrient survives it — boiled into a gravy keeps 85%
of a vegetable's vitamin C and 100% of its minerals, boiled and drained keeps
75% and 90%. The trap is double-counting: SR Legacy carries both raw and
cooked rows, this catalog cites the cooked one wherever it exists, and taking
the loss off *again* would manufacture a shortfall — in the direction that
flatters a product built to sell shortfalls. So those rows take a factor of
1.0 and a test enforces it.

Paneer and jaggery have no SR Legacy equivalent. Using a bad USDA substitute
would have been worse than admitting the gap: whole-milk ricotta, the nearest
fresh acid-set cheese, reports 7.5 g protein per 100 g against paneer's 18.9 g.
Both now come from the Indian Food Composition Tables 2017 (NIN-ICMR), which
is a measured Indian table rather than a guess at an Indian food — and which
puts paneer's calcium at 476 mg per 100 g against the 208 mg previously
guessed. Both stay flagged as *estimated* anyway, for one honest reason:
IFCT 2017 does not measure vitamin B12 for any food in the book, so fifteen of
the sixteen nutrients are sourced and the sixteenth is not. The catalog names
which.

Every serving weight, recipe and retention factor is printed in
[docs/DATA.md](docs/DATA.md), which is generated from the catalog rather than
written, so it cannot quietly drift away from what the solver actually uses.

Targets ship two reference systems, ICMR-NIN 2020 and the US DRI, because they
disagree sharply. Iron for an adult man is 19 mg under one and 8 mg under the
other, since the Indian figure assumes a largely plant-based diet and poorer
absorption. Presenting either as universal would be wrong for half the people
who open the app.

## Architecture

```
CloudFront ──▶ S3 (private, OAC)          the site: no framework, no build step
     │
  browser ──▶ Lambda Function URL ──▶ handler.py ──▶ solver/
                                                      simplex.py   two-phase simplex + duals
                                                      model.py     menu + profile + prices → LP
                                                      plan.py      gap / cheapest / frontier / week
                                                      audit.py     reduced-cost menu search
                                                      menutext.py  pasted menu → catalog dishes
                                                      explain.py   Bedrock write-up, with a fallback
                                                      targets.py   ICMR and DRI reference intakes
```

No API Gateway: the function takes a JSON body and returns one, and needs no
routing, authorizers or usage plans. One wrinkle if you deploy this yourself:
AWS accounts created from around 2024 onward block public Lambda function URLs
by default, and the symptom is a bare 403 with a resource policy that plainly
allows the call. Granting `lambda:InvokeFunction` to `*` alongside the
`InvokeFunctionUrl` grant is what opens it; `infra/lambda.tf` does this and
explains what it costs. No database: the catalog ships inside the
deployment package, which is 51 KB. The function's only permission is to write
its own logs.

CloudFront attaches a response headers policy carrying HSTS and a content
security policy, and because the site is three files with no framework the
policy could be written by reading them rather than by guessing:

```
default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:;
connect-src 'self' https://<function-id>.lambda-url.us-east-1.on.aws;
base-uri 'none'; form-action 'none'; frame-ancestors 'none'
```

Everything the page loads is same-origin. The two exceptions are the emoji
favicon, which is a `data:` SVG in the head, and the `fetch` to the Function
URL, which is a different origin and so has to be named — Terraform takes it
from the resource rather than a pasted string, so a rebuild in another account
gets a policy that works instead of one that silently blocks every request.
There is no `'unsafe-inline'` anywhere: the chart is an inline `<svg>` styled
with classes, nothing assigns to `element.style`, and although `app.js` uses
`innerHTML` freely, markup written that way cannot execute a script it
contains under any policy.

The function has 1769 MB of memory, which is a speed setting rather than a
memory one — it is the point at which Lambda hands out a whole vCPU, and a
single-threaded pure-Python solver cannot use a second one. That number came
out of `scripts/benchmark_solver.py`, which is in the repository precisely so
the next person does not have to take it on trust. `infra/variables.tf` has
the full argument and the measurements.

On **arm64 versus x86\_64**: the function runs on arm64 and this repository
does not claim that is faster, because nobody has measured it. The
architecture is worth keeping for the published Graviton price — about 20%
less per GB-second — and that much is a price list, not a benchmark. The
performance question is genuinely open: the solver is pure Python, its inner
loop is list and float arithmetic in the interpreter, and which way that goes
on Graviton is not something to assert from an armchair. Running
`scripts/benchmark_solver.py` on an arm64 box with the same `--repeat` and
comparing medians would settle it in a couple of minutes.

Costs are in `docs/hackathon/COST-AND-INFRA.md`. In short: Lambda's million
free requests a month and CloudFront's free tier are always-free, and the
rest is fractions of a cent.

## Running it

```bash
uv run --group dev pytest -q             # 442 tests
uv run python scripts/dev_server.py      # http://127.0.0.1:8000
uv run python scripts/benchmark_solver.py  # times the four solver actions
```

Rebuilding the food catalog needs the SR Legacy CSV download, and the data
document is regenerated from the rebuilt catalog:

```bash
uv run python data/build_catalog.py --sr path/to/FoodData_Central_sr_legacy_food_csv_2018-04
uv run python scripts/gen_data_doc.py   # rewrites docs/DATA.md
```

## Deploying

```bash
cd infra
terraform init
terraform apply
```

Terraform keeps its state in a local file, and that is deliberate rather than
an oversight. For one person applying from one machine, a local state file is
one fewer bucket, one fewer table, and no chicken-and-egg problem about which
Terraform builds the backend the state lives in; the file is gitignored, so
nothing leaks, it simply lives in exactly one place.

What it cannot survive is a second person. Two states that each believe they
are the truth produce orphaned resources that Terraform will cheerfully create
again, and the fix is remote state with locking.
`infra/backend.tf.example` is the configuration, with the bucket and DynamoDB
table creation commands and the `terraform init -migrate-state` sequence
written out. It is an example on purpose: switching the live backend here
would strand the state that currently describes running infrastructure, and
the right moment to adopt it is the day a second person shows up — not
before, and not after the first collision.

Then set the four outputs as **repository variables** (not secrets — they are
identifiers, not credentials): `AWS_DEPLOY_ROLE`, `AWS_REGION`, `SITE_BUCKET`,
`LAMBDA_FUNCTION`, `DISTRIBUTION_ID`. Pushes to `main` then run the tests,
build the package, and deploy.

There are no access keys in this repository or its settings. GitHub Actions
assumes an AWS role through OIDC, and the trust policy is pinned to this
repository and the `main` branch, so a pull request from a fork gets a token
with a different subject and cannot assume it. The role can update function
code, write the site and invalidate the cache; it cannot create or destroy
infrastructure. Terraform is run by a person, deliberately.

## What it doesn't know

- Whether the kitchen cooked the recipe we assumed.
- What you like eating. The plan is nutritionally cheapest, not nicest.
- What a serving actually weighs. Every one is an estimate, and
  [docs/DATA.md](docs/DATA.md) says which kind.
- Losses in serving and reheating. Cook loss is accounted for; a dish sitting
  in a warmer for an hour is not.
- Anything marked *estimated*.

Open problems are in [TODO.md](TODO.md).
