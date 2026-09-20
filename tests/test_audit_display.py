"""Tests for what the audit says a recommendation costs.

The audit ranks menu additions by what they save a student. Saving is not the
whole story: on the US dining hall preset the second recommendation is french
fries, which is honest arithmetic -- they are a cheap route to energy,
potassium and fibre -- and reads like advice to serve more chips unless the
screen also says what a serving puts against the day's ceilings.

So `serving_costs` exists, and these check the properties that make it worth
printing:

  * the numbers are the catalog's, not a restatement of the reduced cost
  * a ceiling that is not binding is still reported, because that is exactly
    when the dish looks free in the arithmetic and is not
  * nothing gets filtered out of the recommendations on account of its cost
"""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from solver import audit as audit_module  # noqa: E402
from solver import model, simplex, targets  # noqa: E402


@pytest.fixture(scope="module")
def catalog():
    with open(os.path.join(ROOT, "data", "foods.json")) as handle:
        return json.load(handle)


def _load_menu(name):
    with open(os.path.join(ROOT, "data", "menus", "%s.json" % name)) as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def hall():
    return _load_menu("dining-hall")


@pytest.fixture(scope="module")
def mess():
    return _load_menu("iiit")


# The dining hall is written for US reference intakes and US prices, and the
# handler defaults the region to whatever the menu says. These read the same
# way, so that a number here is a number the site can actually show.
HALL_PROFILE = {"region": "US"}


@pytest.fixture(scope="module")
def hall_day(catalog, hall):
    return audit_module.audit_day(catalog, hall, "mon", profile=HALL_PROFILE)


def _costs_by_key(entry):
    return {cost["key"]: cost for cost in entry["costs"]}


# --------------------------------------------------------------------------
# The numbers themselves
# --------------------------------------------------------------------------

def test_a_serving_cost_is_the_catalogs_own_figure(catalog, hall_day):
    """Per-serving loads have to be the composition, not a derived quantity.

    If these ever drifted from `perServing` the screen would be quoting a
    number that nothing in the repository can be argued with.
    """
    assert hall_day["feasible"]
    checked = 0
    for entry in hall_day["candidates"]:
        dish = catalog["dishes"][entry["id"]]
        for cost in entry["costs"]:
            if cost["kind"] == "limit":
                assert cost["perServing"] == pytest.approx(dish["servingGrams"])
            else:
                assert cost["perServing"] == pytest.approx(
                    dish["perServing"][cost["key"]], rel=1e-4)
            checked += 1
    assert checked > 20, "too few costs reported to have tested anything"


def test_every_ceiling_the_dish_loads_is_reported(catalog, hall_day):
    goals = targets.targets_for(HALL_PROFILE)
    for entry in hall_day["candidates"]:
        dish = catalog["dishes"][entry["id"]]
        reported = _costs_by_key(entry)
        for nutrient in goals["ceilings"]:
            amount = dish["perServing"].get(nutrient, 0.0)
            if amount > 0:
                assert nutrient in reported, "%s hides its %s" % (entry["id"], nutrient)
            else:
                assert nutrient not in reported
        assert "plateGrams" in reported


def test_the_share_of_the_day_is_arithmetic_anyone_can_redo(hall_day):
    for entry in hall_day["candidates"]:
        for cost in entry["costs"]:
            assert cost["target"] > 0
            assert cost["percentOfTarget"] == pytest.approx(
                100.0 * cost["perServing"] / cost["target"], abs=0.05)


def test_costs_are_heaviest_first(hall_day):
    for entry in hall_day["candidates"]:
        shares = [cost["percentOfTarget"] for cost in entry["costs"]]
        assert shares == sorted(shares, reverse=True)


def test_only_upper_bounds_can_be_a_cost(hall_day):
    """Floors and ration caps are not costs and must not be shown as ones."""
    for entry in hall_day["candidates"]:
        for cost in entry["costs"]:
            assert cost["kind"] in ("ceiling", "limit")
            assert cost["perServing"] > 0


# --------------------------------------------------------------------------
# The honesty properties
# --------------------------------------------------------------------------

def test_a_ceiling_that_does_not_bind_is_still_reported(catalog, hall):
    """The case the feature exists for.

    A ceiling with a zero dual contributes nothing to the reduced cost, so a
    display driven by the reduced cost alone would show the dish as costing
    nothing at all. It reports as a cost with a zero contribution instead,
    flagged as not binding.
    """
    answer = audit_module.audit_day(catalog, hall, "mon", profile=HALL_PROFILE)
    slack = [cost
             for entry in answer["candidates"]
             for cost in entry["costs"]
             if not cost["binding"]]
    assert slack, "no non-binding ceiling in this solve, so nothing was proved"
    for cost in slack:
        assert cost["contribution"] == pytest.approx(0.0, abs=1e-6)
        assert cost["perServing"] > 0


def test_a_binding_ceiling_prices_the_load_it_reports(catalog, hall):
    """Where a ceiling does bind, the contribution is the dual times the load.

    That keeps the two halves of the screen consistent: the cost shown is the
    same term that made the reduced cost what it is.
    """
    goals = targets.targets_for(HALL_PROFILE)
    base = (model.mess_variables(catalog, hall, "mon")
            + model.market_variables(catalog, region="US"))
    program = model.assemble(base, goals, objective="cost")
    result = program.solve()
    assert result.status == simplex.OPTIMAL

    candidates = audit_module._candidate_dishes(catalog, hall, "mon", "egg", set())
    duals = {(row["kind"], row["key"]): y
             for row, y in zip(program.rows, result.duals_ub)}

    checked = 0
    for candidate in candidates:
        for cost in audit_module.serving_costs(candidate, program, result.duals_ub):
            if not cost["binding"]:
                continue
            expected = -duals[(cost["kind"], cost["key"])] * cost["perServing"]
            assert cost["contribution"] == pytest.approx(expected, abs=1e-5)
            assert cost["contribution"] > 0, (
                "an upper bound can only ever work against a candidate")
            checked += 1
    assert checked > 0, "nothing bound, so nothing was checked"


def test_french_fries_are_recommended_and_say_what_they_cost(catalog, hall):
    """The dish that made this necessary.

    The recommendation is not removed and not softened -- that would be
    editing the answer. It arrives with the energy, saturated fat, sodium and
    plate weight one serving spends, so the trade is on the screen next to
    the saving.
    """
    answer = audit_module.audit_week(catalog, hall, profile=HALL_PROFILE,
                                     students=600)
    fries = [r for r in answer["recommendations"] if r["id"] == "french_fries"]
    assert fries, "the preset no longer recommends fries; rewrite this test"

    costs = _costs_by_key(fries[0])
    assert fries[0]["monthlySaving"] > 0
    for key in ("kcal", "satfat", "sodium", "plateGrams"):
        assert key in costs
        assert costs[key]["perServing"] > 0
        assert costs[key]["percentOfTarget"] > 0


def test_reporting_a_cost_never_changes_the_ranking(catalog, hall):
    """Honesty here means saying more, not recommending differently.

    The order is the saving and nothing but the saving, however heavy a dish
    turns out to be on the ceilings.
    """
    answer = audit_module.audit_week(catalog, hall, profile=HALL_PROFILE,
                                     students=600)
    savings = [r["weeklySaving"] for r in answer["recommendations"]]
    assert savings == sorted(savings, reverse=True)
    assert all(r["costs"] for r in answer["recommendations"])


def test_the_weekly_recommendation_carries_the_per_serving_load(catalog, mess):
    """Aggregating days must not turn a per-serving figure into a weekly one.

    A dish recommended on four days is still one serving of the same dish, so
    its cost is the day's cost, unmultiplied.
    """
    week = audit_module.audit_week(catalog, mess, students=1)
    days = {}
    for day_answer in week["days"]:
        for entry in day_answer.get("candidates", []):
            if entry["saving"] is not None:
                days.setdefault(entry["id"], entry["costs"])

    assert week["recommendations"], "nothing to aggregate"
    for record in week["recommendations"]:
        assert record["costs"] == days[record["id"]]
        assert len(record["days"]) >= 1
