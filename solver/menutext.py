"""Read a mess menu somebody pasted, and match it to the catalog.

Picking a preset is fine for a demo. Using this on your own mess means typing
your menu in, and nobody is going to type forty dish ids by hand. So this
takes the timetable as it is actually written -- on a notice board, in a
WhatsApp forward, in a spreadsheet someone exported -- and works out which
catalog dish each line means.

Two things make that harder than string matching:

  * Menus are written by people who are not spelling for a computer. The real
    IIIT timetable this project was built on says "reoti" for roti, "araher
    dal" for toor dal, "muteer paneer" for mutter paneer. The menu files carry
    an `aliases` map of exactly these, which is the best evidence we have of
    how a real mess writes things down, so the map is used as a first-class
    source of matches rather than as a curiosity.

  * A wrong match is silent. If "chana masala" quietly becomes "chole", the
    solve still returns, still looks confident, and is wrong in a way nobody
    can see. That is worse than any amount of "I don't know this one". So a
    guess is only used when it is a long way ahead of the alternatives, and
    everything else -- including the near misses -- comes back in a list the
    caller has to look at.

Standard library only, and no model. Matching a menu against a fixed catalog
of a hundred dishes is a string problem, and a string problem with an exact
answer should not be handed to something that will make one up.
"""

import difflib
import re
import unicodedata

from . import model

# --------------------------------------------------------------------------
# How sure is sure enough
#
# `difflib`'s ratio on short dish names sits around 0.9 for the kind of
# misspelling a menu actually contains ("reoti"/"roti" is 0.89, "sambar"/
# "sambhar" is 0.92) and drops fast for genuinely different dishes. The floor
# for using a match is set above the first and below the second; between the
# two thresholds a candidate is offered as a suggestion but never applied.
# --------------------------------------------------------------------------

STRONG_ENOUGH = 0.86
WORTH_SUGGESTING = 0.68

# Two different dishes this close together is not a match, it is a coin toss.
AMBIGUOUS_MARGIN = 0.04

MAX_SUGGESTIONS = 3

# A paste is length-bounded by the caller, but a pathological one could still
# be thousands of two-character fragments, and each fragment costs a fuzzy
# search. Read a generous menu's worth and say plainly that the rest was left.
MAX_ITEMS = 300

# Meal labels. "tea" on its own is deliberately absent: the catalog has a dish
# called tea, and a mess menu that lists tea as a snack item is far more
# common than one that uses the bare word as a column heading. "High tea" and
# "tea time" are unambiguous, so they stay.
MEAL_LABELS = {
    "breakfast": "breakfast",
    "break fast": "breakfast",
    "brekfast": "breakfast",
    "breakfa": "breakfast",
    "morning": "breakfast",
    "brunch": "lunch",
    "lunch": "lunch",
    "afternoon": "lunch",
    "snack": "snacks",
    "snacks": "snacks",
    "evening": "snacks",
    "evening snack": "snacks",
    "evening snacks": "snacks",
    "high tea": "snacks",
    "tea time": "snacks",
    "tiffin": "snacks",
    "evening tiffin": "snacks",
    "dinner": "dinner",
    "supper": "dinner",
    "night": "dinner",
}

DAY_LABELS = {
    "mon": "mon", "monday": "mon",
    "tue": "tue", "tues": "tue", "tuesday": "tue",
    "wed": "wed", "weds": "wed", "wednesday": "wed",
    "thu": "thu", "thur": "thu", "thurs": "thu", "thursday": "thu",
    "fri": "fri", "friday": "fri",
    "sat": "sat", "saturday": "sat",
    "sun": "sun", "sunday": "sun",
}

# A column of paid extras is on the menu and is not part of the mess plan:
# the student pays for it at the counter. Reading it as free food would
# make every menu that prints its extras look better than the one that
# doesn't, so its heading marks it as a column to leave out.
SKIP = "skip"
_PAID_COLUMN = re.compile(r"\b(extras?|paid|add ons?|a la carte|optional)\b")

# The same thing written inside a cell: "Mix Veg + Dal. Extra: Chicken Kali
# Mirch, Tawa Paneer". Everything from the word to the end of the cell is
# sold, not served.
_PAID_TAIL = re.compile(r"\bextras?\b\s*[:\-\u2013\u2014]+.*$", re.IGNORECASE | re.DOTALL)

# The first cell of a row that is served on every day of the week, in a grid
# with the days down the side.
_EVERY_DAY = re.compile(
    r"^(daily|every ?day|all days|compulsory|common|regular|fixed|standard)\b")

_DAY_AT_START = re.compile(
    r"^\s*(%s)\b[\s:.\-–—]*" % "|".join(
        sorted(DAY_LABELS, key=len, reverse=True)),
    re.IGNORECASE)

_MEAL_AT_START = re.compile(
    r"^\s*(%s)\b[\s:.\-–—]*" % "|".join(
        sorted(MEAL_LABELS, key=len, reverse=True)),
    re.IGNORECASE)

# A meal label used mid-line only counts when it is punctuated as a heading,
# so "snacks: tea, samosa" splits and "tea" stays a dish.
_MEAL_INLINE = re.compile(
    r"\b(%s)\b\s*[:\-–—]" % "|".join(
        sorted(MEAL_LABELS, key=len, reverse=True)),
    re.IGNORECASE)

# Cells of a table row: pipes and tabs. Commas are item separators, not cell
# separators, because every menu puts several dishes in one cell.
_CELLS = re.compile(r"\s*[|\t]\s*|\s{4,}")

_ITEMS = re.compile(r"\s*(?:,|;|/|\+|•|\band\b)\s*", re.IGNORECASE)

# Leading counts and bullets ("2x", "-", "1."), and trailing punctuation.
_ITEM_EDGES = re.compile(r"^[\s\W\d_]*|[\s\W_]*$")

# A trailing serving size. A menu written for people says how much of a thing
# you get -- "boiled egg 2 pcs", "milk 200 ml", "papad 2 pcs" -- and the
# catalog names the dish, not the portion, so the quantity is noise that
# would otherwise sink the match. Portions are the solver's business and it
# works them out itself.
_QUANTITY_TAIL = re.compile(
    r"[\s\-/(]*\b\d+\s*"
    r"(?:pcs?|pieces?|nos?|ml|ltr?|litres?|liters?|g|gm|gms|gram|grams|kg"
    r"|glass(?:es)?|cups?|bowls?|plates?|slices?|katori|katoris)\b\.?\s*$",
    re.IGNORECASE)
_PARENS = re.compile(r"\([^)]*\)")


def normalise(text):
    """Fold a written dish name down to something comparable.

    Accents off, case off, punctuation to spaces. `roti.` and `Roti` and
    `ROTI ` are the same three letters and should not be three problems.
    """
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("_", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


# Transliteration, not spelling. There is no official Latin spelling of these
# dishes, so a menu writes down what the word sounds like: idli or idly,
# sambhar or sambar, paratha or parantha. These substitutions collapse the
# choices a writer has when there is no right answer -- the aspirate h that
# English does not hear, doubled vowels, a final y that is an i. What is left
# is close to how the word is said, and two spellings of one dish land on the
# same string far more often than two different dishes do.
_FOLDS = (
    (re.compile(r"(?<=[bcdgjkpstz])h"), ""),
    (re.compile(r"ee"), "i"),
    (re.compile(r"oo"), "u"),
    (re.compile(r"([a-z])\1+"), r"\1"),
    (re.compile(r"y\b"), "i"),
)


def fold(norm):
    for pattern, replacement in _FOLDS:
        norm = pattern.sub(replacement, norm)
    return norm


# --------------------------------------------------------------------------
# The index of things a pasted name is allowed to mean
# --------------------------------------------------------------------------

def build_index(catalog, aliases=None):
    """Every string that identifies a dish, and how strong that claim is.

    Three sources, in descending authority: the dish's printed name, its
    catalog id, and an alias from a shipped menu file. When two sources
    disagree about the same string the stronger one wins, and when two
    *different* dishes claim one string it is dropped rather than resolved --
    an index entry that silently picks a winner is the silent wrong match
    this module exists to avoid.
    """
    claims = {}

    def claim(key, dish_id, how, rank):
        if not key:
            return
        held = claims.get(key)
        if held is None or rank < held[2]:
            claims[key] = (dish_id, how, rank)
        elif held[0] != dish_id and rank == held[2]:
            claims[key] = (None, "conflict", rank)

    for dish_id, dish in catalog["dishes"].items():
        claim(normalise(dish["name"]), dish_id, "name", 0)
        claim(normalise(dish_id), dish_id, "id", 1)

    for written, dish_id in (aliases or {}).items():
        # An alias pointing at a dish the catalog no longer has is a stale
        # menu file, not an input error. Ignore it quietly.
        if dish_id in catalog["dishes"]:
            claim(normalise(written), dish_id, "alias", 2)

    index = {key: (dish_id, how)
             for key, (dish_id, how, _) in claims.items() if dish_id}

    # The same keys heard rather than spelled. One folded string can be owned
    # by more than one dish, and when it is, that is not a match to resolve --
    # it is a question to ask.
    owners = {}
    for key, (dish_id, _) in index.items():
        owners.setdefault(fold(key), set()).add(dish_id)

    # Word containment is only offered against the catalog's own names and
    # ids. An alias is one kitchen's spelling of one dish, and it is trusted
    # as a spelling; letting its words stand for the dish as well is how
    # "rice" (plain rice) came to swallow "curd rice", and "milk" "milk cake".
    named = {fold(key) for key, (_, how) in index.items() if how != "alias"}

    return {
        "byKey": index,
        "owners": owners,
        "folded": sorted(owners),
        "tokens": {key: (frozenset(key.split()), key.split()[-1])
                   for key in named},
    }


# Words that describe how a dish is cooked or served, or a raw ingredient
# put out beside it, and never name a cooked dish on their own. "Dry" is the
# last word of "Gobhi dry" and still not a dish; "tomato" on a menu is a
# sliced tomato, not the aloo tomato it is the last word of.
_ONLY_DESCRIBES = frozenset(fold(word) for word in (
    "dry", "fry", "fried", "curry", "gravy", "masala", "plain", "special",
    "veg", "mix", "mixed", "boiled", "roasted", "stir", "side", "bowl",
    "portion", "glass", "slice", "sweet", "green", "red", "white",
    "tomato", "onion", "cucumber", "carrot", "lemon", "chilli", "salt"))


def _containment(written_tokens, key_tokens, key_head=None):
    """Score a name that is one of the words of a dish, or all of them.

    "Curd" is not a typo for "plain curd" and no edit-distance measure will
    ever say it is -- four characters against ten scores 0.57, below any
    threshold worth having. But a menu that says curd means the curd, and a
    menu that says dal means one of six dals and needs to be asked which. So
    a name whose words are a subset of a dish's words (or the other way
    round) scores high, and the ambiguity check below does the rest.
    """
    if not written_tokens or not key_tokens:
        return 0.0
    if written_tokens <= _ONLY_DESCRIBES:
        return 0.0
    if not (written_tokens <= key_tokens or key_tokens <= written_tokens):
        return 0.0
    # A shorter name has to include the word the dish is named for, which in
    # these names is the last one: "curd" is a plain curd, but "dinner" is
    # not a dinner roll, "green" is not a green chutney and "moong" is not
    # moong halwa.
    if key_head is not None and written_tokens < key_tokens \
            and key_head not in written_tokens:
        return 0.0
    shared = float(min(len(written_tokens), len(key_tokens)))
    return 0.80 + 0.20 * (shared / max(len(written_tokens), len(key_tokens)))


def _candidates(norm, index):
    """Best candidate per dish, strongest first.

    Two measures, whichever says more: how alike two spellings are, and
    whether one name is contained in the other.
    """
    heard = fold(norm)
    written_tokens = frozenset(heard.split())
    scores = {}

    def offer(folded_key, score):
        if score < WORTH_SUGGESTING:
            return
        for dish_id in index["owners"][folded_key]:
            if dish_id not in scores or score > scores[dish_id][0]:
                scores[dish_id] = (score, folded_key)

    for folded_key in difflib.get_close_matches(heard, index["folded"], n=6,
                                                cutoff=WORTH_SUGGESTING):
        offer(folded_key,
              difflib.SequenceMatcher(None, heard, folded_key).ratio())

    for folded_key, (key_tokens, key_head) in index["tokens"].items():
        offer(folded_key, _containment(written_tokens, key_tokens, key_head))

    return sorted(((score, dish_id, folded_key)
                   for dish_id, (score, folded_key) in scores.items()),
                  key=lambda entry: (-entry[0], entry[1]))


def match_one(written, catalog, index):
    """Resolve one written dish name, and say how sure that is.

    Returns a dict with either `id` set (we are using this) or `reason` set
    (we are not, and here is why, and here is what we nearly said).

    A name that fails is tried once more without its serving size, because
    the catalog names dishes and menus name portions: "boiled egg 2 pcs" is
    the egg. The full name is tried first and kept when it wins, because the
    catalog also contains a dish called "Milk 200 ml", and a rule that
    stripped quantities up front would throw that exact match away.
    """
    outcome = _match_written(written, catalog, index)
    if "id" in outcome:
        return outcome

    shorter = _QUANTITY_TAIL.sub("", written).strip()
    if shorter and shorter != written:
        retry = _match_written(shorter, catalog, index)
        if "id" in retry:
            retry["text"] = written
            return retry
    return outcome


def _match_written(written, catalog, index):
    norm = normalise(_PARENS.sub(" ", written))
    if not norm:
        return {"text": written, "reason": "nothing readable in this item"}

    if norm in index["byKey"]:
        dish_id, how = index["byKey"][norm]
        return {
            "text": written,
            "id": dish_id,
            "name": catalog["dishes"][dish_id]["name"],
            "how": how if how == "alias" else "exact",
            "confidence": 1.0,
        }

    ranked = _candidates(norm, index)
    if not ranked:
        return {
            "text": written,
            "reason": "no dish in the catalog is close to this name",
            "suggestions": [],
        }

    suggestions = [
        {
            "id": other_id,
            "name": catalog["dishes"][other_id]["name"],
            "score": round(other_score, 3),
        }
        for other_score, other_id, _ in ranked[:MAX_SUGGESTIONS]
    ]

    def ambiguous():
        return {
            "text": written,
            "reason": "this could be %s or %s, and guessing between them "
                      "would be a coin toss" % (suggestions[0]["name"],
                                                suggestions[1]["name"]),
            "suggestions": suggestions,
        }

    # Same word, spelled differently. Believed unless two dishes answer to it.
    owners = index["owners"].get(fold(norm))
    if owners:
        if len(owners) > 1:
            return ambiguous()
        dish_id = sorted(owners)[0]
        return {
            "text": written,
            "id": dish_id,
            "name": catalog["dishes"][dish_id]["name"],
            "how": "spelling",
            "confidence": 0.95,
        }

    score, dish_id, _ = ranked[0]
    if len(ranked) > 1 and score - ranked[1][0] < AMBIGUOUS_MARGIN:
        return ambiguous()

    if score < STRONG_ENOUGH:
        return {
            "text": written,
            "reason": "closest catalog dish is %s, and that is not close "
                      "enough to use" % suggestions[0]["name"],
            "suggestions": suggestions,
        }

    # A near match must not put meat on a plate the menu never put it on.
    # "Sandwich" is a word of "Turkey sandwich" and of nothing else in the
    # catalog, so it scores as a clear winner -- and a vegetarian mess that
    # serves a sandwich would be read as serving turkey.
    dish = catalog["dishes"][dish_id]
    if "meat" in dish.get("tags", ()):
        heard = fold(norm).split()
        named = fold(normalise(dish["name"])).split()
        if not all(difflib.get_close_matches(word, heard, n=1, cutoff=0.75)
                   for word in named):
            return {
                "text": written,
                "reason": "the closest catalog dish is %s, and this name "
                          "does not say it is meat" % dish["name"],
                "suggestions": suggestions,
            }

    return {
        "text": written,
        "id": dish_id,
        "name": catalog["dishes"][dish_id]["name"],
        "how": "fuzzy",
        "confidence": round(score, 3),
        "suggestions": suggestions[1:],
    }


# --------------------------------------------------------------------------
# Reading the shape of the paste
# --------------------------------------------------------------------------

def _day_at_start(line):
    found = _DAY_AT_START.match(line)
    if not found:
        return None, line
    return DAY_LABELS[found.group(1).lower()], line[found.end():]


def _meal_at_start(text):
    found = _MEAL_AT_START.match(text)
    if not found:
        return None, text
    return MEAL_LABELS[found.group(1).lower()], text[found.end():]


def _split_on_meals(text):
    """Break `breakfast: idli lunch: chole` into labelled chunks.

    The chunk before the first label carries `None` for its meal, which the
    caller resolves against whatever meal was last in force.
    """
    chunks, position, meal = [], 0, None
    for found in _MEAL_INLINE.finditer(text):
        piece = text[position:found.start()]
        if piece.strip():
            chunks.append((meal, piece))
        meal = MEAL_LABELS[found.group(1).lower()]
        position = found.end()
    tail = text[position:]
    if tail.strip() or not chunks:
        chunks.append((meal, tail))
    return chunks


def _cells(text):
    return [cell for cell in _CELLS.split(text) if cell.strip()]


_PIPE_ROW = re.compile(r"^\s*\|.*\|\s*$")


def _grid_cells(line):
    """Cells of a pipe-delimited row, empty ones kept.

    `_cells` throws empty cells away, which is right for a pasted line and
    wrong for a grid: a blank Tuesday is the only thing keeping Wednesday in
    the Wednesday column.
    """
    cells = line.split("|")
    if cells and not cells[0].strip():
        cells = cells[1:]
    if cells and not cells[-1].strip():
        cells = cells[:-1]
    return [cell.strip() for cell in cells]


_DAY_NAMES = sorted(DAY_LABELS)


def _day_label(cell):
    """The weekday a header cell names, allowing for how it was spelled.

    Real timetables carry real typos -- the mess menu this was built against
    says "SAETURDAY" -- and one unrecognised header cell costs every dish in
    the column under it. So day names are matched the same forgiving way the
    dish names are.
    """
    norm = normalise(cell)
    if not norm:
        return None
    if norm in DAY_LABELS:
        return DAY_LABELS[norm]
    close = difflib.get_close_matches(norm, _DAY_NAMES, n=1, cutoff=0.8)
    return DAY_LABELS[close[0]] if close else None


def _day_in(cell):
    """The weekday a header cell names, also when it is written next to a
    date: "15th Feb, Friday"."""
    found = _day_label(cell)
    if found:
        return found
    named = {DAY_LABELS[word] for word in normalise(cell).split()
             if len(word) >= 3 and word in DAY_LABELS}
    return named.pop() if len(named) == 1 else None


def _is_day_header(cells):
    """A row of weekday names tells us which column is which day.

    This is the other way a timetable can be laid out, and by far the commoner
    one: days across the top, meals down the side. Every mess noticeboard
    worth the name is drawn this way. The first one or two cells are allowed
    not to be a day, because they are the corner of the grid -- "Meal",
    "Day", "Day | Structure", or nothing.

    A dated timetable can run past a week ("15th Feb, Friday" to "28th Feb,
    Thursday"). The first time each day appears is the one that is read; a
    column naming a day already seen comes back as None and is left out.

    Returns `(skip, days)`, `skip` being how many corner cells came before
    the day columns, so a caller reading the body rows knows where the label
    ends and the days begin. `None` if the row is not a day header.
    """
    for skip in (0, 1, 2):
        days = [_day_in(cell) for cell in cells[skip:]]
        if len(days) < 3 or not all(days):
            continue
        first = set()
        for position, found in enumerate(days):
            if found in first:
                days[position] = None
            first.add(found)
        return skip, days
    return None


def _meal_label(cell):
    """The meal a column heading names, `SKIP` for a column of paid extras,
    or None. A heading often carries the serving hours in brackets --
    "Breakfast (7:30 am to 9:30 am)" -- and they are not part of the name."""
    norm = normalise(_PARENS.sub(" ", cell))
    if norm in MEAL_LABELS:
        return MEAL_LABELS[norm]
    if _PAID_COLUMN.search(norm):
        return SKIP
    return None


def _is_meal_header(cells):
    """A row of nothing but meal names tells us the column order.

    The first cell is allowed not to be a meal, because a timetable's header
    row starts with something like "Day" or an empty corner cell above the
    column of weekdays. Everything after it has to be a meal name, or the
    heading of a column of paid extras, which is what stops a line of dishes
    being read as a header.
    """
    for skip in (0, 1):
        meals = []
        for cell in cells[skip:]:
            label = _meal_label(cell)
            if label is None:
                break
            meals.append(label)
        else:
            if len([m for m in meals if m != SKIP]) >= 2:
                return meals
    return None


def _items(text):
    out = []
    for piece in _ITEMS.split(text):
        piece = _ITEM_EDGES.sub("", piece).strip()
        if piece:
            out.append(piece)
    return out


# --------------------------------------------------------------------------
# The whole job
# --------------------------------------------------------------------------

def parse(catalog, text, aliases=None, name=None, region=None,
          max_items=MAX_ITEMS):
    """Turn pasted text into a menu object plus an honest account of it.

    The menu that comes back holds only dishes we are confident about. Every
    fragment we could not place is in `unmatched`, with the near misses that
    were rejected, because a caller who can see "we dropped chana masala"
    can fix it and a caller who cannot see it never knows.
    """
    index = build_index(catalog, aliases)

    days, matched, unmatched, warnings = {}, [], [], []
    daily = {}
    seen = {}
    day = None
    meal = None
    columns = None
    day_columns = None
    day_skip = 1
    items_read = 0
    truncated = False
    assumed_day = False
    assumed_meal = False
    guessed_columns = False
    paid_left_out = 0

    def served_part(cell):
        """A cell without its paid extras."""
        nonlocal paid_left_out
        kept = _PAID_TAIL.sub("", cell)
        if kept != cell:
            paid_left_out += 1
        return kept

    def place(day_name, meal_name, written):
        nonlocal assumed_day, assumed_meal
        if day_name is None:
            day_name, assumed_day = model.DAYS[0], True
        if meal_name is None:
            meal_name, assumed_meal = "lunch", True
        # The same name written twice is the same answer twice, and the
        # fuzzy search is the expensive part of this module.
        if written not in seen:
            seen[written] = match_one(written, catalog, index)
        outcome = dict(seen[written])
        outcome["day"] = day_name
        outcome["meal"] = meal_name
        if "id" in outcome:
            served = days.setdefault(day_name, {}).setdefault(meal_name, [])
            if outcome["id"] not in served:
                served.append(outcome["id"])
            matched.append(outcome)
        else:
            unmatched.append(outcome)

    def place_daily(meal_name, written):
        """Something served every day of the week.

        The menu model already serves a `daily` list on all seven days, so
        these go there rather than being written out seven times -- which
        would be seven times the fuzzy searches, and seven copies of the same
        complaint when one of them does not match.
        """
        nonlocal assumed_meal
        if meal_name is None:
            meal_name, assumed_meal = "lunch", True
        if written not in seen:
            seen[written] = match_one(written, catalog, index)
        outcome = dict(seen[written])
        outcome["day"] = None
        outcome["everyDay"] = True
        outcome["meal"] = meal_name
        if "id" in outcome:
            served = daily.setdefault(meal_name, [])
            if outcome["id"] not in served:
                served.append(outcome["id"])
            matched.append(outcome)
        else:
            unmatched.append(outcome)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or not re.search(r"[A-Za-z]", line):
            continue

        grid = _grid_cells(line) if _PIPE_ROW.match(line) else None
        cells = _cells(line)

        header_cells = grid if grid is not None else cells
        header = _is_meal_header(header_cells) if len(cells) >= 2 else None
        if header:
            columns, day_columns = header, None
            continue

        if grid is not None and len(grid) >= 4:
            found_days = _is_day_header(grid)
            if found_days:
                day_skip, day_columns = found_days
                columns = None
                continue

        # A row of a day-column grid. The leading cell or two names the
        # meal, or is blank because the meal is the one named a row or two
        # above and the kitchen only wrote it once.
        if day_columns is not None and grid is not None and len(grid) >= day_skip + 1:
            head = normalise(grid[0])
            label = MEAL_LABELS.get(head)
            if label is not None:
                meal = label
            body = grid[day_skip:]
            filled = [cell for cell in body if cell]
            # A "daily" row whose items are spread across the day columns is
            # not a daily row at all -- it is a row of ordinary per-day
            # dishes that happened to be written under that heading, and a
            # sweet served on Wednesday should not become a sweet served
            # every day. One cell of content is a merged cell; several are
            # seven different answers.
            everyday = ((head.startswith("daily")
                         or head.startswith("every day"))
                        and len(filled) <= 1)
            if everyday:
                # Which column the items sit in means nothing: a timetable
                # merges the cells for them, so they land wherever the merge
                # began. They belong to all seven days.
                for cell in body:
                    for written in _items(served_part(cell)):
                        if items_read >= max_items:
                            truncated = True
                            break
                        items_read += 1
                        place_daily(meal, written)
            else:
                for column_day, cell in zip(day_columns, body):
                    if column_day is None:
                        continue
                    for written in _items(served_part(cell)):
                        if items_read >= max_items:
                            truncated = True
                            break
                        items_read += 1
                        place(column_day, meal, written)
            continue

        # A row of a grid with the days down the side and the meals across
        # the top: the first cell names the day, or says the row is served
        # every day, or is blank because the day carries down from above.
        if columns is not None and grid is not None and len(grid) >= 2:
            head = grid[0]
            row_day = _day_label(head)
            everyday = bool(_EVERY_DAY.match(normalise(head)))
            if row_day or everyday or (not head and day is not None):
                if row_day:
                    day = row_day
                for column_meal, cell in zip(columns, grid[1:]):
                    if column_meal == SKIP:
                        if cell.strip():
                            paid_left_out += 1
                        continue
                    for written in _items(served_part(cell)):
                        if items_read >= max_items:
                            truncated = True
                            break
                        items_read += 1
                        if everyday:
                            place_daily(column_meal, written)
                        else:
                            place(day, column_meal, written)
                meal = None
                continue

        found_day, rest = _day_at_start(line)
        if found_day:
            day = found_day
            # A day on a line of its own is a heading for what follows, and
            # the meal in force from the previous day should not leak into it.
            if not rest.strip():
                meal = None
                continue
            line = rest

        # A table row: the day label was the first cell, and what is left is
        # one cell per meal. Only trusted when the column order was stated in
        # a header, or when there are exactly as many cells as meals.
        row_cells = _cells(line)
        if (found_day and len(row_cells) >= 2
                and not _MEAL_INLINE.search(line)
                and _meal_at_start(line)[0] is None):
            order = columns
            if order is None and len(row_cells) == len(model.MEALS):
                order = list(model.MEALS)
                guessed_columns = True
            if order and len(row_cells) <= len(order):
                for column_meal, cell in zip(order, row_cells):
                    if column_meal == SKIP:
                        paid_left_out += 1
                        continue
                    for written in _items(served_part(cell)):
                        if items_read >= max_items:
                            truncated = True
                            break
                        items_read += 1
                        place(day, column_meal, written)
                meal = None
                continue

        for chunk_meal, chunk in _split_on_meals(line):
            if chunk_meal is not None:
                meal = chunk_meal
            else:
                leading, chunk = _meal_at_start(chunk)
                if leading is not None:
                    meal = leading
            for written in _items(chunk):
                if items_read >= max_items:
                    truncated = True
                    break
                items_read += 1
                place(day, meal, written)

    if paid_left_out:
        warnings.append("%d cell%s of paid extras %s left out: they are sold "
                        "at the counter, not served on the mess plan"
                        % (paid_left_out, "" if paid_left_out == 1 else "s",
                           "was" if paid_left_out == 1 else "were"))
    if truncated:
        warnings.append("only the first %d items were read; the rest of the "
                        "paste was left alone" % max_items)
    if guessed_columns:
        warnings.append("this was read as a table with no heading row, so "
                        "each day's %d columns were taken to be %s in that "
                        "order" % (len(model.MEALS), ", ".join(model.MEALS)))
    if assumed_day:
        warnings.append("some items came before any day heading and were "
                        "read as %s" % model.DAYS[0])
    if assumed_meal:
        warnings.append("some items came before any meal heading and were "
                        "read as lunch")

    cuisine = _dominant_cuisine(catalog, matched)
    menu = {
        "name": name or "Pasted menu",
        "region": region or ("IN" if cuisine != "american" else "US"),
        "cuisine": cuisine,
        "daily": {meal_name: daily[meal_name]
                  for meal_name in model.MEALS if meal_name in daily},
        "days": {day_name: days[day_name]
                 for day_name in model.DAYS if day_name in days},
    }

    return {
        "menu": menu,
        "matched": matched,
        "unmatched": unmatched,
        "warnings": warnings,
        "stats": {
            "itemsRead": items_read,
            "matched": len(matched),
            "unmatched": len(unmatched),
            "exact": sum(1 for m in matched if m["how"] == "exact"),
            "alias": sum(1 for m in matched if m["how"] == "alias"),
            "spelling": sum(1 for m in matched if m["how"] == "spelling"),
            "fuzzy": sum(1 for m in matched if m["how"] == "fuzzy"),
            "days": len(menu["days"]),
            "coverage": round(len(matched) / float(items_read), 3)
                        if items_read else 0.0,
        },
    }


def _dominant_cuisine(catalog, matched):
    """Whichever kitchen most of the matched dishes came from.

    The audit refuses to recommend across kitchens, so a parsed menu needs a
    cuisine or it gets offered a yogurt parfait for its hostel mess.
    """
    counts = {}
    for entry in matched:
        dish = catalog["dishes"].get(entry["id"])
        if dish:
            counts[dish["cuisine"]] = counts.get(dish["cuisine"], 0) + 1
    if not counts:
        return None
    return max(sorted(counts), key=counts.get)
