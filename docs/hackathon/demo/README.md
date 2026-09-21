# Screenshots of the live site

Captured from <https://d2u44arueak38s.cloudfront.net> by
`scripts/capture_demo.py`, which fails if the browser console reports an error
— so these are pictures of a page that actually worked, not of a page that
looked fine.

| File | What it shows |
| --- | --- |
| `01-the-gap.png` | Indian hostel mess, Monday. 4 of 12 targets the menu cannot reach and ₹7.82 a day to close them, with the shortfalls given the top of the page and the method folded underneath — the shadow prices are one click away: zinc at ₹7.53/mg, one more roti worth ₹0.597, 100 g more appetite worth ₹3.47. |
| `02-what-each-rupee-buys.png` | The cost-of-nutrition frontier. Convex and flattening — the first coins buy a lot, the last ones buy very little. |
| `03-the-menu-audit.png` | The institutional view. 600 students leak ₹264,486 a month; the top menu change recovers ₹82,842 of it. Each row says which duals it answers, and what one serving spends against the ceilings. |
| `04-where-the-numbers-come-from.png` | Provenance: USDA FoodData Central ids, the retention factors, which two ingredients come from IFCT 2017, which reference intakes were used. |
| `05-us-dining-hall.png` | The same machinery on a North American dining hall: 5 of 12 targets unreachable, $1.25 a day, measured against the US DRIs. |
| `06-us-dining-hall-audit.png` | Dining-hall audit at 3000 students — $99,177.86 a month, a black bean and rice bowl worth $30,284 of it — with what each recommendation costs in energy, saturated fat and sodium next to what it saves. |
| `07-build-a-menu.png` | The builder: start from a preset or from nothing, pick dishes per meal per day, and share the result as a link that carries the whole menu in the fragment. |

Re-shoot them with:

    uv run --group dev python scripts/capture_demo.py
