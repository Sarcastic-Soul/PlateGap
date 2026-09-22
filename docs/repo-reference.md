# Repo map and generated files

Reference detail split out of AGENTS.md — full file-by-file map and the list of files a generator owns.

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
