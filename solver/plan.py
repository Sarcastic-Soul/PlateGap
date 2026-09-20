"""The three questions PlateGap answers, as callable functions.

`gap`      -- eat the mess as well as it can be eaten. What is still missing?
`cheapest` -- what is the least money that closes the gap, and what does the
              last unit of each nutrient cost?
`frontier` -- spend nothing, spend everything, and every point between.

Everything returned here is plain dicts and floats, ready to be serialised
straight to JSON. Nothing in this module knows about HTTP, and nothing in it
imports anything outside the standard library.
"""

from . import model
from . import simplex
from . import targets as targets_module

FRONTIER_POINTS = 24
DISPLAY_EPSILON = 0.01


def _catalog_nutrients(catalog):
    return {n["id"]: n for n in catalog["nutrients"]}


def _totals(variables, x):
    totals = {}
    for variable, amount in zip(variables, x):
        if amount <= model.SERVING_EPSILON:
            continue
        for key, value in variable["per"].items():
            totals[key] = totals.get(key, 0.0) + value * amount
    return totals


def _plate(variables, x, currency_decimals):
    mess, buy, grams, spend = [], [], 0.0, 0.0
    for variable, amount in zip(variables, x):
        if amount <= DISPLAY_EPSILON:
            continue
        grams += variable["servingGrams"] * amount
        entry = {
            "id": variable["id"],
            "name": variable["name"],
            "amount": round(amount, 2),
            "proxy": variable["proxy"],
        }
        if variable["kind"] == "mess":
            entry["cap"] = variable["cap"]
            entry["atCap"] = amount >= variable["cap"] - 1e-6
            entry["grams"] = round(variable["servingGrams"] * amount, 1)
            mess.append(entry)
        else:
            cost = variable["cost"] * amount
            spend += cost
            entry["unit"] = variable["unit"]
            entry["unitPrice"] = round(variable["cost"], currency_decimals)
            entry["cost"] = round(cost, currency_decimals)
            entry["priceIsDefault"] = variable["priceIsDefault"]
            buy.append(entry)

    mess.sort(key=lambda e: -e["amount"])
    buy.sort(key=lambda e: -e["cost"])
    return mess, buy, grams, spend


def _nutrient_report(catalog, goals, totals):
    meta = _catalog_nutrients(catalog)
    report = []
    for key in sorted(set(goals["floors"]) | set(goals["ceilings"])):
        info = meta.get(key, {"name": key, "unit": ""})
        floor = goals["floors"].get(key)
        ceiling = goals["ceilings"].get(key)
        got = totals.get(key, 0.0)
        status = "ok"
        if floor is not None and got < floor - 1e-4:
            status = "short"
        elif ceiling is not None and got > ceiling + 1e-4:
            status = "over"
        entry = {
            "id": key,
            "name": info["name"],
            "unit": info["unit"],
            "got": round(got, 2),
            "floor": floor,
            "ceiling": ceiling,
            "status": status,
        }
        if floor:
            entry["percentOfFloor"] = round(100.0 * got / floor, 1)
        report.append(entry)
    return report


def _shadow_prices(program, result, decimals):
    """The duals, labelled, with the ones that say nothing filtered out.

    A row with a zero dual is a row that is not binding, and telling the user
    that loosening it would save them nothing is noise. Only binding rows get
    reported, which is exactly complementary slackness used as a UI rule.
    """
    binding = []
    for row, dual in zip(program.rows, result.duals_ub):
        if abs(dual) < 1e-7:
            continue
        # A `<=` row has a non-positive marginal. Report the magnitude, since
        # "relaxing this by one unit saves you X" reads better than a minus.
        binding.append({
            "kind": row["kind"],
            "key": row["key"],
            "target": row.get("target"),
            "shadowPrice": round(abs(dual), max(decimals, 4)),
        })
    binding.sort(key=lambda e: -e["shadowPrice"])
    return binding


def _currency(catalog, region):
    return catalog.get("currencies", {}).get(
        region, {"code": "", "symbol": "", "decimals": 2})


# --------------------------------------------------------------------------
# Question 1: what does the mess alone leave you short of?
# --------------------------------------------------------------------------

def gap(catalog, menu, day, profile=None, diet="egg", excluded=()):
    """Eat the mess as well as it can be eaten, and see what is still missing.

    No money is involved. Every floor gets a shortfall variable priced at one
    over the requirement, so the objective is "total fraction of your
    requirements left unmet" and a milligram of iron competes fairly with a
    gram of protein.
    """
    goals = targets_module.targets_for(profile)
    variables = model.mess_variables(catalog, menu, day, diet=diet, excluded=excluded)
    if not variables:
        raise model.MenuError("nothing on the %s menu survives this diet" % day)

    floors = sorted(goals["floors"])
    program = model.assemble(variables, goals, objective="shortfall",
                             shortfall_for=floors)
    result = program.solve()
    if result.status != simplex.OPTIMAL:
        return {"day": day, "feasible": False, "status": result.status}

    n_food = len(variables)
    totals = _totals(variables, result.x[:n_food])
    mess, _, grams, _ = _plate(variables, result.x[:n_food],
                               _currency(catalog, goals["region"])["decimals"])

    shortfalls = []
    for name, amount in zip(floors, result.x[n_food:]):
        if amount <= 1e-6:
            continue
        floor = goals["floors"][name]
        info = _catalog_nutrients(catalog).get(name, {"name": name, "unit": ""})
        shortfalls.append({
            "id": name,
            "name": info["name"],
            "unit": info["unit"],
            "short": round(amount, 2),
            "floor": floor,
            "percentShort": round(100.0 * amount / floor, 1),
        })
    shortfalls.sort(key=lambda e: -e["percentShort"])

    return {
        "day": day,
        "feasible": True,
        "diet": diet,
        "targets": goals,
        "unmetFraction": round(result.objective, 4),
        "targetsMissed": len(shortfalls),
        "targetsMet": len(floors) - len(shortfalls),
        "shortfalls": shortfalls,
        "nutrients": _nutrient_report(catalog, goals, totals),
        "plate": mess,
        "plateGrams": round(grams, 0),
        "binding": _shadow_prices(program, result, 4),
        "iterations": result.iterations,
    }


# --------------------------------------------------------------------------
# Question 2: what is the cheapest way to close it?
# --------------------------------------------------------------------------

def cheapest(catalog, menu, day, profile=None, diet="egg", prices=None,
             budget=None, excluded=()):
    """Minimise money spent subject to hitting every floor.

    Solved twice. The first solve finds the cheapest spend and produces the
    shadow prices, which are the numbers the interface reports. The second
    solve pins spend at that optimum and minimises the weight of food on the
    plate, because the first solve is usually degenerate -- many different
    plates cost the same nothing, and the one worth showing is the one you
    could actually finish.
    """
    goals = targets_module.targets_for(profile)
    currency = _currency(catalog, goals["region"])
    decimals = currency["decimals"]

    mess = model.mess_variables(catalog, menu, day, diet=diet, excluded=excluded)
    market = model.market_variables(catalog, region=goals["region"], diet=diet,
                                    prices=prices, excluded=excluded)
    variables = mess + market

    program = model.assemble(variables, goals, objective="cost", budget=budget)
    result = program.solve()

    if result.status != simplex.OPTIMAL:
        # Not reachable at any price within the caps. Say which floors are the
        # problem rather than returning an empty screen.
        fallback = gap(catalog, menu, day, profile=profile, diet=diet,
                       excluded=excluded)
        return {
            "day": day,
            "feasible": False,
            "status": result.status,
            "reason": ("no combination of mess servings and purchases inside "
                       "the portion limits reaches every target"),
            "messOnly": fallback,
        }

    spend = result.objective
    shadow = _shadow_prices(program, result, decimals)

    # Stage two: same cost, lightest plate.
    lightest = model.assemble(
        variables, goals, objective="grams",
        extra_rows=[([v["cost"] for v in variables], spend + model.SPEND_SLACK,
                     {"kind": "budget", "key": "atOptimum", "target": spend})])
    polished = lightest.solve()
    x = polished.x if polished.status == simplex.OPTIMAL else result.x

    totals = _totals(variables, x)
    on_plate, to_buy, grams, shown_spend = _plate(variables, x, decimals)
    # Sum over the whole solution, not just the rows big enough to display,
    # so the headline figure never quietly drops a fraction of a purchase.
    actual_spend = sum(v["cost"] * amount for v, amount in zip(variables, x))

    return {
        "day": day,
        "feasible": True,
        "diet": diet,
        "currency": currency,
        "spend": round(actual_spend, decimals),
        "spendExact": actual_spend,
        "spendShown": round(shown_spend, decimals),
        "spendOptimal": round(spend, decimals),
        "budget": budget,
        "targets": goals,
        "plate": on_plate,
        "buy": to_buy,
        "plateGrams": round(grams, 0),
        "nutrients": _nutrient_report(catalog, goals, totals),
        "binding": shadow,
        "iterations": result.iterations + polished.iterations,
    }


# --------------------------------------------------------------------------
# Question 3: what does each rupee buy?
# --------------------------------------------------------------------------

def frontier(catalog, menu, day, profile=None, diet="egg", prices=None,
             points=FRONTIER_POINTS, excluded=()):
    """Sweep the budget and record how much of the gap each level closes.

    The curve is convex and it flattens, which is the point worth showing: the
    first few rupees buy a great deal of nutrition and the last few buy almost
    none. A student deciding whether to spend anything at all can read the
    knee off the chart.
    """
    goals = targets_module.targets_for(profile)
    currency = _currency(catalog, goals["region"])
    decimals = currency["decimals"]

    mess = model.mess_variables(catalog, menu, day, diet=diet, excluded=excluded)
    market = model.market_variables(catalog, region=goals["region"], diet=diet,
                                    prices=prices, excluded=excluded)
    variables = mess + market
    floors = sorted(goals["floors"])

    ceiling_spend = cheapest(catalog, menu, day, profile=profile, diet=diet,
                             prices=prices, excluded=excluded)
    if ceiling_spend.get("feasible"):
        top = ceiling_spend["spendExact"]
    else:
        # Unreachable at any price; sweep far enough to show the plateau.
        top = max(v["cost"] * v["cap"] for v in market) * 3 if market else 0.0

    if top <= 0:
        top = 1.0

    curve = []
    for index in range(points + 1):
        budget = top * index / float(points)
        program = model.assemble(variables, goals, objective="shortfall",
                                 shortfall_for=floors, budget=budget)
        result = program.solve()
        if result.status != simplex.OPTIMAL:
            continue
        missed = sum(1 for amount in result.x[len(variables):] if amount > 1e-6)
        curve.append({
            # Budgets are kept to two places whatever the currency rounds to,
            # so that a sweep in rupees does not collapse several points onto
            # the same integer.
            "budget": round(budget, 2),
            "unmetFraction": round(result.objective, 4),
            "targetsMissed": missed,
            "targetsMet": len(floors) - missed,
            "averagePercentMet": round(
                100.0 * max(0.0, 1.0 - result.objective / len(floors)), 1),
        })

    return {
        "day": day,
        "diet": diet,
        "currency": currency,
        "floorCount": len(floors),
        "spendToCloseGap": round(top, 2) if ceiling_spend.get("feasible") else None,
        "curve": curve,
    }


def week(catalog, menu, profile=None, diet="egg", prices=None, excluded=()):
    """Run `cheapest` across every day the menu carries.

    The weekly figure is the one worth quoting, because a single day is noise
    -- Sunday's biryani and Tuesday's poori are very different problems.
    """
    days = [d for d in model.DAYS if d in menu.get("days", {})]
    results, total, unreachable = [], 0.0, []
    for day in days:
        answer = cheapest(catalog, menu, day, profile=profile, diet=diet,
                          prices=prices, excluded=excluded)
        if answer.get("feasible"):
            total += answer["spend"]
        else:
            unreachable.append(day)
        results.append(answer)

    goals = targets_module.targets_for(profile)
    currency = _currency(catalog, goals["region"])
    reachable = len(days) - len(unreachable)
    return {
        "days": results,
        "currency": currency,
        "weeklySpend": round(total, currency["decimals"]),
        "dailyAverage": round(total / reachable, currency["decimals"]) if reachable else None,
        "monthlyEstimate": round(total / 7.0 * 30.0, currency["decimals"]) if reachable else None,
        "unreachableDays": unreachable,
    }
