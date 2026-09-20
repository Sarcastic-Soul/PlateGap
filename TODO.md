# TODO

Things worth doing that aren't blocking. One line each. Add to it, tick it off,
delete when done.

## Waiting on the account owner

- [ ] Run `./scripts/bootstrap_aws.sh -auto-approve` to apply the CSP/HSTS policy, the Lambda memory bump and the Bedrock policy
- [ ] Submit the Anthropic use-case form in the console so Haiku 4.5 answers — Nova Lite already does
- [ ] Ask AWS to raise the Lambda concurrency limit — this account is capped at 10, which is thin if several people click at once
- [ ] Sanity-check the seed market prices against a real shop near campus
- [ ] A/B Nova Lite against Claude Haiku 4.5 on explanation quality — blocked until Haiku is enabled on the account

## Product

- [ ] Migrate the front end to Preact + htm, vendored, no build step — the UI changes get cheap after that
- [ ] Decide whether a shared link should be able to carry prices as well as the menu

## Data

- [ ] Vitamin B12 for paneer and jaggery is still estimated — IFCT 2017 measures it for no food at all, so it needs another source
- [ ] Deep-fried flour uses the sauteed-flour retention code, which probably understates the loss; pressure cooking has no code in Release 6 at all
- [ ] Sprouts use the shortest legume boiling code, which is longer than sprouts need and so probably overstates the loss

## Settled, with the measurement that settled it

- [x] Bounded-variable simplex — not needed: a real solve is 42 variables and 58 rows, nowhere near the ~200 where a row per serving cap would matter
- [x] Frontier points stay 24 — 12 points 176 ms, 24 points 314 ms, 40 points 502 ms, and at chart width 24 is already a point every 30 px
- [x] Lambda memory 1769 MB — the exact point AWS hands over one whole vCPU; above it a single-threaded interpreter pays for a core it cannot use
- [x] arm64 stays, justified on Graviton's published price, and the repo does not claim it is faster because nobody has measured it
- [x] Local Terraform state stays; `infra/backend.tf.example` has the S3 + DynamoDB migration for the day a second person applies
- [x] `allowed_origin` stays `*` on purpose — anyone should be able to call the API from their own clone
