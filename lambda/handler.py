"""Lambda entry point, served through a Function URL.

One function, one route table, no API Gateway. The Function URL is public and
unauthenticated, which is the right trade for a tool anyone should be able to
try without signing up -- and it means every input has to be treated as
hostile. Everything below is bounded: the body size, the number of prices, the
length of a pasted menu, the number of frontier points, the student count.

The handler owns no AWS credentials. It runs under an execution role, reads
its catalog from the deployment package, and writes nothing.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# In the deployment package `solver/` and `data/` sit next to this file. When
# running from a checkout they sit one level up. Supporting both means the
# tests exercise the same handler that ships, rather than a copy of it.
for _candidate in (HERE, REPO):
    if _candidate not in sys.path:
        sys.path.append(_candidate)

from solver import audit as audit_module      # noqa: E402
from solver import explain as explain_module  # noqa: E402
from solver import menutext                   # noqa: E402
from solver import model                      # noqa: E402
from solver import plan                       # noqa: E402
from solver import targets as targets_module  # noqa: E402

DATA = os.path.join(HERE, "data")
if not os.path.isdir(os.path.join(DATA, "menus")):
    DATA = os.path.join(REPO, "data")

# ---- Input bounds. A public endpoint gets exactly as much work as it asks
# ---- for, so it does not get to ask for very much.
MAX_BODY_BYTES = 256 * 1024
MAX_PRICE_ENTRIES = 200
MAX_EXCLUDED = 200
MAX_MENU_DISHES_PER_MEAL = 40
MAX_FRONTIER_POINTS = 60
MAX_STUDENTS = 1_000_000
MAX_PASTED_CHARS = 8_000
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_MENU_NAME_CHARS = 120

ID_PATTERN = re.compile(r"^[a-z0-9_\-]{1,64}$")

# Which models `explain` may be asked for. An unauthenticated endpoint that
# forwards an arbitrary model id to Bedrock is an invitation to run somebody
# else's inference on this account's bill, so the choice is a short list
# rather than a string. Both are cheap and both are enabled in this account;
# having two is what makes comparing them on explanation quality possible.
EXPLAIN_MODELS = (
    "amazon.nova-lite-v1:0",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
)



# CORS is configured on the Function URL, not here. The Lambda service adds
# the headers to every response and answers preflight without invoking this
# function at all -- so setting them here too made the browser see
# `Access-Control-Allow-Origin: *, *`, which is two values where the spec
# allows one, and every request from the site failed. curl does not enforce
# CORS, which is why the endpoint looked healthy from a terminal and was dead
# in a browser.
#
# Anyone hosting this behind something other than a Function URL owns CORS
# themselves; `scripts/dev_server.py` serves the site and the API on one
# origin, so it needs none.


class BadRequest(ValueError):
    """Something the caller sent is wrong, and it is worth telling them what."""


# --------------------------------------------------------------------------
# Loading, once per cold start
# --------------------------------------------------------------------------

def _load_json(path):
    with open(path) as handle:
        return json.load(handle)


CATALOG = _load_json(os.path.join(DATA, "foods.json"))

KNOWN_CUISINES = {dish["cuisine"] for dish in CATALOG["dishes"].values()}

MENUS = {}
for _name in sorted(os.listdir(os.path.join(DATA, "menus"))):
    if _name.endswith(".json"):
        _menu = _load_json(os.path.join(DATA, "menus", _name))
        MENUS[_menu["id"]] = _menu

# Every alias any shipped menu knows about, merged into one lookup for
# `parse`. The maps are small and they do not contradict each other, and
# somebody pasting a menu has not told us which mess they are at yet -- so
# asking them to pick a preset before they can type in their own menu would
# be backwards. `araher dal` means toor dal wherever it was written down.
ALIASES = {}
for _menu in MENUS.values():
    ALIASES.update(_menu.get("aliases", {}))


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def _as_dict(value, what):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise BadRequest("%s must be an object" % what)
    return value


def _clean_id(value, what):
    if not isinstance(value, str) or not ID_PATTERN.match(value):
        raise BadRequest("%s must be a short identifier" % what)
    return value


def _clean_prices(raw):
    prices = _as_dict(raw, "prices")
    if len(prices) > MAX_PRICE_ENTRIES:
        raise BadRequest("too many price overrides")
    cleaned = {}
    for key, value in prices.items():
        _clean_id(key, "price key")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise BadRequest("price for %s must be a number" % key)
        if value < 0 or value > 1e7:
            raise BadRequest("price for %s is out of range" % key)
        cleaned[key] = float(value)
    return cleaned


def _clean_excluded(raw):
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_EXCLUDED:
        raise BadRequest("excluded must be a short list of identifiers")
    return [_clean_id(item, "excluded item") for item in raw]


def _clean_profile(raw):
    profile = _as_dict(raw, "profile")
    allowed = {"region", "sex", "activity", "maxPlateGrams"}
    unknown = set(profile) - allowed
    if unknown:
        raise BadRequest("unknown profile fields: %s" % ", ".join(sorted(unknown)))
    grams = profile.get("maxPlateGrams")
    if grams is not None:
        if not isinstance(grams, (int, float)) or isinstance(grams, bool):
            raise BadRequest("maxPlateGrams must be a number")
        if not 300 <= grams <= 5000:
            raise BadRequest("maxPlateGrams must be between 300 and 5000")
    return profile


def _clean_diet(raw):
    diet = raw or "egg"
    if diet not in model.DIETS:
        raise BadRequest("diet must be one of %s" % ", ".join(sorted(model.DIETS)))
    return diet


def _resolve_menu(body):
    """Either a named preset or a menu supplied inline."""
    inline = body.get("menu")
    if inline is not None:
        return _clean_menu(inline)
    menu_id = body.get("menuId", "iiit")
    _clean_id(menu_id, "menuId")
    if menu_id not in MENUS:
        raise BadRequest("no preset called %r" % menu_id)
    return MENUS[menu_id]


def _clean_menu(raw):
    """Validate a menu the caller supplied, dish by dish.

    An unknown dish id is refused rather than silently dropped. Quietly
    ignoring half of someone's menu and then reporting a shortfall would be
    the worst possible failure mode for this product.
    """
    menu = _as_dict(raw, "menu")
    if "days" not in menu:
        raise BadRequest("menu needs a days object")

    known = set(CATALOG["dishes"])
    cleaned_days = {}
    days = _as_dict(menu["days"], "menu.days")
    if not days or len(days) > len(model.DAYS):
        raise BadRequest("menu must carry between one and seven days")

    for day, meals in days.items():
        if day not in model.DAYS:
            raise BadRequest("unknown day %r" % day)
        cleaned_meals = {}
        for meal, served in _as_dict(meals, "menu.days.%s" % day).items():
            if meal not in model.MEALS:
                raise BadRequest("unknown meal %r" % meal)
            if not isinstance(served, list) or len(served) > MAX_MENU_DISHES_PER_MEAL:
                raise BadRequest("%s %s must be a short list of dishes" % (day, meal))
            for dish_id in served:
                _clean_id(dish_id, "dish id")
                if dish_id not in known:
                    raise BadRequest("no dish called %r in the catalog" % dish_id)
            cleaned_meals[meal] = list(served)
        cleaned_days[day] = cleaned_meals

    cleaned_daily = {}
    for meal, served in _as_dict(menu.get("daily"), "menu.daily").items():
        if meal not in model.MEALS:
            raise BadRequest("unknown meal %r" % meal)
        if not isinstance(served, list) or len(served) > MAX_MENU_DISHES_PER_MEAL:
            raise BadRequest("daily %s must be a short list of dishes" % meal)
        for dish_id in served:
            _clean_id(dish_id, "dish id")
            if dish_id not in known:
                raise BadRequest("no dish called %r in the catalog" % dish_id)
        cleaned_daily[meal] = list(served)

    region = menu.get("region", "IN")
    if region not in targets_module.REFERENCES:
        raise BadRequest("unknown region %r" % region)

    cuisine = menu.get("cuisine")
    if cuisine is not None and cuisine not in KNOWN_CUISINES:
        raise BadRequest("unknown cuisine %r" % cuisine)

    return {
        "id": "custom",
        "name": str(menu.get("name", "Your menu"))[:120],
        "region": region,
        "cuisine": cuisine,
        "daily": cleaned_daily,
        "days": cleaned_days,
    }


def _common(body):
    return {
        "profile": _clean_profile(body.get("profile")),
        "diet": _clean_diet(body.get("diet")),
        "prices": _clean_prices(body.get("prices")),
        "excluded": _clean_excluded(body.get("excluded")),
    }


def _clean_day(body, menu):
    day = body.get("day", "mon")
    if day not in menu["days"]:
        raise BadRequest("this menu has no %r" % day)
    return day


def _profile_for(menu, profile):
    """Default the region to whatever the menu is written for."""
    merged = dict(profile)
    merged.setdefault("region", menu.get("region", "IN"))
    return merged


# --------------------------------------------------------------------------
# Actions
# --------------------------------------------------------------------------

def action_presets(body):
    return {
        "menus": [
            {
                "id": menu["id"],
                "name": menu["name"],
                "subtitle": menu.get("subtitle", ""),
                "providerNoun": menu.get("providerNoun", "your meal plan"),
                "region": menu.get("region", "IN"),
                "cuisine": menu.get("cuisine", ""),
                "currency": menu.get("currency", ""),
                "servingStyleNote": menu.get("servingStyleNote", ""),
                "source": menu.get("source", {}),
                "days": sorted(menu["days"], key=model.DAYS.index),
                # The dishes themselves, so the builder can start from a
                # preset and edit it rather than from an empty week. `days`
                # stays a list of day names because the interface reads it
                # that way; this is the same menu keyed for editing, and it
                # goes back through `_clean_menu` on the way in like anything
                # else a caller posts.
                "offerings": {
                    day: {meal: list(dishes)
                          for meal, dishes in sorted(meals.items())}
                    for day, meals in menu["days"].items()
                },
                "daily": {meal: list(dishes)
                          for meal, dishes in sorted(menu.get("daily", {}).items())},
            }
            for menu in sorted(MENUS.values(), key=lambda m: m["id"])
        ],
        "diets": sorted(model.DIETS),
        "regions": targets_module.regions(),
        "nutrients": CATALOG["nutrients"],
        "notes": CATALOG["notes"],
    }


def action_catalog(body):
    """Everything the front end needs to let someone build their own menu."""
    return {
        "dishes": [
            {
                "id": dish["id"],
                "name": dish["name"],
                "tags": dish["tags"],
                "servingGrams": dish["servingGrams"],
                "maxServings": dish["maxServings"],
                "proxy": bool(dish.get("proxy")),
            }
            for dish in sorted(CATALOG["dishes"].values(), key=lambda d: d["name"])
        ],
        "market": [
            {
                "id": item["id"],
                "name": item["name"],
                "unit": item["unit"],
                "tags": item["tags"],
                "maxUnits": item["maxUnits"],
                "defaultPrice": item["defaultPrice"],
                "proxy": bool(item.get("proxy")),
            }
            for item in sorted(CATALOG["market"].values(), key=lambda i: i["name"])
        ],
        "currencies": CATALOG["currencies"],
    }


def action_gap(body):
    menu = _resolve_menu(body)
    common = _common(body)
    return plan.gap(CATALOG, menu, _clean_day(body, menu),
                    profile=_profile_for(menu, common["profile"]),
                    diet=common["diet"], excluded=common["excluded"])


def action_solve(body):
    menu = _resolve_menu(body)
    common = _common(body)
    budget = body.get("budget")
    if budget is not None:
        if not isinstance(budget, (int, float)) or isinstance(budget, bool):
            raise BadRequest("budget must be a number")
        if budget < 0 or budget > 1e7:
            raise BadRequest("budget is out of range")
    return plan.cheapest(CATALOG, menu, _clean_day(body, menu),
                         profile=_profile_for(menu, common["profile"]),
                         diet=common["diet"], prices=common["prices"],
                         budget=budget, excluded=common["excluded"])


def action_frontier(body):
    menu = _resolve_menu(body)
    common = _common(body)
    points = body.get("points", plan.FRONTIER_POINTS)
    if not isinstance(points, int) or isinstance(points, bool):
        raise BadRequest("points must be a whole number")
    if not 2 <= points <= MAX_FRONTIER_POINTS:
        raise BadRequest("points must be between 2 and %d" % MAX_FRONTIER_POINTS)
    return plan.frontier(CATALOG, menu, _clean_day(body, menu),
                         profile=_profile_for(menu, common["profile"]),
                         diet=common["diet"], prices=common["prices"],
                         points=points, excluded=common["excluded"])


def action_week(body):
    menu = _resolve_menu(body)
    common = _common(body)
    return plan.week(CATALOG, menu,
                     profile=_profile_for(menu, common["profile"]),
                     diet=common["diet"], prices=common["prices"],
                     excluded=common["excluded"])


def action_audit(body):
    menu = _resolve_menu(body)
    common = _common(body)
    students = body.get("students", 1)
    if not isinstance(students, int) or isinstance(students, bool):
        raise BadRequest("students must be a whole number")
    if not 1 <= students <= MAX_STUDENTS:
        raise BadRequest("students must be between 1 and %d" % MAX_STUDENTS)
    return audit_module.audit_week(CATALOG, menu,
                                   profile=_profile_for(menu, common["profile"]),
                                   diet=common["diet"], prices=common["prices"],
                                   students=students, excluded=common["excluded"])


def action_parse(body):
    """Read a pasted menu and say, dish by dish, what we think it says.

    No model and no network: matching written names against a fixed catalog
    is a string problem with a right answer, and this path has to work on a
    cold start with nothing but the standard library.

    The interesting part of the response is `unmatched`. Everything we could
    not place comes back with the near misses that were rejected, because the
    failure mode that would ruin this product is quietly dropping half of
    somebody's menu and then reporting a shortfall they do not have.
    """
    text = body.get("text")
    if not isinstance(text, str):
        raise BadRequest("text must be your menu, pasted as a string")
    if len(text) > MAX_PASTED_CHARS:
        raise BadRequest("pasted menu must be under %d characters"
                         % MAX_PASTED_CHARS)
    if not text.strip():
        raise BadRequest("there is no menu in that text")

    name = body.get("name")
    if name is not None:
        if not isinstance(name, str):
            raise BadRequest("name must be a string")
        name = name[:MAX_MENU_NAME_CHARS].strip() or None

    region = body.get("region")
    if region is not None and region not in targets_module.REFERENCES:
        raise BadRequest("unknown region %r" % region)

    reading = menutext.parse(CATALOG, text, aliases=ALIASES, name=name,
                             region=region)
    if not reading["stats"]["itemsRead"]:
        raise BadRequest("could not find anything that looks like a dish in "
                         "that text")

    # Run the parsed menu through the same validation a caller-supplied menu
    # gets, so that what comes back is exactly what `solve` will accept. A
    # parser whose output the solver then rejects is worse than no parser.
    parsed = reading["menu"]
    ready = bool(parsed["days"])
    return {
        "menu": _clean_menu(parsed) if ready else None,
        "readyToSolve": ready,
        "days": sorted(parsed["days"], key=model.DAYS.index),
        "matched": reading["matched"],
        "unmatched": reading["unmatched"],
        "warnings": reading["warnings"],
        "stats": reading["stats"],
    }


def action_explain(body):
    """Write up one day's solve in prose, and check its arithmetic.

    Takes the same body as `solve`, and re-solves rather than accepting a
    result from the caller: numbers the caller supplied are the caller's
    numbers, and the entire point of this action is that every figure in the
    text came out of the simplex.

    Always returns 200. If Bedrock is missing, denied, slow, or writes a
    number that does not reconcile, the templated explanation is returned
    with `source` saying so.
    """
    menu = _resolve_menu(body)
    common = _common(body)
    day = _clean_day(body, menu)
    profile = _profile_for(menu, common["profile"])

    model_id = body.get("model")
    if model_id is not None and model_id not in EXPLAIN_MODELS:
        raise BadRequest("model must be one of %s" % ", ".join(EXPLAIN_MODELS))

    shortfall = plan.gap(CATALOG, menu, day, profile=profile,
                         diet=common["diet"], excluded=common["excluded"])
    answer = plan.cheapest(CATALOG, menu, day, profile=profile,
                           diet=common["diet"], prices=common["prices"],
                           excluded=common["excluded"])

    # A preset's name ships with us and is safe to put in a prompt. A menu
    # the caller posted carries a name the caller wrote, so it does not go
    # anywhere near the model.
    label = menu["name"] if menu.get("id") != "custom" else "your menu"

    written = explain_module.write(CATALOG, label, shortfall, answer,
                                   model_id=model_id)
    written.update({
        "day": day,
        "diet": common["diet"],
        "feasible": bool(answer.get("feasible")),
        "currency": answer.get("currency"),
        "spend": answer.get("spend"),
    })
    return written


ACTIONS = {
    "presets": action_presets,
    "catalog": action_catalog,
    "gap": action_gap,
    "solve": action_solve,
    "frontier": action_frontier,
    "week": action_week,
    "audit": action_audit,
    "parse": action_parse,
    "explain": action_explain,
}


# --------------------------------------------------------------------------
# Plumbing
# --------------------------------------------------------------------------

def _respond(status, payload):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(payload),
    }


def _read_body(event):
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        import base64
        raw = base64.b64decode(raw).decode("utf-8", "replace")
    if len(raw) > MAX_BODY_BYTES:
        raise BadRequest("request body is too large")
    try:
        body = json.loads(raw)
    except ValueError:
        raise BadRequest("body is not valid JSON")
    if not isinstance(body, dict):
        raise BadRequest("body must be a JSON object")
    return body


def handler(event, context):
    method = (event.get("requestContext", {})
              .get("http", {})
              .get("method", "POST")).upper()
    if method == "OPTIONS":
        return {"statusCode": 204, "body": ""}

    try:
        body = _read_body(event)
        name = body.get("action", "presets")
        if name not in ACTIONS:
            raise BadRequest("unknown action %r; try one of %s"
                             % (name, ", ".join(sorted(ACTIONS))))
        return _respond(200, ACTIONS[name](body))
    except BadRequest as problem:
        return _respond(400, {"error": str(problem)})
    except (model.MenuError, targets_module.UnknownProfile) as problem:
        return _respond(400, {"error": str(problem)})
    except Exception:
        # Log the detail, return none of it. A stack trace from a public
        # endpoint tells an attacker about the runtime and nothing useful to
        # anyone else.
        import traceback
        traceback.print_exc()
        return _respond(500, {"error": "the solver failed on this input"})
