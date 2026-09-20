# TODO

Things worth doing that aren't blocking. One line each. Add to it, tick it off,
delete when done.

## Waiting on the account owner

- [ ] Sanity-check the seed market prices against a real shop near campus
- [ ] Apply the Terraform for the scan budget table, the cap and the 30 s timeout — the code ships without it, but the ceiling does not exist until it is applied
- [ ] Set an AWS Budgets alert (free, two per account) so a surprise bill is an email rather than a discovery
- [ ] Decide on a licence — there is no LICENSE file, so by default nobody may reuse the code

## Product

- [ ] Decide whether a shared link should be able to carry prices as well as the menu
- [ ] A scanned menu's corrections are lost on "Start over" — worth keeping the edited text around
- [ ] Only the first page of a multi-page PDF menu is reliably read; a second page would need a second call

## Data

- [ ] Vitamin B12 for paneer and jaggery is still estimated — IFCT 2017 measures it for no food at all, so it needs another source
- [ ] Deep-fried flour uses the sauteed-flour retention code, which probably understates the loss; pressure cooking has no code in Release 6 at all
- [ ] Sprouts use the shortest legume boiling code, which is longer than sprouts need and so probably overstates the loss

## Settled, with the measurement that settled it

- [x] Bounded-variable simplex — not needed: a real solve is 42 variables and 58 rows, nowhere near the ~200 where a row per serving cap would matter
- [x] Frontier points stay 24 — 12 points 176 ms, 24 points 314 ms, 40 points 502 ms, and at chart width 24 is already a point every 30 px
- [x] Applied: CSP and HSTS are on the live responses, the function has 1769 MB, and `explain` now answers from Nova Lite rather than the templated fallback
- [x] Lambda memory 1769 MB — the exact point AWS hands over one whole vCPU; above it a single-threaded interpreter pays for a core it cannot use
- [x] arm64 stays, justified on Graviton's published price, and the repo does not claim it is faster because nobody has measured it
- [x] Local Terraform state stays; `infra/backend.tf.example` has the S3 + DynamoDB migration for the day a second person applies
- [x] `explain` stays on Nova Lite — one call is 732 in and ~130 out, so $0.075 per thousand against Haiku 4.5's $1.38; Haiku also needs Anthropic's use-case form, which is the only thing standing between this account and it
- [x] Lambda concurrency stays at 10 — ten browsers arriving at once lost 4 of 40 calls and the whole burst was over in 5.6 s, so the front end retries a 429 with jitter instead; ten arrivals over a minute lost nothing
- [x] Front end is Preact + htm, vendored in `web/vendor/`, still no build step — all seven demo screenshots came out byte-identical to the hand-rolled version, so the port changed no pixels
- [x] `allowed_origin` stays `*` on purpose — anyone should be able to call the API from their own clone
- [x] The tab bar fits on one line at 1440 px — the redesign gave each tab an icon and a short label, and the bar scrolls sideways rather than wrapping
- [x] Demo screenshots match the live site — capturing against CloudFront after the redesign produced files byte-identical to the committed ones
- [x] A PDF goes to Bedrock whole, as a `document` block — no rasterising, so the function needs no poppler or PIL; measured at 1,862 tokens in, ~1,100 out, about ten seconds
- [x] The model transcribes and never matches — asked to emit the days down the side instead of across the top it dropped most of the grid and looped one row to the token cap, and every instruction past "copy what is printed" cost transcription quality
- [x] `scan` is capped at 500 reads a day, counted in DynamoDB — reserved concurrency alone allows ~1 scan/sec, which is ~$34/day of Bedrock on a public endpoint, and WAF costs more per month than the loss it would prevent
- [x] The counter fails closed and uses `ADD` rather than read-then-write — a module global is per warm container, so its real ceiling is that number times however many are alive
- [x] Near misses are grouped by written name — a week of menu says "SAMBER" four times and "CHUTNEY" three, so 29 rows of unmatched became 11 worth a tap and 9 folded away
