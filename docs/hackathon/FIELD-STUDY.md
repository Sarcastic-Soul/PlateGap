# Field study: 27 published mess menus

One menu is an anecdote. PlateGap was built against the menu of the mess I
eat at, and that proves the solver works on one menu. It does not show that
the problem is common. So I took every hostel mess menu I could find on an
Indian college website, 27 menus from 22 institutions, and ran each one
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
   `data/field/menus/SOURCES.csv`. I tried 15 more that failed to download
   (removed files, bot walls, login pages, dead servers). I set aside 7
   documents that turned out not to be a hostel's menu: tender papers, a
   priced guest-house list, a school, a duplicate. One of those was a list of
   students' fee dues, which I deleted. All 22 are in
   `data/field/menus/FAILED.csv`.
2. **Transcribed.** 25 of the menus are PDFs or scans. The app's own reader,
   Amazon Nova Lite on Bedrock (`solver/menuscan.py`), copied them into text
   one page at a time. The other two, a JSON feed and an HTML table, were
   converted directly with no model involved. The raw documents belong to
   the institutions and are not committed. The transcriptions are, in
   `data/field/menus/text/`, so every number below can be traced back to the
   text it came from.
3. **Parsed.** The live parser (`solver/menutext.py`, the one behind the
   app's paste box) matched 2,577 written names to catalog dishes on its own.
4. **Settled.** The parser refuses to guess, so it left the rest. Every name
   it would not place was then settled in `data/field/settlements.json`,
   with a stated reason for each decision:
   - 86 ordered rules covered 895 distinct names. For example, "any dal the
     catalog doesn't have becomes dal tadka", and "meat and fish are not
     counted, because the study solves vegetarian and egg diets".
   - 349 more names were settled by hand. These were mostly cells where
     several dishes run together with no separator, such as "dal lauki chana
     seasonal veg plain rice phulka salad achar".

   158 fragments were page furniture (serving hours, prices, page numbers)
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

A vegetarian eating the best plate the menu allows, every day of the week, within the portion limits. Out of 27 menus:

| Nutrient | Women: short some day | Women: short every day | Men: short some day | Men: short every day |
| --- | --- | --- | --- | --- |
| Iron | 26 | 13 | 20 | 2 |
| Vitamin B12 | 21 | 9 | 24 | 13 |
| Calcium | 24 | 8 | 26 | 9 |
| Zinc | 27 | 13 | 27 | 27 |
| Potassium | 23 | 3 | 25 | 2 |
| Vitamin C | 8 | 0 | 19 | 0 |
| Vitamin A | 9 | 0 | 13 | 0 |
| Magnesium | 4 | 0 | 8 | 0 |
| Energy | 2 | 0 | 8 | 0 |
| Protein | 1 | 0 | 1 | 0 |
| Fibre | 1 | 0 | 1 | 0 |

### Menu by menu

Days of the week (out of 7) on which the best vegetarian plate from the mess is still short, for a woman; and what closing every gap costs a week at the catalog's market prices.

| Institution | Mess | Menu dated | Dishes | Iron | B12 | Calcium | Top-up a week (woman) | Top-up a week (man) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| IIT Kharagpur | All halls - Hall Management Centre revised menu | effective 23/01/2017 | 35 | 7 | 7 | 7 | ₹741 | ₹454 |
| SNS College of Engineering, Coimbatore | Hostel mess | not stated | 32 | 7 | 6 | 7 | ₹602 | ₹658 |
| Pondicherry University | Madame Curie Mess - PhD scholars | 2022-2023 | 29 | 7 | 7 | 7 | ₹493 | ₹441 |
| IIT Roorkee | Azad Bhawan mess | 15-11-2021 to 21-11-2021 | 47 | 4 | 4 | 6 | ₹454 | ₹537 |
| Chhatrapati Shahu Ji Maharaj University, Kanpur | University hostel mess | not stated (uploaded 2022-08) | 38 | 7 | 7 | 7 | ₹403 | ₹271 |
| IIT Kanpur | Hall VIII mess | Dated 20/01/2025 | 46 | 6 | 7 | 6 | ₹394 | ₹382 |
| Pondicherry University | Ilango Adigal Hostel Mess - PhD scholars | 2022-23 (signed 28/06/2022) | 36 | 7 | 5 | 6 | ₹329 | ₹189 |
| IIT Madras | CCW Veg Menu (weeks A-D, without non-veg extras) | not stated (signed 8/7) | 48 | 4 | 2 | 4 | ₹326 | ₹470 |
| Central University of Punjab | Student Cooperative Mess | W.E.F. 12/12/2016 | 35 | 7 | 7 | 7 | ₹324 | ₹202 |
| Sant Longowal Institute of Engineering and Technology (SLIET) | Hostel mess (common) | not stated (uploaded 2025-02; PDF created 2025-01-02) | 39 | 7 | 2 | 7 | ₹297 | ₹325 |
| NIT Manipur | Hostels - revised mess menu | not stated (PDF created 2015-02-27) | 42 | 4 | 7 | 7 | ₹289 | ₹353 |
| GNIOT Institute of Professional Studies, Greater Noida | Hostel mess | not stated (PDF created 2025-09-01) | 52 | 7 | 5 | 5 | ₹284 | ₹241 |
| Tezpur University | KWH women's hostel mess | 15-28 Feb (year not stated) | 24 | 3 | 7 | 7 | ₹270 | ₹303 |
| IIIT Lucknow | Institute mess | not stated (uploaded 2019-11; PDF created 2019-11-10) | 39 | 7 | 6 | 4 | ₹249 | ₹196 |
| VNIT Nagpur | Aaswad mess (boys hostels) | Effective from 19 January 2026 | 54 | 7 | 7 | 6 | ₹235 | ₹197 |
| IIT Bombay | Hostel 16 mess | 1/10/18 to 7/10/18 | 44 | 7 | 7 | 5 | ₹196 | ₹337 |
| MNIT Jaipur | Girls hostel mess - Menu B | not stated (uploaded 2022-12) | 58 | 4 | 1 | 2 | ₹188 | ₹350 |
| IIIT Delhi | Both messes (common menu) | w.e.f. 14 October 2019 | 53 | 4 | 2 | 1 | ₹182 | ₹157 |
| NIT Tiruchirappalli | Boys mess (Rs 61/day) | not stated (PDF created 2012-07-06) | 59 | 6 | 0 | 4 | ₹156 | ₹75 |
| IIT Tirupati | Institute hostel mess (common menu) | New Mess Menu Apr 2024 | 46 | 7 | 0 | 5 | ₹143 | ₹105 |
| MNIT Jaipur | Girls hostel mess - Menu A | not stated (uploaded 2022-12) | 62 | 4 | 1 | 1 | ₹141 | ₹293 |
| NIT Tiruchirappalli | All NITT messes - South Indian and North Indian tentative menus | not stated; marked TENTATIVE (PDF created 2015-07-12) | 56 | 7 | 0 | 4 | ₹137 | ₹72 |
| IIT Delhi | Jwalamukhi hostel mess | month 'September 26' (Sept 2026) | 64 | 4 | 2 | 3 | ₹110 | ₹126 |
| Nalanda University | University hostel mess | rotating weeks (1st&3rd / 2nd&4th); not dated (uploaded 2019-07; PDF created 2016-07-02) | 60 | 3 | 1 | 1 | ₹82 | ₹81 |
| IIT Kanpur | Hall II mess | not stated | 49 | 1 | 0 | 0 | ₹66 | ₹76 |
| IISER Bhopal | Mess 3 & Mess 4 (Veg mess), Dining Hall 3 | 17/09/2026 | 52 | 0 | 0 | 0 | ₹51 | ₹73 |
| IIT Kanpur | Hall XI mess | 01-10-2024 | 47 | 1 | 0 | 0 | ₹38 | ₹74 |

Median top-up: ₹249 a week for a woman, ₹241 for a man. Range ₹38 to ₹741 (women) and ₹72 to ₹658 (men).

### What closes the gap

How many menus' cheapest weekly top-up (for either sex) includes each item.

| Item | Menus |
| --- | --- |
| Spinach, cooked | 27 |
| Guava | 27 |
| Milk | 25 |
| Carrot | 20 |
| Soya chunks | 17 |
| Rajma, boiled | 15 |
| Boiled chana | 14 |
| Paneer | 6 |
| Curd | 5 |
| Roasted peanuts | 5 |

### With and without the hand-settled names

The 22 menus the live parser alone gave a dish for every day, solved twice: with every settled name, and with only the parser's own matches. Menus short on a nutrient on every day of the week:

| Nutrient | Women, settled | Women, parser only | Men, settled | Men, parser only |
| --- | --- | --- | --- | --- |
| Iron | 10 | 21 | 2 | 9 |
| Vitamin B12 | 8 | 13 | 10 | 15 |
| Calcium | 7 | 16 | 7 | 15 |
| Zinc | 9 | 19 | 22 | 22 |
| Potassium | 2 | 5 | 1 | 3 |
| Vitamin C | 0 | 8 | 0 | 13 |
| Vitamin A | 0 | 4 | 0 | 4 |
| Energy | 0 | 0 | 0 | 3 |

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
- **Many menus are old.** Only a few are current (IISER Bhopal, IIT Delhi,
  VNIT Nagpur). The "Menu dated" column says what each one claims. Several
  are from 2016–2019. The study is about what messes plan, and old plans are
  still plans, but I would not call any single row a description of that mess
  today.
- **It is a convenience sample.** These are the menus that are online, which
  over-represents IITs and NITs. Four institutions have more than one menu
  here (IIT Kanpur, MNIT Jaipur, Pondicherry University, NIT Trichy). Twenty-
  two institutions do not make a claim about Indian hostels in general.
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
