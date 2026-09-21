# AGENTS.md

A guide for coding agents and new contributors. It says what the project is,
where things live, how to run and change them, and which files you must not
edit by hand. For the product itself read [README.md](README.md); for an index
of every doc, [docs/README.md](docs/README.md).

## What this is

PlateGap tells a hostel student what their pre-paid mess menu leaves them short
of nutritionally, and the cheapest top-up that closes the gap. It also audits a
whole menu for the institution. The core is a two-phase simplex written from
scratch in stdlib Python; its shadow prices are what the interface shows.

Live at <https://d2u44arueak38s.cloudfront.net>. It is an entry in AWS's
"Zero to Shipped" hackathon, due 2026-10-02 ([docs/hackathon/](docs/hackathon/)).

## Repo map

| Path | What it is |
| --- | --- |
| `solver/` | The engine. `simplex.py` (two-phase simplex, duals, sensitivity ranges), `model.py` (menu to LP), `plan.py` (gap, cheapest, frontier, week), `audit.py` (reduced-cost menu audit), `menutext.py` (menu text to catalog dishes, no model), `menuscan.py` (PDF or photo to text via Bedrock), `explain.py` (Bedrock write-up with arithmetic check), `scanbudget.py` (daily `scan` cap in DynamoDB), `targets.py` (daily nutrient targets) |
| `lambda/handler.py` | The one Lambda entry point. Ten actions, dispatched on the body's `action` field |
| `web/` | The front end. Preact + htm vendored in `web/vendor/`, no build step. `config.js` is overwritten at deploy time |
| `data/build_catalog.py` | Builds `data/foods.json` from USDA SR Legacy plus hand-cited rows. Recipes, serving sizes (`SERVING_SOURCES`) and retention factors live here |
| `data/foods.json` | The catalog the solver reads. Generated |
| `data/menus/` | The three preset menus (`iiit`, `dining-hall`, `generic`) and the IIIT source PDF |
| `data/aliases.json` | Regional dish names the live parser accepts |
| `data/field/` | Field-study inputs and outputs: `menus/` (transcriptions and `SOURCES.csv`), `settlements.json`, `settled.csv`, `results.json` |
| `tests/` | pytest suite. `test_simplex.py` holds the solver to scipy |
| `scripts/` | Dev server, benchmark, UI smoke test, screenshots, field study, CloudTrail export, doc generator, Lambda packaging, AWS bootstrap |
| `infra/` | Terraform: S3 + CloudFront, Lambda + Function URL, DynamoDB, GitHub OIDC role, budget |
| `.github/workflows/` | `test.yml` on every push; `deploy.yml` on push to `main` |
| `docs/` | [DATA.md](docs/DATA.md) (generated) and [hackathon/](docs/hackathon/) (design, cost, sources, field study, submission) |
| `TODO.md` | Open problems, and the measurements that closed the settled ones |

## Run it

```bash
uv run --with pytest --with scipy python -m pytest -q    # 873 passed, 40 skipped
uv run --group dev pytest -q                             # the same suite, as CI runs it
uv run python scripts/dev_server.py                      # http://127.0.0.1:8000 (PORT to change)
uv run python scripts/benchmark_solver.py                # times gap, cheapest, frontier, weekly audit
```

The dev server serves `web/` and routes POSTs to the same `handler` Lambda
runs. Bedrock-backed actions (`scan`, `explain`) fall back gracefully without
AWS credentials.

Browser checks need Playwright from the dev group:

```bash
PORT=8123 uv run python scripts/dev_server.py
SITE=http://127.0.0.1:8123 uv run --group dev python scripts/smoke_ui.py
uv run --group dev python scripts/capture_demo.py        # re-shoots docs/hackathon/demo/ from the live site
```

## How the data is built

1. `data/build_catalog.py` needs the USDA SR Legacy CSVs, which are not
   committed (about 36 MB). Download them from the URL in the script's
   docstring, then:

   ```bash
   uv run python data/build_catalog.py --sr path/to/FoodData_Central_sr_legacy_food_csv_2018-04
   ```

   This rewrites `data/foods.json`.
2. Regenerate the data document from the rebuilt catalog:

   ```bash
   uv run python scripts/gen_data_doc.py
   ```

   This rewrites `docs/DATA.md`. `tests/test_catalog_data.py` fails if the
   file on disk differs from what the generator would write.

To change a recipe, serving weight or retention factor, edit
`data/build_catalog.py`, then run both steps.

## The field study

`scripts/field_study.py` runs the app's own pipeline over published hostel
menus. Each step can be re-run on its own:

| Command | What it does |
| --- | --- |
| `transcribe` | Reads each source file into text with the live reader (Bedrock Nova Lite). Needs AWS credentials and `uv run --with boto3 --with 'botocore[crt]' --with pillow`. The raw files are gitignored; `data/field/menus/SOURCES.csv` has the URLs |
| `parse` | Matches the text to catalog dishes with `solver/menutext.py`, applies `data/field/settlements.json`, and writes `data/field/menus/parsed/` and `data/field/settled.csv` |
| `open` | Lists every name still unsettled, grouped, with near misses, for writing settlements against |
| `run` | Solves each week and writes `data/field/results.json` (the default command) |
| `report` | Rewrites the generated tables in `docs/hackathon/FIELD-STUDY.md` from `results.json` |

```bash
uv run python scripts/field_study.py parse
uv run python scripts/field_study.py run
uv run python scripts/field_study.py report
```

## Deploy

Push to `main`. `.github/workflows/deploy.yml` runs the tests, builds
`build/lambda.zip` with `scripts/package_lambda.sh`, assumes an AWS role over
OIDC, updates the function, writes `web/config.js`, syncs `web/` to S3,
invalidates CloudFront, and calls the live endpoint before it finishes. There
are no AWS keys in the repo or its settings.

Infrastructure is Terraform in `infra/`, applied by a person, never by CI
(`scripts/bootstrap_aws.sh` does the first apply and sets the repository
variables). The deploy role can update code and the site; it cannot create or
destroy infrastructure.

## Conventions

- **Commit messages.** An imperative, plain-English subject that says what
  changed for a reader, not which files ("Size servings to the standard
  katori", "Say how far every shadow price holds"). A prose body explaining
  why, with the numbers that moved. No `Co-Authored-By`, no "Generated with"
  line, no AI attribution of any kind.
- **The solver is stdlib-only Python.** `dependencies = []` in
  `pyproject.toml`, and CI unzips the Lambda package and runs a solve in a
  clean interpreter to prove it. boto3 is imported lazily, only on the Bedrock
  and DynamoDB paths, because the Lambda runtime provides it. scipy, pytest and
  Playwright are dev-only.
- **No front-end build step.** Plain ES modules and a vendored Preact + htm.
  No `node_modules`, no bundler. The CSP is `script-src 'self'` with no
  `unsafe-inline`, so no inline scripts or `element.style` writes.
- **Every input to the handler is bounded.** The endpoint is public and
  unauthenticated.
- **Numbers in docs are measured or derived from the code.** If you change the
  catalog or solver, re-check the figures quoted in README.md and
  docs/hackathon/SUBMISSION.md.
- Terms used throughout: *mess*, *menu*, *top-up*, *shadow price*, *catalog*,
  *ladle* (a serving sized to an ICMR-NIN standard katori).

## Generated files: do not hand-edit

| File | Generator |
| --- | --- |
| `data/foods.json` | `data/build_catalog.py` |
| `docs/DATA.md` | `scripts/gen_data_doc.py` (a test enforces it) |
| `data/field/menus/text/` | `scripts/field_study.py transcribe` |
| `data/field/menus/parsed/`, `data/field/settled.csv` | `scripts/field_study.py parse` |
| `data/field/results.json` | `scripts/field_study.py run` |
| Tables between the `generated` markers in `docs/hackathon/FIELD-STUDY.md` | `scripts/field_study.py report` |
| `docs/hackathon/evidence/*` | `scripts/export_cloudtrail.py` |
| `docs/hackathon/demo/*.png` | `scripts/capture_demo.py` |
| `web/config.js` | The deploy workflow (committed as `null`, which the dev server relies on) |
| `build/` | `scripts/package_lambda.sh` (gitignored) |
