# Data sources for Indian food composition, portions and student nutrition

Research notes, 2026-09-21. I checked every URL below on that date unless it is
marked otherwise. Anything I could not read at source is marked
**unverified**.

Where PlateGap stands today: `data/build_catalog.py` builds `data/foods.json`
(76 ingredients, 109 dishes) from USDA FoodData Central SR Legacy, which is
public domain. It breaks dishes down into raw-gram recipes and applies USDA
Retention Factors Release 6. Paneer (IFCT L003) and jaggery (IFCT I001) are
hand-entered from IFCT 2017 and carry the `proxy` flag. `servingGrams` is an
estimate tagged with a `servingSource` (counted, ladle, plate and so on). None
of the serving weights were weighed.

## 1. Nutrient composition

### IFCT 2017 (ICMR-NIN): the authoritative table, not openly licensed

- Longvah T, Ananthan R, Bhaskarachary K, Venkaiah K. *Indian Food Composition
  Tables 2017*. National Institute of Nutrition (ICMR), Hyderabad.
- The PDF resolves at https://www.nin.res.in/ebooks/IFCT2017.pdf (12.4 MB,
  HTTP 200, slow server). It covers 542 raw foods measured in six regions. It
  has no cooked dishes.
- **Licence.** The copyright page says: "The use and dissemination of the data
  in this book is encouraged. This publication can be reproduced for personal
  use with full acknowledgment of the source. However, no part of this
  publication can be stored or reproduced in any electronic format for creating
  a product without the prior written permission of the National Institute of
  Nutrition." A public app that ships a machine-readable copy therefore needs
  NIN's permission. This already applies to the two IFCT rows in the catalog. A
  handful of cited values is a much weaker case than bulk redistribution, but
  it is worth a line in the README or an email to NIN (nin@nic.in).
- **Vitamin B12.** IFCT 2017 has B12 for only a few foods: its introduction
  mentions 2 fish and 8 flesh foods. It has no B12 value for paneer, milk or
  curd, which is why the catalog's paneer B12 is still an estimate.

**Machine-readable community extraction: nodef/ifct2017**

- https://github.com/nodef/ifct2017. Main table:
  https://raw.githubusercontent.com/nodef/ifct2017/main/compositions/index.csv
  (542 rows × 421 columns, one `_e` error column per nutrient). Also on npm as
  `ifct2017` and `@ifct2017/compositions` (v2.0.9, npm licence field "MIT"), and
  on Zenodo (e.g. https://zenodo.org/records/7088121).
- The repo is **AGPL-3.0** (it was MIT before April 2025). That licence covers
  the code. It cannot relicense NIN's data, so the NIN restriction above still
  applies.
- The data was extracted with a PDF-to-Excel converter, then checked by hand.
  Units are normalised to grams, so for example `ca` is g/100 g, not mg.
- **Accuracy check.** I compared water, protein and energy against the PDF text
  for 284 foods I could parse cleanly. Everything matched except **L003
  Paneer**. In the CSV, paneer has fat 14.78, carbs 12.41 and energy 1079 kJ.
  The PDF prints fat 24.78±0.17, carbs 2.41±0.12 and energy 1278±61 kJ. The
  catalog's hand-entered paneer matches the PDF and is correct. If the CSV is
  ever adopted, spot-check it against the PDF, starting with paneer.

### Indian Nutrient Databank (INDB): about 1,000 cooked recipes

- Vijayakumar A, Dubasi HB, Awasthi A, Jaacks LM. "Development of an Indian Food
  Composition Database." *Current Developments in Nutrition* 2024;8(7):103790.
  doi:10.1016/j.cdnut.2024.103790. The article is CC BY.
  https://pmc.ncbi.nlm.nih.gov/articles/PMC11277795
- Data and code: https://github.com/lindsayjaacks/Indian-Nutrient-Databank-INDB-
  (I verified that the raw URLs download). The main files are `INDB.xlsx` (1,014
  recipes × 42 nutrients, per 100 g and per serving unit), `recipes.xlsx`
  (ingredient lines with amount, unit and food code),
  `recipes_servingsize.xlsx`, `Units.xlsx` (household-measure conversions) and
  `INDB.do` (Stata code). The Anuvaad portal
  (https://www.anuvaad.org.in/indian-nutrient-databank/) timed out from here:
  **unverified**.
- **Licence: unclear.** The GitHub repo has no LICENSE file. The paper says the
  files are "publicly and freely available", which falls short of a licence
  grant. The recipe values are also computed mostly from IFCT 2017 and 2004, so
  NIN's restriction plausibly carries over. For that reason I did **not** copy
  it into `data/external/`.
- **Recipe sources.** 490 recipes come from Khanna et al., *The Art & Science
  of Cooking* (5th ed., 2007) and 378 from Raina et al., *Basic Food
  Preparation* (4th ed., 2011). The rest are about 150 web recipes. For
  ingredients, IFCT 2017 is used first, then IFCT 2004, then UK CoFID 2021, then
  USDA FDC. It also applies USDA retention factors, the same approach PlateGap
  already takes.
- **Nutrients.** Energy, carbohydrate, protein, fat, free sugar, fibre, SFA,
  MUFA and PUFA, cholesterol, 11 minerals, vitamins A, E, D2, D3, K1 and K2,
  B1–B7, folate and vitamin C. **There is no vitamin B12**, one of the
  nutrients PlateGap most needs, so INDB cannot replace USDA for B12.
- **Problems I found in the data. Do not ingest it blindly:**
  - The frying medium is counted in full. Paneer pakora includes 480 ml of
    sunflower oil "for deep frying", which gives about 4,640 kcal per plate.
    Samosa, bonda, cutlets and kofta curries are inflated the same way, running
    800 to 4,700 kcal per serving.
  - Per 100 g means per 100 g of summed *raw* ingredients, including cooking
    water. The code applies no cooking-yield or moisture-loss correction. For
    example, the boiled egg includes 100 ml of boiling water, so the per-100 g
    figure is diluted about 3×.
  - Some ingredient lines are duplicated. Paneer pakora lists salt three times
    and garam masala twice.
  - A serving is `recipe total ÷ no_of_servings`, labelled with a unit such as
    "bowl", "plate" or "chapati". There is **no gram weight per serving**. 82
    recipes have no serving size at all.
- **What it is good for.** `recipes.xlsx` gives PlateGap independent,
  textbook-sourced raw-ingredient recipes to cross-check its own decompositions
  against: dal, rajma, aloo gobhi, egg curry, poha, upma, sambar, idli and dosa
  are all there. For dishes that are not fried, the per-serving energy and
  protein make a reasonable sanity band.

### Others

- **Nutritive Value of Indian Foods** (Gopalan et al., NIN, revised 2004). This
  is IFCT's predecessor. It is print only, and INDB uses it as a fallback. It is
  not worth pursuing separately.
- **USDA FNDDS** (Survey foods in FoodData Central, public domain). It includes
  a few Indian dishes with B12 and portion weights. For example, "Dal" (fdcId
  2707427, FNDDS code 41305050) has 145 kcal and 8.6 g protein per 100 g, B12 of
  0, and "1 cup = 240 g". There is also "Bread, naan" (2707613). Since the
  licence is compatible and the pipeline already reads FDC, this is the easiest
  place to borrow a dish-level B12 or portion figure.
- **UK CoFID 2021** (McCance & Widdowson), under the Open Government Licence.
  https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid
  It has some Indian and takeaway dishes and B12. INDB uses it for 144
  ingredients.
- **Kaggle "Indian Food Nutritional Values Dataset (2025)"**
  (https://www.kaggle.com/datasets/batthulavinay/indian-food-nutrition) is a
  cleaned copy of INDB. It has the same licence problem as INDB and adds nothing.
- I found no FSSAI composition dataset worth using.

## 2. Portion and serving sizes

What I verified at source:

| Source | What it gives | Value |
|---|---|---|
| ICMR-NIN *Dietary Guidelines for Indians 2024*, Annexure I | Standard katori volumes used by NIN | Large 360 ml, **medium 200 ml**, small 155 ml and 115 ml; tablespoon 15 g, teaspoon 5 g. The meal plans use "1 cup/Katori = 200 ml" |
| DGI 2024, Table 1.2a ("My Plate for the Day", 2000 kcal, vegetarian) | Daily **raw** weights by food group | Cereals 250 g, pulses 85 g, milk/curd 300 ml, vegetables and GLV 400 g, fruit 100 g, nuts 35 g, fats and oils 27 g. Gives about 72 g protein |
| DGI 2024, Table 1.2b (non-vegetarian) | Same | Cereals 260 g, pulses 55 g, chicken/meat 70 g, milk 300 ml, vegetables 400 g, fruit 100 g, nuts 30 g, oil 27 g |
| INDB `recipes.xlsx` + `INDB.xlsx` | Implied grams per unit (raw-ingredient basis, including water; see caveats above) | Chapati about 36 g (80 g atta + water + 1 tsp ghee, divided); idli about 25 g; plain dosa about 36 g; plain paratha about 56 g; boiled rice "plate" about 300 g; egg 50 g raw |
| USDA FNDDS "Dal" | Portion weight | 1 cup = 240 g |

DGI 2024 PDF: https://agritech.tnau.ac.in/nutrition/pdf/DGI_07th_May_2024_fin.pdf
(verified, 24 MB). NIN's own copy at
https://nin.res.in/dietaryguidelines/pdfjs/locale/DGI_2024.pdf returns 200 but
is very slow. DGI carries the same "no electronic product without permission"
clause as IFCT, so cite its numbers rather than bundling the PDF.

DGI 2024 gives raw weights per food group, not cooked weights per dish. To
convert, a medium 200 ml katori of dal or sabzi comes to roughly 180–200 g
cooked, taking density as close to water. That conversion is **our inference,
not NIN's**.

Published portion-weight papers I found but could not read in full (**values
unverified**; both publisher sites refused the connection or returned 403):

- Sharma S, Chadha R. "Assessment of Portion Sizes of Food Items Commonly
  Consumed by Urban Indian Adults: A Preliminary Study." *Curr Res Nutr Food Sci*
  2020;8(1). doi:10.12944/CRNFSJ.8.1.17. Delhi adults aged 25–60, measured
  portions.
- Mahajani K, Jain, Dhaka. "Portion Size Estimation of Indian Flat Breads in
  Terms of Weight." *IJCMAS* 2019;8(2). doi:10.20546/ijcmas.2019.802.093.
  Weighed roti, paratha and poori.
- Dr. Mohan's *Atlas of Indian Foods* (https://drmohans.com/atlas-of-indian-foods/)
  covers 247 items in grams, e.g. a dosa at 55–80 g according to a search
  snippet. It is commercial and copyrighted.

I found no published study that weighed **mess or hostel ladle portions**.
PlateGap's `ladle` estimates are therefore not contradicted by anything, but
they are not supported by anything either. The honest path is to weigh them: a
kitchen scale, one mess and a week of meals.

How the catalog compares: its roti (35 g) matches INDB's chapati (36 g). Egg
50 g matches INDB and DGI. `plain_rice` at 150 g is half of INDB's 300 g
"plate", which is plausible for one ladle when refills are allowed. `idli` at
60 g reads as two idlis at INDB's 25–35 g each; check that the dish is labelled
that way.

## 3. Context: student nutritional status

Verified at source or from a peer-reviewed abstract:

- **Anaemia, NFHS-5 (2019–21).** Women aged 15–49: 57.0%. Adolescent girls aged
  15–19: 59.1%. Men aged 15–49: 25.0%. Adolescent boys aged 15–19: 31.1%.
  Source: NFHS-5 national factsheet, as quoted by EPW Engage
  (https://www.epw.in/engage/article/examining-prevalence-anaemia-india) and the
  PIB Anaemia Mukt Bharat release. The factsheet has no single 20–24 figure. The
  NFHS-5 national report tables by age would give one, but I did not get it:
  **unverified**.
- **B12 and folate, adolescents 10–19 (CNNS 2016–18).** B12 deficiency 31.0%
  (95% CI 28.7–33.5, n = 11,748). Folate deficiency 35.6% (n = 13,621). Boys are
  about 8 points higher than girls for B12. Source: Shalini T et al., *Nutrients*
  2023;15(13):3026, doi:10.3390/nu15133026 (CC BY).
- **B12, young vegetarian graduates.** n = 119 in Pune. 50% had serum B12 below
  148 pmol/l. Low holoTC was found in 70% of men and 50% of women. Source: Naik
  S, Mahalle N, Bhide V. *Br J Nutr* 2018;119(6):629–635.
  doi:10.1017/S0007114518000090.

Hostel-diet studies (**unverified**: full text was unreachable, and the numbers
come from search snippets only):

- Ritu Priya, Mukul Sinha. "Adequacy of Hostel Diet in Terms of Nutrient
  Supply." *IJCMAS* 2021;10(1). A 24-hour recall of university hostel residents
  compared with ICMR RDA 2010. The snippet reports that, relative to girls, boys
  ate more protein (+28.8%) and iron (+42.1%), and less B12 (−83%) and folate
  (−14.1%). It is not clear from the snippet whether these are differences
  between the sexes or gaps against the RDA.
- Older primary data does exist: Banerjee & Biswas, *IJMR* 1957, on the cooked
  diet at the Eden Hindu Hostel in Calcutta, and Pathak, *Indian Med Gaz* 1948,
  on medical-college hostel students (PMC5190275). These are useful as history,
  not as ground truth.

Taken together: I found no modern, open, peer-reviewed dataset of analysed
nutrients in Indian hostel mess menus. The defensible way to frame PlateGap's
context is anaemia from NFHS-5 plus B12 from CNNS. A claim that mess food is
specifically short on B12, iron or protein should cite those national figures
and PlateGap's own menu analysis. Do not cite a hostel study we have not read.

## Recommended plan

1. **Keep USDA SR Legacy as the backbone.** It is public domain, carries B12,
   and the pipeline and retention factors already work. None of the Indian
   sources is both openly licensed and complete enough to replace it.
2. **Use IFCT 2017 for single Indian ingredients where USDA has no good
   equivalent,** as is already done for paneer and jaggery. Candidates are
   besan, the specific dals (toor, masoor, moong, chana), atta, soya chunks and
   the Indian leafy greens. Hand-cite the code and table per row, as
   `MANUAL_INGREDIENTS` already does. Take values from the NIN PDF, not the
   nodef CSV (see the paneer error), or use the CSV only after checking it
   against the PDF. Before going further, get NIN's permission or add a clear
   attribution and non-commercial note.
3. **Use INDB as a validator, not a source.** A small script (outside
   `data/`, reading the xlsx from a path the way `--sr` works today) would
   match about 30 PlateGap dishes to INDB codes (e.g. `dal_tadka` → BFP/ASC dal
   rows, `roti` → ASC096, `egg_curry` → BFP240, `poha` → BFP044). It would
   report the kcal and protein per 100 g of raw ingredients side by side and
   exclude deep-fried recipes. Use it to flag recipe decompositions that are far
   off. Record the INDB code in each dish's note as a second citation.
4. **Anchor serving grams to cited volumes.** Add a `katori` serving source
   that uses DGI 2024's 200 ml medium katori (and 155 ml or 115 ml small), and
   cite DGI in `SERVING_SOURCES`. Cross-cite counted items (roti, idli, dosa,
   egg) to INDB or the Mahajani 2019 paper once read. The most valuable data
   anyone could add is a week of weighed ladles from one real mess.
5. **B12 for Indian dairy.** Neither IFCT nor INDB has it. Keep USDA or FNDDS
   dairy for B12. For paneer, USDA "cheese, cottage" or ricotta per 100 g
   protein is a stated proxy, and it should stay flagged.
6. **Context numbers for the pitch:** NFHS-5 anaemia at 59.1% (girls aged
   15–19) and 31.1% (boys aged 15–19), and CNNS B12 deficiency at 31.0% of
   adolescents, with citations as above.

## Downloads

Nothing went into `data/external/`. None of the Indian datasets is clearly
openly licensed: IFCT and DGI reserve electronic reuse, INDB has no licence and
is derived from IFCT, and nodef is AGPL over NIN data. USDA FNDDS and UK CoFID
are open but only marginally useful, and PlateGap already fetches FDC data on
demand. INDB can be fetched for local validation with:

```
for f in INDB.xlsx recipes.xlsx recipes_servingsize.xlsx Units.xlsx; do
  curl -LO https://raw.githubusercontent.com/lindsayjaacks/Indian-Nutrient-Databank-INDB-/main/$f
done
```
