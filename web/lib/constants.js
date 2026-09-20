/* The vocabulary the interface shares with the solver.
 *
 * `MEALS` is the order `model.MEALS` uses and the order the share link
 * encodes positionally, so the two must not drift.
 */

export const DAY_NAMES = {
  mon: 'Monday', tue: 'Tuesday', wed: 'Wednesday', thu: 'Thursday',
  fri: 'Friday', sat: 'Saturday', sun: 'Sunday'
};

export const DIET_NAMES = {
  all: 'Everything', egg: 'Egg, no meat', veg: 'Vegetarian', vegan: 'Vegan'
};

export const MEALS = ['breakfast', 'lunch', 'snacks', 'dinner'];

export const MEAL_NAMES = {
  breakfast: 'Breakfast', lunch: 'Lunch', snacks: 'Snacks', dinner: 'Dinner'
};

export const DAY_ORDER = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

export const SHORT_DAY = {
  mon: 'Mon', tue: 'Tue', wed: 'Wed', thu: 'Thu', fri: 'Fri', sat: 'Sat', sun: 'Sun'
};

/* The preset select carries this alongside the real presets. It is not a menu
   id the API knows: choosing it makes every request send the menu inline. */
export const CUSTOM = 'custom';

/* The handler refuses a meal with more than this many dishes. Stopping here
   gives a sentence instead of a 400. */
export const MAX_DISHES_PER_MEAL = 40;

export const TABS = [
  { id: 'plan', label: 'The gap' },
  { id: 'frontier', label: 'What each rupee buys' },
  { id: 'audit', label: 'For whoever writes the menu' },
  { id: 'build', label: 'Build a menu' },
  { id: 'data', label: 'Where the numbers come from' }
];
