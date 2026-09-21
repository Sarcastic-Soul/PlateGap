#!/usr/bin/env python3
"""Run PlateGap over every published hostel mess menu we could find.

One menu is an anecdote. This takes the menus Indian colleges post on their
own websites -- listed, with the URL each came from, in
`data/field/menus/SOURCES.csv` -- and puts every one of them through the same
pipeline a person uses in the app:

    transcribe   the product's own reader (Nova Lite, `solver/menuscan.py`)
                 copies each page into text. Structured sources (a JSON feed,
                 an HTML table) are converted directly, with no model.
    parse        `solver/menutext.py` matches the written names to catalog
                 dishes, and says which ones it would not place.
    settle       the names it would not place are settled by hand, in
                 `data/field/settlements.json`, one decision per written name,
                 each with a reason. Nothing is settled silently.
    run          the week is solved for each menu, and the results go to
                 `data/field/results.json` and `docs/hackathon/FIELD-STUDY.md`.

    uv run --with boto3 --with 'botocore[crt]' --with pillow \
        python scripts/field_study.py transcribe
    uv run python scripts/field_study.py parse
    uv run python scripts/field_study.py run
    uv run python scripts/field_study.py report

The raw files are not committed -- they are other institutions' documents,
and the source URLs make the study reproducible. The transcriptions are, so
that every number downstream can be traced to the text it came from.
"""

import base64
import csv
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from solver import menuscan, menutext, model, plan  # noqa: E402

FIELD = os.path.join(ROOT, "data", "field")
RAW = os.path.join(FIELD, "menus", "raw")
TEXT = os.path.join(FIELD, "menus", "text")
PARSED = os.path.join(FIELD, "menus", "parsed")
SOURCES = os.path.join(FIELD, "menus", "SOURCES.csv")
SETTLEMENTS = os.path.join(FIELD, "settlements.json")
RESULTS = os.path.join(FIELD, "results.json")

DAY_LABELS = dict(zip(model.DAYS, ("Monday", "Tuesday", "Wednesday", "Thursday",
                                   "Friday", "Saturday", "Sunday")))


def sources():
    with open(SOURCES, newline="") as handle:
        return list(csv.DictReader(handle))


def stem(filename):
    return filename.rsplit(".", 1)[0]


# --------------------------------------------------------------------------
# transcribe
# --------------------------------------------------------------------------

def _pdf_pages(path):
    """Each page of a PDF as its own PDF, because the reader takes one page
    at a time reliably and a week often runs onto a second one."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdfseparate", path, os.path.join(tmp, "p-%d.pdf")],
                       check=True, capture_output=True)
        names = sorted(os.listdir(tmp), key=lambda n: int(n[2:-4]))
        pages = []
        for name in names:
            with open(os.path.join(tmp, name), "rb") as handle:
                pages.append(handle.read())
        return pages


def _read(data, kind):
    try:
        answer = menuscan.read(data, kind)
    except menuscan.ScanUnavailable as problem:
        return {"error": str(problem)}
    return answer


def _json_feed(path):
    """IIT Delhi's hostel publishes the menu as the JSON behind its page."""
    with open(path) as handle:
        feed = json.load(handle)
    meals = [h["id"] for h in feed["hours"]]
    days = feed["days"]
    lines = ["| Meal | " + " | ".join(d["label"] for d in days) + " |",
             "|---" * (len(days) + 1) + "|"]
    always = feed.get("always", {})
    for meal in meals:
        cells = []
        for day in days:
            names = [i["name"] for i in day["meals"].get(meal, [])]
            names += always.get(meal, [])
            cells.append(", ".join(names))
        lines.append("| %s | %s |" % (meal.title(), " | ".join(cells)))
    return "\n".join(lines)


def _html_text(path):
    """A menu published as an HTML table, reduced to pipe-separated rows."""
    with open(path, errors="ignore") as handle:
        page = handle.read()
    page = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", page)
    page = re.sub(r"(?i)</t[dh]>", " | ", page)
    page = re.sub(r"(?i)</tr>|<br\s*/?>|</p>|</li>|</h\d>", "\n", page)
    page = html.unescape(re.sub(r"<[^>]+>", " ", page))
    lines = [re.sub(r"\s+", " ", line).strip(" |") for line in page.splitlines()]
    return "\n".join(line for line in lines if line)


def _embedded_images(path):
    with open(path, errors="ignore") as handle:
        page = handle.read()
    return [base64.b64decode(m) for m in
            re.findall(r"data:image/png;base64,([A-Za-z0-9+/=]+)", page)]


def _as_jpeg(png):
    """Re-encode a large scan as JPEG, as the web page does with a photo
    before uploading it. A 2.4 MB PNG is inside the size limit but slow
    enough to read that the call times out."""
    import io
    from PIL import Image  # only this step needs it: uv run --with pillow
    image = Image.open(io.BytesIO(png)).convert("RGB")
    out = io.BytesIO()
    image.save(out, "JPEG", quality=85)
    return out.getvalue()


def transcribe_one(row):
    name = row["file"]
    path = os.path.join(RAW, name)
    out = os.path.join(TEXT, stem(name) + ".txt")
    if os.path.exists(out):
        return name, "kept"
    ext = name.rsplit(".", 1)[1].lower()
    parts, notes = [], []

    if ext == "json":
        parts.append(_json_feed(path))
        notes.append("converted from the JSON feed, no model")
    elif ext == "html" and "embedded" not in row["format"]:
        parts.append(_html_text(path))
        notes.append("converted from the HTML page, no model")
    elif ext == "html":
        # Four weeks of a rotating cycle as scanned images. Week A only: the
        # study compares one week per institution.
        images = _embedded_images(path)
        answer = _read(_as_jpeg(images[0]), "jpeg")
        parts.append(answer.get("text", ""))
        notes.append("week A of %d embedded scans, read by the model" % len(images))
        if "error" in answer:
            notes.append("read failed: " + answer["error"])
    else:
        for number, page in enumerate(_pdf_pages(path), 1):
            answer = _read(page, "pdf")
            if "error" in answer:
                notes.append("page %d read failed: %s" % (number, answer["error"]))
                continue
            notes.extend("page %d: %s" % (number, w) for w in answer["warnings"])
            parts.append("<!-- page %d -->\n%s" % (number, answer["text"]))

    if not any(p.strip() for p in parts):
        # Nothing to keep. Writing an empty file would make the next run
        # skip this menu as done.
        return name, "NOTHING READ: " + "; ".join(notes)

    header = "<!-- %s | %s | %s -->\n" % (row["institution"], row["hostel_or_mess"],
                                         "; ".join(notes) or "read by the model")
    with open(out, "w") as handle:
        handle.write(header + "\n\n".join(p for p in parts if p) + "\n")
    return name, "; ".join(notes) or "ok"


def transcribe():
    os.makedirs(TEXT, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for name, outcome in pool.map(transcribe_one, sources()):
            print("%-60s %s" % (name, outcome))


# --------------------------------------------------------------------------
# parse and settle
# --------------------------------------------------------------------------

def _catalog():
    with open(os.path.join(ROOT, "data", "foods.json")) as handle:
        return json.load(handle)


def _settlements():
    if not os.path.exists(SETTLEMENTS):
        return {"_about": "", "global": {}, "menus": {}}
    with open(SETTLEMENTS) as handle:
        return json.load(handle)


def _aliases():
    """The same aliases the live parser uses: the shared synonyms, then every
    shipped menu's own spellings on top."""
    with open(os.path.join(ROOT, "data", "aliases.json")) as handle:
        aliases = dict(json.load(handle)["aliases"])
    menus = os.path.join(ROOT, "data", "menus")
    for name in sorted(os.listdir(menus)):
        if name.endswith(".json"):
            with open(os.path.join(menus, name)) as handle:
                aliases.update(json.load(handle).get("aliases", {}))
    return aliases


# A menu that numbers its dishes ("1 Chole Puri 2. Upma 3. Bread Butter")
# has no other separator between them. The live parser does not split on
# numbers, because "Egg 2 pcs" is one item; for the menus listed as numbered
# in the settlements file the numbers are turned into commas first.
_NUMBERING = re.compile(r"(?:(?<=\s)|(?<=^)|(?<=\|))\s*\d{1,2}\s*[.)]?\s*(?=[A-Za-z])")


def _text_for(row, settlements):
    """The transcription, without the file's own header comments, which are
    notes about where the text came from and not part of the menu."""
    with open(os.path.join(TEXT, stem(row["file"]) + ".txt")) as handle:
        text = handle.read()
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    crop = settlements.get("crop", {}).get(stem(row["file"]))
    if crop:
        # A menu published inside a whole web page: keep from the line that
        # starts the menu to the one that ends it.
        start = text.index(crop[0])
        text = text[start:text.index(crop[1], start)]
    # An HTML page that breaks a day's name across a tag: "Wednes day".
    text = re.sub(r"(?im)^(mon|tues|wednes|thurs|fri|satur|sun) day\b", r"\1day", text)
    if stem(row["file"]) in settlements.get("numbered", []):
        text = "\n".join(_NUMBERING.sub(", ", line) if line.lstrip().startswith("|")
                         else line for line in text.splitlines())
    return text


# Things a transcription picks up that are not food: serving hours, prices,
# page furniture, stray letters. Dropped by rule rather than one by one, and
# counted, so the study can say how much it threw away this way.
_NOISE = re.compile(
    r"^(?:"
    r"(?:\d{1,2}(?: \d{2})? )?(?:am|pm)(?: to \d{1,2}(?: \d{2})? (?:am|pm))?"
    r"|(?:\d{1,2} \d{2} )?(?:am|pm) to .*"
    r"|page \d+"
    r"|[a-z]{1,2}"
    r"|.*\brs \d+.*"
    r"|paid extras?"
    r")$")


def _is_noise(key):
    return bool(_NOISE.match(key))


def _compile_rules(settlements):
    return [(re.compile(pattern), dishes, why)
            for pattern, dishes, why in settlements.get("rules", [])]


def _decide(key, decisions, rules):
    """(dishes, how, reason) for one written name the parser would not place,
    or None when nothing settles it. A decision written for the name wins;
    then the first rule whose pattern the name contains."""
    if key in decisions:
        return decisions[key], "by hand", ""
    for pattern, dishes, why in rules:
        if pattern.search(key):
            return dishes, "by rule", why
    return None


def _apply(menu, unmatched, decisions, rules=(), log=None):
    """Settle the names the parser would not place.

    `decisions` maps a written name (as the parser normalised it) to a dish
    id, or to null for "not a dish the catalog should count" -- a condiment,
    a drink, a label. Every unmatched name either has a decision or is
    reported as still open.
    """
    open_names, settled, noise = [], 0, 0
    for item in unmatched:
        written = item.get("written") or item.get("text") or ""
        key = menutext.normalise(written)
        if _is_noise(key) and key not in decisions:
            noise += 1
            continue
        decided = _decide(key, decisions, rules)
        if decided is None:
            open_names.append(written)
            continue
        settled += 1
        dishes, how, why = decided
        if log is not None:
            log.append((key, how, dishes, why))
        if dishes is None:
            continue
        if isinstance(dishes, str):
            dishes = [dishes]
        if item.get("everyDay") or item.get("day") is None:
            served = menu.setdefault("daily", {}).setdefault(item["meal"], [])
        else:
            served = menu["days"].setdefault(item["day"], {}).setdefault(item["meal"], [])
        for dish in dishes:
            if dish not in served:
                served.append(dish)
    return open_names, settled, noise


def parse():
    catalog = _catalog()
    aliases = _aliases()
    settlements = _settlements()
    known = set(catalog["dishes"])
    scopes = [settlements.get("global", {})] + list(settlements.get("menus", {}).values())
    scopes.append({pattern: dishes for pattern, dishes, _ in settlements.get("rules", [])})
    for scope in scopes:
        for key, dishes in scope.items():
            for dish in ([dishes] if isinstance(dishes, str) else dishes or []):
                if dish not in known:
                    raise SystemExit("settlement %r names %r, which the catalog "
                                     "does not have" % (key, dish))
    rules = _compile_rules(settlements)
    ledger = {}
    os.makedirs(PARSED, exist_ok=True)
    report = []
    for row in sources():
        name = stem(row["file"])
        text = _text_for(row, settlements)
        answer = menutext.parse(catalog, text, aliases=aliases, name=row["institution"],
                                region="IN", max_items=5000)
        menu = answer["menu"]
        menu["id"] = name
        strict = json.loads(json.dumps(menu))
        decisions = dict(settlements.get("global", {}))
        decisions.update(settlements.get("menus", {}).get(name, {}))
        log = []
        open_names, settled, noise = _apply(menu, answer["unmatched"], decisions,
                                            rules, log)
        for key, how, dishes, why in log:
            ledger.setdefault((key, how, json.dumps(dishes), why), set()).add(name)
        with open(os.path.join(PARSED, name + ".json"), "w") as handle:
            json.dump({"menu": menu, "parserOnly": strict,
                       "matched": len(answer["matched"]),
                       "settledByHand": settled, "noise": noise, "open": open_names,
                       "warnings": answer.get("warnings", [])},
                      handle, indent=1, sort_keys=True)
        days = sorted(menu.get("days", {}))
        report.append((name, len(answer["matched"]), settled, noise, len(open_names),
                       len(days)))
    # Every settled name, what it became and why, so each stand-in can be
    # checked against the text it came from.
    with open(os.path.join(FIELD, "settled.csv"), "w", newline="") as handle:
        out = csv.writer(handle)
        out.writerow(["written", "how", "became", "reason", "menus"])
        for (key, how, dishes, why), menus in sorted(ledger.items()):
            out.writerow([key, how, "; ".join(json.loads(dishes) if dishes.startswith("[")
                                              else [json.loads(dishes) or "(not counted)"]),
                          why, " ".join(sorted(menus))])
    for line in report:
        print("%-52s matched %3d  settled %3d  noise %3d  open %3d  days %d" % line)
    print("total: matched %d  settled %d  noise %d  open %d" % tuple(
        sum(line[i] for line in report) for i in (1, 2, 3, 4)))


def open_names():
    """Every name still unsettled, grouped, for writing decisions against."""
    catalog = _catalog()
    index = menutext.build_index(catalog, _aliases())
    counts = {}
    for row in sources():
        with open(os.path.join(PARSED, stem(row["file"]) + ".json")) as handle:
            parsed = json.load(handle)
        for written in parsed["open"]:
            key = menutext.normalise(written)
            counts.setdefault(key, [written, 0, set()])
            counts[key][1] += 1
            counts[key][2].add(stem(row["file"]))
    for key, (written, count, menus) in sorted(counts.items(), key=lambda kv: -kv[1][1]):
        near = menutext.match_one(written, catalog, index)
        hints = [c.get("id") for c in near.get("suggestions", [])][:3]
        print("%3d  %-40s %-30s %s" % (count, key[:40], ",".join(h for h in hints if h),
                                       ",".join(sorted(menus))[:60]))


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------

PROFILES = {"male": {"region": "IN", "sex": "male"},
            "female": {"region": "IN", "sex": "female"}}


def _solve_menu(catalog, menu, profile, diet):
    """Two questions per day, the same two the app asks: what does the mess
    alone leave short, and what is the cheapest way to close it."""
    days, spend, unreachable = [], 0.0, []
    for day in model.DAYS:
        if day not in menu["days"]:
            continue
        alone = plan.gap(catalog, menu, day, profile=profile, diet=diet)
        topup = plan.cheapest(catalog, menu, day, profile=profile, diet=diet)
        if topup.get("feasible"):
            spend += topup["spendExact"]
        else:
            unreachable.append(day)
        days.append({
            "day": day,
            "short": {s["id"]: s["percentShort"] for s in alone.get("shortfalls", [])},
            "buy": [{"id": b["id"], "name": b["name"], "cost": b.get("cost")}
                    for b in topup.get("buy", [])],
            "spend": round(topup["spendExact"], 2) if topup.get("feasible") else None,
        })
    reachable = len(days) - len(unreachable)
    return {
        "days": days,
        "weeklySpend": round(spend, 2),
        "dailyAverage": round(spend / reachable, 2) if reachable else None,
        "unreachableDays": unreachable,
    }


def run():
    catalog = _catalog()
    rows = sources()
    out = {"about": "Every menu in data/field/menus solved for a whole week, "
                    "the same way the app solves one day. See "
                    "docs/hackathon/FIELD-STUDY.md for what this does and does "
                    "not show.",
           "reference": "ICMR-NIN 2020, adult aged 19-30, sedentary",
           "menus": []}
    for row in rows:
        name = stem(row["file"])
        with open(os.path.join(PARSED, name + ".json")) as handle:
            parsed = json.load(handle)
        menu = parsed["menu"]
        entry = {"id": name, "institution": row["institution"],
                 "mess": row["hostel_or_mess"], "state": row["state"],
                 "region": row["region"], "type": row["institution_type"],
                 "period": row["menu_period_if_stated"], "vegOnly": row["veg_only"] == "yes",
                 "source": row["source_url"],
                 "names": {"matched": parsed["matched"], "settled": parsed["settledByHand"],
                           "noise": parsed["noise"]},
                 "dishes": len({d for day in menu["days"].values() for meal in day.values()
                                for d in meal} | {d for meal in menu.get("daily", {}).values()
                                                  for d in meal}),
                 "results": {}}
        diets = ["veg"] if entry["vegOnly"] else ["veg", "egg"]
        for sex, profile in PROFILES.items():
            for diet in diets:
                entry["results"]["%s/%s" % (sex, diet)] = _solve_menu(catalog, menu, profile, diet)
        # The same week with nothing settled by hand or by rule: only what
        # the live parser placed on its own. Fewer dishes can only make a
        # shortfall worse, so a conclusion that holds in both is not an
        # artefact of the stand-ins.
        strict = parsed["parserOnly"]
        if all(strict["days"].get(day) for day in model.DAYS):
            for sex, profile in PROFILES.items():
                entry["results"]["%s/veg/parserOnly" % sex] = _solve_menu(
                    catalog, strict, profile, "veg")
        out["menus"].append(entry)
        veg = entry["results"]["male/veg"]
        print("%-52s %2d dishes  veg male: short on %s  top-up Rs %.0f/week" % (
            name, entry["dishes"],
            ",".join(sorted({n for d in veg["days"] for n in d["short"]})) or "-",
            veg["weeklySpend"]))
    with open(RESULTS, "w") as handle:
        json.dump(out, handle, indent=1, sort_keys=True)


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

STUDY_DOC = os.path.join(ROOT, "docs", "hackathon", "FIELD-STUDY.md")
BEGIN, END = "<!-- generated by scripts/field_study.py report -->", "<!-- end generated -->"

NUTRIENTS = (("iron", "Iron"), ("vitb12", "Vitamin B12"), ("calcium", "Calcium"),
             ("zinc", "Zinc"), ("potassium", "Potassium"), ("vitc", "Vitamin C"),
             ("vita", "Vitamin A"), ("magnesium", "Magnesium"), ("kcal", "Energy"),
             ("protein", "Protein"), ("fibre", "Fibre"), ("folate", "Folate"))


def _short_on(result, nutrient):
    days = result["days"]
    hit = sum(1 for day in days if nutrient in day["short"])
    return hit, len(days)


def _count(menus, key, nutrient):
    """Menus short on a nutrient on at least one day, and on every day."""
    some = every = 0
    for menu in menus:
        hit, total = _short_on(menu["results"][key], nutrient)
        some += hit > 0
        every += hit == total
    return some, every


def _rupees(value):
    return "₹%s" % format(int(round(value)), ",")


def report():
    with open(RESULTS) as handle:
        results = json.load(handle)
    menus = results["menus"]
    lines = [BEGIN, ""]

    lines += ["### What the mess alone cannot reach",
              "",
              "A vegetarian eating the best plate the menu allows, every day of "
              "the week, within the portion limits. Out of %d menus:" % len(menus),
              "",
              "| Nutrient | Women: short some day | Women: short every day "
              "| Men: short some day | Men: short every day |",
              "| --- | --- | --- | --- | --- |"]
    for nutrient, label in NUTRIENTS:
        f_some, f_every = _count(menus, "female/veg", nutrient)
        m_some, m_every = _count(menus, "male/veg", nutrient)
        if f_some or m_some:
            lines.append("| %s | %d | %d | %d | %d |" % (label, f_some, f_every, m_some, m_every))
    lines.append("")

    lines += ["### Menu by menu",
              "",
              "Days of the week (out of 7) on which the best vegetarian plate "
              "from the mess is still short, for a woman; and what closing "
              "every gap costs a week at the catalog's market prices.",
              "",
              "| Institution | Mess | Menu dated | Dishes | Iron | B12 | Calcium "
              "| Top-up a week (woman) | Top-up a week (man) |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for menu in sorted(menus, key=lambda m: -m["results"]["female/veg"]["weeklySpend"]):
        female, male = menu["results"]["female/veg"], menu["results"]["male/veg"]
        lines.append("| %s | %s | %s | %d | %d | %d | %d | %s | %s |" % (
            menu["institution"], menu["mess"], menu["period"] or "not stated",
            menu["dishes"], _short_on(female, "iron")[0], _short_on(female, "vitb12")[0],
            _short_on(female, "calcium")[0], _rupees(female["weeklySpend"]),
            _rupees(male["weeklySpend"])))
    spends = sorted(m["results"]["female/veg"]["weeklySpend"] for m in menus)
    male_spends = sorted(m["results"]["male/veg"]["weeklySpend"] for m in menus)
    lines += ["",
              "Median top-up: %s a week for a woman, %s for a man. Range %s to %s "
              "(women) and %s to %s (men)." % (
                  _rupees(spends[len(spends) // 2]), _rupees(male_spends[len(male_spends) // 2]),
                  _rupees(spends[0]), _rupees(spends[-1]),
                  _rupees(male_spends[0]), _rupees(male_spends[-1])),
              ""]

    buys = {}
    for menu in menus:
        for key in ("female/veg", "male/veg"):
            for day in menu["results"][key]["days"]:
                for item in day["buy"]:
                    buys.setdefault(item["name"], set()).add(menu["id"])
    lines += ["### What closes the gap",
              "",
              "How many menus' cheapest weekly top-up (for either sex) includes each item.",
              "",
              "| Item | Menus |", "| --- | --- |"]
    for name, where in sorted(buys.items(), key=lambda kv: -len(kv[1])):
        lines.append("| %s | %d |" % (name, len(where)))
    lines.append("")

    strict = [m for m in menus if "female/veg/parserOnly" in m["results"]]
    lines += ["### With and without the hand-settled names",
              "",
              "The %d menus the live parser alone gave a dish for every day, "
              "solved twice: with every settled name, and with only the "
              "parser's own matches. Menus short on a nutrient on every day "
              "of the week:" % len(strict),
              "",
              "| Nutrient | Women, settled | Women, parser only "
              "| Men, settled | Men, parser only |",
              "| --- | --- | --- | --- | --- |"]
    for nutrient, label in NUTRIENTS:
        cells = [_count(strict, key, nutrient)[1] for key in
                 ("female/veg", "female/veg/parserOnly", "male/veg", "male/veg/parserOnly")]
        if any(cells):
            lines.append("| %s | %d | %d | %d | %d |" % tuple([label] + cells))
    lines += ["", END]

    with open(STUDY_DOC) as handle:
        doc = handle.read()
    head, rest = doc.split(BEGIN, 1)
    tail = rest.split(END, 1)[1]
    with open(STUDY_DOC, "w") as handle:
        handle.write(head + "\n".join(lines) + tail)


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "run"
    {"transcribe": transcribe, "parse": parse, "open": open_names, "run": run,
     "report": report}[command]()
