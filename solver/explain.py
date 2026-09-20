"""Write up a solve in words, and refuse to publish a number we did not solve.

The interface already explains itself in templated sentences, and templates
are honest but they do not join anything up: they will tell you that zinc is
short by 4.2 mg and that spinach is on the shopping list and never that the
first is why the second is there. A model is good at exactly that joining up,
and catastrophically bad at the one thing this product sells, which is
arithmetic somebody can check.

So the model is allowed to write and is not allowed to count.

  * Everything it is given is a fact computed by the simplex -- a shortfall, a
    spend, a shadow price. Nothing the caller typed reaches the prompt: dish
    names come from the catalog, the day is one of seven words, and a menu
    somebody pasted in is referred to as "your menu" rather than by the name
    they gave it. A public endpoint that forwards user text to a model is a
    prompt injection with extra steps.

  * Everything it writes is checked back. Every number in the generated text
    is extracted and matched against the facts it was given, and if even one
    does not reconcile the whole explanation is thrown away and the templated
    one is returned instead. A paragraph that is right about four numbers and
    invented the fifth is not 80% useful, it is a liability, and there is no
    way to tell from the outside which number was the invented one.

The Bedrock import is lazy and the call is optional. The Lambda runtime ships
boto3 (AWS documents the Python runtimes as including the SDK, and this
function is deployed on python3.12), but nothing here may assume it: if the
import fails, or the role has no `bedrock:InvokeModel`, or the model times
out, the caller gets the templated explanation and a 200. An explanation is a
nicety. Failing a solve because a language model was unreachable would be
absurd.
"""

import json
import os
import re

# The default is the cheapest model that can write two decent paragraphs.
# Setting this to "off" disables the call entirely, which is what a deployment
# without the IAM grant should do rather than pay a timeout per request.
MODEL_ID = os.environ.get("PLATEGAP_EXPLAIN_MODEL", "amazon.nova-lite-v1:0")
BEDROCK_REGION = os.environ.get(
    "PLATEGAP_BEDROCK_REGION", os.environ.get("AWS_REGION", "us-east-1"))

# Two paragraphs. Generous enough not to truncate mid-sentence, small enough
# that a public endpoint cannot be used to rent someone else's inference.
MAX_OUTPUT_TOKENS = 400

# The Lambda's own timeout is 20s and the solve has already spent some of it.
# A model that has not answered in eight seconds is a fallback, not a wait.
READ_TIMEOUT_SECONDS = 8
CONNECT_TIMEOUT_SECONDS = 3

# Only so much of a solve is worth narrating. The rest is a table's job.
TOP_GAPS = 3
TOP_BUYS = 4
TOP_BINDING = 3

_CLIENT = None


class ModelUnavailable(RuntimeError):
    """The model could not be reached, or would not answer usefully."""


# --------------------------------------------------------------------------
# What the model is allowed to know
# --------------------------------------------------------------------------

def _nutrient_names(catalog):
    return {n["id"]: n["name"] for n in catalog["nutrients"]}


def _binding_label(catalog, row):
    """Turn a dual's row key into something a person can read."""
    names = _nutrient_names(catalog)
    if row["kind"] == "floor":
        return "the %s floor" % names.get(row["key"], row["key"])
    if row["kind"] == "ceiling":
        return "the %s ceiling" % names.get(row["key"], row["key"])
    if row["kind"] == "cap":
        dish = catalog["dishes"].get(row["key"])
        return "the ration on %s" % (dish["name"] if dish else row["key"])
    if row["kind"] == "limit":
        return "how much food fits on one day's plate"
    return row["key"]


def facts_from(catalog, menu_label, shortfall, answer):
    """Everything the write-up may mention, and nothing else.

    Values are the rounded ones the interface displays, so that the model is
    copying the same figures the reader can see on screen rather than a more
    precise number that would look like a contradiction.
    """
    facts = {
        "menu": menu_label,
        "day": answer["day"],
        "diet": answer.get("diet", shortfall.get("diet")),
        "feasible": bool(answer.get("feasible")),
    }

    if shortfall.get("feasible"):
        total = shortfall["targetsMet"] + shortfall["targetsMissed"]
        facts["targetsTotal"] = total
        facts["targetsTheMenuAloneMisses"] = shortfall["targetsMissed"]
        facts["targetsTheMenuAloneMeets"] = shortfall["targetsMet"]
        facts["biggestGaps"] = [
            {
                "nutrient": gap["name"],
                "shortBy": gap["short"],
                "unit": gap["unit"],
                "percentOfRequirementMissing": gap["percentShort"],
            }
            for gap in shortfall["shortfalls"][:TOP_GAPS]
        ]

    if not answer.get("feasible"):
        facts["whyNot"] = answer.get("reason", "")
        return facts

    currency = answer["currency"]
    facts["currencySymbol"] = currency["symbol"]
    facts["currencyCode"] = currency["code"]
    facts["spendToCloseTheGap"] = answer["spend"]
    facts["spendOverThirtyDays"] = round(answer["spendExact"] * 30,
                                         currency["decimals"])
    facts["gramsOfFoodOnThePlan"] = answer["plateGrams"]
    facts["buy"] = [
        {"item": item["name"], "howMany": item["amount"],
         "unit": item["unit"], "cost": item["cost"]}
        for item in answer["buy"][:TOP_BUYS]
    ]
    facts["messItemsEatenToTheirRationLimit"] = [
        item["name"] for item in answer["plate"] if item.get("atCap")
    ][:TOP_BUYS]
    facts["whatIsBinding"] = [
        {
            "constraint": _binding_label(catalog, row),
            "costOfOneMoreUnit": row["shadowPrice"],
        }
        for row in answer["binding"][:TOP_BINDING]
    ]
    return facts


def allowed_numbers(facts, extra=()):
    """Every number the write-up is permitted to contain."""
    found = []

    def walk(value):
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            found.append(float(value))
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(facts)
    found.extend(float(value) for value in extra)
    return found


# --------------------------------------------------------------------------
# Checking the numbers back
# --------------------------------------------------------------------------

_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


def _mask_labels(text, facts):
    """Blank out names before counting digits.

    A dish called "Chicken 65" would otherwise fail its own check. Only
    strings that contain a digit are masked, so the mask cannot be used to
    smuggle a number past the check.
    """
    labels = []

    def walk(value):
        if isinstance(value, str):
            if any(ch.isdigit() for ch in value):
                labels.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(facts)
    for label in sorted(labels, key=len, reverse=True):
        text = re.sub(re.escape(label), " ", text, flags=re.IGNORECASE)
    return text


def unsupported_numbers(text, facts, extra=()):
    """Every number in `text` that no solver output accounts for.

    A number is accounted for when some fact rounds to it at the precision it
    was written with -- "9" stands for 9.0 and "11.42" does not stand for
    11.4. Writing a figure to fewer places than we computed it is normal
    English; inventing a figure is not.
    """
    permitted = allowed_numbers(facts, extra)
    unsupported = []
    for written in _NUMBER.findall(_mask_labels(text, facts)):
        cleaned = written.replace(",", "")
        try:
            value = float(cleaned)
        except ValueError:            # pragma: no cover - regex forbids this
            unsupported.append(written)
            continue
        places = len(cleaned.split(".")[1]) if "." in cleaned else 0
        tolerance = 0.5 * (10 ** -places) + 1e-9
        if not any(abs(candidate - value) <= tolerance
                   for candidate in permitted):
            unsupported.append(written)
    return unsupported


# --------------------------------------------------------------------------
# The templated explanation, which is also the fallback
# --------------------------------------------------------------------------

def _figure(value):
    """A whole number is written without its decimal point.

    Rupees carry no paise in this catalog, so the templated text would
    otherwise say "9.0 a day" where the screen says 9.
    """
    if isinstance(value, float) and value == int(value):
        return "%d" % int(value)
    return "%s" % value


def templated(facts):
    """The same sentences the interface builds, as one paragraph.

    This is what ships when there is no model, and it is deliberately the
    same text the screen already shows: a fallback that says something
    different from the rest of the page would just look like a bug.
    """
    day = facts["day"]
    menu = facts["menu"]

    if not facts.get("feasible"):
        return ("On %s, %s cannot reach every target even with purchases, "
                "inside the portion limits and what one person can eat. %s"
                % (day, menu, facts.get("whyNot", ""))).strip()

    symbol = facts["currencySymbol"]
    money = "%s%s" % (symbol, _figure(facts["spendToCloseTheGap"]))
    monthly = "%s%s" % (symbol, _figure(facts["spendOverThirtyDays"]))

    parts = []
    # Absent is not zero. If the shortfall solve did not come back at all,
    # there is nothing true to say about how much of the menu is covered, and
    # saying nothing beats saying it covers everything.
    missed = facts.get("targetsTheMenuAloneMisses")
    if missed:
        gaps = ", ".join(
            "%s (short by %s %s, %s%% of the requirement)"
            % (gap["nutrient"], _figure(gap["shortBy"]), gap["unit"],
               _figure(gap["percentOfRequirementMissing"]))
            for gap in facts.get("biggestGaps", []))
        parts.append(
            "Eaten as well as it can be eaten, %s on %s still misses %d of "
            "%d targets: %s."
            % (menu, day, missed, facts["targetsTotal"], gaps))
    elif missed == 0:
        parts.append("Eaten carefully, %s on %s meets every target on its "
                     "own." % (menu, day))

    if not facts["buy"]:
        # A menu that needs no topping up is a result, not an empty screen.
        parts.append("There is nothing you need to buy on top of it.")
    else:
        buys = ", ".join(
            "%s × %s of %s for %s%s"
            % (_figure(item["howMany"]), item["unit"], item["item"],
               symbol, _figure(item["cost"]))
            for item in facts["buy"])
        parts.append("The cheapest way to close it is %s a day -- %s -- which "
                     "is %s over thirty days on top of a fee you have already "
                     "paid." % (money, buys, monthly))

    if facts["messItemsEatenToTheirRationLimit"]:
        parts.append("The plan eats %s up to the ration limit."
                     % ", ".join(facts["messItemsEatenToTheirRationLimit"]))

    if facts["whatIsBinding"]:
        binding = facts["whatIsBinding"][0]
        parts.append("What is actually holding the cost up is %s: one more "
                     "unit of it is worth %s%s."
                     % (binding["constraint"], symbol,
                        _figure(binding["costOfOneMoreUnit"])))

    return " ".join(parts)


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------

INSTRUCTIONS = """You are writing the short plain-language summary that sits \
at the top of a nutrition planner's results for one student, for one day.

A linear program has already worked everything out. Your only job is to say \
what it found, in two short paragraphs of no more than about 110 words in \
total, in calm plain English. Second person. No headings, no bullet points, \
no markdown, no greeting, no sign-off.

The rules about numbers are absolute:
- Use only numbers that appear in the FACTS below.
- Copy each one exactly as it is written there. Do not round it, scale it, \
convert it, or combine it with another one.
- Do not calculate anything. No totals, no percentages, no per-week or \
per-year figures, no averages.
- If you want to say something the FACTS do not give you a number for, say it \
without a number.

The meal plan is already paid for, so the food on the counter is free at the \
margin but rationed. The money in the FACTS is what the student would spend \
of their own, on top of that, to reach every nutritional target. A shadow \
price is what one more unit of a binding constraint would be worth.

FACTS:
%s"""


def prompt_for(facts):
    return INSTRUCTIONS % json.dumps(facts, indent=1, sort_keys=True)


def _body_for(model_id, prompt):
    """Bedrock takes a different JSON body per model family."""
    if "anthropic" in model_id:
        return {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": MAX_OUTPUT_TOKENS,
            "temperature": 0.2,
            "messages": [{"role": "user",
                          "content": [{"type": "text", "text": prompt}]}],
        }
    return {
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": MAX_OUTPUT_TOKENS,
                            "temperature": 0.2},
    }


def _text_from(model_id, payload):
    if "anthropic" in model_id:
        blocks = payload.get("content") or []
    else:
        blocks = payload.get("output", {}).get("message", {}).get("content") or []
    text = " ".join(block.get("text", "") for block in blocks).strip()
    if not text:
        raise ModelUnavailable("the model returned nothing to show")
    return text


def call_model(prompt, model_id=None):
    """Invoke Bedrock, importing boto3 only if we get this far.

    Every other action in this function pays nothing for this: the import,
    the client and the endpoint resolution all happen inside this call, on
    the first explanation a warm container serves.
    """
    global _CLIENT
    model_id = model_id or MODEL_ID
    if not model_id or model_id.lower() in ("off", "none", "disabled"):
        raise ModelUnavailable("the written explanation is switched off")

    if _CLIENT is None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as problem:
            raise ModelUnavailable("no AWS SDK in this runtime: %s" % problem)
        try:
            _CLIENT = boto3.client(
                "bedrock-runtime", region_name=BEDROCK_REGION,
                config=Config(connect_timeout=CONNECT_TIMEOUT_SECONDS,
                              read_timeout=READ_TIMEOUT_SECONDS,
                              retries={"max_attempts": 1}))
        except Exception as problem:
            raise ModelUnavailable("no Bedrock client: %s" % problem)

    try:
        response = _CLIENT.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(_body_for(model_id, prompt)))
        payload = json.loads(response["body"].read())
    except ModelUnavailable:
        raise
    except Exception as problem:
        # AccessDeniedException until the role is granted bedrock:InvokeModel,
        # then throttling, timeouts and the rest. They all mean the same thing
        # here, which is that there is no written explanation this time.
        raise ModelUnavailable("%s: %s" % (type(problem).__name__, problem))

    return _text_from(model_id, payload)


def write(catalog, menu_label, shortfall, answer, invoke=None, model_id=None):
    """The whole action: facts, a written attempt, and a checked result."""
    facts = facts_from(catalog, menu_label, shortfall, answer)
    fallback = templated(facts)
    # The exact figures behind the rounded ones on screen. The model is never
    # shown these, but if it happens to echo one it is still the solver's.
    extra = [answer[key] for key in ("spendExact", "spendOptimal", "spend")
             if isinstance(answer.get(key), (int, float))]
    extra += [answer["spendExact"] * 30] if "spendExact" in answer else []

    result = {
        "explanation": fallback,
        "templated": fallback,
        "source": "templated",
        "model": None,
        "facts": facts,
    }

    if not facts.get("feasible"):
        # Nothing to narrate but a refusal, and the templated refusal already
        # says the only true thing there is to say.
        result["fallbackReason"] = ("this day cannot be reached at any price, "
                                    "so there is no plan to describe")
        return result

    if invoke is None:
        # Resolved here rather than bound above so that the choice of model
        # travels with the request, and so that a test can replace
        # `call_model` without having to know this module's signature.
        def invoke(prompt):
            return call_model(prompt, model_id)

    try:
        written = invoke(prompt_for(facts))
    except ModelUnavailable as problem:
        result["fallbackReason"] = str(problem)
        return result
    except Exception as problem:
        # Anything at all. A socket that died mid-read, a botocore that
        # disagrees with the runtime about a model id, a JSON body in a shape
        # nobody expected. None of it is worth a 500 on a solve that worked.
        result["fallbackReason"] = "%s: %s" % (type(problem).__name__, problem)
        return result

    if not isinstance(written, str) or not written.strip():
        result["fallbackReason"] = "the model returned nothing to show"
        return result

    written = written.strip()
    invented = unsupported_numbers(written, facts, extra)
    if invented:
        result["fallbackReason"] = (
            "the written explanation used %s, which is not a number this "
            "solve produced, so it was discarded"
            % ", ".join(invented[:4]))
        result["unsupportedNumbers"] = invented
        return result

    result["explanation"] = written
    result["source"] = "model"
    result["model"] = model_id or MODEL_ID
    return result
