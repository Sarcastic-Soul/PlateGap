# TODO

Things worth doing that aren't blocking. One line each. Add to it, tick it off,
delete when done.

## Solver

- [ ] Audit endpoint takes ~8s for 100 candidates x 7 days — trim to ~40 candidates or show a progress indicator
- [ ] `choose_leaving` has two tie-break branches that do the same thing — collapse them
- [ ] If the problem ever grows past ~200 variables, switch to bounded-variable simplex so serving caps stop costing a row each
- [ ] Confirm a row dropped by `_drive_out_artificials` reports a zero dual and not a stale one

## Data

- [ ] Replace the paneer and jaggery proxies with IFCT 2017 values and drop the estimated flag
- [ ] Sanity-check the seed market prices against a real shop near campus
- [ ] Cook-loss factors: the catalog treats a cooked ingredient as the ingredient, which overstates some vitamins
- [ ] Write down the serving-size assumption for each mess item so the numbers are auditable
- [ ] Decide whether nutrient targets follow ICMR (India) or US DRI, and switch by region

## Infra and repo

- [ ] Pin the dev dependencies to exact versions so CI and local agree
- [ ] Pick the number of points on the frontier chart — 30 was a guess

## Product

- [ ] Build the parse endpoint: paste a menu as text, or photograph the notice board, and match it to the catalog
- [ ] Build the explain endpoint so the write-up on screen is written rather than templated
- [ ] Let someone assemble a menu from the catalog in the interface, not just pick a preset
- [ ] Share a menu by link so a whole hostel can use one someone already typed in
- [ ] A/B Nova Lite against Claude Haiku 4.5 on explanation quality once explanations exist
- [ ] Assert in tests that the explanation contains no number that wasn't in the solver output
- [ ] Decide what the app does when the menu alone already meets every target — the answer is a good screen, not an empty one

## Infra

- [x] `allowed_origin` stays `*` on purpose — anyone should be able to call the API from their own clone
- [ ] Add a CloudFront response headers policy with CSP and HSTS
- [ ] Ask AWS to raise the Lambda concurrency limit — this account is capped at 10, which is thin if several people click at once
- [ ] Move Terraform state to S3 with DynamoDB locking if anyone else ever runs it
- [ ] Check whether arm64 is actually faster than x86_64 for this solver before claiming it
