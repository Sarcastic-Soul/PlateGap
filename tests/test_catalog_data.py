"""Tests for the catalog's provenance: cook loss, servings, and the doc.

`data/foods.json` is the only thing in this project that is not derived from
something else at runtime, so it is the only thing that can be quietly wrong.
These check the properties that keep it honest:

  * cooking can only take nutrients away, never add them
  * an ingredient whose USDA row is already cooked is never cooked again, or
    the loss would be counted twice and the shortfall we sell would be ours
  * every factor, and every 1.0, is declared rather than implied
  * every dish says what kind of guess its serving weight is
  * the generated document still matches the catalog it claims to describe
"""

import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import gen_data_doc  # noqa: E402

# Words in an SR Legacy description that mean the row is already the cooked
# food. Applying a retention factor on top of one of these would subtract the
# same loss twice.
ALREADY_COOKED = re.compile(
    r"\b(cooked|boiled|roasted|baked|broiled|fried|toasted)\b", re.I)


@pytest.fixture(scope="module")
def catalog():
    with open(os.path.join(ROOT, "data", "foods.json")) as handle:
        return json.load(handle)


def _lines(catalog):
    for source in ("dishes", "market"):
        for item_id, item in catalog[source].items():
            for line in item["recipe"]:
                yield item_id, line


# --------------------------------------------------------------------------
# Retention factors
# --------------------------------------------------------------------------

def test_every_recipe_line_names_a_preparation_the_catalog_defines(catalog):
    for item_id, line in _lines(catalog):
        assert line["prep"] in catalog["retention"], (
            "%s prepares %s by %r" % (item_id, line["ingredient"], line["prep"]))


def test_every_preparation_is_used(catalog):
    """A method nobody cooks by is a factor nobody can check."""
    used = {line["prep"] for _, line in _lines(catalog)}
    unused = sorted(set(catalog["retention"]) - used)
    assert not unused, "declared but never used: %s" % unused


def test_retention_factors_are_fractions(catalog):
    for method_id, method in catalog["retention"].items():
        for key, factor in method["factors"].items():
            assert 0.0 < factor <= 1.0, "%s %s = %r" % (method_id, key, factor)


def test_every_factor_names_only_nutrients_the_catalog_tracks(catalog):
    known = {n["id"] for n in catalog["nutrients"]}
    for method_id, method in catalog["retention"].items():
        unknown = sorted(set(method["factors"]) - known)
        assert not unknown, "%s: %s" % (method_id, unknown)


def test_every_preparation_explains_itself(catalog):
    """Including the ones that keep everything -- 1.0 is a claim too."""
    for method_id, method in catalog["retention"].items():
        assert method["why"].strip(), method_id
        assert method["name"].strip(), method_id
        if method["usdaCode"]:
            assert method["usdaDescription"].strip(), method_id


def test_methods_that_do_nothing_really_do_nothing(catalog):
    """`raw` and `as_sourced` must not smuggle a loss in."""
    for method_id in ("raw", "as_sourced"):
        factors = catalog["retention"][method_id]["factors"]
        assert all(f == 1.0 for f in factors.values()), method_id


def test_cooking_never_adds_a_nutrient(catalog):
    """The retained figure can never exceed the uncooked ingredient sum."""
    for source, per_key in (("dishes", "perServing"), ("market", "perUnit")):
        for item_id, item in catalog[source].items():
            raw = {}
            for line in item["recipe"]:
                per100 = catalog["ingredients"][line["ingredient"]]["per100g"]
                for key, value in per100.items():
                    raw[key] = raw.get(key, 0.0) + value * line["grams"] / 100.0
            for key, value in item[per_key].items():
                # The catalog stores four decimals, so a factor of 1.0 can
                # round a hair upwards. The tolerance is that rounding and
                # nothing wider.
                assert value <= raw[key] + 1e-4, "%s %s" % (item_id, key)


def test_already_cooked_ingredients_are_not_cooked_twice(catalog):
    """The mistake this whole mechanism is most likely to make.

    SR Legacy carries both raw and cooked rows, and this catalog cites the
    cooked one wherever it can. Those figures already have the cook loss in
    them, so a second factor on top would manufacture a shortfall -- in the
    direction that flatters a product built to sell shortfalls.
    """
    cooked = {key for key, ingredient in catalog["ingredients"].items()
              if ALREADY_COOKED.search(ingredient["source"].get("description") or "")}
    assert len(cooked) > 10, "expected the catalog to cite many cooked rows"
    for item_id, line in _lines(catalog):
        if line["ingredient"] in cooked:
            assert line["prep"] == "as_sourced", (
                "%s cooks %s (already a cooked USDA row) as %r"
                % (item_id, line["ingredient"], line["prep"]))


def test_cook_loss_actually_bites_somewhere(catalog):
    """A table of factors that never changes a number is decoration."""
    changed = 0
    for dish_id, dish in catalog["dishes"].items():
        raw_vitc = sum(catalog["ingredients"][l["ingredient"]]["per100g"]["vitc"]
                       * l["grams"] / 100.0 for l in dish["recipe"])
        if raw_vitc > 0.1 and dish["perServing"]["vitc"] < raw_vitc - 1e-6:
            changed += 1
    assert changed >= 10, "only %d dishes lose any vitamin C" % changed


# --------------------------------------------------------------------------
# Serving sizes
# --------------------------------------------------------------------------

def test_every_dish_says_what_kind_of_guess_its_serving_is(catalog):
    for dish_id, dish in catalog["dishes"].items():
        assert dish["servingSource"] in catalog["servingSources"], dish_id
        assert dish["servingGrams"] > 0, dish_id


def test_every_serving_source_is_used_and_explained(catalog):
    used = {d["servingSource"] for d in catalog["dishes"].values()}
    unused = sorted(set(catalog["servingSources"]) - used)
    assert not unused, "declared but never used: %s" % unused
    for key, text in catalog["servingSources"].items():
        assert len(text) > 40, key


def test_serving_weight_is_in_the_same_world_as_its_recipe(catalog):
    """A serving is its ingredients plus gravy or minus water, not ten times them.

    This catches the typo that matters: a gram figure off by a factor of ten
    reads perfectly plausibly on its own and is obvious next to its recipe.
    """
    for dish_id, dish in catalog["dishes"].items():
        recipe_grams = sum(line["grams"] for line in dish["recipe"])
        ratio = dish["servingGrams"] / recipe_grams
        assert 0.4 <= ratio <= 3.0, (
            "%s serves %s g from %s g of ingredients"
            % (dish_id, dish["servingGrams"], recipe_grams))


# --------------------------------------------------------------------------
# The generated document
# --------------------------------------------------------------------------

def test_the_data_document_is_not_stale(catalog):
    """Regenerate it and compare. A doc that drifts is worse than none."""
    with open(os.path.join(ROOT, "docs", "DATA.md")) as handle:
        on_disk = handle.read()
    assert gen_data_doc.render(catalog) == on_disk, (
        "docs/DATA.md is out of date -- run "
        "`uv run python scripts/gen_data_doc.py`")


def test_the_data_document_mentions_every_dish(catalog):
    with open(os.path.join(ROOT, "docs", "DATA.md")) as handle:
        text = handle.read()
    for dish_id in catalog["dishes"]:
        assert "`%s`" % dish_id in text, dish_id
    for item_id in catalog["market"]:
        assert "`%s`" % item_id in text, item_id
