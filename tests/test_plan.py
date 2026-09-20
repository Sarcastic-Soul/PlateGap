"""Tests for the model and plan layers.

These are not differential tests -- there is no reference implementation of
"what should a hostel student eat". They check the properties that have to
hold for the answer to mean anything:

  * the plan the solver returns actually meets the targets it claims to
  * duals obey complementary slackness against the plan we display
  * a diet restriction can never make food cheaper
  * more budget can never buy less nutrition
"""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from solver import model, plan, simplex, targets  # noqa: E402


@pytest.fixture(scope="module")
def catalog():
    with open(os.path.join(ROOT, "data", "foods.json")) as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def menu():
    with open(os.path.join(ROOT, "data", "menus", "iiit.json")) as handle:
        return json.load(handle)


# --------------------------------------------------------------------------
# Catalog and menu integrity
# --------------------------------------------------------------------------

def test_every_menu_dish_exists_in_the_catalog(catalog, menu):
    named = set()
    for served in menu["daily"].values():
        named.update(served)
    for day in menu["days"].values():
        for served in day.values():
            named.update(served)
    missing = sorted(named - set(catalog["dishes"]))
    assert not missing, "menu names dishes the catalog lacks: %s" % missing


def test_every_recipe_ingredient_exists(catalog):
    known = set(catalog["ingredients"])
    for source in ("dishes", "market"):
        for item_id, item in catalog[source].items():
            for line in item["recipe"]:
                assert line["ingredient"] in known, (
                    "%s %r uses unknown ingredient %r"
                    % (source, item_id, line["ingredient"]))


def test_dish_nutrients_match_their_recipes(catalog):
    """Dishes are computed, not estimated. Recompute one and check."""
    for dish_id, dish in catalog["dishes"].items():
        expected = {}
        for line in dish["recipe"]:
            per100 = catalog["ingredients"][line["ingredient"]]["per100g"]
            scale = line["grams"] / 100.0
            for key, value in per100.items():
                expected[key] = expected.get(key, 0.0) + value * scale
        for key, value in expected.items():
            assert dish["perServing"][key] == pytest.approx(value, abs=1e-3), (
                "%s %s" % (dish_id, key))


def test_proxy_ingredients_are_flagged_all_the_way_up(catalog):
    """A dish built on an estimated ingredient must inherit the warning."""
    proxy_ingredients = {k for k, v in catalog["ingredients"].items() if v.get("proxy")}
    assert proxy_ingredients, "the fixture should contain at least one proxy"
    for dish_id, dish in catalog["dishes"].items():
        uses_proxy = any(line["ingredient"] in proxy_ingredients
                         for line in dish["recipe"])
        assert bool(dish.get("proxy")) == uses_proxy, dish_id


# --------------------------------------------------------------------------
# Targets
# --------------------------------------------------------------------------

def test_targets_only_name_nutrients_the_catalog_carries(catalog):
    known = {n["id"] for n in catalog["nutrients"]}
    for region in ("IN", "US"):
        for sex in ("male", "female"):
            goals = targets.targets_for({"region": region, "sex": sex})
            assert set(goals["floors"]) <= known
            assert set(goals["ceilings"]) <= known


def test_energy_band_is_ordered():
    goals = targets.targets_for()
    assert goals["floors"]["kcal"] < goals["ceilings"]["kcal"]


def test_activity_raises_energy():
    sedentary = targets.targets_for({"activity": "sedentary"})["energy"]
    active = targets.targets_for({"activity": "active"})["energy"]
    assert active > sedentary


def test_unknown_region_is_refused():
    with pytest.raises(targets.UnknownProfile):
        targets.targets_for({"region": "ZZ"})


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------

def test_a_dish_served_twice_gets_twice_the_ration(catalog, menu):
    offerings = model.day_offerings(menu, "mon")
    assert offerings["roti"] == 2, "roti is on both lunch and dinner on Monday"
    variables = {v["id"]: v for v in model.mess_variables(catalog, menu, "mon")}
    assert variables["roti"]["cap"] == catalog["dishes"]["roti"]["maxServings"] * 2


def test_diet_removes_what_it_refuses(catalog, menu):
    everything = {v["id"] for v in model.mess_variables(catalog, menu, "mon", diet="all")}
    eggs_only = {v["id"] for v in model.mess_variables(catalog, menu, "mon", diet="egg")}
    veg = {v["id"] for v in model.mess_variables(catalog, menu, "mon", diet="veg")}
    assert veg <= eggs_only <= everything
    assert "chicken_butter_masala" in everything
    assert "chicken_butter_masala" not in eggs_only


def test_prices_can_be_overridden(catalog):
    default = {v["id"]: v for v in model.market_variables(catalog)}["egg"]
    overridden = {v["id"]: v for v in
                  model.market_variables(catalog, prices={"egg": 99.0})}["egg"]
    assert default["priceIsDefault"] is True
    assert overridden["cost"] == 99.0
    assert overridden["priceIsDefault"] is False


def test_rows_line_up_with_the_dual_vector(catalog, menu):
    goals = targets.targets_for()
    variables = (model.mess_variables(catalog, menu, "mon")
                 + model.market_variables(catalog))
    program = model.assemble(variables, goals)
    result = program.solve()
    assert result.status == simplex.OPTIMAL
    assert len(program.rows) == len(result.duals_ub)


def test_mess_alone_cannot_meet_every_target(catalog, menu):
    """The premise of the product, asserted rather than assumed.

    With no money spent, the hard program is infeasible -- there is no way to
    eat the mess that reaches every floor. If this test ever starts failing,
    the menu or the reference intakes have changed and the headline claim
    needs rewriting, not patching.
    """
    goals = targets.targets_for()
    variables = model.mess_variables(catalog, menu, "mon")
    program = model.assemble(variables, goals)
    assert program.solve().status == simplex.INFEASIBLE


# --------------------------------------------------------------------------
# The plan
# --------------------------------------------------------------------------

@pytest.mark.parametrize("day", model.DAYS)
def test_cheapest_plan_actually_meets_every_target(catalog, menu, day):
    answer = plan.cheapest(catalog, menu, day)
    if not answer["feasible"]:
        pytest.skip("%s is unreachable inside the portion limits" % day)
    for nutrient in answer["nutrients"]:
        assert nutrient["status"] == "ok", (
            "%s %s is %s: got %s against floor %s ceiling %s"
            % (day, nutrient["id"], nutrient["status"], nutrient["got"],
               nutrient["floor"], nutrient["ceiling"]))


@pytest.mark.parametrize("day", model.DAYS)
def test_plan_respects_the_plate_limit(catalog, menu, day):
    answer = plan.cheapest(catalog, menu, day)
    if not answer["feasible"]:
        pytest.skip("unreachable")
    limit = answer["targets"]["limits"]["plateGrams"]
    assert answer["plateGrams"] <= limit + 1.0


@pytest.mark.parametrize("day", model.DAYS)
def test_nothing_exceeds_its_ration(catalog, menu, day):
    answer = plan.cheapest(catalog, menu, day)
    if not answer["feasible"]:
        pytest.skip("unreachable")
    for item in answer["plate"]:
        assert item["amount"] <= item["cap"] + 1e-6, item


def test_only_binding_rows_get_a_shadow_price(catalog, menu):
    """Complementary slackness, used as a user-interface rule.

    Reporting a shadow price on a row that is not binding would be telling
    someone that loosening a limit they are nowhere near would save them
    money, which is false.
    """
    goals = targets.targets_for()
    variables = (model.mess_variables(catalog, menu, "mon")
                 + model.market_variables(catalog))
    program = model.assemble(variables, goals, objective="cost")
    result = program.solve()
    assert result.status == simplex.OPTIMAL

    for row, coefficients, rhs, dual in zip(
            program.rows, program.A_ub, program.b_ub, result.duals_ub):
        slack = rhs - sum(a * x for a, x in zip(coefficients, result.x))
        assert slack >= -1e-6, "%s %s is violated" % (row["kind"], row["key"])
        if abs(dual) > 1e-7:
            assert abs(slack) < 1e-5, (
                "%s %s has a shadow price but is not binding (slack %.8g)"
                % (row["kind"], row["key"], slack))


def test_a_stricter_diet_never_costs_less(catalog, menu):
    """Removing options from a minimisation cannot lower the minimum."""
    costs = {}
    for diet in ("all", "egg", "veg", "vegan"):
        answer = plan.cheapest(catalog, menu, "mon", diet=diet)
        costs[diet] = answer["spendExact"] if answer["feasible"] else float("inf")
    assert costs["all"] <= costs["egg"] + 1e-6
    assert costs["egg"] <= costs["veg"] + 1e-6
    assert costs["veg"] <= costs["vegan"] + 1e-6


def test_frontier_never_goes_backwards(catalog, menu):
    """More money cannot buy less nutrition."""
    curve = plan.frontier(catalog, menu, "mon", points=12)["curve"]
    assert len(curve) > 2
    for earlier, later in zip(curve, curve[1:]):
        assert later["budget"] >= earlier["budget"] - 1e-9
        assert later["unmetFraction"] <= earlier["unmetFraction"] + 1e-6


def test_frontier_ends_where_the_gap_closes(catalog, menu):
    answer = plan.frontier(catalog, menu, "mon", points=8)
    assert answer["curve"][-1]["unmetFraction"] == pytest.approx(0.0, abs=1e-6)
    assert answer["curve"][-1]["targetsMissed"] == 0


def test_gap_and_cheapest_agree_about_what_is_missing(catalog, menu):
    """Whatever the mess cannot supply is what money has to buy."""
    shortfall = plan.gap(catalog, menu, "mon")
    answer = plan.cheapest(catalog, menu, "mon")
    assert shortfall["feasible"] and answer["feasible"]
    if shortfall["targetsMissed"] == 0:
        assert answer["spendExact"] == pytest.approx(0.0, abs=1e-6)
    else:
        assert answer["spendExact"] > 0.0


def test_a_tighter_plate_limit_never_costs_less(catalog, menu):
    roomy = plan.cheapest(catalog, menu, "mon", profile={"maxPlateGrams": 1600})
    tight = plan.cheapest(catalog, menu, "mon", profile={"maxPlateGrams": 1100})
    assert tight["spendExact"] >= roomy["spendExact"] - 1e-6


def test_week_covers_every_day_the_menu_carries(catalog, menu):
    answer = plan.week(catalog, menu)
    assert len(answer["days"]) == len(menu["days"])
    assert answer["monthlyEstimate"] is not None


def test_unknown_day_is_refused(catalog, menu):
    with pytest.raises(model.MenuError):
        plan.gap(catalog, menu, "someday")


# --------------------------------------------------------------------------
# The audit
# --------------------------------------------------------------------------

def test_pricing_never_hides_a_worthwhile_candidate(catalog, menu):
    """The screen must have no false negatives.

    Reduced-cost screening is only legitimate if a candidate priced at or
    above zero genuinely cannot improve the objective. If that ever stopped
    holding, the audit would silently drop the best recommendation and still
    look like it worked -- so this checks every rejected candidate the slow
    way, by actually adding it and re-solving.
    """
    from solver import audit as audit_module

    goals = targets.targets_for()
    base = (model.mess_variables(catalog, menu, "mon")
            + model.market_variables(catalog))
    program = model.assemble(base, goals, objective="cost")
    result = program.solve()
    assert result.status == simplex.OPTIMAL
    baseline = result.objective

    candidates = audit_module._candidate_dishes(catalog, menu, "mon", "egg", set())
    assert len(candidates) > 20, "not enough candidates to be a real test"

    rejected = 0
    for candidate in candidates:
        priced = audit_module.reduced_cost(candidate, program, result.duals_ub)
        if priced < audit_module.PRICING_TOL:
            continue
        rejected += 1
        exact = model.assemble(base + [candidate], goals, objective="cost").solve()
        assert exact.status == simplex.OPTIMAL
        assert exact.objective >= baseline - 1e-6, (
            "%s was screened out but saves %.8g"
            % (candidate["id"], baseline - exact.objective))
    assert rejected > 0, "the screen rejected nothing, so it proved nothing"


def test_a_candidate_can_never_make_things_worse(catalog, menu):
    """Adding an option to a minimisation cannot raise the minimum."""
    from solver import audit as audit_module

    answer = audit_module.audit_day(catalog, menu, "mon")
    assert answer["feasible"]
    for candidate in answer["candidates"]:
        if candidate["saving"] is None:
            continue
        assert candidate["savingExact"] >= -1e-9
        assert candidate["spendAfter"] <= answer["baselineSpend"] + 1e-6


def test_ration_shadow_prices_only_appear_on_binding_caps(catalog, menu):
    from solver import audit as audit_module

    answer = audit_module.audit_day(catalog, menu, "mon")
    plan_answer = plan.cheapest(catalog, menu, "mon")
    capped = {item["id"] for item in plan_answer["plate"] if item["atCap"]}
    for ration in answer["rations"]:
        assert ration["id"] in capped, (
            "%s has a shadow price but is not served at its cap" % ration["id"])


def test_audit_scales_with_the_student_count(catalog, menu):
    from solver import audit as audit_module

    one = audit_module.audit_week(catalog, menu, students=1, shortlist=3)
    many = audit_module.audit_week(catalog, menu, students=500, shortlist=3)
    assert many["baselineMonthlySpendAllStudents"] == pytest.approx(
        one["baselineMonthlySpendAllStudents"] * 500, rel=1e-3)
