"""Build `data/foods.json` from USDA FoodData Central SR Legacy.

Run:
    uv run python data/build_catalog.py --sr path/to/FoodData_Central_sr_legacy_food_csv_2018-04

SR Legacy is public domain. Download it once from
https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip
and unzip; the CSVs are not committed because they are ~36 MB.

Two kinds of row come out the other end.

*Ingredients* are a direct lift of one SR Legacy food, cited by its fdcId, so
anyone can check a number against the source database.

*Dishes* are what a mess actually serves, and they are **decomposed into
ingredients** rather than guessed at dish level. `dal tadka` is lentils plus oil
plus onion and tomato in stated grams, and its nutrition is computed from those.
This is the honest way to do it: the recipe is an assumption, but it is an
assumption written down in one place where anyone can disagree with a specific
number instead of with a black box.

Each recipe line also says how that ingredient is *prepared*, because a raw
cauliflower and a boiled one are not the same food. The USDA retention factors
for that preparation are applied before the ingredient is added in, so a menu
is not credited with vitamin C the kitchen boiled away.

Where SR Legacy simply has no equivalent -- paneer being the obvious one -- the
row is marked `"proxy": true` with a note naming where the number came from
instead. Those rows are flagged in the UI rather than quietly presented as
fact, and the note says which individual nutrients are still estimates.

`docs/DATA.md` prints all of this back out, dish by dish. It is generated from
the catalog by `scripts/gen_data_doc.py` and a test fails if it drifts.
"""

import argparse
import csv
import json
import os
import sys

# --------------------------------------------------------------------------
# Nutrients we track, by SR Legacy nutrient id.
# --------------------------------------------------------------------------

NUTRIENTS = [
    ("kcal",      1008, "Energy",              "kcal"),
    ("protein",   1003, "Protein",             "g"),
    ("fat",       1004, "Total fat",           "g"),
    ("satfat",    1258, "Saturated fat",       "g"),
    ("carbs",     1005, "Carbohydrate",        "g"),
    ("fibre",     1079, "Fibre",               "g"),
    ("calcium",   1087, "Calcium",             "mg"),
    ("iron",      1089, "Iron",                "mg"),
    ("magnesium", 1090, "Magnesium",           "mg"),
    ("potassium", 1092, "Potassium",           "mg"),
    ("sodium",    1093, "Sodium",              "mg"),
    ("zinc",      1095, "Zinc",                "mg"),
    ("vita",      1106, "Vitamin A",           "ug"),
    ("vitc",      1162, "Vitamin C",           "mg"),
    ("vitb12",    1178, "Vitamin B12",         "ug"),
    ("folate",    1190, "Folate",              "ug"),
]

NUTRIENT_IDS = {key: fdc_id for key, fdc_id, _, _ in NUTRIENTS}

# --------------------------------------------------------------------------
# Cook loss.
#
# A raw cauliflower and a boiled one are not the same food. Vitamin C, folate
# and the B vitamins are destroyed by heat and leached into water that gets
# poured away, and a catalog that treats the raw figure as the cooked one
# overstates exactly the nutrients this product is most likely to report as
# short. That error runs in our favour, which is the worst direction for it to
# run in.
#
# Every factor below is read out of the *USDA Table of Nutrient Retention
# Factors, Release 6* (Agricultural Research Service, Nutrient Data
# Laboratory, December 2007), by its retention code:
#
#   https://www.ars.usda.gov/ARSUserFiles/80400525/Data/retn/retn06.pdf
#   https://www.ars.usda.gov/ARSUserFiles/80400525/Data/retn/retn06.txt
#
# The codes are the same ones SR Legacy ships in `retention_factor.csv`, so a
# reader with the download already has the lookup table. USDA reports to the
# nearest 5 percent and caps at 100.
#
# Two things about how they are applied here.
#
# *The yield factor does not appear, on purpose.* USDA defines retention as
# (Nc x Gc) / (Nr x Gr): nutrient per gram of cooked food times grams of
# cooked food, over the same for raw. Recipes here state raw grams going into
# the pot, so the mass of nutrient on the plate is just Nr x Gr x factor and
# the cooked weight cancels out. The familiar "divide by the yield" step is
# only needed to get back to a per-100 g-cooked figure, which nothing here
# wants. Skipping it by accident is the classic way to overstate a boiled dal
# by a factor of two and a half.
#
# *Release 6 does not cover macronutrients.* It carries 8 minerals, 16
# vitamins and alcohol -- no energy, protein, fat, carbohydrate or fibre. Those
# are left at 1.0 because there is no source for anything else, not because
# cooking leaves them untouched.
#
# Vitamin A maps to USDA nutrient 392 (retinol equivalents) while the catalog
# carries 1106 (retinol activity equivalents). Release 6 predates RAE, but it
# gives every vitamin A and carotenoid component the same factor within a
# code, so the distinction does not reach the arithmetic.
# --------------------------------------------------------------------------

RETENTION = {
    "raw": {
        "name": "raw",
        "usdaCode": None,
        "usdaDescription": "",
        "why": ("Eaten uncooked -- salad onion, a banana, coconut in a fresh "
                "chutney. Nothing has been heated, so nothing has been lost."),
        "factors": {},
    },
    "as_sourced": {
        "name": "already cooked in the source row",
        "usdaCode": None,
        "usdaDescription": "",
        "why": ("The USDA row this ingredient cites is already the cooked "
                "food -- `Rice, white, cooked`, `Lentils, boiled`, `Chicken, "
                "roasted`. The cook loss is in the number we started from, and "
                "applying a factor on top would subtract it twice and invent a "
                "shortfall. Also used for shelf-stable things that are never "
                "heated at all, like sugar and pickle."),
        "factors": {},
    },
    "fat_heated": {
        "name": "fat heated in a pan",
        "usdaCode": None,
        "usdaDescription": "",
        "why": ("Release 6 has no fats-and-oils group at all, so there is no "
                "factor to apply. It happens not to matter: the only things "
                "oil, ghee and butter contribute to this catalog in quantity "
                "are energy and fat, which Release 6 does not cover either. "
                "1.0 here means unsourced, not measured."),
        "factors": {},
    },

    # ---- Flours. Roti and paratha are griddle-cooked, which is nearest to
    # ---- baked; upma and noodle dough are boiled.
    "flour_baked": {
        "name": "flour, baked or griddled",
        "usdaCode": "301",
        "usdaDescription": "FLOUR/MEAL, BAKED",
        "why": ("A roti on a tawa is dry heat on a thin dough, which is what "
                "the baked code describes. Release 6 has no griddle code."),
        # code 301 -- FLOUR/MEAL,BAKED
        "factors": {"vita": 0.90, "vitc": 0.80, "folate": 0.70},
    },
    "flour_boiled": {
        "name": "flour or semolina, boiled",
        "usdaCode": "302",
        "usdaDescription": "FLOUR/MEAL, BOILED, STEAMED",
        "why": "Semolina cooked into upma or a noodle dough, water retained.",
        # code 302 -- FLOUR/MEAL,BOILED,STEAMED
        "factors": {"vita": 0.90, "vitc": 0.80, "folate": 0.70},
    },
    "flour_fried": {
        "name": "flour, deep fried",
        "usdaCode": "305",
        "usdaDescription": "FLOUR/MEAL, SAUTEED",
        "why": ("Release 6 has no deep-fry code for flour, and poori, samosa, "
                "pakoda and boondi are all deep fried. Sauteed is the nearest "
                "code and is the most generous of the flour codes' neighbours, "
                "so this one is an approximation rather than a measurement and "
                "probably understates the loss."),
        # code 305 -- FLOUR/MEAL,SAUTEED
        "factors": {"vita": 0.85, "vitc": 0.80, "folate": 0.65},
    },

    # ---- Vegetables. Which code applies turns on whether the cooking water
    # ---- ends up on the plate, which in a gravy it does.
    "veg_sauteed": {
        "name": "vegetable, sauteed",
        "usdaCode": "3785",
        "usdaDescription": "VEG, OTHER, STIR FRY",
        "why": ("Onion, cabbage and cauliflower turned in hot oil. Release 6 "
                "has no sauteed code for non-root vegetables; stir fry is the "
                "same treatment under a different name."),
        # code 3785 -- VEG,OTHER,STIR FRY
        "factors": {"vita": 0.90, "vitc": 0.85, "folate": 0.80},
    },
    "veg_fried": {
        "name": "vegetable, fried",
        "usdaCode": "3780",
        "usdaDescription": "VEG, OTHER, FRIED",
        "why": ("Harder frying than a saute -- bhindi taken to crisp, onion "
                "browned for biryani, pakoda. Costs more folate than stir "
                "frying does."),
        # code 3780 -- VEG,OTHER,FRIED
        "factors": {"vita": 0.85, "vitc": 0.85, "folate": 0.70},
    },
    "veg_boiled_in_dish": {
        "name": "vegetable, boiled into the dish",
        "usdaCode": "3776",
        "usdaDescription": "VEG, OTHER, BLD, WATER USED",
        "why": ("Peas and cauliflower simmered in a gravy that is then eaten. "
                "What leaches out stays in the bowl, which is why the minerals "
                "hold at 100 percent here and drop when the water is poured "
                "away."),
        # code 3776 -- VEG,OTHER,BLD,WATER USED
        "factors": {"vita": 0.95, "vitc": 0.85, "folate": 0.85},
    },
    "veg_boiled_drained": {
        "name": "vegetable, boiled and drained",
        "usdaCode": "3775",
        "usdaDescription": "VEG, OTHER, BLD, WATER COVER, DRAINED",
        "why": ("Boiled in plenty of water and strained, so the minerals go "
                "down the sink with it. The worst case for a vegetable and "
                "the reason the drained-or-not distinction is worth carrying."),
        # code 3775 -- VEG,OTHER,BLD,WATER COVER,DRAINED
        "factors": {"calcium": 0.95, "iron": 0.95, "magnesium": 0.95,
                    "potassium": 0.90, "sodium": 0.95, "zinc": 0.95,
                    "vita": 0.90, "vitc": 0.75, "folate": 0.65},
    },
    "root_sauteed": {
        "name": "root vegetable, sauteed",
        "usdaCode": "3460",
        "usdaDescription": "VEG, ROOTS, ETC, SAUTEED",
        "why": "Carrot turned in oil, as in upma or a dry kolhapuri.",
        # code 3460 -- VEG,ROOTS,ETC,SAUTEED
        "factors": {"vita": 0.85, "vitc": 0.75, "folate": 0.70},
    },
    "root_boiled_in_dish": {
        "name": "root vegetable, boiled into the dish",
        "usdaCode": "3456",
        "usdaDescription": "VEG, ROOTS, ETC, BOILED, WATER USED",
        "why": "Carrot simmered in sambhar or a mixed sabzi, water retained.",
        # code 3456 -- VEG,ROOTS,ETC,BOILED,WATER USED
        "factors": {"vita": 0.90, "vitc": 0.75, "folate": 0.80},
    },
    "tomato_boiled": {
        "name": "tomato, simmered",
        "usdaCode": "3751",
        "usdaDescription": "TOMATOES, BOILED/BAKED",
        "why": ("Tomato has its own codes because it holds vitamin C far "
                "better than other vegetables -- 95 percent against 85 -- and "
                "it is in nearly every gravy on this menu."),
        # code 3751 -- TOMATOES,BOILED/BAKED
        "factors": {"vita": 0.95, "vitc": 0.95, "folate": 0.70},
    },
    "tomato_fried": {
        "name": "tomato, fried",
        "usdaCode": "3752",
        "usdaDescription": "TOMATOES, FRIED/BROILED",
        "why": "Tomato cooked down hard in oil, as in a bhuna masala.",
        # code 3752 -- TOMATOES,FRIED/BROILED
        "factors": {"vita": 0.90, "vitc": 0.95, "folate": 0.70},
    },

    # ---- Pulses, dairy and cheese
    "legume_boiled_drained": {
        "name": "sprouted pulse, boiled and drained",
        "usdaCode": "501",
        "usdaDescription": "LEGUMES, CKD 15/20MIN, BOILED, DRAINED",
        "why": ("Sprouts boiled briefly and strained. The shortest legume code "
                "Release 6 offers is still 15 to 20 minutes, longer than "
                "sprouts need, so this probably overstates the loss. Every "
                "other pulse in the catalog cites an SR row that is already "
                "boiled and so takes no factor at all."),
        # code 501 -- LEGUMES,CKD 15/20MIN,BOILED,DRAINED
        "factors": {"calcium": 0.85, "iron": 0.85, "magnesium": 0.80,
                    "potassium": 0.75, "sodium": 0.90, "zinc": 0.85,
                    "vita": 0.85, "vitc": 0.65, "folate": 0.60},
    },
    "milk_heated_short": {
        "name": "milk, heated briefly",
        "usdaCode": "2151",
        "usdaDescription": "MILK, HEATED APPROX 10MIN",
        "why": ("Mess milk is boiled before it is served and milk stirred into "
                "a gravy is heated through. Release 6 indexes milk only by how "
                "long it is held hot, so a duration has to be chosen; ten "
                "minutes is the shortest it offers and the least it can be."),
        # code 2151 -- MILK,HEATED APPROX 10MIN
        "factors": {"vitc": 0.85, "vitb12": 0.80, "folate": 0.85},
    },
    "milk_heated_long": {
        "name": "milk, simmered down",
        "usdaCode": "2152",
        "usdaDescription": "MILK, HEATED APPROX 30MIN",
        "why": ("Kheer and the khoya in a gulab jamun are milk reduced over "
                "half an hour or more. B12 is the casualty: 55 percent here "
                "against 80 for a brief heat."),
        # code 2152 -- MILK,HEATED APPROX 30MIN
        "factors": {"vitc": 0.65, "vitb12": 0.55, "folate": 0.80},
    },
    "cheese_in_liquid": {
        "name": "cheese, simmered in a gravy",
        "usdaCode": "5",
        "usdaDescription": "CHEESE, COOKED W/LIQUID",
        "why": "Paneer cubes dropped into a gravy, or cheddar melted into a sauce.",
        # code 5 -- CHEESE,COOKED W/LIQUID
        "factors": {"vitc": 0.65, "vitb12": 0.55, "folate": 0.80},
    },
    "cheese_baked": {
        "name": "cheese, baked or pan cooked",
        "usdaCode": "1",
        "usdaDescription": "CHEESE, BAKED",
        "why": ("Paneer scrambled in a pan or fried into a kofta, and "
                "mozzarella on a pizza. Release 6 gives the baked, broiled and "
                "cooked-with-liquid cheese codes identical factors, so the "
                "choice between them changes nothing arithmetically and is "
                "made for the record rather than the number."),
        # code 1 -- CHEESE,BAKED
        "factors": {"vitc": 0.65, "vitb12": 0.55, "folate": 0.80},
    },
}

# --------------------------------------------------------------------------
# Ingredients: one SR Legacy food each, values per 100 g.
# (our id, fdcId, display name, tags, proxy note or None)
# --------------------------------------------------------------------------

INGREDIENTS = [
    # Grains and flours
    ("rice_cooked",    169757, "Cooked white rice",      ["veg", "grain"], None),
    ("atta",           168893, "Whole wheat flour",      ["veg", "grain"], None),
    ("semolina",       169715, "Semolina (rava)",        ["veg", "grain"], None),
    ("bread_white",    172818, "White bread",            ["veg", "grain"], None),
    ("besan",          174288, "Gram flour (besan)",     ["veg", "pulse"], None),

    # Pulses, cooked without salt
    ("toor_dal",       172437, "Pigeon pea (toor/arhar)", ["veg", "pulse"], None),
    ("moong_dal",      174257, "Mung bean (moong)",      ["veg", "pulse"], None),
    ("masoor_dal",     172421, "Red lentil (masoor)",    ["veg", "pulse"], None),
    ("chana",          173757, "Chickpea (chana)",       ["veg", "pulse"], None),
    ("rajma",          175194, "Kidney bean (rajma)",    ["veg", "pulse"], None),
    ("soybean",        174299, "Soybean",                ["veg", "pulse"], None),
    ("sprouts",        169957, "Sprouted mung beans",    ["veg", "pulse"], None),

    # Vegetables
    ("potato",         170440, "Boiled potato",          ["veg", "vegetable"], None),
    ("onion",          170000, "Onion",                  ["veg", "vegetable"], None),
    ("tomato",         170457, "Tomato",                 ["veg", "vegetable"], None),
    ("spinach",        168463, "Cooked spinach",         ["veg", "vegetable"], None),
    ("cabbage",        169975, "Cabbage",                ["veg", "vegetable"], None),
    ("cauliflower",    169986, "Cauliflower",            ["veg", "vegetable"], None),
    ("okra",           169260, "Okra (bhindi)",          ["veg", "vegetable"], None),
    ("peas",           170419, "Green peas",             ["veg", "vegetable"], None),
    ("carrot",         170393, "Carrot",                 ["veg", "vegetable"], None),

    # Dairy and fats
    ("milk",           171265, "Whole milk",             ["veg", "dairy"], None),
    ("curd",           171284, "Curd (plain yoghurt)",   ["veg", "dairy"], None),
    ("butter",         173410, "Butter",                 ["veg", "dairy"], None),
    ("ghee",           173412, "Ghee",                   ["veg", "dairy"], None),

    # Animal protein
    ("egg_boiled",     173424, "Boiled egg",             ["egg", "protein"], None),
    ("chicken",        171477, "Cooked chicken breast",  ["meat", "protein"], None),

    # Fats, sugars, nuts, fruit
    ("oil",            171411, "Cooking oil (soybean)",  ["veg", "fat"], None),
    ("sugar",          169655, "Sugar",                  ["veg", "sugar"], None),
    ("peanut",         173806, "Roasted peanuts",        ["veg", "nut"], None),
    ("coconut",        170169, "Fresh coconut",          ["veg", "nut"], None),
    ("banana",         173944, "Banana",                 ["veg", "fruit"], None),
    ("orange",         169097, "Orange",                 ["veg", "fruit"], None),
    ("guava",          173044, "Guava",                  ["veg", "fruit"], None),
    ("papaya",         169926, "Papaya",                 ["veg", "fruit"], None),
    ("apple",          171688, "Apple",                  ["veg", "fruit"], None),
    ("dates",          168191, "Dates",                  ["veg", "fruit"], None),
    # ---- North American dining hall. Same pipeline, same citations: this
    # ---- project is not about one campus, and a menu the judges recognise
    # ---- has to be buildable from the same traceable base.
    ("beef_patty", 174031, "Ground beef patty, 90/10", ["meat"], None),
    ("burger_bun", 172796, "Hamburger bun", ["veg", "grain"], None),
    ("cheddar", 173414, "Cheddar cheese", ["veg", "dairy"], None),
    ("mozzarella", 170847, "Mozzarella, part skim", ["veg", "dairy"], None),
    ("american_cheese", 171290, "American cheese", ["veg", "dairy"], None),
    ("pasta_cooked", 169728, "Pasta, cooked", ["veg", "grain"], None),
    ("marinara", 171192, "Marinara sauce", ["veg"], None),
    ("chicken_breast", 171075, "Chicken breast, roasted", ["meat"], None),
    ("salmon", 175168, "Salmon, farmed, cooked", ["meat", "fish"], None),
    ("turkey_deli", 174572, "Turkey breast, deli", ["meat"], None),
    ("bacon", 167914, "Bacon, baked", ["meat"], None),
    ("egg_scrambled", 172187, "Scrambled egg", ["egg"], None),
    ("romaine", 169247, "Romaine lettuce", ["veg"], None),
    ("cucumber", 168409, "Cucumber", ["veg"], None),
    ("bell_pepper", 170108, "Red bell pepper", ["veg"], None),
    ("broccoli", 168510, "Broccoli, boiled", ["veg"], None),
    ("mushroom", 169251, "White mushrooms", ["veg"], None),
    ("sweetcorn", 168525, "Sweetcorn, boiled", ["veg"], None),
    ("fries", 170118, "French fries, oven-heated", ["veg"], None),
    ("oats_cooked", 173905, "Oatmeal, cooked", ["veg", "grain"], None),
    ("corn_flakes", 174648, "Corn flakes", ["veg", "grain"], None),
    ("bagel", 174899, "Bagel", ["veg", "grain"], None),
    ("pancake", 172771, "Pancakes", ["veg", "grain"], None),
    ("bread_wheat", 172688, "Whole-wheat bread", ["veg", "grain"], None),
    ("flour_white", 168894, "White flour", ["veg", "grain"], None),
    ("yogurt_lowfat", 170886, "Yogurt, plain low fat", ["veg", "dairy"], None),
    ("milk_2pct", 171267, "Milk, 2%", ["veg", "dairy"], None),
    ("black_beans", 173735, "Black beans, boiled", ["veg"], None),
    ("chickpeas_canned", 173801, "Chickpeas, canned", ["veg"], None),
    ("tofu", 172448, "Tofu, firm", ["veg"], None),
    ("almonds", 170568, "Almonds, blanched", ["veg"], None),
    ("olive_oil", 171413, "Olive oil", ["veg"], None),
    ("ranch_dressing", 173592, "Ranch dressing", ["veg"], None),
    ("orange_juice", 169098, "Orange juice", ["veg", "fruit"], None),
    ("tomato_soup", 171176, "Tomato soup", ["veg"], None),
    ("brownie_mix", 172713, "Brownie", ["veg", "sweet"], None),
]


# --------------------------------------------------------------------------
# How a serving was arrived at.
#
# `servingGrams` is the single most arguable number in the catalog and until
# now it was a bare integer with nothing attached. Each dish names one of
# these, so a reader can tell a counted object from a ladle estimate without
# having to guess which kind of number they are looking at. None of them are
# weighed; saying which kind of guess it is at least tells you how much to
# trust it.
# --------------------------------------------------------------------------

SERVING_SOURCES = {
    "counted": (
        "A counted object -- one roti, one egg, two gulab jamun -- taken at a "
        "typical size for that object. The count is real; the grams per piece "
        "are an estimate."),
    "ladle": (
        "One service-counter ladle of a cooked dish, sized to the standard "
        "katoris in ICMR-NIN's Dietary Guidelines for Indians (2024), Annexure "
        "I: a 155 ml small katori for dal, curry, sabzi and rice, a 115 ml one "
        "for curd, raita and sprouts, a 200 ml medium one for biryani. The "
        "grams are that volume at the dish's likely density, not weighed."),
    "plate": (
        "One plated portion of a dry or composed dish, as handed over at the "
        "counter. Estimated, not weighed."),
    "bowl": (
        "One bowl, as served. Estimated from the usual bowl in a dining hall, "
        "not weighed."),
    "cup": (
        "One cup or tumbler, as served. Estimated, not weighed."),
    "glass": (
        "One glass, taken at its stated volume and converted at roughly the "
        "density of milk or juice."),
    "packet": (
        "One sealed retail packet, at its labelled weight."),
    "spoon": (
        "One spoonful of a condiment. Estimated, not weighed, and small enough "
        "that the error barely moves a day's totals."),
}


# --------------------------------------------------------------------------
# Dishes: what the mess actually puts on the plate.
#
# `recipe` maps each ingredient to `(grams, preparation)` for ONE serving.
# The preparation names an entry in RETENTION below, which is how much of each
# nutrient survives that treatment. `serving` is the gram weight of that
# serving as eaten, used only for display, and `serving source` says what kind
# of estimate that gram figure is. `cap` is how many servings a student can
# realistically get -- staples are effectively unlimited in a self-serve hostel
# mess, while paneer, chicken and sweets are rationed to what is ladled out.
#
# Every number here is an assumption. That is the point of writing them down.
# --------------------------------------------------------------------------

DISHES = [
    # ---- Staples. Unlimited in practice, so a generous cap.
    ("roti", "Roti", {"atta": (30, "flour_baked"), "oil": (1, "fat_heated")},
     35, 6, ["veg", "staple"], "counted"),
    ("plain_rice", "Plain rice", {"rice_cooked": (150, "as_sourced")},
     150, 4, ["veg", "staple"], "ladle"),
    ("jeera_rice", "Jeera rice",
     {"rice_cooked": (150, "as_sourced"), "oil": (4, "fat_heated")},
     155, 4, ["veg", "staple"], "ladle"),
    ("onion_rice", "Onion rice",
     {"rice_cooked": (150, "as_sourced"), "onion": (25, "veg_sauteed"),
      "oil": (4, "fat_heated")}, 175, 4, ["veg", "staple"], "ladle"),
    ("peas_pulao", "Peas pulao",
     {"rice_cooked": (150, "as_sourced"), "peas": (30, "veg_boiled_in_dish"),
      "oil": (5, "fat_heated")}, 180, 3, ["veg", "staple"], "ladle"),
    ("poori", "Poori", {"atta": (25, "flour_fried"), "oil": (6, "fat_heated")},
     32, 4, ["veg", "staple"], "counted"),
    ("bread_slice", "Bread slice", {"bread_white": (25, "as_sourced")},
     25, 4, ["veg", "staple"], "counted"),

    # ---- Dals. Also effectively unlimited.
    ("toor_dal_tadka", "Arhar dal tadka",
     {"toor_dal": (130, "as_sourced"), "oil": (5, "fat_heated"),
      "onion": (15, "veg_sauteed"), "tomato": (15, "tomato_boiled")},
     165, 4, ["veg", "dal"], "ladle"),
    ("dal_tadka", "Dal tadka",
     {"masoor_dal": (130, "as_sourced"), "oil": (5, "fat_heated"),
      "onion": (15, "veg_sauteed"), "tomato": (15, "tomato_boiled")},
     165, 4, ["veg", "dal"], "ladle"),
    ("dal_mix", "Mix dal",
     {"toor_dal": (70, "as_sourced"), "moong_dal": (60, "as_sourced"),
      "oil": (5, "fat_heated"), "tomato": (15, "tomato_boiled")},
     150, 4, ["veg", "dal"], "ladle"),
    ("masoor_dal_dish", "Khada masoor dal",
     {"masoor_dal": (140, "as_sourced"), "oil": (5, "fat_heated"),
      "onion": (15, "veg_sauteed")}, 160, 4, ["veg", "dal"], "ladle"),
    ("dal_makhani", "Dal makhani",
     {"rajma": (60, "as_sourced"), "masoor_dal": (70, "as_sourced"),
      "butter": (8, "fat_heated"), "milk": (20, "milk_heated_short"),
      "tomato": (20, "tomato_boiled")}, 175, 3, ["veg", "dal"], "ladle"),
    ("sambhar", "Sambhar",
     {"toor_dal": (70, "as_sourced"), "carrot": (20, "root_boiled_in_dish"),
      "okra": (15, "veg_boiled_in_dish"), "onion": (15, "veg_boiled_in_dish"),
      "oil": (4, "fat_heated"), "tomato": (15, "tomato_boiled")},
     140, 4, ["veg", "dal"], "ladle"),
    ("rasam", "Rasam",
     {"toor_dal": (25, "as_sourced"), "tomato": (40, "tomato_boiled"),
      "oil": (3, "fat_heated")}, 150, 3, ["veg", "dal"], "ladle"),

    # ---- Pulse-based mains
    ("chole", "Chole",
     {"chana": (130, "as_sourced"), "onion": (25, "veg_sauteed"),
      "tomato": (25, "tomato_boiled"), "oil": (7, "fat_heated")},
     185, 2, ["veg", "main"], "ladle"),
    ("chole_curry", "Chole curry",
     {"chana": (120, "as_sourced"), "onion": (25, "veg_sauteed"),
      "tomato": (30, "tomato_boiled"), "oil": (7, "fat_heated")},
     185, 2, ["veg", "main"], "ladle"),
    ("rajma_dish", "Rajma",
     {"rajma": (130, "as_sourced"), "onion": (25, "veg_sauteed"),
      "tomato": (25, "tomato_boiled"), "oil": (7, "fat_heated")},
     185, 2, ["veg", "main"], "ladle"),
    ("black_chana_aloo", "Black chana aloo",
     {"chana": (90, "as_sourced"), "potato": (60, "as_sourced"),
      "onion": (20, "veg_sauteed"), "oil": (6, "fat_heated")},
     175, 2, ["veg", "main"], "ladle"),
    ("matar_chola", "Matar chola",
     {"chana": (100, "as_sourced"), "peas": (30, "veg_boiled_in_dish"),
      "onion": (20, "veg_sauteed"), "oil": (6, "fat_heated")},
     155, 2, ["veg", "main"], "ladle"),
    ("soya_badi", "Soya badi",
     {"soybean": (80, "as_sourced"), "onion": (20, "veg_sauteed"),
      "tomato": (20, "tomato_boiled"), "oil": (6, "fat_heated")},
     125, 2, ["veg", "main"], "ladle"),
    ("soya_chilli", "Soya chilli",
     {"soybean": (80, "as_sourced"), "onion": (30, "veg_sauteed"),
      "oil": (7, "fat_heated")}, 120, 2, ["veg", "main"], "ladle"),
    ("mangodi", "Mangodi",
     {"moong_dal": (70, "as_sourced"), "oil": (6, "fat_heated"),
      "onion": (15, "veg_sauteed")}, 95, 2, ["veg", "main"], "ladle"),

    # ---- Vegetable sabzis
    ("aloo_jeera", "Aloo jeera",
     {"potato": (120, "as_sourced"), "oil": (6, "fat_heated")},
     125, 2, ["veg", "sabzi"], "ladle"),
    ("aloo_tomato", "Aloo tomato",
     {"potato": (100, "as_sourced"), "tomato": (40, "tomato_boiled"),
      "oil": (6, "fat_heated")}, 145, 2, ["veg", "sabzi"], "ladle"),
    ("aloo_choka", "Aloo choka",
     {"potato": (110, "as_sourced"), "onion": (20, "raw"),
      "oil": (4, "fat_heated")}, 135, 2, ["veg", "sabzi"], "ladle"),
    ("aloo_bhujiya", "Aloo bhujiya",
     {"potato": (110, "as_sourced"), "oil": (7, "fat_heated")},
     120, 2, ["veg", "sabzi"], "ladle"),
    ("dum_aloo", "Dum aloo",
     {"potato": (110, "as_sourced"), "curd": (25, "as_sourced"),
      "tomato": (20, "tomato_boiled"), "oil": (8, "fat_heated")},
     155, 2, ["veg", "sabzi"], "ladle"),
    ("mix_veg", "Mix veg",
     {"potato": (40, "as_sourced"), "carrot": (30, "root_boiled_in_dish"),
      "peas": (25, "veg_boiled_in_dish"), "cauliflower": (30, "veg_boiled_in_dish"),
      "oil": (6, "fat_heated")}, 130, 2, ["veg", "sabzi"], "ladle"),
    ("veg_kolhapuri", "Veg kolhapuri",
     {"cauliflower": (35, "veg_sauteed"), "carrot": (25, "root_sauteed"),
      "peas": (25, "veg_boiled_in_dish"), "potato": (30, "as_sourced"),
      "oil": (8, "fat_heated")}, 130, 2, ["veg", "sabzi"], "ladle"),
    ("gobhi_dry", "Gobhi dry",
     {"cauliflower": (110, "veg_fried"), "oil": (6, "fat_heated")},
     115, 2, ["veg", "sabzi"], "ladle"),
    ("kurmuri_bhindi", "Kurmuri bhindi",
     {"okra": (100, "veg_fried"), "besan": (10, "flour_fried"),
      "oil": (9, "fat_heated")}, 110, 2, ["veg", "sabzi"], "ladle"),
    ("kadu_masala", "Kadu masala",
     {"cabbage": (100, "veg_sauteed"), "onion": (20, "veg_sauteed"),
      "oil": (6, "fat_heated")}, 120, 2, ["veg", "sabzi"], "ladle"),
    ("pyaj_muter_malai", "Pyaj mutter malai",
     {"peas": (50, "veg_boiled_in_dish"), "onion": (40, "veg_sauteed"),
      "milk": (25, "milk_heated_short"), "oil": (6, "fat_heated")},
     125, 2, ["veg", "sabzi"], "ladle"),
    ("kadai_masala", "Kadai masala",
     {"cauliflower": (40, "veg_sauteed"), "onion": (30, "veg_sauteed"),
      "tomato": (30, "tomato_fried"), "oil": (7, "fat_heated")},
     110, 2, ["veg", "sabzi"], "ladle"),

    # ---- Paneer. Rationed.
    ("paneer_butter_masala", "Paneer butter masala",
     {"paneer": (60, "cheese_in_liquid"), "butter": (8, "fat_heated"),
      "tomato": (35, "tomato_boiled"), "milk": (20, "milk_heated_short"),
      "oil": (4, "fat_heated")}, 130, 1, ["veg", "main"], "ladle"),
    ("paneer_bhurji", "Paneer bhurji",
     {"paneer": (65, "cheese_baked"), "onion": (25, "veg_sauteed"),
      "tomato": (20, "tomato_fried"), "oil": (6, "fat_heated")},
     115, 1, ["veg", "main"], "ladle"),
    ("malai_kofta", "Malai kofta",
     {"paneer": (45, "cheese_baked"), "potato": (40, "as_sourced"),
      "milk": (25, "milk_heated_short"), "oil": (9, "fat_heated")},
     130, 1, ["veg", "main"], "counted"),
    ("mutter_paneer", "Mutter paneer",
     {"paneer": (50, "cheese_in_liquid"), "peas": (35, "veg_boiled_in_dish"),
      "tomato": (25, "tomato_boiled"), "oil": (6, "fat_heated")},
     125, 1, ["veg", "main"], "ladle"),
    ("veg_kofta", "Veg kofta",
     {"potato": (50, "as_sourced"), "besan": (15, "flour_fried"),
      "paneer": (20, "cheese_baked"), "oil": (10, "fat_heated")},
     115, 1, ["veg", "main"], "counted"),

    # ---- Egg and chicken. Rationed.
    ("boiled_egg", "Boiled egg", {"egg_boiled": (50, "as_sourced")},
     50, 2, ["egg", "protein"], "counted"),
    ("egg_curry", "Egg curry",
     {"egg_boiled": (100, "as_sourced"), "onion": (25, "veg_sauteed"),
      "tomato": (25, "tomato_boiled"), "oil": (7, "fat_heated")},
     160, 1, ["egg", "protein"], "counted"),
    ("egg_bhurji", "Egg bhurji",
     {"egg_boiled": (100, "as_sourced"), "onion": (25, "veg_sauteed"),
      "oil": (6, "fat_heated")}, 130, 1, ["egg", "protein"], "ladle"),
    ("chicken_butter_masala", "Chicken butter masala",
     {"chicken": (85, "as_sourced"), "butter": (8, "fat_heated"),
      "tomato": (30, "tomato_boiled"), "milk": (20, "milk_heated_short")},
     145, 1, ["meat", "protein"], "ladle"),
    ("kadhai_chicken", "Kadhai chicken",
     {"chicken": (85, "as_sourced"), "onion": (30, "veg_sauteed"),
      "tomato": (25, "tomato_fried"), "oil": (7, "fat_heated")},
     145, 1, ["meat", "protein"], "ladle"),
    ("chicken_biryani", "Chicken biryani",
     {"rice_cooked": (140, "as_sourced"), "chicken": (55, "as_sourced"),
      "oil": (8, "fat_heated"), "onion": (20, "veg_fried")},
     220, 1, ["meat", "main"], "ladle"),
    ("veg_biryani", "Veg biryani",
     {"rice_cooked": (150, "as_sourced"), "carrot": (25, "root_boiled_in_dish"),
      "peas": (25, "veg_boiled_in_dish"), "oil": (8, "fat_heated")},
     210, 2, ["veg", "main"], "ladle"),

    # ---- Breakfast
    ("aloo_paratha", "Aloo paratha",
     {"atta": (40, "flour_baked"), "potato": (45, "as_sourced"),
      "oil": (7, "fat_heated")}, 95, 3, ["veg", "breakfast"], "counted"),
    ("idli", "Idli",
     {"rice_cooked": (45, "as_sourced"), "moong_dal": (15, "as_sourced")},
     60, 4, ["veg", "breakfast"], "counted"),
    ("dosa", "Dosa",
     {"rice_cooked": (60, "as_sourced"), "moong_dal": (20, "as_sourced"),
      "oil": (5, "fat_heated")}, 90, 2, ["veg", "breakfast"], "counted"),
    ("poha", "Poha",
     {"rice_cooked": (130, "as_sourced"), "onion": (20, "veg_sauteed"),
      "peanut": (8, "as_sourced"), "oil": (5, "fat_heated")},
     160, 2, ["veg", "breakfast"], "ladle"),
    ("upma", "Upma",
     {"semolina": (45, "flour_boiled"), "onion": (20, "veg_sauteed"),
      "oil": (6, "fat_heated"), "carrot": (15, "root_sauteed")},
     160, 2, ["veg", "breakfast"], "ladle"),
    ("vada", "Vada",
     {"moong_dal": (45, "as_sourced"), "oil": (9, "fat_heated")},
     55, 2, ["veg", "breakfast"], "counted"),
    ("boiled_sprouts", "Boiled sprouts", {"sprouts": (60, "legume_boiled_drained")},
     60, 2, ["veg", "breakfast"], "ladle"),
    ("nariyal_chutney", "Coconut chutney",
     {"coconut": (20, "raw"), "oil": (2, "fat_heated")},
     30, 2, ["veg", "side"], "spoon"),
    ("green_chutney", "Green chutney",
     {"coconut": (8, "raw"), "onion": (8, "raw")}, 20, 2, ["veg", "side"], "spoon"),
    ("red_chutney", "Red chutney",
     {"tomato": (15, "tomato_fried"), "oil": (2, "fat_heated")},
     20, 2, ["veg", "side"], "spoon"),
    ("imli_chutney", "Imli chutney",
     {"jaggery": (8, "as_sourced"), "dates": (5, "as_sourced")},
     20, 2, ["veg", "side"], "spoon"),
    ("jam", "Jam", {"sugar": (12, "as_sourced")}, 15, 2, ["veg", "side"], "spoon"),
    ("amul_butter", "Butter portion", {"butter": (10, "as_sourced")},
     10, 2, ["veg", "side"], "packet"),

    # ---- Snacks
    ("noodles", "Noodles",
     {"semolina": (60, "flour_boiled"), "oil": (7, "fat_heated"),
      "cabbage": (20, "veg_sauteed")}, 150, 2, ["veg", "snack"], "ladle"),
    ("pav_bhaji", "Pav bhaji",
     {"bread_white": (50, "as_sourced"), "potato": (60, "as_sourced"),
      "peas": (20, "veg_boiled_in_dish"), "butter": (10, "fat_heated"),
      "tomato": (25, "tomato_boiled")}, 175, 1, ["veg", "snack"], "plate"),
    ("samosa", "Samosa",
     {"atta": (25, "flour_fried"), "potato": (40, "as_sourced"),
      "oil": (12, "fat_heated")}, 70, 2, ["veg", "snack"], "counted"),
    ("pakoda", "Pakoda",
     {"besan": (30, "flour_fried"), "onion": (25, "veg_fried"),
      "oil": (12, "fat_heated")}, 60, 2, ["veg", "snack"], "plate"),
    ("cutlet", "Cutlet",
     {"potato": (45, "as_sourced"), "besan": (12, "flour_fried"),
      "oil": (9, "fat_heated")}, 55, 4, ["veg", "snack"], "counted"),
    ("corn_chat", "Corn chat",
     {"peas": (60, "veg_boiled_drained"), "onion": (15, "raw"),
      "tomato": (15, "raw")}, 90, 2, ["veg", "snack"], "plate"),
    ("ratlami_sev", "Ratlami sev",
     {"besan": (22, "flour_fried"), "oil": (10, "fat_heated")},
     30, 2, ["veg", "snack"], "plate"),

    # ---- Everyday extras
    ("plain_curd", "Plain curd", {"curd": (120, "as_sourced")},
     120, 2, ["veg", "dairy"], "ladle"),
    ("boondi_raita", "Boondi raita",
     {"curd": (90, "as_sourced"), "besan": (10, "flour_fried"),
      "oil": (4, "fat_heated")}, 110, 2, ["veg", "dairy"], "ladle"),
    ("veg_raita", "Veg raita",
     {"curd": (90, "as_sourced"), "carrot": (15, "raw"), "onion": (10, "raw")},
     115, 2, ["veg", "dairy"], "ladle"),
    # One 115 ml katori of curd, which weighs about 120 g.
    ("dahi", "Dahi", {"curd": (120, "as_sourced")}, 120, 2, ["veg", "dairy"], "ladle"),
    ("milk_glass", "Milk 200 ml", {"milk": (206, "milk_heated_short")},
     206, 2, ["veg", "dairy"], "glass"),
    ("tea", "Tea",
     {"milk": (50, "milk_heated_short"), "sugar": (8, "as_sourced")},
     150, 3, ["veg", "beverage"], "cup"),
    ("salad", "Salad",
     {"onion": (25, "raw"), "tomato": (30, "raw"), "carrot": (20, "raw")},
     75, 3, ["veg", "side"], "plate"),
    ("onion_chop", "Onion chopped", {"onion": (30, "raw")},
     30, 2, ["veg", "side"], "spoon"),
    ("tomato_chop", "Tomato chopped", {"tomato": (30, "raw")},
     30, 2, ["veg", "side"], "spoon"),
    ("papad", "Papad",
     {"besan": (10, "flour_fried"), "oil": (4, "fat_heated")},
     14, 2, ["veg", "side"], "counted"),
    ("pickle", "Pickle", {"oil": (4, "as_sourced")}, 12, 2, ["veg", "side"], "spoon"),
    ("fruit_portion", "Fruit (2 pcs)",
     {"banana": (100, "raw"), "apple": (80, "raw")},
     180, 2, ["veg", "fruit"], "counted"),

    # ---- Sweets. One portion, take it or leave it.
    ("kheer", "Kheer",
     {"milk": (130, "milk_heated_long"), "rice_cooked": (25, "as_sourced"),
      "sugar": (15, "as_sourced")}, 160, 1, ["veg", "sweet"], "ladle"),
    ("moong_halwa", "Moong halwa",
     {"moong_dal": (45, "as_sourced"), "ghee": (12, "fat_heated"),
      "sugar": (20, "as_sourced")}, 90, 1, ["veg", "sweet"], "ladle"),
    ("fruit_custard", "Fruit custard",
     {"milk": (100, "milk_heated_short"), "sugar": (12, "as_sourced"),
      "banana": (35, "raw")}, 150, 1, ["veg", "sweet"], "ladle"),
    ("gulab_jamun", "Gulab jamun (2 pcs)",
     {"milk": (40, "milk_heated_long"), "atta": (15, "flour_fried"),
      "sugar": (30, "as_sourced"), "ghee": (8, "fat_heated")},
     90, 1, ["veg", "sweet"], "counted"),
]

# --------------------------------------------------------------------------
# The same thing again for a North American dining hall. Kept as a separate
# list purely so that each dish can be tagged with the cuisine it belongs to
# without writing "indian" or "american" a hundred and nine times.
#
# The tag is not decoration. The menu audit searches for dishes worth adding,
# and without it the search cheerfully recommends putting a yogurt parfait on
# an Indian hostel menu -- arithmetically correct, useless as advice.
# --------------------------------------------------------------------------

US_DISHES = [
    ("cheeseburger", "Cheeseburger",
     {"beef_patty": (85, "as_sourced"), "burger_bun": (50, "as_sourced"),
      "cheddar": (20, "as_sourced"), "tomato": (15, "raw"), "onion": (10, "raw")},
     180, 1, ["meat", "main"], "counted"),
    ("cheese_pizza", "Cheese pizza slice",
     {"flour_white": (55, "flour_baked"), "mozzarella": (35, "cheese_baked"),
      "marinara": (30, "as_sourced"), "olive_oil": (3, "fat_heated")},
     120, 3, ["veg", "main"], "counted"),
    ("pasta_marinara", "Pasta marinara",
     {"pasta_cooked": (200, "as_sourced"), "marinara": (100, "as_sourced"),
      "olive_oil": (5, "fat_heated")}, 305, 2, ["veg", "main"], "plate"),
    ("mac_and_cheese", "Macaroni and cheese",
     {"pasta_cooked": (150, "as_sourced"), "cheddar": (40, "cheese_in_liquid"),
      "milk_2pct": (40, "milk_heated_short"), "butter": (8, "fat_heated")},
     238, 2, ["veg", "main"], "ladle"),
    ("grilled_chicken", "Grilled chicken breast",
     {"chicken_breast": (120, "as_sourced"), "olive_oil": (5, "fat_heated")},
     125, 1, ["meat", "protein", "main"], "counted"),
    ("baked_salmon", "Baked salmon",
     {"salmon": (120, "as_sourced"), "olive_oil": (4, "fat_heated")},
     124, 1, ["meat", "fish", "protein", "main"], "counted"),
    ("turkey_sandwich", "Turkey sandwich",
     {"bread_wheat": (60, "as_sourced"), "turkey_deli": (60, "as_sourced"),
      "american_cheese": (20, "as_sourced"), "romaine": (10, "raw"),
      "tomato": (15, "raw")}, 165, 1, ["meat", "main"], "counted"),
    ("black_bean_bowl", "Black bean and rice bowl",
     {"black_beans": (150, "as_sourced"), "rice_cooked": (150, "as_sourced"),
      "sweetcorn": (40, "as_sourced"), "tomato": (30, "raw")},
     370, 1, ["veg", "protein", "main"], "plate"),
    ("tofu_stirfry", "Tofu stir fry",
     {"tofu": (120, "as_sourced"), "bell_pepper": (40, "veg_sauteed"),
      "broccoli": (50, "as_sourced"), "mushroom": (30, "veg_sauteed"),
      "olive_oil": (6, "fat_heated")}, 246, 1, ["veg", "protein", "main"], "plate"),
    ("garden_salad", "Garden salad",
     {"romaine": (60, "raw"), "tomato": (30, "raw"), "cucumber": (30, "raw"),
      "bell_pepper": (20, "raw"), "ranch_dressing": (15, "as_sourced")},
     155, 3, ["veg", "side"], "plate"),
    ("chickpea_salad", "Chickpea salad",
     {"chickpeas_canned": (120, "as_sourced"), "cucumber": (40, "raw"),
      "tomato": (30, "raw"), "olive_oil": (5, "as_sourced")},
     195, 2, ["veg", "protein", "side"], "plate"),
    ("french_fries", "French fries", {"fries": (100, "as_sourced")},
     100, 2, ["veg", "side"], "plate"),
    ("steamed_broccoli", "Steamed broccoli", {"broccoli": (90, "as_sourced")},
     90, 3, ["veg", "side"], "ladle"),
    ("sweetcorn_side", "Sweetcorn", {"sweetcorn": (90, "as_sourced")},
     90, 2, ["veg", "side"], "ladle"),
    ("tomato_soup_bowl", "Tomato soup", {"tomato_soup": (245, "as_sourced")},
     245, 2, ["veg", "side"], "bowl"),
    ("dinner_roll", "Dinner roll", {"burger_bun": (40, "as_sourced")},
     40, 4, ["veg", "staple"], "counted"),
    ("scrambled_eggs", "Scrambled eggs", {"egg_scrambled": (100, "as_sourced")},
     100, 2, ["egg", "protein", "breakfast"], "ladle"),
    ("bacon_strips", "Bacon", {"bacon": (25, "as_sourced")},
     25, 2, ["meat", "breakfast"], "counted"),
    ("oatmeal", "Oatmeal", {"oats_cooked": (230, "as_sourced")},
     230, 2, ["veg", "breakfast"], "bowl"),
    ("cereal_bowl", "Cereal with milk",
     {"corn_flakes": (40, "as_sourced"), "milk_2pct": (200, "as_sourced")},
     240, 2, ["veg", "dairy", "breakfast"], "bowl"),
    ("bagel_butter", "Bagel with butter",
     {"bagel": (90, "as_sourced"), "butter": (10, "as_sourced")},
     100, 2, ["veg", "breakfast"], "counted"),
    ("pancakes_stack", "Pancakes",
     {"pancake": (120, "as_sourced"), "butter": (8, "as_sourced"),
      "sugar": (12, "as_sourced")}, 140, 2, ["veg", "breakfast"], "counted"),
    ("yogurt_parfait", "Yogurt parfait",
     {"yogurt_lowfat": (170, "as_sourced"), "banana": (50, "raw"),
      "almonds": (10, "as_sourced")}, 230, 2,
     ["veg", "dairy", "breakfast"], "cup"),
    ("orange_juice_glass", "Orange juice", {"orange_juice": (240, "as_sourced")},
     240, 2, ["veg", "fruit", "beverage"], "glass"),
    ("milk_carton", "Milk carton", {"milk_2pct": (240, "as_sourced")},
     240, 2, ["veg", "dairy", "beverage"], "packet"),
    ("apple_whole", "Whole apple", {"apple": (180, "raw")},
     180, 2, ["veg", "fruit"], "counted"),
    ("brownie_square", "Brownie", {"brownie_mix": (56, "as_sourced")},
     56, 1, ["veg", "sweet"], "counted"),
]


# --------------------------------------------------------------------------
# Ingredients SR Legacy simply does not carry.
#
# Using a poor USDA substitute would have been worse than admitting the gap:
# whole-milk ricotta, the nearest fresh acid-set cheese, reports 7.5 g protein
# per 100 g against paneer's ~19 g. Understating the single biggest vegetarian
# protein source on the menu would have inflated the very shortfall this
# product exists to measure.
#
# Paneer and jaggery now come from the *Indian Food Composition Tables 2017*
# (T. Longvah, R. Ananthan, K. Bhaskarachary, K. Venkaiah; National Institute
# of Nutrition, ICMR, Hyderabad), which is a measured Indian table rather than
# a guess at an Indian food:
#
#   https://www.nin.res.in/ebooks/IFCT2017.pdf
#
# Both keep the `proxy` flag, for one reason each and a good one: **IFCT 2017
# does not measure vitamin B12 for any food in the book.** Fifteen of the
# sixteen nutrients this catalog tracks are now sourced; the sixteenth is not,
# and a flag that came off while a value was still invented would be worse
# than no flag. Each row names exactly which nutrients are sourced, so the
# interface can say "estimated" about the one that deserves it rather than the
# whole row.
#
# Two conversions are ours, not IFCT's, and are marked as such below: IFCT
# prints energy only in kilojoules, and prints retinol and carotenoids rather
# than a retinol-activity-equivalent total.
# --------------------------------------------------------------------------

IFCT = "Indian Food Composition Tables 2017 (NIN-ICMR, Hyderabad)"

# Every nutrient except vitamin B12, which IFCT 2017 does not carry.
IFCT_SOURCED = ["kcal", "protein", "fat", "satfat", "carbs", "fibre",
                "calcium", "iron", "magnesium", "potassium", "sodium",
                "zinc", "vita", "vitc", "folate"]

MANUAL_INGREDIENTS = [
    ("paneer", "Paneer", ["veg", "dairy"], {
        # IFCT 2017 food code L003, "Paneer", per 100 g edible portion.
        # Energy is printed as 1278 kJ; IFCT's own stated conversion is
        # 1 kcal = 4.18 kJ, which gives 305.7.
        "kcal": 305.7, "protein": 18.86, "fat": 24.78, "satfat": 8.851,
        # CHOAVLDF, available carbohydrate, already net of fibre. Fibre is
        # blank in IFCT, which its table footer defines as below the limit of
        # detection rather than unmeasured.
        "carbs": 2.41, "fibre": 0.0, "calcium": 476, "iron": 0.90,
        "magnesium": 26.62, "potassium": 63.53, "sodium": 18.04, "zinc": 2.74,
        # Retinol 20.58 ug plus beta-carotene 4.39 ug, combined as retinol
        # activity equivalents at the conventional 12:1. IFCT prints the two
        # components separately and no RAE column.
        "vita": 20.9, "vitc": 0.0,
        # Not measured by IFCT 2017. Carried over from the previous hand-
        # entered figure and still an estimate; this is why the row stays
        # flagged.
        "vitb12": 0.9, "folate": 93.31,
    }, "Paneer is IFCT 2017 code L003, measured, per 100 g edible portion "
       "(tables 1, 2, 3, 5 and 7). Every nutrient here is from that source "
       "except vitamin B12, which IFCT 2017 does not measure for any food -- "
       "that one figure is still a hand-entered estimate. Energy is converted "
       "from IFCT's kilojoules and vitamin A is combined from its separate "
       "retinol and carotene figures. Note also that IFCT's own fatty-acid "
       "table sums to about 55 percent of the total fat it reports in table 1, "
       "a discrepancy in the source that is reproduced here rather than "
       "quietly reconciled.",
     IFCT_SOURCED),

    ("jaggery", "Jaggery", ["veg", "sugar"], {
        # IFCT 2017 food code I001, "Jaggery, cane (Saccharum officinarum)".
        # 1480 kJ at IFCT's 4.18 kJ per kcal.
        "kcal": 354.1, "protein": 1.85, "fat": 0.16, "satfat": 0.069,
        "carbs": 84.87, "fibre": 0.0, "calcium": 107, "iron": 4.63,
        "magnesium": 115, "potassium": 488, "sodium": 25.38, "zinc": 0.45,
        "vita": 0.0, "vitc": 0.0,
        # Not measured by IFCT. Zero because sugarcane products contain no
        # B12, which is what USDA reports for every sugar it carries -- but it
        # is still a value nobody measured in this food.
        "vitb12": 0.0, "folate": 14.40,
    }, "Jaggery is IFCT 2017 code I001, measured, per 100 g edible portion. "
       "This replaces a hand-entered figure whose iron was a mid-point of a "
       "2-11 mg range; IFCT measures 4.63 mg. Vitamin B12 is the one nutrient "
       "IFCT 2017 does not carry, and is recorded as zero on the grounds that "
       "cane sugar products contain none -- reasonable, but not measured, "
       "which is why the row stays flagged.",
     IFCT_SOURCED),

    ("whey_protein", "Whey protein powder", ["veg", "supplement"], {
        "kcal": 380, "protein": 80.0, "fat": 6.0, "satfat": 3.0,
        "carbs": 8.0, "fibre": 0.0, "calcium": 500, "iron": 1.0,
        "magnesium": 80, "potassium": 500, "sodium": 300, "zinc": 3.0,
        "vita": 0.0, "vitc": 0.0, "vitb12": 1.5, "folate": 0,
    }, "Hand-entered from a typical whey concentrate label. Brands vary "
       "widely and fortification differs, so treat the micronutrients as "
       "indicative only. No composition table covers a manufactured blend, so "
       "there is nothing better to replace this with.",
     []),
]


# --------------------------------------------------------------------------
# The market basket: what a student can buy with their own money.
#
# These are the priced goods in the linear program. Mess dishes cost nothing
# at the margin because the plan is already paid for; these cost real money,
# which is exactly what the solver is asked to minimise.
#
# `unit` is what one unit means to a human -- one egg, one 500 ml packet --
# and `recipe` is the grams of catalog ingredient in that unit, so the
# nutrition comes down the same traced path as the mess dishes.
#
# Prices are seed defaults, not measured. They are per unit, in local
# currency, and the interface lets the user overwrite every one of them --
# a price that is wrong for your campus makes the answer wrong for you, so
# it has to be editable rather than authoritative.
# --------------------------------------------------------------------------

MARKET = [
    ("egg", "Boiled egg", "1 egg", {"egg_boiled": (50, "as_sourced")}, 4,
     {"IN": 8.0, "US": 0.35}, ["egg", "protein"]),
    ("milk_packet", "Milk", "500 ml packet", {"milk": (500, "milk_heated_short")}, 2,
     {"IN": 33.0, "US": 0.75}, ["veg", "dairy"]),
    ("curd_cup", "Curd", "200 g cup", {"curd": (200, "as_sourced")}, 2,
     {"IN": 25.0}, ["veg", "dairy"]),
    ("paneer_block", "Paneer", "100 g", {"paneer": (100, "as_sourced")}, 2,
     {"IN": 45.0}, ["veg", "dairy", "protein"]),
    ("whey_scoop", "Whey protein", "30 g scoop", {"whey_protein": (30, "as_sourced")}, 2,
     {"IN": 60.0, "US": 1.10}, ["veg", "supplement", "protein"]),
    ("peanuts", "Roasted peanuts", "50 g", {"peanut": (50, "as_sourced")}, 3,
     {"IN": 15.0, "US": 0.60}, ["veg", "protein"]),
    ("peanut_butter", "Peanut butter", "30 g", {"peanut": (30, "as_sourced")}, 3,
     {"IN": 18.0, "US": 0.45}, ["veg", "protein"]),
    ("boiled_chana", "Boiled chana", "100 g", {"chana": (100, "as_sourced")}, 3,
     {"IN": 20.0}, ["veg", "protein"]),
    ("rajma_bowl", "Rajma, boiled", "150 g", {"rajma": (150, "as_sourced")}, 2,
     {"IN": 22.0}, ["veg", "protein"]),
    ("soya_chunks", "Soya chunks", "80 g cooked", {"soybean": (80, "as_sourced")}, 2,
     {"IN": 14.0}, ["veg", "protein"]),
    ("sprouts_bowl", "Sprouts", "100 g", {"sprouts": (100, "raw")}, 2,
     {"IN": 15.0}, ["veg"]),
    ("banana", "Banana", "1 banana", {"banana": (100, "raw")}, 4,
     {"IN": 7.0, "US": 0.30}, ["veg", "fruit"]),
    ("apple", "Apple", "1 apple", {"apple": (150, "raw")}, 3,
     {"IN": 28.0, "US": 0.90}, ["veg", "fruit"]),
    ("orange", "Orange", "1 orange", {"orange": (130, "raw")}, 3,
     {"IN": 18.0, "US": 0.80}, ["veg", "fruit"]),
    ("guava", "Guava", "1 guava", {"guava": (150, "raw")}, 3,
     {"IN": 16.0}, ["veg", "fruit"]),
    ("papaya_bowl", "Papaya, cut", "200 g bowl", {"papaya": (200, "raw")}, 2,
     {"IN": 25.0}, ["veg", "fruit"]),
    ("dates", "Dates", "40 g", {"dates": (40, "as_sourced")}, 2,
     {"IN": 25.0, "US": 0.90}, ["veg", "fruit"]),
    ("spinach_side", "Spinach, cooked", "100 g", {"spinach": (100, "as_sourced")}, 2,
     {"IN": 12.0, "US": 0.90}, ["veg"]),
    ("carrot_stick", "Carrot", "100 g", {"carrot": (100, "raw")}, 2,
     {"IN": 10.0, "US": 0.50}, ["veg"]),
    # ---- Stocked where the dining-hall preset applies.
    ("greek_yogurt", "Greek yogurt", "170 g cup", {"yogurt_lowfat": (170, "as_sourced")}, 2,
     {"US": 1.30}, ["veg", "dairy", "protein"]),
    ("string_cheese", "String cheese", "1 stick", {"mozzarella": (28, "as_sourced")}, 3,
     {"US": 0.50}, ["veg", "dairy", "protein"]),
    ("almonds_pack", "Almonds", "30 g", {"almonds": (30, "as_sourced")}, 3,
     {"US": 0.55}, ["veg", "protein"]),
    ("baby_carrots", "Baby carrots", "85 g", {"carrot": (85, "raw")}, 2,
     {"US": 0.60}, ["veg"]),
    ("frozen_broccoli", "Broccoli", "100 g cooked", {"broccoli": (100, "as_sourced")}, 2,
     {"US": 0.70}, ["veg"]),
    ("black_bean_can", "Black beans", "130 g", {"black_beans": (130, "as_sourced")}, 2,
     {"US": 0.65}, ["veg", "protein"]),
    ("tofu_block", "Tofu", "120 g", {"tofu": (120, "as_sourced")}, 2,
     {"US": 1.20}, ["veg", "protein"]),
    ("oj_bottle", "Orange juice", "240 ml", {"orange_juice": (240, "as_sourced")}, 2,
     {"US": 1.10}, ["veg", "fruit"]),
    ("yogurt_cup_us", "Yogurt", "227 g cup", {"yogurt_lowfat": (227, "as_sourced")}, 2,
     {"US": 1.00}, ["veg", "dairy"]),
]

def load_sr_nutrients(sr_dir):
    """Return {fdc_id: {nutrient_key: amount per 100 g}} for the ids we want."""
    wanted_foods = {str(fdc_id) for _, fdc_id, _, _, _ in INGREDIENTS}
    by_nutrient_id = {str(v): k for k, v in NUTRIENT_IDS.items()}

    path = os.path.join(sr_dir, "food_nutrient.csv")
    if not os.path.exists(path):
        sys.exit("could not find food_nutrient.csv under %s" % sr_dir)

    out = {fdc_id: {} for fdc_id in wanted_foods}
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            fdc_id = row["fdc_id"]
            if fdc_id not in wanted_foods:
                continue
            key = by_nutrient_id.get(row["nutrient_id"])
            if key is None:
                continue
            value = row["amount"]
            if value == "":
                continue
            out[fdc_id][key] = float(value)
    return out


def load_sr_descriptions(sr_dir):
    wanted = {str(fdc_id) for _, fdc_id, _, _, _ in INGREDIENTS}
    out = {}
    with open(os.path.join(sr_dir, "food.csv"), newline="") as handle:
        for row in csv.DictReader(handle):
            if row["fdc_id"] in wanted:
                out[row["fdc_id"]] = row["description"]
    return out


def build(sr_dir):
    nutrient_table = load_sr_nutrients(sr_dir)
    descriptions = load_sr_descriptions(sr_dir)

    ingredients = {}
    missing = []
    for our_id, fdc_id, name, tags, proxy_note in INGREDIENTS:
        key = str(fdc_id)
        values = nutrient_table.get(key)
        if not values:
            missing.append((our_id, fdc_id))
            continue
        # Anything SR Legacy does not report is recorded as zero, which
        # understates rather than invents.
        per_100g = {k: round(values.get(k, 0.0), 4) for k, _, _, _ in NUTRIENTS}
        entry = {
            "id": our_id,
            "name": name,
            "tags": tags,
            "per100g": per_100g,
            "source": {
                "dataset": "USDA FoodData Central, SR Legacy (2018-04)",
                "fdcId": fdc_id,
                "description": descriptions.get(key, ""),
            },
            "reported": sorted(values.keys()),
        }
        if proxy_note:
            entry["proxy"] = True
            entry["proxyNote"] = proxy_note
        ingredients[our_id] = entry

    if missing:
        sys.exit("no SR Legacy nutrients found for: %r" % missing)

    for our_id, name, tags, per_100g, note, sourced in MANUAL_INGREDIENTS:
        # `reported` used to list every key, which said nothing. It now lists
        # only what a published table actually measured, so the remainder --
        # the difference against the sixteen nutrients -- is the honest list
        # of what is still somebody's estimate.
        dataset = IFCT if sourced else "manual estimate, not from a published table"
        ingredients[our_id] = {
            "id": our_id,
            "name": name,
            "tags": tags,
            "per100g": {k: float(per_100g[k]) for k, _, _, _ in NUTRIENTS},
            "source": {
                "dataset": dataset,
                "fdcId": None,
                "description": note,
            },
            "reported": sorted(sourced),
            "estimated": sorted(set(NUTRIENT_IDS) - set(sourced)),
            "proxy": True,
            "proxyNote": note,
        }

    def compose(owner, recipe):
        """Add up one serving from its ingredient grams, after cook loss.

        Each recipe line names how that ingredient is prepared, and the
        matching retention factors scale it down before it is added in. A
        factor of 1.0 is as much a claim as any other number, so the reason it
        is 1.0 is written against the method in RETENTION rather than left to
        be inferred from its absence.

        Returns the nutrient totals plus whether any ingredient involved was a
        proxy, so a dish built on an estimated ingredient inherits the warning
        instead of quietly laundering it into a clean-looking number."""
        totals = {k: 0.0 for k, _, _, _ in NUTRIENTS}
        reasons = []
        for ingredient_id, (grams, method) in recipe.items():
            ingredient = ingredients.get(ingredient_id)
            if ingredient is None:
                sys.exit("%s refers to unknown ingredient %r" % (owner, ingredient_id))
            if method not in RETENTION:
                sys.exit("%s prepares %s by %r, which RETENTION does not define"
                         % (owner, ingredient_id, method))
            factors = RETENTION[method]["factors"]
            scale = grams / 100.0
            for key, value in ingredient["per100g"].items():
                totals[key] += value * scale * factors.get(key, 1.0)
            if ingredient.get("proxy"):
                reasons.append("%s: %s" % (ingredient["name"], ingredient["proxyNote"]))
        return totals, reasons

    def recipe_lines(recipe):
        return [{"ingredient": k, "grams": g, "prep": m}
                for k, (g, m) in sorted(recipe.items())]

    dishes = {}
    catalogued = ([(entry, "indian") for entry in DISHES]
                  + [(entry, "american") for entry in US_DISHES])
    for (dish_id, name, recipe, serving_g, cap, tags, serving_kind), cuisine in catalogued:
        tags = list(tags) + [cuisine]
        if serving_kind not in SERVING_SOURCES:
            sys.exit("dish %r claims serving source %r, which is not defined"
                     % (dish_id, serving_kind))
        totals, proxy_reasons = compose("dish %r" % dish_id, recipe)
        is_proxy = bool(proxy_reasons)

        entry = {
            "id": dish_id,
            "name": name,
            "cuisine": cuisine,
            "tags": tags,
            "servingGrams": serving_g,
            "servingSource": serving_kind,
            "maxServings": cap,
            "perServing": {k: round(v, 4) for k, v in totals.items()},
            "recipe": recipe_lines(recipe),
        }
        if is_proxy:
            entry["proxy"] = True
            entry["proxyNote"] = " | ".join(proxy_reasons)
        dishes[dish_id] = entry

    market = {}
    for item_id, name, unit, recipe, cap, prices, tags in MARKET:
        totals, proxy_reasons = compose("market item %r" % item_id, recipe)
        entry = {
            "id": item_id,
            "name": name,
            "unit": unit,
            "tags": tags,
            "maxUnits": cap,
            "defaultPrice": dict(prices),
            "perUnit": {k: round(v, 4) for k, v in totals.items()},
            "recipe": recipe_lines(recipe),
        }
        if proxy_reasons:
            entry["proxy"] = True
            entry["proxyNote"] = " | ".join(proxy_reasons)
        market[item_id] = entry

    return {
        "schemaVersion": 1,
        "nutrients": [
            {"id": k, "name": name, "unit": unit, "fdcNutrientId": fdc_id}
            for k, fdc_id, name, unit in NUTRIENTS
        ],
        "notes": {
            "ingredients": (
                "Each ingredient is one USDA FoodData Central SR Legacy food, "
                "cited by fdcId, per 100 g."
            ),
            "cuisine": (
                "Every dish carries a cuisine so that the menu audit suggests "
                "additions that belong on the menu it is auditing."
            ),
            "dishes": (
                "Dishes are computed from their ingredient recipes, not estimated "
                "at dish level. Recipes are stated assumptions -- see "
                "data/build_catalog.py -- so any individual gram figure can be "
                "argued with directly."
            ),
            "market": (
                "Market prices are seed defaults, not survey data. Every one "
                "is editable in the interface, because a price that is wrong "
                "for your campus makes the recommendation wrong for you."
            ),
            "retention": (
                "Cooking destroys vitamin C, folate and some B vitamins. Every "
                "recipe line says how that ingredient is prepared, and the "
                "matching retention factors are applied before it is added up. "
                "Where an ingredient's USDA row is already the cooked food, the "
                "factor is 1.0, because the loss is in the source number and "
                "applying it twice would invent a shortfall."
            ),
            "servings": (
                "Every dish says what kind of estimate its serving weight is -- "
                "a counted piece, a ladle, a plated portion. None of them are "
                "weighed, and the kind of guess tells you how far to trust it."
            ),
            "proxies": (
                "Rows marked proxy have no SR Legacy equivalent and use a named "
                "substitute. They are flagged in the interface rather than "
                "presented as measured."
            ),
        },
        "retention": {
            method: {
                "id": method,
                "name": spec["name"],
                "usdaCode": spec["usdaCode"],
                "usdaDescription": spec["usdaDescription"],
                "why": spec["why"],
                "factors": dict(spec["factors"]),
            }
            for method, spec in sorted(RETENTION.items())
        },
        "servingSources": dict(SERVING_SOURCES),
        "ingredients": ingredients,
        "dishes": dishes,
        "market": market,
        "currencies": {
            "IN": {"code": "INR", "symbol": "\u20b9", "decimals": 0},
            "US": {"code": "USD", "symbol": "$", "decimals": 2},
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sr", required=True,
                        help="unzipped SR Legacy CSV directory")
    parser.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "foods.json"))
    args = parser.parse_args()

    catalog = build(args.sr)
    with open(args.out, "w") as handle:
        json.dump(catalog, handle, indent=1, sort_keys=True)
        handle.write("\n")

    proxies = sum(1 for d in catalog["dishes"].values() if d.get("proxy"))
    print("wrote %s" % args.out)
    print("  %d ingredients, %d dishes, %d market items, %d nutrients, "
          "%d dishes flagged as proxy"
          % (len(catalog["ingredients"]), len(catalog["dishes"]),
             len(catalog["market"]), len(catalog["nutrients"]), proxies))


if __name__ == "__main__":
    main()
