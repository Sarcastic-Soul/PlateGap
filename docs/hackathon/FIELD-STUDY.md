# Field study: 14 published mess menus

One menu is an anecdote. PlateGap was built against the menu of the mess I
eat at, and that proves the solver works on one menu. It does not show that
the problem is common. So I took every hostel mess menu I could find on an
Indian college website, 14 menus from 12 institutions, and ran each one
through the same pipeline a person uses in the app. Then I solved a whole
week for each.

## Why these nutrients

National surveys already show the problem in this age group. These figures
set the context. The study does not measure any of them:

- **Anaemia.** 59.1% of girls aged 15–19 and 31.1% of boys aged 15–19 are
  anaemic (NFHS-5, 2019–21).
- **Vitamin B12.** 31.0% of adolescents aged 10–19 are B12-deficient (CNNS
  2016–18; Shalini et al., *Nutrients* 2023). Among young vegetarian
  graduates in Pune, half had serum B12 below 148 pmol/l (Naik et al., *Br J
  Nutr* 2018).

Sources and caveats for these figures are in `DATA-SOURCES.md`. I found no
modern, open, peer-reviewed analysis of what Indian hostel mess menus supply,
which is part of why this study was worth doing.

## What was done

1. **Collected.** Every menu comes from an institution's own website. The URL,
   the date I retrieved it and the date the menu gives for itself are in
   `data/field/menus/SOURCES.csv`. I tried 57 more that failed to download
   (removed files, bot walls, login pages, dead servers, DNS failures, or no
   public menu at all). I set aside 13 documents that turned out not to be a
   hostel's published menu: tender documents, food-policy notes, a priced
   guest-house list, a school, a duplicate, and four institutions whose menu
   is only ever set informally by a student mess committee and never
   published. One earlier excluded document was a list of students' fee
   dues, which I deleted. 15 more menus that were in an earlier version of
   this study were retired for being out of date (2012–2022) and, where a
   current one could be found, replaced. All 85 are in
   `data/field/menus/FAILED.csv`.
2. **Transcribed.** 12 of the 14 menus are PDFs, scans or a photo. The app's
   own reader, Amazon Nova Lite on Bedrock (`solver/menuscan.py`), copied
   them into text a page (or image) at a time. The other two, a JSON feed
   and an HTML table, were converted directly with no model involved. The
   raw documents belong to the institutions and are not committed. The
   transcriptions are, in `data/field/menus/text/`, so every number below
   can be traced back to the text it came from.
3. **Parsed.** The live parser (`solver/menutext.py`, the one behind the
   app's paste box) matched 1,053 written names to catalog dishes on its own.
4. **Settled.** The parser refuses to guess, so it left the rest. Every name
   it would not place was then settled in `data/field/settlements.json`,
   with a stated reason for each decision:
   - 86 ordered rules covered 558 distinct names. For example, "any dal the
     catalog doesn't have becomes dal tadka", and "meat and fish are not
     counted, because the study solves vegetarian and egg diets".
   - 149 more names were settled by hand. These were mostly cells where
     several dishes run together with no separator, such as "dal lauki chana
     seasonal veg plain rice phulka salad achar".

   71 fragments were page furniture (serving hours, prices, page numbers)
   and were dropped by pattern. At the end, no name was left unaccounted for.
   What every name became, and why, is listed in `data/field/settled.csv`.
5. **Solved.** For each menu and each day, the solver answered the app's two
   questions:
   - What is the best a vegetarian can do from the mess alone?
   - What is the cheapest way to close what is left?

   It did this for a man and for a woman, using ICMR-NIN 2020 targets for
   ages 19–30. Menus that serve eggs were also solved for an egg-eating diet;
   those results are in `data/field/results.json`.

## What the field taught the parser

Real menus broke the parser in five ways that the one menu it was built on
never did. All five are fixed, with tests, because every one of them would
have hit a real user:

- **Days down the side.** About half the menus list the days down the left
  and the meals across the top. The parser only knew the opposite layout. It
  read each of those menus as a single Monday.
- **Paid extras counted as mess food.** Menus print their extras (chicken,
  paneer tikka, eggs) in their own column, or after "Extra:" inside a cell.
  These are sold at the counter. Counting them made a menu that prints its
  price list look better fed than one that doesn't. Now they are left out,
  and the parser says so.
- **A fortnight read as a week.** A dated timetable ("15th Feb, Friday" …
  "28th Feb, Thursday") was not recognised as a grid of days at all.
- **Near matches that were wrong.** Some matches came from one dish name
  containing another. The parser accepted "curd rice" as plain rice, "milk
  cake" as a glass of milk, "dinner" as a dinner roll, "moong" as moong
  halwa, and "veg butter masala" as a pat of butter. Two changes fix this:
  - An alias now counts only as the exact spelling it records.
  - A short name has to contain the word the dish is named for. "Curd" still
    finds plain curd; "dinner" no longer finds a dinner roll.
- **Meat on a vegetarian plate.** "Sandwich" matched the only sandwich in
  the catalog, which is turkey. A near match can no longer add meat that the
  written name does not mention.

The regional names that turned up again and again are now aliases that ship
with the app, in `data/aliases.json`: chapati, phulka, chawal, appalam,
payasam and others.

## Results

<!-- generated by scripts/field_study.py report -->

### What the mess alone cannot reach

A vegetarian eating the best plate the menu allows, every day of the week, within the portion limits. Out of 14 menus:

| Nutrient | Women: short some day | Women: short every day | Men: short some day | Men: short every day |
| --- | --- | --- | --- | --- |
| Iron | 12 | 6 | 9 | 1 |
| Vitamin B12 | 9 | 2 | 10 | 3 |
| Calcium | 11 | 3 | 13 | 2 |
| Zinc | 14 | 4 | 14 | 14 |
| Potassium | 13 | 2 | 13 | 3 |
| Vitamin C | 4 | 0 | 8 | 1 |
| Vitamin A | 6 | 0 | 8 | 0 |
| Magnesium | 2 | 0 | 5 | 0 |
| Energy | 2 | 0 | 5 | 0 |
| Protein | 1 | 0 | 1 | 0 |
| Fibre | 1 | 0 | 1 | 0 |
| Folate | 0 | 0 | 1 | 0 |

### Menu by menu

Days of the week (out of 7) on which the best vegetarian plate from the mess is still short, for a woman; and what closing every gap costs a week at the catalog's market prices.

| Institution | Mess | Menu dated | Dishes | Iron | B12 | Calcium | Top-up a week (woman) | Top-up a week (man) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SNS College of Engineering, Coimbatore | Hostel mess | not stated | 32 | 7 | 6 | 7 | ₹559 | ₹621 |
| IIT Kanpur | Hall VIII mess | Dated 20/01/2025 | 46 | 6 | 6 | 6 | ₹387 | ₹375 |
| IIT Dharwad | Central mess (common) | not stated (PDF created 2026-09-10) | 33 | 7 | 1 | 6 | ₹334 | ₹251 |
| IIT Madras | CCW Veg Menu (weeks A-D, without non-veg extras) | not stated (signed 8/7) | 48 | 4 | 2 | 4 | ₹318 | ₹464 |
| Sant Longowal Institute of Engineering and Technology (SLIET) | Hostel mess (common) | not stated (uploaded 2025-02; PDF created 2025-01-02) | 39 | 7 | 2 | 7 | ₹297 | ₹319 |
| Tezpur University | KWH women's hostel mess | 15-28 Feb (year not stated) | 24 | 3 | 7 | 7 | ₹269 | ₹303 |
| GNIOT Institute of Professional Studies, Greater Noida | Hostel mess | not stated (PDF created 2025-09-01) | 52 | 7 | 5 | 5 | ₹267 | ₹222 |
| VNIT Nagpur | Aaswad mess (boys hostels) | Effective from 19 January 2026 | 54 | 7 | 7 | 6 | ₹223 | ₹184 |
| IIT Tirupati | Institute hostel mess (common menu) | New Mess Menu Apr 2024 | 46 | 7 | 0 | 5 | ₹142 | ₹100 |
| IIT Delhi | Jwalamukhi hostel mess | month 'September 26' (Sept 2026) | 64 | 4 | 2 | 3 | ₹109 | ₹121 |
| IIT Kanpur | Hall II mess | not stated | 49 | 1 | 0 | 0 | ₹64 | ₹70 |
| IISER Bhopal | Mess 3 & Mess 4 (Veg mess), Dining Hall 3 | 17/09/2026 | 52 | 0 | 0 | 0 | ₹48 | ₹68 |
| IIT Bombay | Hostel 3 mess | not stated | 53 | 0 | 0 | 2 | ₹43 | ₹87 |
| IIT Kanpur | Hall XI mess | 01-10-2024 | 47 | 1 | 0 | 0 | ₹36 | ₹68 |

Median top-up: ₹267 a week for a woman, ₹222 for a man. Range ₹36 to ₹559 (women) and ₹68 to ₹621 (men).

### What closes the gap

How many menus' cheapest weekly top-up (for either sex) includes each item.

| Item | Menus |
| --- | --- |
| Spinach, cooked | 14 |
| Guava | 14 |
| Milk | 11 |
| Carrot | 11 |
| Rajma, boiled | 6 |
| Soya chunks | 6 |
| Boiled chana | 6 |
| Roasted peanuts | 3 |
| Curd | 1 |
| Paneer | 1 |

### With and without the hand-settled names

The 13 menus the live parser alone gave a dish for every day, solved twice: with every settled name, and with only the parser's own matches. Menus short on a nutrient on every day of the week:

| Nutrient | Women, settled | Women, parser only | Men, settled | Men, parser only |
| --- | --- | --- | --- | --- |
| Iron | 6 | 13 | 1 | 6 |
| Vitamin B12 | 2 | 7 | 3 | 7 |
| Calcium | 3 | 9 | 2 | 10 |
| Zinc | 4 | 12 | 13 | 12 |
| Potassium | 1 | 5 | 2 | 3 |
| Vitamin C | 0 | 5 | 1 | 7 |
| Vitamin A | 0 | 3 | 0 | 3 |
| Energy | 0 | 0 | 0 | 2 |

<!-- end generated -->


## How to read this

- **"Short" means short even when eating the best the menu allows.** The
  solver picks the best possible plate each day, within each dish's serving
  cap and 1,400 g of food a day. A student eating what they like will do
  worse than that plate, never better. Every shortfall here is a lower bound
  on the real one.
- **The settled names make menus look better, not worse.** A stand-in only
  ever adds food to a day, so settling names can only shrink a shortfall.
  The last table shows how much the conclusions depend on the settling.
  No count goes down without the settling, and most go up a lot. The
  headline counts use the settled menus, which is the kinder reading.
- **The solve trades one gap against another.** It minimises the total
  fraction of targets left unmet, so a menu can come out short on B12 on one
  day and short on calcium on another, depending on which plate was best
  overall. The "some day" column is the robust one. The "every day" column
  is a statement about the whole week.
- **Zinc is partly the reference.** ICMR-NIN 2020 sets zinc at 17 mg a day
  for men. The US reference is 11 mg. Every menu misses the Indian figure on
  every day, and that says as much about the target as about the food. Read
  the zinc row with that in mind.
- **Iron differs by sex because the target does.** ICMR sets iron at 29 mg
  for women and 19 mg for men. That is why iron is the women's headline and
  B12 is the men's.

## What this does not show

- **A published menu is an intention.** It is not what was served, in what
  amount, or what was eaten. Serving sizes are the catalog's, because no
  mess publishes its ladle weights.
- **It is a convenience sample.** These are the menus that are online, which
  over-represents IITs. One institution has more than one menu here (IIT
  Kanpur, three halls). Twelve institutions do not make a claim about Indian
  hostels in general.
- **Stand-ins are approximations.** A dish the catalog does not have is
  counted as the nearest dish it does have: any dal as dal tadka, any
  vegetable sabzi as mix veg. `settled.csv` has every one of these, so each
  can be checked.
- **Prices are the catalog's.** The top-up cost uses the app's seeded market
  prices, not local ones. The app lets a user enter their own prices; the
  study does not.

## Reproducing it

```
uv run --with boto3 --with 'botocore[crt]' --with pillow \
    python scripts/field_study.py transcribe   # needs Bedrock; skips menus already read
uv run python scripts/field_study.py parse
uv run python scripts/field_study.py open      # names still unsettled: none
uv run python scripts/field_study.py run
uv run python scripts/field_study.py report    # rewrites the tables above
```

`transcribe` needs the raw documents. Their URLs are in `SOURCES.csv`. Every
step after it runs from the committed text, with no network and no model.
