"""Inverse optimisation: which menu change is worth the most to students?

A student using PlateGap learns what to buy. The person who writes the menu
wants the opposite question answered -- given that students are spending their
own money to patch the menu, what single change to the menu would cut that
spending the most?

That is a search over candidate menu changes, and the naive version is very
slow: re-solve the whole week once per candidate, for every candidate. The
fast version comes free with the duals we already compute.

At the optimum of a linear program, a variable that is not in the basis
improves the objective only if its reduced cost is negative:

    reduced cost of j  =  c_j  -  sum_i ( y_i * A_ij )

where y is the dual vector. A dish that is not on the menu is exactly such a
variable -- one we left out of the program. Pricing it against the duals costs
one dot product, so every candidate can be screened with no extra solve at
all. Only the handful that price out negative are worth re-solving exactly.

This is the pricing step of the simplex method used as a product feature, and
it is why the audit runs in a fraction of a second instead of ten.
"""

from . import model
from . import plan
from . import simplex
from . import targets as targets_module

# Candidates priced above this are not worth an exact re-solve.
PRICING_TOL = -1e-7

# How many candidates survive screening and get solved properly.
DEFAULT_SHORTLIST = 8


def _column_for(variable, program):
    """Build the candidate's column against an existing program's rows.

    The cap row the variable would bring with it is deliberately left out.
    Including it can only make the candidate look worse, so omitting it keeps
    the screen optimistic -- which is the right direction for a filter. A
    candidate that survives is then re-solved with its cap in place.
    """
    column = []
    for row in program.rows:
        kind, key = row["kind"], row["key"]
        if kind == "floor":
            column.append(-float(variable["per"].get(key, 0.0)))
        elif kind == "ceiling":
            column.append(float(variable["per"].get(key, 0.0)))
        elif kind == "limit" and key == "plateGrams":
            column.append(float(variable["servingGrams"]))
        elif kind == "budget":
            column.append(float(variable["cost"]))
        else:
            # Cap rows belong to other variables; this one is not in them.
            column.append(0.0)
    return column


def reduced_cost(variable, program, duals):
    column = _column_for(variable, program)
    return variable["cost"] - sum(y * a for y, a in zip(duals, column))


def _candidate_dishes(catalog, menu, day, diet, excluded):
    """Dishes the catalog knows about that this day does not serve."""
    refused = model.DIETS[diet]
    already = set(model.day_offerings(menu, day))
    candidates = []
    for dish_id, dish in sorted(catalog["dishes"].items()):
        if dish_id in already or dish_id in excluded:
            continue
        if any(tag in refused for tag in dish["tags"]):
            continue
        candidates.append({
            "kind": "mess",
            "id": dish_id,
            "name": dish["name"],
            "tags": list(dish["tags"]),
            "cost": 0.0,
            "cap": float(dish["maxServings"]),
            "timesOffered": 1,
            "servingGrams": float(dish["servingGrams"]),
            "per": dish["perServing"],
            "proxy": bool(dish.get("proxy")),
        })
    return candidates


def _solve_day(variables, goals):
    program = model.assemble(variables, goals, objective="cost")
    return program, program.solve()


def audit_day(catalog, menu, day, profile=None, diet="egg", prices=None,
              shortlist=DEFAULT_SHORTLIST, excluded=()):
    """Rank menu additions for one day by what they save the student.

    Returns the screened candidates in pricing order, with an exact saving
    attached to the shortlist and `None` on the rest.
    """
    goals = targets_module.targets_for(profile)
    currency = plan._currency(catalog, goals["region"])
    excluded = set(excluded)

    base_mess = model.mess_variables(catalog, menu, day, diet=diet, excluded=excluded)
    market = model.market_variables(catalog, region=goals["region"], diet=diet,
                                    prices=prices, excluded=excluded)
    base_variables = base_mess + market

    program, result = _solve_day(base_variables, goals)
    if result.status != simplex.OPTIMAL:
        return {
            "day": day,
            "feasible": False,
            "status": result.status,
            "reason": "the day is unreachable even with purchases, so there "
                      "is no spend to reduce",
        }

    baseline = result.objective
    if baseline <= 1e-9:
        return {
            "day": day,
            "feasible": True,
            "baselineSpend": 0.0,
            "candidates": [],
            "note": "students already need to spend nothing on this day",
            "screened": 0,
        }

    candidates = _candidate_dishes(catalog, menu, day, diet, excluded)
    priced = []
    for candidate in candidates:
        value = reduced_cost(candidate, program, result.duals_ub)
        if value < PRICING_TOL:
            priced.append((value, candidate))
    priced.sort(key=lambda pair: pair[0])

    ranked = []
    for index, (value, candidate) in enumerate(priced):
        entry = {
            "id": candidate["id"],
            "name": candidate["name"],
            "tags": candidate["tags"],
            "reducedCost": round(value, 6),
            "servingGrams": candidate["servingGrams"],
            "proxy": candidate["proxy"],
            "saving": None,
        }
        if index < shortlist:
            _, exact = _solve_day(base_variables + [candidate], goals)
            if exact.status == simplex.OPTIMAL:
                saving = baseline - exact.objective
                entry["saving"] = round(max(0.0, saving), currency["decimals"])
                entry["savingExact"] = max(0.0, saving)
                entry["spendAfter"] = round(exact.objective, currency["decimals"])
        ranked.append(entry)

    solved = [e for e in ranked if e["saving"] is not None]
    solved.sort(key=lambda e: -e["savingExact"])

    return {
        "day": day,
        "feasible": True,
        "currency": currency,
        "baselineSpend": round(baseline, currency["decimals"]),
        "baselineSpendExact": baseline,
        "screened": len(candidates),
        "pricedIn": len(priced),
        "solved": len(solved),
        "candidates": solved + [e for e in ranked if e["saving"] is None],
        "rations": _ration_report(program, result, currency),
    }


def _ration_report(program, result, currency):
    """Cap rows with a shadow price, straight out of the same solve.

    No search is needed here at all. If the dual on a ration cap is non-zero,
    the cap is binding, and the dual is what one more serving of that item
    would save the student. It is the cheapest possible menu change to
    identify, because the solver already worked it out.
    """
    report = []
    for row, dual in zip(program.rows, result.duals_ub):
        if row["kind"] != "cap" or abs(dual) < 1e-7:
            continue
        report.append({
            "id": row["key"],
            "servingsAllowed": row["target"],
            "savingPerExtraServing": round(abs(dual), max(currency["decimals"], 4)),
        })
    report.sort(key=lambda e: -e["savingPerExtraServing"])
    return report


def audit_week(catalog, menu, profile=None, diet="egg", prices=None,
               students=1, shortlist=DEFAULT_SHORTLIST, excluded=()):
    """Aggregate the daily audits into the figure a mess committee can act on.

    `students` scales one person's weekly saving into an institutional one.
    That number is the whole reason this endpoint exists: a warden will not
    change a menu to save one student eleven rupees, and may well change it to
    save six hundred students thirty thousand a month.
    """
    goals = targets_module.targets_for(profile)
    currency = plan._currency(catalog, goals["region"])
    days = [d for d in model.DAYS if d in menu.get("days", {})]

    per_day, totals, baseline_total = [], {}, 0.0
    for day in days:
        answer = audit_day(catalog, menu, day, profile=profile, diet=diet,
                           prices=prices, shortlist=shortlist, excluded=excluded)
        per_day.append(answer)
        if not answer.get("feasible"):
            continue
        baseline_total += answer.get("baselineSpendExact", 0.0)
        for candidate in answer.get("candidates", []):
            if candidate.get("saving") is None:
                continue
            record = totals.setdefault(candidate["id"], {
                "id": candidate["id"],
                "name": candidate["name"],
                "tags": candidate["tags"],
                "proxy": candidate["proxy"],
                "days": [],
                "weeklySavingExact": 0.0,
            })
            record["days"].append(day)
            record["weeklySavingExact"] += candidate["savingExact"]

    ranked = sorted(totals.values(), key=lambda r: -r["weeklySavingExact"])
    for record in ranked:
        weekly = record.pop("weeklySavingExact")
        record["weeklySaving"] = round(weekly, currency["decimals"])
        record["monthlySaving"] = round(weekly / 7.0 * 30.0, currency["decimals"])
        record["monthlySavingAllStudents"] = round(
            weekly / 7.0 * 30.0 * students, currency["decimals"])

    monthly_baseline = baseline_total / 7.0 * 30.0
    return {
        "currency": currency,
        "students": students,
        "diet": diet,
        "baselineWeeklySpend": round(baseline_total, currency["decimals"]),
        "baselineMonthlySpend": round(monthly_baseline, currency["decimals"]),
        "baselineMonthlySpendAllStudents": round(monthly_baseline * students,
                                                 currency["decimals"]),
        "recommendations": ranked,
        "days": per_day,
    }
