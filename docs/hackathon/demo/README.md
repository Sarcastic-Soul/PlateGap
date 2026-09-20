# Screenshots of the live site

Captured from <https://d2u44arueak38s.cloudfront.net> by
`scripts/capture_demo.py`, which fails if the browser console reports an error
— so these are pictures of a page that actually worked, not of a page that
looked fine.

| File | What it shows |
| --- | --- |
| `01-the-gap.png` | Indian hostel mess, Monday. 3 of 12 targets the menu cannot reach, ₹9.29 a day to close them, and the shadow prices underneath: zinc at ₹3.90/mg, one more roti worth ₹0.605, 100 g more appetite worth ₹4.22. |
| `02-what-each-rupee-buys.png` | The cost-of-nutrition frontier. Convex and flattening — the first coins buy a lot, the last ones buy very little. |
| `03-the-menu-audit.png` | The institutional view. 600 students leak ₹284,355 a month; matar chola on its six absent days recovers ₹85,534 of it. Each row says which duals it is answering. |
| `04-where-the-numbers-come-from.png` | Provenance: USDA FoodData Central ids, which dishes are proxies, which reference intakes were used. |
| `05-us-dining-hall.png` | The same machinery on a North American dining hall: 5 of 12 targets unreachable, $1.25 a day, $37.38 a month, measured against the US DRIs. |
| `06-us-dining-hall-audit.png` | Dining-hall audit. A black bean and rice bowl on six days is worth $6,097 a month across 600 students. |

Re-shoot them with:

    uv run --with playwright python scripts/capture_demo.py
