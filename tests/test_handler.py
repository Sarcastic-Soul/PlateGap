"""Tests for the Lambda handler.

The Function URL is public and unauthenticated, so most of what is worth
testing here is what happens when the input is wrong rather than when it is
right: bad actions, unknown dishes, out-of-range numbers, oversized bodies.
A handler that solves correctly and leaks a stack trace on bad input has
still failed.
"""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "lambda"))

import handler  # noqa: E402


def call(**body):
    event = {
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps(body),
    }
    response = handler.handler(event, None)
    return response["statusCode"], json.loads(response["body"] or "{}")


def test_preflight_is_answered():
    response = handler.handler(
        {"requestContext": {"http": {"method": "OPTIONS"}}}, None)
    assert response["statusCode"] == 204


def test_the_function_never_sends_cors_headers_itself():
    """CORS belongs to the Function URL, which adds the headers to every

    response. Sending them from here as well produced
    `Access-Control-Allow-Origin: *, *` -- two values where the spec allows
    one -- and the browser refused every call while curl, which does not
    enforce CORS, reported a healthy endpoint."""
    status, _ = call(action="presets")
    assert status == 200
    for event in ({"requestContext": {"http": {"method": "OPTIONS"}}},
                  {"body": json.dumps({"action": "presets"})}):
        headers = handler.handler(event, None).get("headers", {})
        assert not [h for h in headers if h.lower().startswith("access-control")]


def test_presets_lists_every_menu_that_shipped():
    status, body = call(action="presets")
    assert status == 200
    ids = {menu["id"] for menu in body["menus"]}
    assert {"iiit", "dining-hall", "generic"} <= ids
    for menu in body["menus"]:
        assert menu["days"], "%s has no days" % menu["id"]


def test_every_preset_solves_through_the_handler():
    _, presets = call(action="presets")
    for menu in presets["menus"]:
        for day in menu["days"]:
            status, body = call(action="solve", menuId=menu["id"], day=day,
                                diet="all")
            assert status == 200, (menu["id"], day, body)
            assert body["feasible"], (menu["id"], day)


def test_catalog_exposes_enough_to_build_a_menu():
    status, body = call(action="catalog")
    assert status == 200
    assert len(body["dishes"]) > 50
    assert len(body["market"]) > 10
    assert all("name" in dish and "id" in dish for dish in body["dishes"])


def test_a_menu_can_be_supplied_inline():
    status, body = call(
        action="solve", day="mon",
        menu={"region": "US", "cuisine": "american",
              "days": {"mon": {"lunch": ["cheeseburger", "french_fries"],
                               "dinner": ["grilled_chicken", "steamed_broccoli"]}}})
    assert status == 200
    assert body["feasible"]
    assert body["currency"]["code"] == "USD"


def test_prices_supplied_by_the_caller_are_used():
    cheap = call(action="solve", menuId="iiit", day="mon",
                 prices={"egg": 1.0})[1]
    dear = call(action="solve", menuId="iiit", day="mon",
                prices={"egg": 500.0})[1]
    assert cheap["spendExact"] <= dear["spendExact"] + 1e-6


@pytest.mark.parametrize("body,fragment", [
    ({"action": "nonsense"}, "unknown action"),
    ({"action": "solve", "menuId": "nope"}, "no preset"),
    ({"action": "solve", "menuId": "iiit", "day": "funday"}, "no 'funday'"),
    ({"action": "solve", "diet": "carnivore"}, "diet must be"),
    ({"action": "solve", "profile": {"sneaky": 1}}, "unknown profile"),
    ({"action": "solve", "profile": {"maxPlateGrams": 9}}, "between 300"),
    ({"action": "solve", "prices": {"egg": -5}}, "out of range"),
    ({"action": "solve", "prices": {"../etc": 5}}, "price key"),
    ({"action": "frontier", "points": 1000}, "points must be"),
    ({"action": "audit", "students": 0}, "students must be"),
    ({"action": "solve", "menu": {"days": {"mon": {"lunch": ["no_such_dish"]}}}},
     "no dish called"),
    ({"action": "solve", "menu": {"days": {"someday": {}}}}, "unknown day"),
    ({"action": "solve", "menu": {"days": {"mon": {"brunch": []}}}}, "unknown meal"),
])
def test_bad_input_is_refused_with_a_reason(body, fragment):
    status, answer = call(**body)
    assert status == 400, answer
    assert fragment in answer["error"], answer["error"]


def test_a_traversal_attempt_is_not_a_dish_name():
    status, answer = call(
        action="solve",
        menu={"days": {"mon": {"lunch": ["../../etc/passwd"]}}})
    assert status == 400
    assert "identifier" in answer["error"]


def test_oversized_body_is_refused():
    event = {"requestContext": {"http": {"method": "POST"}},
             "body": "x" * (handler.MAX_BODY_BYTES + 1)}
    response = handler.handler(event, None)
    assert response["statusCode"] == 400


def test_malformed_json_is_refused():
    event = {"requestContext": {"http": {"method": "POST"}}, "body": "{oh no"}
    response = handler.handler(event, None)
    assert response["statusCode"] == 400
    assert "valid JSON" in json.loads(response["body"])["error"]


def test_failures_do_not_leak_internals(monkeypatch):
    def explode(body):
        raise RuntimeError("secret detail: /var/task/handler.py line 12")

    monkeypatch.setitem(handler.ACTIONS, "solve", explode)
    status, answer = call(action="solve")
    assert status == 500
    assert "secret detail" not in answer["error"]
    assert "/var/task" not in answer["error"]


def test_the_audit_only_suggests_dishes_from_the_right_kitchen():
    status, body = call(action="audit", menuId="iiit", students=10)
    assert status == 200
    american = {d["id"] for d in call(action="catalog")[1]["dishes"]}
    _, catalog = call(action="catalog")
    for recommendation in body["recommendations"]:
        assert recommendation["id"] in american
    # And the reverse: nothing Indian shows up for the dining hall.
    _, hall = call(action="audit", menuId="dining-hall", students=10)
    names = {r["id"] for r in hall["recommendations"]}
    assert "matar_chola" not in names


def test_every_recommendation_says_why():
    _, body = call(action="audit", menuId="iiit", students=10)
    assert body["recommendations"]
    for recommendation in body["recommendations"]:
        drivers = recommendation["drivers"]
        assert drivers, recommendation["id"]
        # Drivers come back most-helpful first. A positive one is a real
        # answer too -- it says the dish also uses up stomach space or
        # calories -- but a candidate that priced in must have at least one
        # constraint it relieves.
        assert drivers[0]["contribution"] < 0, recommendation["id"]


def test_responses_are_json_serialisable_all_the_way_down():
    for action in ("presets", "catalog", "gap", "solve", "frontier", "week"):
        status, body = call(action=action, menuId="iiit", day="mon")
        assert status == 200, (action, body)
        json.dumps(body)
