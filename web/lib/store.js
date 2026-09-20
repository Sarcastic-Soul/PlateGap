/* One mutable state object, and a way for components to hear about it.
 *
 * Preact is doing the rendering now, but the state it renders is deliberately
 * not held in a component. Everything on screen -- five tabs, a sidebar, a
 * builder -- answers to the same handful of fields, and a shared link has to
 * be able to set all of them at once before the first render. A module-level
 * object with a subscription is the smallest thing that does that; there is
 * no prop drilling and no context, and `state` reads the same way in a helper
 * as it does in a component.
 */

import { useState, useEffect } from '../vendor/preact.js';
import { CUSTOM, DAY_ORDER, MEALS } from './constants.js';

function emptyDays() {
  const days = {};
  DAY_ORDER.forEach(function (day) {
    days[day] = {};
    MEALS.forEach(function (meal) { days[day][meal] = []; });
  });
  return days;
}

export function emptyCustom() {
  return { name: '', days: emptyDays() };
}

export const state = {
  presets: null,
  catalog: null,
  menuId: 'iiit',
  day: 'mon',
  diet: 'egg',
  region: null,
  sex: 'male',
  activity: 'sedentary',
  grams: 1400,
  students: 600,
  prices: {},
  tab: 'plan',
  /* The menu being assembled in the browser. It exists whether or not it is
   * the menu being solved, so switching to a preset and back does not throw
   * away what someone typed. */
  custom: emptyCustom(),
  picker: null,
  notice: null,
  wroteFragment: '',
  failure: null
};

const listeners = new Set();

/* Apply a change and redraw. Every mutation goes through here, including the
   ones that only nudge a nested field -- pass nothing and it is a plain
   "I have already edited `state`, please redraw". */
export function update(change) {
  if (change) { Object.assign(state, change); }
  listeners.forEach(function (notify) { notify(); });
}

export function useStore() {
  const [, bump] = useState(0);
  useEffect(function () {
    const notify = function () { bump(function (n) { return n + 1; }); };
    listeners.add(notify);
    return function () { listeners.delete(notify); };
  }, []);
  return state;
}

/* ------------------------------------------------------- reading the menu */

export function isCustom() { return state.menuId === CUSTOM; }

export function currentMenu() {
  if (!state.presets) { return null; }
  if (isCustom()) {
    return {
      id: CUSTOM,
      name: state.custom.name || 'Your menu',
      subtitle: 'Assembled here, in the browser. Nothing is stored anywhere.',
      providerNoun: 'this menu',
      region: state.region || 'IN',
      /* Every day is offered whether or not it has anything on it yet, so
         the day control does not fight the person filling it in. */
      days: DAY_ORDER.slice()
    };
  }
  return state.presets.menus.find(function (menu) {
    return menu.id === state.menuId;
  }) || null;
}

/* What to call the place the food comes from. A hostel mess, a dining hall and
   a canteen are the same thing to the solver and three different words to the
   person reading the screen, so the menu carries its own noun. */
export function providerNoun() {
  const menu = currentMenu();
  return (menu && menu.providerNoun) || 'your meal plan';
}

/* ---------------------------------------------------------- the built menu */

export function servedOn(day, meal) { return state.custom.days[day][meal]; }

export function dishesOn(day) {
  return MEALS.reduce(function (total, meal) {
    return total + servedOn(day, meal).length;
  }, 0);
}

export function customTotal() {
  return DAY_ORDER.reduce(function (total, day) { return total + dishesOn(day); }, 0);
}

/* Seed the builder from a preset, so "start from my mess menu and change
   three things" is possible. The everyday items a preset serves regardless of
   the day are folded into each day rather than kept as a separate list: in the
   builder they are chips you can see and remove, which is the whole point of
   opening a menu up to editing. */
export function seedFromPreset(preset, maxPerMeal) {
  const seeded = emptyCustom();
  seeded.name = preset.name;
  DAY_ORDER.forEach(function (day) {
    const offered = (preset.offerings || {})[day] || {};
    MEALS.forEach(function (meal) {
      const everyDay = (preset.daily || {})[meal] || [];
      const thisDay = offered[meal] || [];
      const dishes = [];
      everyDay.concat(thisDay).forEach(function (id) {
        if (dishes.indexOf(id) === -1 && dishes.length < maxPerMeal) {
          dishes.push(id);
        }
      });
      seeded.days[day][meal] = dishes;
    });
  });
  return seeded;
}

/* A menu the parser read, in the shape the builder edits.
 *
 * The everyday items are folded into each day exactly as `seedFromPreset`
 * folds a preset's, and for the same reason: in the builder they are chips
 * you can see and remove.
 *
 * Only days the menu actually carries are filled. A timetable that covers
 * Monday to Friday must not come back with breakfast on Saturday just
 * because the mess serves bread every day -- that would be the parser
 * inventing a meal, which is the one thing it is built not to do. */
export function customFromMenu(menu, maxPerMeal) {
  const seeded = emptyCustom();
  seeded.name = menu.name || '';
  DAY_ORDER.forEach(function (day) {
    const offered = (menu.days || {})[day];
    if (!offered) { return; }
    MEALS.forEach(function (meal) {
      const dishes = [];
      ((menu.daily || {})[meal] || []).concat(offered[meal] || [])
        .forEach(function (id) {
          if (dishes.indexOf(id) === -1 && dishes.length < maxPerMeal) {
            dishes.push(id);
          }
        });
      seeded.days[day][meal] = dishes;
    });
  });
  return seeded;
}

/* The inline menu the API takes in place of a preset id.
 *
 * Only days with something on them are sent, plus the day being asked about
 * -- the handler checks that the day it is given is one the menu carries,
 * and it wants between one and seven of them. An empty day is legal and
 * means exactly what it says: nothing is served, so everything is bought. */
export function customPayload() {
  const days = {};
  DAY_ORDER.forEach(function (day) {
    const meals = {};
    let any = false;
    MEALS.forEach(function (meal) {
      if (servedOn(day, meal).length) {
        meals[meal] = servedOn(day, meal).slice();
        any = true;
      }
    });
    if (any) { days[day] = meals; }
  });
  if (!days[state.day]) { days[state.day] = {}; }
  return {
    name: state.custom.name || 'Your menu',
    region: state.region || 'IN',
    days: days
  };
}

/* A menu with nothing on it at all, used to ask the solver the counterfactual
   question: what would this day cost if there were no meal plan? */
export function noMealPlanPayload() {
  const days = {};
  days[state.day] = {};
  return { name: 'No meal plan', region: state.region || 'IN', days: days };
}

/* Everything a solve depends on, as one string.
 *
 * Tabs re-fetch when this changes and not otherwise, which is what stops a
 * click on a chip that changes nothing from re-solving, and what makes the
 * stale-answer problem disappear: a fetch belongs to a key, and an answer
 * that arrives under a key nobody is asking about any more is dropped by the
 * effect that started it. */
export function solveKey() {
  return JSON.stringify([
    state.menuId, state.day, state.diet, state.region, state.sex,
    state.activity, state.grams, state.prices,
    isCustom() ? customPayload() : null
  ]);
}
