#!/usr/bin/env python3
"""Write `docs/DATA.md` out of the catalog.

    uv run python scripts/gen_data_doc.py

Every serving weight in this project is a guess, and a guess nobody can read
is indistinguishable from a measurement. This prints all of them -- each dish,
what one serving is assumed to weigh, what kind of estimate that is, the
ingredient recipe it is built from, how each ingredient is cooked and what
that costs in vitamins, and the USDA row every ingredient came from.

It is generated rather than written so that it cannot drift away from
`data/foods.json`. If the two disagree, the file is stale, and the test in
`tests/test_data_doc.py` fails rather than letting it rot quietly.
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "data", "foods.json")
OUT = os.path.join(ROOT, "docs", "DATA.md")

# Only the nutrients worth printing per dish. The full sixteen make a table
# nobody reads; these are the ones the solver's floors actually bind on, plus
# the two the cook-loss factors move.
HEADLINE = ["kcal", "protein", "calcium", "iron", "zinc", "vitc", "folate"]

# Nutrients whose retention factor is worth showing next to a recipe line. The
# minerals are 1.0 almost everywhere, so printing them per line would bury the
# two columns that vary.
SHOWN_FACTORS = ["vitc", "folate"]

CUISINE_TITLES = [
    ("indian", "Indian hostel mess"),
    ("american", "North American dining hall"),
]


def fmt(value):
    """Trim a float to something a reader can scan."""
    if value is None:
        return "--"
    if abs(value - round(value)) < 0.005:
        return "%d" % round(value)
    return ("%.2f" % value).rstrip("0").rstrip(".")


def ingredient_label(catalog, ingredient_id):
    ingredient = catalog["ingredients"][ingredient_id]
    fdc_id = ingredient["source"].get("fdcId")
    if fdc_id:
        return "%s ([%s](https://fdc.nal.usda.gov/food-details/%s/nutrients))" % (
            ingredient["name"], fdc_id, fdc_id)
    # Not USDA is not the same as not measured. The rows taken from the Indian
    # tables say so; the ones nobody measured say that instead.
    if ingredient.get("reported"):
        return "%s (%s)" % (ingredient["name"], ingredient["source"]["dataset"])
    return "%s (estimated, no published table)" % ingredient["name"]


def write_retention(out, catalog):
    out.append("## Cook loss\n")
    out.append(
        "A cooked vegetable is not a raw one. Vitamin C and folate are the\n"
        "worst of it: boiling a cauliflower and pouring the water away takes\n"
        "most of both. Every recipe line below names how that ingredient is\n"
        "prepared, and the factors here are applied to it before it is added\n"
        "into the dish.\n")
    out.append(
        "A factor of 1.0 is a claim like any other, so the reason for each one\n"
        "is written down. The commonest reason is that the ingredient's USDA\n"
        "row is *already* the cooked food -- `Rice, white, cooked`, `Lentils,\n"
        "boiled` -- in which case the loss is in the source number and applying\n"
        "it again would invent a shortfall this project would then be paid to\n"
        "point out.\n")
    out.append("")
    nutrients = [n["id"] for n in catalog["nutrients"]]
    varying = [k for k in nutrients
               if any(m["factors"].get(k, 1.0) != 1.0
                      for m in catalog["retention"].values())]

    header = ["Preparation", "USDA code"] + varying
    out.append("| " + " | ".join(header) + " |")
    out.append("|" + "|".join(["---"] * len(header)) + "|")
    for method_id in sorted(catalog["retention"]):
        method = catalog["retention"][method_id]
        code = method["usdaCode"]
        code_cell = "`%s` %s" % (code, method["usdaDescription"]) if code else "none"
        row = ["**%s**<br>`%s`" % (method["name"], method_id), code_cell]
        row += [fmt(method["factors"].get(k, 1.0)) for k in varying]
        out.append("| " + " | ".join(row) + " |")
    out.append("")
    out.append("Why each one is what it is:\n")
    for method_id in sorted(catalog["retention"]):
        method = catalog["retention"][method_id]
        out.append("- **%s** (`%s`) -- %s" % (method["name"], method_id, method["why"]))
    out.append("")


def write_serving_sources(out, catalog):
    out.append("## What a serving means\n")
    out.append(
        "None of these were weighed. Each dish says which kind of estimate its\n"
        "serving weight is, which is the difference between a number you can\n"
        "check by counting and a number somebody eyeballed at a counter.\n")
    out.append("")
    out.append("| Kind | What it means |")
    out.append("|---|---|")
    for key in sorted(catalog["servingSources"]):
        out.append("| `%s` | %s |" % (key, catalog["servingSources"][key]))
    out.append("")


def write_item(out, catalog, item, per_key, portion):
    """One dish or market item, with its recipe and what it comes to.

    `portion` is the word for one of whatever this is -- a mess serving, or a
    shop unit -- because a dish and a purchase are the same shape of thing
    with different names for the amount you get at once.
    """
    retention = catalog["retention"]
    recipe_grams = sum(line["grams"] for line in item["recipe"])
    # A dish states what one serving weighs on the plate; a market item is
    # sold as a unit whose weight is exactly what is in it.
    weight = item.get("servingGrams", recipe_grams)

    out.append("#### %s" % item["name"])
    out.append("")
    bits = ["`%s`" % item["id"], "**%s g** per %s" % (fmt(weight), portion)]
    if "unit" in item:
        bits.append("sold as %s" % item["unit"])
    if "servingSource" in item:
        bits.append("serving is a `%s`" % item["servingSource"])
    cap = item.get("maxServings", item.get("maxUnits"))
    if cap is not None:
        bits.append("at most %d a day" % cap)
    if item.get("proxy"):
        bits.append("**estimated**")
    out.append(" &middot; ".join(bits) + "\n")

    out.append("| Ingredient | g | Prepared | " +
               " | ".join("%s kept" % k for k in SHOWN_FACTORS) + " |")
    out.append("|---|---|---|" + "|".join(["---"] * len(SHOWN_FACTORS)) + "|")
    for line in sorted(item["recipe"], key=lambda l: -l["grams"]):
        factors = retention[line["prep"]]["factors"]
        cells = [ingredient_label(catalog, line["ingredient"]),
                 fmt(line["grams"]),
                 retention[line["prep"]]["name"]]
        cells += ["%d%%" % round(100 * factors.get(k, 1.0)) for k in SHOWN_FACTORS]
        out.append("| " + " | ".join(cells) + " |")
    out.append("")

    # The gap between what goes in and what comes out is water added in a
    # gravy or water driven off in a pan, and it is worth showing because a
    # reader who thinks the two should match has found a real question.
    delta = weight - recipe_grams
    if abs(delta) >= 1:
        note = "water added in cooking" if delta > 0 else "weight lost in cooking"
        out.append("Recipe totals %s g against a %s g %s: %s g %s.\n"
                   % (fmt(recipe_grams), fmt(weight), portion, fmt(abs(delta)), note))

    per = item[per_key]
    meta = {n["id"]: n for n in catalog["nutrients"]}
    parts = ["%s %s %s" % (fmt(per[k]), meta[k]["unit"], meta[k]["name"].lower())
             for k in HEADLINE if k in per]
    out.append("Per %s: %s.\n" % (portion, ", ".join(parts)))

    if item.get("proxy"):
        out.append("> Estimated: %s\n" % item["proxyNote"])


def write_ingredients(out, catalog):
    out.append("## Ingredients\n")
    out.append(
        "Each one is a single USDA FoodData Central SR Legacy food, per 100 g,\n"
        "cited by its `fdcId` so any figure can be checked against the source\n"
        "database. The handful with no USDA row are marked, and what they are\n"
        "based on instead is written against them.\n")
    out.append("")
    out.append("| Ingredient | Source | Per 100 g |")
    out.append("|---|---|---|")
    meta = {n["id"]: n for n in catalog["nutrients"]}
    for key in sorted(catalog["ingredients"]):
        ingredient = catalog["ingredients"][key]
        fdc_id = ingredient["source"].get("fdcId")
        if fdc_id:
            source = "[%s](https://fdc.nal.usda.gov/food-details/%s/nutrients) %s" % (
                fdc_id, fdc_id, ingredient["source"]["description"])
        else:
            source = "**%s** -- %s" % (ingredient["source"]["dataset"],
                                       ingredient["source"]["description"])
            still = ingredient.get("estimated") or []
            if still:
                source += " Still estimated: %s." % ", ".join(
                    "`%s`" % k for k in still)
        per = ingredient["per100g"]
        summary = ", ".join("%s %s %s" % (fmt(per[k]), meta[k]["unit"],
                                          meta[k]["name"].lower())
                            for k in HEADLINE if k in per)
        out.append("| %s<br>`%s` | %s | %s |" % (ingredient["name"], key, source, summary))
    out.append("")


def render(catalog):
    out = []
    out.append("# Where every number comes from\n")
    out.append(
        "**Generated by `scripts/gen_data_doc.py` from `data/foods.json`. Do not\n"
        "edit by hand -- edit `data/build_catalog.py`, rebuild the catalog and\n"
        "run the generator again.**\n")
    out.append(
        "A dish's nutrition here is never estimated at dish level. It is the sum\n"
        "of its ingredients in stated grams -- nearly all of them a single USDA\n"
        "row, the Indian-only ones a single row of the Indian tables -- each one\n"
        "scaled by how much of it survives the way that dish cooks it:\n")
    out.append("")
    out.append("```")
    out.append("dish nutrient  =  sum over ingredients of")
    out.append("                    (per-100 g value)")
    out.append("                  x (grams in the recipe / 100)")
    out.append("                  x (retention factor for how it is prepared)")
    out.append("```")
    out.append("")
    out.append(
        "So every number below can be argued with one term at a time: the USDA\n"
        "row, the grams, or the cooking. That is the whole point of writing them\n"
        "out.\n")

    dishes = catalog["dishes"]
    out.append("%d dishes, %d market items and %d ingredients follow.\n"
               % (len(dishes), len(catalog["market"]), len(catalog["ingredients"])))

    write_retention(out, catalog)
    write_serving_sources(out, catalog)

    out.append("## Dishes\n")
    for cuisine, title in CUISINE_TITLES:
        chosen = [d for d in dishes.values() if d["cuisine"] == cuisine]
        if not chosen:
            continue
        out.append("### %s\n" % title)
        for dish in sorted(chosen, key=lambda d: d["name"]):
            write_item(out, catalog, dish, "perServing", "serving")

    out.append("## Market items\n")
    out.append(
        "What a student can buy with their own money. The recipe is the grams of\n"
        "catalog ingredient in one purchasable unit, so a bought item's nutrition\n"
        "comes down exactly the same path as a mess dish.\n")
    out.append("")
    for item in sorted(catalog["market"].values(), key=lambda d: d["name"]):
        write_item(out, catalog, item, "perUnit", "unit")

    write_ingredients(out, catalog)
    return "\n".join(out).rstrip() + "\n"


def main():
    with open(CATALOG) as handle:
        catalog = json.load(handle)
    text = render(catalog)
    with open(OUT, "w") as handle:
        handle.write(text)
    print("wrote %s (%d lines)" % (OUT, text.count("\n")))


if __name__ == "__main__":
    main()
