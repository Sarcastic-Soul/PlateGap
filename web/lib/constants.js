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

/* The tab bar used to carry the full sentence for each screen -- "What each
   rupee buys", "For whoever writes the menu" -- which wrapped onto two lines
   at desktop width and was the first thing anyone saw. The sentence is worth
   keeping, so it became the tooltip and the screen's own heading, and the tab
   carries one word and an icon. */
export const TABS = [
  { id: 'plan', label: 'The gap', icon: 'target',
    hint: 'What it leaves out, and what closing it costs' },
  { id: 'frontier', label: 'Spending', icon: 'trending-down',
    hint: 'What each rupee of it buys' },
  { id: 'audit', label: 'Kitchen', icon: 'chef-hat',
    hint: 'The one menu change worth making' },
  { id: 'build', label: 'Build', icon: 'square-pen',
    hint: 'Make a menu of your own' },
  { id: 'data', label: 'Sources', icon: 'book-open',
    hint: 'Where the numbers come from' }
];
