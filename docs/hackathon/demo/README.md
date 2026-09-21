# Screenshots of the live site

Seven screenshots of <https://d2u44arueak38s.cloudfront.net>, with what each
one shows, for a judge who wants the tour without opening the site. The
write-up that uses them is [SUBMISSION.md](../SUBMISSION.md).

They are taken by `scripts/capture_demo.py`, which fails if the browser console
reports an error, so each is a picture of a page that worked, not one that only
looked fine.

| File | What it shows |
| --- | --- |
| [01-the-gap.png](01-the-gap.png) | The Indian hostel mess on Monday: 4 of 12 targets the menu cannot reach, and ₹7.82 a day to close them. The shortfalls lead; the method is folded underneath, with the shadow prices one click away: zinc at ₹7.53/mg, one more roti worth ₹0.597, 100 g more appetite worth ₹3.47. |
| [02-what-each-rupee-buys.png](02-what-each-rupee-buys.png) | The cost-of-nutrition frontier. Convex and flattening: the first rupees buy a lot, the last ones very little. |
| [03-the-menu-audit.png](03-the-menu-audit.png) | The institutional view. 600 students spend ₹264,486 a month topping up; the top menu change, khada masoor dal, recovers ₹82,842 of it. Each row says which shadow prices it answers, and what one serving uses of each ceiling. |
| [04-where-the-numbers-come-from.png](04-where-the-numbers-come-from.png) | Provenance: USDA FoodData Central ids, the retention factors, the two ingredients from IFCT 2017, and which reference intakes apply. |
| [05-us-dining-hall.png](05-us-dining-hall.png) | The same machinery on a North American dining hall: 5 of 12 targets unreachable, $1.25 a day, against the US DRIs. |
| [06-us-dining-hall-audit.png](06-us-dining-hall-audit.png) | The dining-hall audit at 600 students: $19,835.57 a month, of which a black bean and rice bowl recovers $6,056.85. At the 3,000 students the write-up quotes, that is $99,177.86 and $30,284. Each recommendation shows what it costs in energy, saturated fat and sodium next to what it saves. |
| [07-build-a-menu.png](07-build-a-menu.png) | The builder: start from a preset or from nothing, pick dishes per meal per day, and share the result as a link that carries the whole menu in the URL fragment. |

**03 is out of date.** It was shot before servings were resized to the
standard katori on 2026-09-21, and still shows the old audit (₹271,698 a month,
mutter paneer first). The caption above gives what the live site shows now.
Re-shoot before submitting.

Re-shoot them with:

```bash
uv run --group dev python scripts/capture_demo.py
```
