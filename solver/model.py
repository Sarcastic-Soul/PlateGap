"""Turn a menu, a profile and a set of prices into linear programs.

PlateGap asks two questions, and each is one LP.

  1. What does the mess alone leave you short of?
     Mess servings only, no money. Every nutrient floor gets a shortfall
     variable, and we minimise the total shortfall measured as a fraction of
     the requirement. One solve gives the whole gap profile, and the duals on
     the ration caps say which portion limit is doing the damage.

  2. What is the cheapest way to close that gap?
     Mess servings (free, capped) alongside market items (priced, capped),
     minimising money spent subject to hitting every floor. The shadow price
     on a binding floor is then literally "what one more milligram of iron
     costs you", which is the number the interface exists to show.

Both are the classic Stigler diet problem with one twist that matters: the
mess food is free at the margin. The monthly fee is already paid and is sunk,
so a serving of dal costs nothing and a serving of paneer is limited by the
ladle rather than by the wallet. That two-class structure -- free but
rationed, versus priced but unlimited -- is what makes the duals interesting
instead of obvious.
"""

from . import simplex
from . import targets as targets_module

# Which tags a diet refuses. "egg" is the default for the campus this was
# built on: eggs yes, meat no.
DIETS = {
    "all": frozenset(),
    "egg": frozenset({"meat"}),
    "veg": frozenset({"meat", "egg"}),
    "vegan": frozenset({"meat", "egg", "dairy"}),
}

MEALS = ("breakfast", "lunch", "snacks", "dinner")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# Stage two of the priced solve is allowed to spend this much more than the
# true optimum, to absorb floating point rather than to trade money away.
SPEND_SLACK = 1e-6

# Servings below this are treated as not on the plate at all.
SERVING_EPSILON = 1e-6


class MenuError(ValueError):
    """The menu refers to something the catalog does not have."""


# --------------------------------------------------------------------------
# Assembling the variables
# --------------------------------------------------------------------------

def day_offerings(menu, day):
    """Every dish served on one day, with how many times it is offered.

    A dish served at both lunch and dinner is offered twice, so its ration cap
    applies twice. Roti capped at six per meal means twelve across a day on
    which roti appears at two meals -- which is how a mess actually works.
    """
    if day not in menu.get("days", {}):
        raise MenuError("menu %r has no day %r" % (menu.get("id"), day))

    counts = {}
    for meal in MEALS:
        served = list(menu.get("daily", {}).get(meal, []))
        served += list(menu["days"][day].get(meal, []))
        for dish_id in served:
            counts[dish_id] = counts.get(dish_id, 0) + 1
    return counts


def _diet_blocks(tags, refused):
    return any(tag in refused for tag in tags)


def mess_variables(catalog, menu, day, diet="egg", excluded=()):
    """The free-but-rationed side of the program."""
    refused = DIETS.get(diet)
    if refused is None:
        raise ValueError("unknown diet %r; expected one of %s"
                         % (diet, ", ".join(sorted(DIETS))))
    excluded = set(excluded)

    variables = []
    for dish_id, times_offered in sorted(day_offerings(menu, day).items()):
        dish = catalog["dishes"].get(dish_id)
        if dish is None:
            raise MenuError("menu names dish %r, which the catalog does not have"
                            % dish_id)
        if dish_id in excluded or _diet_blocks(dish["tags"], refused):
            continue
        variables.append({
            "kind": "mess",
            "id": dish_id,
            "name": dish["name"],
            "tags": list(dish["tags"]),
            "cost": 0.0,
            "cap": float(dish["maxServings"] * times_offered),
            "timesOffered": times_offered,
            "servingGrams": float(dish["servingGrams"]),
            "per": dish["perServing"],
            "proxy": bool(dish.get("proxy")),
        })
    return variables


def market_variables(catalog, region="IN", diet="egg", prices=None, excluded=()):
    """The priced side of the program.

    `prices` overrides the seed defaults per item. A price that is wrong for
    your campus makes the recommendation wrong for you, so the caller is
    expected to pass real ones whenever it has them.
    """
    refused = DIETS.get(diet)
    if refused is None:
        raise ValueError("unknown diet %r" % diet)
    prices = prices or {}
    excluded = set(excluded)

    variables = []
    for item_id, item in sorted(catalog["market"].items()):
        if item_id in excluded or _diet_blocks(item["tags"], refused):
            continue
        default = item["defaultPrice"].get(region)
        price = prices.get(item_id, default)
        if price is None:
            continue  # no price for this region and none supplied
        price = float(price)
        if price < 0:
            raise ValueError("negative price for %r" % item_id)
        variables.append({
            "kind": "market",
            "id": item_id,
            "name": item["name"],
            "unit": item["unit"],
            "tags": list(item["tags"]),
            "cost": price,
            "priceIsDefault": item_id not in prices,
            "cap": float(item["maxUnits"]),
            "servingGrams": 0.0,  # bought portions are not "on the plate"
            "per": item["perUnit"],
            "proxy": bool(item.get("proxy")),
        })
    return variables


# --------------------------------------------------------------------------
# Assembling the rows
# --------------------------------------------------------------------------

class Program(object):
    """An LP plus the labels needed to read its answer back out.

    `rows` runs parallel to A_ub, so `duals_ub[i]` is the shadow price of
    `rows[i]`. Keeping them together is the whole reason this class exists --
    a dual with no label attached is a number nobody can act on.
    """

    __slots__ = ("variables", "rows", "c", "A_ub", "b_ub", "n_shortfall")

    def __init__(self, variables, rows, c, A_ub, b_ub, n_shortfall=0):
        self.variables = variables
        self.rows = rows
        self.c = c
        self.A_ub = A_ub
        self.b_ub = b_ub
        self.n_shortfall = n_shortfall

    def solve(self):
        return simplex.solve(self.c, self.A_ub, self.b_ub)

    def dual_of(self, kind, key):
        """Look a shadow price up by label rather than by index."""
        for index, row in enumerate(self.rows):
            if row["kind"] == kind and row.get("key") == key:
                return index
        return None


def assemble(variables, goals, objective="cost", budget=None,
             shortfall_for=(), extra_rows=()):
    """Build the LP.

    `objective` is either "cost" (minimise money) or "shortfall" (minimise the
    total unmet fraction of the floors named in `shortfall_for`).

    Shortfall variables appear after the food variables. Each one is attached
    to exactly one floor row and is priced at 1/floor, so a shortfall of half
    the iron requirement and a shortfall of half the calcium requirement cost
    the objective the same amount. Without that normalisation the objective
    would be dominated by whichever nutrient happens to be measured in
    milligrams.
    """
    floors = goals["floors"]
    ceilings = goals["ceilings"]
    shortfall_for = [n for n in shortfall_for if n in floors]

    n_food = len(variables)
    n_short = len(shortfall_for)
    width = n_food + n_short

    if objective == "cost":
        c = [v["cost"] for v in variables] + [0.0] * n_short
    elif objective == "shortfall":
        c = [0.0] * n_food + [1.0 / floors[n] for n in shortfall_for]
    elif objective == "grams":
        c = [v["servingGrams"] for v in variables] + [0.0] * n_short
    else:
        raise ValueError("unknown objective %r" % objective)

    short_index = {name: n_food + i for i, name in enumerate(shortfall_for)}

    rows, A_ub, b_ub = [], [], []

    # Floors: sum(a_j x_j) + shortfall >= floor, written as <= by negation.
    for nutrient in sorted(floors):
        row = [-float(v["per"].get(nutrient, 0.0)) for v in variables]
        row += [0.0] * n_short
        if nutrient in short_index:
            row[short_index[nutrient]] = -1.0
        A_ub.append(row)
        b_ub.append(-float(floors[nutrient]))
        rows.append({"kind": "floor", "key": nutrient, "target": float(floors[nutrient])})

    # Ceilings: sum(a_j x_j) <= ceiling. No shortfall variable -- a ceiling
    # that cannot be respected means the plan is genuinely infeasible and
    # should say so rather than be quietly relaxed.
    for nutrient in sorted(ceilings):
        row = [float(v["per"].get(nutrient, 0.0)) for v in variables]
        row += [0.0] * n_short
        A_ub.append(row)
        b_ub.append(float(ceilings[nutrient]))
        rows.append({"kind": "ceiling", "key": nutrient, "target": float(ceilings[nutrient])})

    # Serving and ration caps, one row per variable.
    for index, variable in enumerate(variables):
        row = [0.0] * width
        row[index] = 1.0
        A_ub.append(row)
        b_ub.append(variable["cap"])
        rows.append({"kind": "cap", "key": variable["id"], "target": variable["cap"]})

    # How much food can physically be eaten. See targets.DEFAULT_PLATE_GRAMS
    # for why this row exists; on a well-stocked menu it is usually the row
    # that binds, and its shadow price is the most interesting number in the
    # whole program -- the money value of one more gram of stomach.
    plate_limit = goals.get("limits", {}).get("plateGrams")
    if plate_limit:
        row = [v["servingGrams"] for v in variables] + [0.0] * n_short
        A_ub.append(row)
        b_ub.append(float(plate_limit))
        rows.append({"kind": "limit", "key": "plateGrams",
                     "target": float(plate_limit)})

    if budget is not None:
        row = [v["cost"] for v in variables] + [0.0] * n_short
        A_ub.append(row)
        b_ub.append(float(budget))
        rows.append({"kind": "budget", "key": "budget", "target": float(budget)})

    for row, rhs, label in extra_rows:
        padded = list(row) + [0.0] * (width - len(row))
        A_ub.append(padded)
        b_ub.append(float(rhs))
        rows.append(label)

    return Program(variables, rows, c, A_ub, b_ub, n_short)
