# TODO

Things worth doing that aren't blocking. One line each. Add to it, tick it off,
delete when done.

## Solver

- [ ] Audit endpoint takes ~8s for 100 candidates x 7 days — trim to ~40 candidates or show a progress indicator
- [ ] `choose_leaving` has two tie-break branches that do the same thing — collapse them
- [ ] If the problem ever grows past ~200 variables, switch to bounded-variable simplex so serving caps stop costing a row each
- [ ] Confirm a row dropped by `_drive_out_artificials` reports a zero dual and not a stale one

## Data

- [ ] Cite a source for every row in the nutrient table, in the repo, not in my head
- [ ] Write down the serving-size assumption for each mess item so the numbers are auditable
- [ ] Decide whether nutrient targets follow ICMR (India) or US DRI, and switch by region

## Infra and repo

- [ ] Add `.gitignore` for `.venv`, `__pycache__`, `.pytest_cache`
- [ ] Add `requirements-dev.txt` pinning scipy and pytest
- [ ] GitHub Actions workflow running the differential test on every push
- [ ] Pick the number of points on the frontier chart — 30 was a guess

## Product

- [ ] A/B Nova Lite against Claude Haiku 4.5 on explanation quality once explanations exist
- [ ] Assert in tests that the explanation contains no number that wasn't in the solver output
- [ ] Decide what the app does when the menu alone already meets every target — the answer is a good screen, not an empty one
