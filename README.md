# PlateGap

**Your meal plan is already paid for. This works out what it still leaves you
short of, and the cheapest thing you can buy to fix it.**

A hostel mess fee or a campus meal plan is a sunk cost. Once it is paid, the
food on the counter is free at the margin — but it is rationed: unlimited
rice and roti, one ladle of paneer, one boiled egg. Students top the rest up
out of their own pockets without ever knowing what they are topping up, or
whether they are buying the right thing.

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
also post your own menu.

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

Two ingredients have no SR Legacy equivalent and are hand-entered from
published composition, flagged `proxy` and shown as *estimated* in the
interface. Using a bad USDA substitute would have been worse than admitting
the gap: whole-milk ricotta, the nearest fresh acid-set cheese, reports 7.5 g
protein per 100 g against paneer's 18.3 g. Understating the single biggest
vegetarian protein source on the menu would have inflated the very shortfall
this project measures — in our own favour.

Targets ship two reference systems, ICMR-NIN 2020 and the US DRI, because they
disagree sharply. Iron for an adult man is 19 mg under one and 8 mg under the
other, since the Indian figure assumes a largely plant-based diet and poorer
absorption. Presenting either as universal would be wrong for half the people
who open the app.

## Architecture

```
CloudFront ──▶ S3 (private, OAC)          the site: three static files
     │
  browser ──▶ Lambda Function URL ──▶ handler.py ──▶ solver/
                                                      simplex.py   two-phase simplex + duals
                                                      model.py     menu + profile + prices → LP
                                                      plan.py      gap / cheapest / frontier / week
                                                      audit.py     reduced-cost menu search
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

Costs are in `docs/hackathon/COST-AND-INFRA.md`. In short: Lambda's million
free requests a month and CloudFront's free tier are always-free, and the
rest is fractions of a cent.

## Running it

```bash
uv run --group dev pytest -q          # 348 tests
uv run python scripts/dev_server.py   # http://127.0.0.1:8000
```

Rebuilding the food catalog needs the SR Legacy CSV download:

```bash
uv run python data/build_catalog.py --sr path/to/FoodData_Central_sr_legacy_food_csv_2018-04
```

## Deploying

```bash
cd infra
terraform init
terraform apply
```

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
- Losses in cooking, serving and reheating.
- Anything marked *estimated*.

Open problems are in [TODO.md](TODO.md).
