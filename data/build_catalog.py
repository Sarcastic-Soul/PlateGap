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

Where SR Legacy simply has no equivalent -- paneer being the obvious one -- the
row is marked `"proxy": true` with a note naming what was substituted. Those
rows are flagged in the UI rather than quietly presented as fact.
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
# Dishes: what the mess actually puts on the plate.
#
# `recipe` is grams of each ingredient in ONE serving. `serving` is the gram
# weight of that serving as eaten, used only for display. `cap` is how many
# servings a student can realistically get -- staples are effectively
# unlimited in a self-serve hostel mess, while paneer, chicken and sweets are
# rationed to what is ladled out.
#
# Every number here is an assumption. That is the point of writing them down.
# --------------------------------------------------------------------------

DISHES = [
    # ---- Staples. Unlimited in practice, so a generous cap.
    ("roti", "Roti", {"atta": 30, "oil": 1}, 35, 6, ["veg", "staple"]),
    ("plain_rice", "Plain rice", {"rice_cooked": 150}, 150, 4, ["veg", "staple"]),
    ("jeera_rice", "Jeera rice", {"rice_cooked": 150, "oil": 4}, 155, 4, ["veg", "staple"]),
    ("onion_rice", "Onion rice", {"rice_cooked": 150, "onion": 25, "oil": 4}, 175, 4, ["veg", "staple"]),
    ("peas_pulao", "Peas pulao", {"rice_cooked": 150, "peas": 30, "oil": 5}, 180, 3, ["veg", "staple"]),
    ("poori", "Poori", {"atta": 25, "oil": 6}, 32, 4, ["veg", "staple"]),
    ("bread_slice", "Bread slice", {"bread_white": 25}, 25, 4, ["veg", "staple"]),

    # ---- Dals. Also effectively unlimited.
    ("toor_dal_tadka", "Arhar dal tadka",
     {"toor_dal": 130, "oil": 5, "onion": 15, "tomato": 15}, 165, 4, ["veg", "dal"]),
    ("dal_tadka", "Dal tadka",
     {"masoor_dal": 130, "oil": 5, "onion": 15, "tomato": 15}, 165, 4, ["veg", "dal"]),
    ("dal_mix", "Mix dal",
     {"toor_dal": 70, "moong_dal": 60, "oil": 5, "tomato": 15}, 150, 4, ["veg", "dal"]),
    ("masoor_dal_dish", "Khada masoor dal",
     {"masoor_dal": 140, "oil": 5, "onion": 15}, 160, 4, ["veg", "dal"]),
    ("dal_makhani", "Dal makhani",
     {"rajma": 60, "masoor_dal": 70, "butter": 8, "milk": 20, "tomato": 20}, 175, 3, ["veg", "dal"]),
    ("sambhar", "Sambhar",
     {"toor_dal": 70, "carrot": 20, "okra": 15, "onion": 15, "oil": 4, "tomato": 15}, 140, 4, ["veg", "dal"]),
    ("rasam", "Rasam", {"toor_dal": 25, "tomato": 40, "oil": 3}, 150, 3, ["veg", "dal"]),

    # ---- Pulse-based mains
    ("chole", "Chole",
     {"chana": 130, "onion": 25, "tomato": 25, "oil": 7}, 185, 2, ["veg", "main"]),
    ("chole_curry", "Chole curry",
     {"chana": 120, "onion": 25, "tomato": 30, "oil": 7}, 185, 2, ["veg", "main"]),
    ("rajma_dish", "Rajma",
     {"rajma": 130, "onion": 25, "tomato": 25, "oil": 7}, 185, 2, ["veg", "main"]),
    ("black_chana_aloo", "Black chana aloo",
     {"chana": 90, "potato": 60, "onion": 20, "oil": 6}, 175, 2, ["veg", "main"]),
    ("matar_chola", "Matar chola",
     {"chana": 100, "peas": 30, "onion": 20, "oil": 6}, 155, 2, ["veg", "main"]),
    ("soya_badi", "Soya badi",
     {"soybean": 80, "onion": 20, "tomato": 20, "oil": 6}, 125, 2, ["veg", "main"]),
    ("soya_chilli", "Soya chilli",
     {"soybean": 80, "onion": 30, "oil": 7}, 120, 2, ["veg", "main"]),
    ("mangodi", "Mangodi", {"moong_dal": 70, "oil": 6, "onion": 15}, 95, 2, ["veg", "main"]),

    # ---- Vegetable sabzis
    ("aloo_jeera", "Aloo jeera", {"potato": 120, "oil": 6}, 125, 2, ["veg", "sabzi"]),
    ("aloo_tomato", "Aloo tomato", {"potato": 100, "tomato": 40, "oil": 6}, 145, 2, ["veg", "sabzi"]),
    ("aloo_choka", "Aloo choka", {"potato": 110, "onion": 20, "oil": 4}, 135, 2, ["veg", "sabzi"]),
    ("aloo_bhujiya", "Aloo bhujiya", {"potato": 110, "oil": 7}, 120, 2, ["veg", "sabzi"]),
    ("dum_aloo", "Dum aloo", {"potato": 110, "curd": 25, "tomato": 20, "oil": 8}, 155, 2, ["veg", "sabzi"]),
    ("mix_veg", "Mix veg",
     {"potato": 40, "carrot": 30, "peas": 25, "cauliflower": 30, "oil": 6}, 130, 2, ["veg", "sabzi"]),
    ("veg_kolhapuri", "Veg kolhapuri",
     {"cauliflower": 35, "carrot": 25, "peas": 25, "potato": 30, "oil": 8}, 130, 2, ["veg", "sabzi"]),
    ("gobhi_dry", "Gobhi dry", {"cauliflower": 110, "oil": 6}, 115, 2, ["veg", "sabzi"]),
    ("kurmuri_bhindi", "Kurmuri bhindi", {"okra": 100, "besan": 10, "oil": 9}, 110, 2, ["veg", "sabzi"]),
    ("kadu_masala", "Kadu masala", {"cabbage": 100, "onion": 20, "oil": 6}, 120, 2, ["veg", "sabzi"]),
    ("pyaj_muter_malai", "Pyaj mutter malai",
     {"peas": 50, "onion": 40, "milk": 25, "oil": 6}, 125, 2, ["veg", "sabzi"]),
    ("kadai_masala", "Kadai masala",
     {"cauliflower": 40, "onion": 30, "tomato": 30, "oil": 7}, 110, 2, ["veg", "sabzi"]),

    # ---- Paneer. Rationed.
    ("paneer_butter_masala", "Paneer butter masala",
     {"paneer": 60, "butter": 8, "tomato": 35, "milk": 20, "oil": 4}, 130, 1, ["veg", "main"]),
    ("paneer_bhurji", "Paneer bhurji",
     {"paneer": 65, "onion": 25, "tomato": 20, "oil": 6}, 115, 1, ["veg", "main"]),
    ("malai_kofta", "Malai kofta",
     {"paneer": 45, "potato": 40, "milk": 25, "oil": 9}, 130, 1, ["veg", "main"]),
    ("mutter_paneer", "Mutter paneer",
     {"paneer": 50, "peas": 35, "tomato": 25, "oil": 6}, 125, 1, ["veg", "main"]),
    ("veg_kofta", "Veg kofta",
     {"potato": 50, "besan": 15, "paneer": 20, "oil": 10}, 115, 1, ["veg", "main"]),

    # ---- Egg and chicken. Rationed.
    ("boiled_egg", "Boiled egg", {"egg_boiled": 50}, 50, 2, ["egg", "protein"]),
    ("egg_curry", "Egg curry",
     {"egg_boiled": 100, "onion": 25, "tomato": 25, "oil": 7}, 160, 1, ["egg", "protein"]),
    ("egg_bhurji", "Egg bhurji",
     {"egg_boiled": 100, "onion": 25, "oil": 6}, 130, 1, ["egg", "protein"]),
    ("chicken_butter_masala", "Chicken butter masala",
     {"chicken": 85, "butter": 8, "tomato": 30, "milk": 20}, 145, 1, ["meat", "protein"]),
    ("kadhai_chicken", "Kadhai chicken",
     {"chicken": 85, "onion": 30, "tomato": 25, "oil": 7}, 145, 1, ["meat", "protein"]),
    ("chicken_biryani", "Chicken biryani",
     {"rice_cooked": 140, "chicken": 55, "oil": 8, "onion": 20}, 220, 1, ["meat", "main"]),
    ("veg_biryani", "Veg biryani",
     {"rice_cooked": 150, "carrot": 25, "peas": 25, "oil": 8}, 210, 2, ["veg", "main"]),

    # ---- Breakfast
    ("aloo_paratha", "Aloo paratha",
     {"atta": 40, "potato": 45, "oil": 7}, 95, 3, ["veg", "breakfast"]),
    ("idli", "Idli", {"rice_cooked": 45, "moong_dal": 15}, 60, 4, ["veg", "breakfast"]),
    ("dosa", "Dosa", {"rice_cooked": 60, "moong_dal": 20, "oil": 5}, 90, 2, ["veg", "breakfast"]),
    ("poha", "Poha",
     {"rice_cooked": 130, "onion": 20, "peanut": 8, "oil": 5}, 160, 2, ["veg", "breakfast"]),
    ("upma", "Upma",
     {"semolina": 45, "onion": 20, "oil": 6, "carrot": 15}, 160, 2, ["veg", "breakfast"]),
    ("vada", "Vada", {"moong_dal": 45, "oil": 9}, 55, 2, ["veg", "breakfast"]),
    ("boiled_sprouts", "Boiled sprouts", {"sprouts": 60}, 60, 2, ["veg", "breakfast"]),
    ("nariyal_chutney", "Coconut chutney", {"coconut": 20, "oil": 2}, 30, 2, ["veg", "side"]),
    ("green_chutney", "Green chutney", {"coconut": 8, "onion": 8}, 20, 2, ["veg", "side"]),
    ("red_chutney", "Red chutney", {"tomato": 15, "oil": 2}, 20, 2, ["veg", "side"]),
    ("imli_chutney", "Imli chutney", {"jaggery": 8, "dates": 5}, 20, 2, ["veg", "side"]),
    ("jam", "Jam", {"sugar": 12}, 15, 2, ["veg", "side"]),
    ("amul_butter", "Butter portion", {"butter": 10}, 10, 2, ["veg", "side"]),

    # ---- Snacks
    ("noodles", "Noodles", {"semolina": 60, "oil": 7, "cabbage": 20}, 150, 2, ["veg", "snack"]),
    ("pav_bhaji", "Pav bhaji",
     {"bread_white": 50, "potato": 60, "peas": 20, "butter": 10, "tomato": 25}, 175, 1, ["veg", "snack"]),
    ("samosa", "Samosa", {"atta": 25, "potato": 40, "oil": 12}, 70, 2, ["veg", "snack"]),
    ("pakoda", "Pakoda", {"besan": 30, "onion": 25, "oil": 12}, 60, 2, ["veg", "snack"]),
    ("cutlet", "Cutlet", {"potato": 45, "besan": 12, "oil": 9}, 55, 4, ["veg", "snack"]),
    ("corn_chat", "Corn chat", {"peas": 60, "onion": 15, "tomato": 15}, 90, 2, ["veg", "snack"]),
    ("ratlami_sev", "Ratlami sev", {"besan": 22, "oil": 10}, 30, 2, ["veg", "snack"]),

    # ---- Everyday extras
    ("plain_curd", "Plain curd", {"curd": 100}, 100, 2, ["veg", "dairy"]),
    ("boondi_raita", "Boondi raita", {"curd": 90, "besan": 10, "oil": 4}, 110, 2, ["veg", "dairy"]),
    ("veg_raita", "Veg raita", {"curd": 90, "carrot": 15, "onion": 10}, 115, 2, ["veg", "dairy"]),
    ("dahi", "Dahi", {"curd": 80}, 80, 2, ["veg", "dairy"]),
    ("milk_glass", "Milk 200 ml", {"milk": 206}, 206, 2, ["veg", "dairy"]),
    ("tea", "Tea", {"milk": 50, "sugar": 8}, 150, 3, ["veg", "beverage"]),
    ("salad", "Salad", {"onion": 25, "tomato": 30, "carrot": 20}, 75, 3, ["veg", "side"]),
    ("onion_chop", "Onion chopped", {"onion": 30}, 30, 2, ["veg", "side"]),
    ("tomato_chop", "Tomato chopped", {"tomato": 30}, 30, 2, ["veg", "side"]),
    ("papad", "Papad", {"besan": 10, "oil": 4}, 14, 2, ["veg", "side"]),
    ("pickle", "Pickle", {"oil": 4}, 12, 2, ["veg", "side"]),
    ("fruit_portion", "Fruit (2 pcs)", {"banana": 100, "apple": 80}, 180, 2, ["veg", "fruit"]),

    # ---- Sweets. One portion, take it or leave it.
    ("kheer", "Kheer", {"milk": 130, "rice_cooked": 25, "sugar": 15}, 160, 1, ["veg", "sweet"]),
    ("moong_halwa", "Moong halwa",
     {"moong_dal": 45, "ghee": 12, "sugar": 20}, 90, 1, ["veg", "sweet"]),
    ("fruit_custard", "Fruit custard",
     {"milk": 100, "sugar": 12, "banana": 35}, 150, 1, ["veg", "sweet"]),
    ("gulab_jamun", "Gulab jamun (2 pcs)",
     {"milk": 40, "atta": 15, "sugar": 30, "ghee": 8}, 90, 1, ["veg", "sweet"]),
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
     {"beef_patty": 85, "burger_bun": 50, "cheddar": 20, "tomato": 15, "onion": 10},
     180, 1, ["meat", "main"]),
    ("cheese_pizza", "Cheese pizza slice",
     {"flour_white": 55, "mozzarella": 35, "marinara": 30, "olive_oil": 3},
     120, 3, ["veg", "main"]),
    ("pasta_marinara", "Pasta marinara",
     {"pasta_cooked": 200, "marinara": 100, "olive_oil": 5},
     305, 2, ["veg", "main"]),
    ("mac_and_cheese", "Macaroni and cheese",
     {"pasta_cooked": 150, "cheddar": 40, "milk_2pct": 40, "butter": 8},
     238, 2, ["veg", "main"]),
    ("grilled_chicken", "Grilled chicken breast",
     {"chicken_breast": 120, "olive_oil": 5}, 125, 1, ["meat", "protein", "main"]),
    ("baked_salmon", "Baked salmon",
     {"salmon": 120, "olive_oil": 4}, 124, 1, ["meat", "fish", "protein", "main"]),
    ("turkey_sandwich", "Turkey sandwich",
     {"bread_wheat": 60, "turkey_deli": 60, "american_cheese": 20,
      "romaine": 10, "tomato": 15}, 165, 1, ["meat", "main"]),
    ("black_bean_bowl", "Black bean and rice bowl",
     {"black_beans": 150, "rice_cooked": 150, "sweetcorn": 40, "tomato": 30},
     370, 1, ["veg", "protein", "main"]),
    ("tofu_stirfry", "Tofu stir fry",
     {"tofu": 120, "bell_pepper": 40, "broccoli": 50, "mushroom": 30,
      "olive_oil": 6}, 246, 1, ["veg", "protein", "main"]),
    ("garden_salad", "Garden salad",
     {"romaine": 60, "tomato": 30, "cucumber": 30, "bell_pepper": 20,
      "ranch_dressing": 15}, 155, 3, ["veg", "side"]),
    ("chickpea_salad", "Chickpea salad",
     {"chickpeas_canned": 120, "cucumber": 40, "tomato": 30, "olive_oil": 5},
     195, 2, ["veg", "protein", "side"]),
    ("french_fries", "French fries", {"fries": 100}, 100, 2, ["veg", "side"]),
    ("steamed_broccoli", "Steamed broccoli", {"broccoli": 90}, 90, 3, ["veg", "side"]),
    ("sweetcorn_side", "Sweetcorn", {"sweetcorn": 90}, 90, 2, ["veg", "side"]),
    ("tomato_soup_bowl", "Tomato soup", {"tomato_soup": 245}, 245, 2, ["veg", "side"]),
    ("dinner_roll", "Dinner roll", {"burger_bun": 40}, 40, 4, ["veg", "staple"]),
    ("scrambled_eggs", "Scrambled eggs", {"egg_scrambled": 100}, 100, 2,
     ["egg", "protein", "breakfast"]),
    ("bacon_strips", "Bacon", {"bacon": 25}, 25, 2, ["meat", "breakfast"]),
    ("oatmeal", "Oatmeal", {"oats_cooked": 230}, 230, 2, ["veg", "breakfast"]),
    ("cereal_bowl", "Cereal with milk",
     {"corn_flakes": 40, "milk_2pct": 200}, 240, 2, ["veg", "dairy", "breakfast"]),
    ("bagel_butter", "Bagel with butter",
     {"bagel": 90, "butter": 10}, 100, 2, ["veg", "breakfast"]),
    ("pancakes_stack", "Pancakes",
     {"pancake": 120, "butter": 8, "sugar": 12}, 140, 2, ["veg", "breakfast"]),
    ("yogurt_parfait", "Yogurt parfait",
     {"yogurt_lowfat": 170, "banana": 50, "almonds": 10}, 230, 2,
     ["veg", "dairy", "breakfast"]),
    ("orange_juice_glass", "Orange juice", {"orange_juice": 240}, 240, 2,
     ["veg", "fruit", "beverage"]),
    ("milk_carton", "Milk carton", {"milk_2pct": 240}, 240, 2,
     ["veg", "dairy", "beverage"]),
    ("apple_whole", "Whole apple", {"apple": 180}, 180, 2, ["veg", "fruit"]),
    ("brownie_square", "Brownie", {"brownie_mix": 56}, 56, 1, ["veg", "sweet"]),
]


# --------------------------------------------------------------------------
# Ingredients SR Legacy simply does not carry.
#
# These are NOT from USDA. They are hand-entered from commonly published
# composition figures, per 100 g, and every one is flagged `proxy` so the
# interface can say so. Replacing them with Indian Food Composition Tables
# (IFCT 2017) values is tracked in TODO.md.
#
# Using a poor USDA substitute would have been worse than admitting the gap:
# whole-milk ricotta, the nearest fresh acid-set cheese, reports 7.5 g protein
# per 100 g against paneer's ~18 g. Understating the single biggest vegetarian
# protein source on the menu would have inflated the very shortfall this
# product exists to measure.
# --------------------------------------------------------------------------

MANUAL_INGREDIENTS = [
    ("paneer", "Paneer", ["veg", "dairy"], {
        "kcal": 265, "protein": 18.3, "fat": 20.8, "satfat": 13.0,
        "carbs": 1.2, "fibre": 0.0, "calcium": 208, "iron": 0.2,
        "magnesium": 22, "potassium": 138, "sodium": 18, "zinc": 1.9,
        "vita": 170, "vitc": 0.0, "vitb12": 0.9, "folate": 8,
    }, "Hand-entered from published paneer composition. SR Legacy has no "
       "equivalent and its nearest cheeses are far off on protein and moisture."),

    ("jaggery", "Jaggery", ["veg", "sugar"], {
        "kcal": 383, "protein": 0.4, "fat": 0.1, "satfat": 0.0,
        "carbs": 98.0, "fibre": 0.0, "calcium": 85, "iron": 4.0,
        "magnesium": 70, "potassium": 1050, "sodium": 30, "zinc": 0.2,
        "vita": 0.0, "vitc": 0.0, "vitb12": 0.0, "folate": 0,
    }, "Hand-entered. Iron in jaggery varies enormously with processing, "
       "roughly 2-11 mg per 100 g; 4 mg is a mid estimate and should not be "
       "leaned on."),
    ("whey_protein", "Whey protein powder", ["veg", "supplement"], {
        "kcal": 380, "protein": 80.0, "fat": 6.0, "satfat": 3.0,
        "carbs": 8.0, "fibre": 0.0, "calcium": 500, "iron": 1.0,
        "magnesium": 80, "potassium": 500, "sodium": 300, "zinc": 3.0,
        "vita": 0.0, "vitc": 0.0, "vitb12": 1.5, "folate": 0,
    }, "Hand-entered from a typical whey concentrate label. Brands vary "
       "widely and fortification differs, so treat the micronutrients as "
       "indicative only."),
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
    ("egg", "Boiled egg", "1 egg", {"egg_boiled": 50}, 4,
     {"IN": 8.0, "US": 0.35}, ["egg", "protein"]),
    ("milk_packet", "Milk", "500 ml packet", {"milk": 500}, 2,
     {"IN": 33.0, "US": 0.75}, ["veg", "dairy"]),
    ("curd_cup", "Curd", "200 g cup", {"curd": 200}, 2,
     {"IN": 25.0}, ["veg", "dairy"]),
    ("paneer_block", "Paneer", "100 g", {"paneer": 100}, 2,
     {"IN": 45.0}, ["veg", "dairy", "protein"]),
    ("whey_scoop", "Whey protein", "30 g scoop", {"whey_protein": 30}, 2,
     {"IN": 60.0, "US": 1.10}, ["veg", "supplement", "protein"]),
    ("peanuts", "Roasted peanuts", "50 g", {"peanut": 50}, 3,
     {"IN": 15.0, "US": 0.60}, ["veg", "protein"]),
    ("peanut_butter", "Peanut butter", "30 g", {"peanut": 30}, 3,
     {"IN": 18.0, "US": 0.45}, ["veg", "protein"]),
    ("boiled_chana", "Boiled chana", "100 g", {"chana": 100}, 3,
     {"IN": 20.0}, ["veg", "protein"]),
    ("rajma_bowl", "Rajma, boiled", "150 g", {"rajma": 150}, 2,
     {"IN": 22.0}, ["veg", "protein"]),
    ("soya_chunks", "Soya chunks", "80 g cooked", {"soybean": 80}, 2,
     {"IN": 14.0}, ["veg", "protein"]),
    ("sprouts_bowl", "Sprouts", "100 g", {"sprouts": 100}, 2,
     {"IN": 15.0}, ["veg"]),
    ("banana", "Banana", "1 banana", {"banana": 100}, 4,
     {"IN": 7.0, "US": 0.30}, ["veg", "fruit"]),
    ("apple", "Apple", "1 apple", {"apple": 150}, 3,
     {"IN": 28.0, "US": 0.90}, ["veg", "fruit"]),
    ("orange", "Orange", "1 orange", {"orange": 130}, 3,
     {"IN": 18.0, "US": 0.80}, ["veg", "fruit"]),
    ("guava", "Guava", "1 guava", {"guava": 150}, 3,
     {"IN": 16.0}, ["veg", "fruit"]),
    ("papaya_bowl", "Papaya, cut", "200 g bowl", {"papaya": 200}, 2,
     {"IN": 25.0}, ["veg", "fruit"]),
    ("dates", "Dates", "40 g", {"dates": 40}, 2,
     {"IN": 25.0, "US": 0.90}, ["veg", "fruit"]),
    ("spinach_side", "Spinach, cooked", "100 g", {"spinach": 100}, 2,
     {"IN": 12.0, "US": 0.90}, ["veg"]),
    ("carrot_stick", "Carrot", "100 g", {"carrot": 100}, 2,
     {"IN": 10.0, "US": 0.50}, ["veg"]),
    # ---- Stocked where the dining-hall preset applies.
    ("greek_yogurt", "Greek yogurt", "170 g cup", {"yogurt_lowfat": 170}, 2,
     {"US": 1.30}, ["veg", "dairy", "protein"]),
    ("string_cheese", "String cheese", "1 stick", {"mozzarella": 28}, 3,
     {"US": 0.50}, ["veg", "dairy", "protein"]),
    ("almonds_pack", "Almonds", "30 g", {"almonds": 30}, 3,
     {"US": 0.55}, ["veg", "protein"]),
    ("baby_carrots", "Baby carrots", "85 g", {"carrot": 85}, 2,
     {"US": 0.60}, ["veg"]),
    ("frozen_broccoli", "Broccoli", "100 g cooked", {"broccoli": 100}, 2,
     {"US": 0.70}, ["veg"]),
    ("black_bean_can", "Black beans", "130 g", {"black_beans": 130}, 2,
     {"US": 0.65}, ["veg", "protein"]),
    ("tofu_block", "Tofu", "120 g", {"tofu": 120}, 2,
     {"US": 1.20}, ["veg", "protein"]),
    ("oj_bottle", "Orange juice", "240 ml", {"orange_juice": 240}, 2,
     {"US": 1.10}, ["veg", "fruit"]),
    ("yogurt_cup_us", "Yogurt", "227 g cup", {"yogurt_lowfat": 227}, 2,
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

    for our_id, name, tags, per_100g, note in MANUAL_INGREDIENTS:
        ingredients[our_id] = {
            "id": our_id,
            "name": name,
            "tags": tags,
            "per100g": {k: float(per_100g[k]) for k, _, _, _ in NUTRIENTS},
            "source": {
                "dataset": "manual estimate, not USDA",
                "fdcId": None,
                "description": note,
            },
            "reported": sorted(per_100g.keys()),
            "proxy": True,
            "proxyNote": note,
        }

    def compose(owner, recipe):
        """Add up one serving from its ingredient grams.

        Returns the nutrient totals plus whether any ingredient involved was a
        proxy, so a dish built on an estimated ingredient inherits the warning
        instead of quietly laundering it into a clean-looking number."""
        totals = {k: 0.0 for k, _, _, _ in NUTRIENTS}
        reasons = []
        for ingredient_id, grams in recipe.items():
            ingredient = ingredients.get(ingredient_id)
            if ingredient is None:
                sys.exit("%s refers to unknown ingredient %r" % (owner, ingredient_id))
            scale = grams / 100.0
            for key, value in ingredient["per100g"].items():
                totals[key] += value * scale
            if ingredient.get("proxy"):
                reasons.append("%s: %s" % (ingredient["name"], ingredient["proxyNote"]))
        return totals, reasons

    dishes = {}
    catalogued = ([(entry, "indian") for entry in DISHES]
                  + [(entry, "american") for entry in US_DISHES])
    for (dish_id, name, recipe, serving_g, cap, tags), cuisine in catalogued:
        tags = list(tags) + [cuisine]
        totals, proxy_reasons = compose("dish %r" % dish_id, recipe)
        is_proxy = bool(proxy_reasons)

        entry = {
            "id": dish_id,
            "name": name,
            "cuisine": cuisine,
            "tags": tags,
            "servingGrams": serving_g,
            "maxServings": cap,
            "perServing": {k: round(v, 4) for k, v in totals.items()},
            "recipe": [{"ingredient": k, "grams": g} for k, g in sorted(recipe.items())],
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
            "recipe": [{"ingredient": k, "grams": g} for k, g in sorted(recipe.items())],
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
            "proxies": (
                "Rows marked proxy have no SR Legacy equivalent and use a named "
                "substitute. They are flagged in the interface rather than "
                "presented as measured."
            ),
        },
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
