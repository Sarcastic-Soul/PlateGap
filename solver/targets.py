"""Daily nutrient targets, by region, sex and activity level.

Two reference systems ship, because PlateGap is meant to be usable outside
the campus it was built on:

  IN  -- ICMR-NIN Recommended Dietary Allowances for Indians, 2020
  US  -- Institute of Medicine / NASEM Dietary Reference Intakes

They disagree, sometimes sharply. Iron for an adult man is 19 mg under ICMR
and 8 mg under the DRI, because the ICMR figure assumes a largely plant-based
diet with poor iron bioavailability. Presenting one number as "the"
requirement would be wrong for half the people who open the app, so the
region picks the reference and the interface says which one it used.

Every figure below is a stated assumption that can be argued with. Nothing
here is derived; they are transcribed values plus two documented adjustments
(activity scaling for energy, and saturated fat as a share of energy).
"""

# Nutrients the catalog carries. Targets only reference these.
KNOWN = (
    "kcal", "protein", "fat", "satfat", "carbs", "fibre", "calcium", "iron",
    "magnesium", "potassium", "sodium", "zinc", "vita", "vitc", "vitb12",
    "folate",
)

# --------------------------------------------------------------------------
# Reference intakes, per day, for an adult aged 19-30 at sedentary activity.
#
# `floor` is a lower bound the plan must reach. `ceiling` is an upper bound it
# must not exceed. A nutrient can have both -- energy does, because a plan
# that overshoots calories to hit a protein floor is not a plan anyone wants.
# --------------------------------------------------------------------------

REFERENCES = {
    "IN": {
        "name": "ICMR-NIN 2020 (India)",
        "citation": "ICMR-NIN, Recommended Dietary Allowances and Estimated "
                    "Average Requirements for Indians, 2020.",
        "energy": {"male": 2110.0, "female": 1660.0},
        "floors": {
            "male": {
                "protein": 54.0, "fibre": 30.0, "calcium": 1000.0,
                "iron": 19.0, "magnesium": 440.0, "potassium": 3500.0,
                "zinc": 17.0, "vita": 1000.0, "vitc": 80.0, "vitb12": 2.2,
                "folate": 300.0,
            },
            "female": {
                "protein": 45.7, "fibre": 30.0, "calcium": 1000.0,
                "iron": 29.0, "magnesium": 370.0, "potassium": 3500.0,
                "zinc": 13.2, "vita": 840.0, "vitc": 65.0, "vitb12": 2.2,
                "folate": 220.0,
            },
        },
        "ceilings": {"sodium": 2000.0},
    },
    "US": {
        "name": "US Dietary Reference Intakes",
        "citation": "Institute of Medicine / NASEM Dietary Reference Intakes; "
                    "sodium is the 2019 Chronic Disease Risk Reduction intake.",
        "energy": {"male": 2400.0, "female": 2000.0},
        "floors": {
            "male": {
                "protein": 56.0, "fibre": 38.0, "calcium": 1000.0,
                "iron": 8.0, "magnesium": 400.0, "potassium": 3400.0,
                "zinc": 11.0, "vita": 900.0, "vitc": 90.0, "vitb12": 2.4,
                "folate": 400.0,
            },
            "female": {
                "protein": 46.0, "fibre": 25.0, "calcium": 1000.0,
                "iron": 18.0, "magnesium": 310.0, "potassium": 2600.0,
                "zinc": 8.0, "vita": 700.0, "vitc": 75.0, "vitb12": 2.4,
                "folate": 400.0,
            },
        },
        "ceilings": {"sodium": 2300.0},
    },
}

# Physical activity multipliers applied to the sedentary energy figure. These
# are coarse by design -- a hostel resident does not know their PAL to two
# decimal places, and pretending otherwise would be false precision.
ACTIVITY = {
    "sedentary": 1.00,
    "moderate": 1.20,
    "active": 1.40,
}

# How far above and below the energy figure a plan may land. A diet plan that
# has to hit a calorie count exactly is not solvable in whole servings.
ENERGY_FLOOR_FRACTION = 0.95
ENERGY_CEILING_FRACTION = 1.10

# How much food and drink a person can actually get through in a day, by
# weight as served. This is the constraint that turns out to bind hardest on a
# well-stocked mess menu: the food to meet every target is on the counter, but
# eating all of it would mean twelve rotis. Without this row the solver
# happily prescribes a plate nobody could finish, and the answer looks fine
# while being useless.
#
# 1400 g is a working assumption, not a measured figure, and the interface
# lets the user change it.
DEFAULT_PLATE_GRAMS = 1400.0

# Saturated fat is capped at a share of the energy ceiling rather than an
# absolute gram figure, following the usual "under 10% of energy" guidance.
SATFAT_ENERGY_SHARE = 0.10
KCAL_PER_GRAM_FAT = 9.0

DEFAULT_PROFILE = {
    "region": "IN",
    "sex": "male",
    "activity": "sedentary",
    "maxPlateGrams": DEFAULT_PLATE_GRAMS,
}


class UnknownProfile(ValueError):
    """The caller asked for a region, sex or activity level we do not carry."""


def _normalise(profile):
    merged = dict(DEFAULT_PROFILE)
    merged.update({k: v for k, v in (profile or {}).items() if v is not None})

    region = str(merged["region"]).upper()
    if region not in REFERENCES:
        raise UnknownProfile(
            "unknown region %r; carried regions are %s"
            % (merged["region"], ", ".join(sorted(REFERENCES))))

    sex = str(merged["sex"]).lower()
    if sex not in REFERENCES[region]["energy"]:
        raise UnknownProfile("unknown sex %r; expected male or female" % merged["sex"])

    activity = str(merged["activity"]).lower()
    if activity not in ACTIVITY:
        raise UnknownProfile(
            "unknown activity %r; expected one of %s"
            % (merged["activity"], ", ".join(ACTIVITY)))

    plate_grams = float(merged.get("maxPlateGrams") or DEFAULT_PLATE_GRAMS)
    if plate_grams <= 0:
        raise UnknownProfile("maxPlateGrams must be positive")

    return region, sex, activity, plate_grams


def targets_for(profile=None):
    """Return the daily targets for one person.

    The shape is deliberately flat, because it becomes LP rows directly:

        {
          "region": "IN",
          "reference": "ICMR-NIN 2020 (India)",
          "citation": "...",
          "energy": 2110.0,
          "floors":   {"protein": 54.0, "kcal": 2004.5, ...},
          "ceilings": {"sodium": 2000.0, "kcal": 2321.0, "satfat": 25.8},
          "limits":   {"plateGrams": 1400.0},
        }

    Floors become `>=` rows and ceilings become `<=` rows. Each one that binds
    gets a shadow price out of the solver, which is the number the interface
    shows: the marginal cost of one more unit of that nutrient.
    """
    region, sex, activity, plate_grams = _normalise(profile)
    reference = REFERENCES[region]

    energy = reference["energy"][sex] * ACTIVITY[activity]

    floors = dict(reference["floors"][sex])
    floors["kcal"] = round(energy * ENERGY_FLOOR_FRACTION, 1)

    ceilings = dict(reference["ceilings"])
    ceilings["kcal"] = round(energy * ENERGY_CEILING_FRACTION, 1)
    ceilings["satfat"] = round(
        ceilings["kcal"] * SATFAT_ENERGY_SHARE / KCAL_PER_GRAM_FAT, 1)

    unknown = (set(floors) | set(ceilings)) - set(KNOWN)
    if unknown:
        raise AssertionError(
            "targets name nutrients the catalog does not carry: %s"
            % ", ".join(sorted(unknown)))

    return {
        "region": region,
        "sex": sex,
        "activity": activity,
        "reference": reference["name"],
        "citation": reference["citation"],
        "energy": round(energy, 1),
        "floors": floors,
        "ceilings": ceilings,
        "limits": {"plateGrams": plate_grams},
    }


def regions():
    """What the interface offers in the region picker."""
    return [
        {"id": key, "name": value["name"], "citation": value["citation"]}
        for key, value in sorted(REFERENCES.items())
    ]
