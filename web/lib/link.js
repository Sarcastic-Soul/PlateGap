/* Menus in a link.
 *
 * A menu somebody assembled is worth sending to the person who cooks it, and
 * this app has no server to keep it on. So the whole menu goes in the
 * fragment, which the browser never sends anywhere: a link restores it
 * without anything being stored, and without a shortener in the middle.
 *
 * The format is versioned and self-contained. Dish ids appear once in a
 * dictionary and everything else refers to them by position, because a mess
 * menu repeats itself -- rice and roti land on most days -- and a week of
 * full ids runs to well over a thousand characters. Positions are into the
 * link's own dictionary, never into the catalog: a catalog that gained a
 * dish would otherwise silently turn an old link into a different menu, and
 * a link that decodes to the wrong menu is worse than one that fails.
 *
 *   1~<name>~<id,id,id>~mon:0,1.2..3;tue:0.1
 *   version  encoded     dictionary  days, meals separated by dots in the
 *                                    order breakfast lunch snacks dinner
 */

import { CUSTOM, DAY_ORDER, MEALS } from './constants.js';
import { dishCount } from './format.js';
import { state, emptyCustom, isCustom, servedOn } from './store.js';

export const LINK_VERSION = '1';

function encodeText(text) {
  /* encodeURIComponent leaves `~` alone and `~` is our separator. */
  return encodeURIComponent(text).replace(/~/g, '%7E');
}

export function encodeMenu() {
  const index = {};
  const dictionary = [];
  function reference(id) {
    if (!(id in index)) { index[id] = dictionary.length; dictionary.push(id); }
    return index[id];
  }

  const days = [];
  DAY_ORDER.forEach(function (day) {
    const meals = MEALS.map(function (meal) {
      return servedOn(day, meal).map(reference).join(',');
    });
    while (meals.length && meals[meals.length - 1] === '') { meals.pop(); }
    if (meals.length) { days.push(day + ':' + meals.join('.')); }
  });

  if (!days.length) { return ''; }
  return [LINK_VERSION, encodeText(state.custom.name),
    dictionary.join(','), days.join(';')].join('~');
}

/* Throws on anything it cannot read. The caller turns that into a sentence
   rather than a blank screen. */
export function decodeMenu(text) {
  const parts = text.split('~');
  if (parts.length < 4 || parts[0] !== LINK_VERSION) {
    throw new Error('not a menu link this version understands');
  }

  const known = {};
  state.catalog.dishes.forEach(function (dish) { known[dish.id] = true; });

  const dictionary = parts[2] ? parts[2].split(',') : [];
  const custom = emptyCustom();
  custom.name = decodeURIComponent(parts[1]).slice(0, 120);
  const dropped = [];

  parts[3].split(';').forEach(function (chunk) {
    const colon = chunk.indexOf(':');
    const day = chunk.slice(0, colon);
    if (DAY_ORDER.indexOf(day) === -1) { throw new Error('unknown day ' + day); }
    chunk.slice(colon + 1).split('.').forEach(function (list, position) {
      const meal = MEALS[position];
      if (!meal) { throw new Error('too many meals in ' + day); }
      if (!list) { return; }
      list.split(',').forEach(function (token) {
        const at = parseInt(token, 10);
        if (isNaN(at) || at < 0 || at >= dictionary.length) {
          throw new Error('a dish reference points nowhere');
        }
        const id = dictionary[at];
        /* A dish the catalog no longer has is dropped and said out loud.
           Quietly serving somebody a shorter menu than they were sent would
           make every number on the screen wrong by an unknown amount. */
        if (!known[id]) {
          if (dropped.indexOf(id) === -1) { dropped.push(id); }
          return;
        }
        if (custom.days[day][meal].indexOf(id) === -1) {
          custom.days[day][meal].push(id);
        }
      });
    });
  });

  return { custom: custom, dropped: dropped };
}

export function fragment() {
  if (!isCustom()) { return ''; }
  const encoded = encodeMenu();
  if (!encoded) { return ''; }
  return '#' + ['m=' + encoded, 'd=' + state.day, 'diet=' + state.diet,
    'r=' + state.region, 'sex=' + state.sex, 'act=' + state.activity,
    'g=' + state.grams].join('&');
}

export function shareUrl() {
  return window.location.origin + window.location.pathname
    + window.location.search + fragment();
}

/* Keep the address bar holding the menu, so copying the URL is enough.
   `replaceState` leaves no history entry and fires no `hashchange`. */
export function updateFragment() {
  const target = window.location.pathname + window.location.search + fragment();
  state.wroteFragment = fragment();
  try {
    window.history.replaceState(null, '', target);
  } catch (problem) {
    /* `file://` and a few embedded browsers refuse this. The share box
       still shows the link, so nothing important is lost. */
  }
}

function oneOf(values, value) { return values.indexOf(value) === -1 ? null : value; }

/* Restore whatever the fragment carries. Anything unreadable is dropped with
   a sentence rather than allowed to half-apply. Mutates `state` directly and
   says whether it did: the caller redraws once, afterwards. */
export function readFragment() {
  const hash = window.location.hash.replace(/^#/, '');
  if (!hash) { return false; }

  const fields = {};
  hash.split('&').forEach(function (pair) {
    const at = pair.indexOf('=');
    if (at > 0) { fields[pair.slice(0, at)] = pair.slice(at + 1); }
  });
  if (!fields.m) { return false; }

  let decoded;
  try {
    decoded = decodeMenu(fields.m);
  } catch (problem) {
    state.notice = 'That link did not carry a menu this version can read ('
      + problem.message + '). Nothing has been half-applied: what you are '
      + 'looking at is the usual starting preset, and the menu still exists '
      + 'wherever the link came from.';
    return false;
  }

  state.custom = decoded.custom;
  state.menuId = CUSTOM;
  state.prices = {};

  const regions = state.presets.regions.map(function (region) { return region.id; });
  state.day = oneOf(DAY_ORDER, fields.d) || state.day;
  state.diet = oneOf(state.presets.diets, fields.diet) || state.diet;
  state.region = oneOf(regions, fields.r) || state.region;
  state.sex = oneOf(['male', 'female'], fields.sex) || state.sex;
  state.activity = oneOf(['sedentary', 'moderate', 'active'], fields.act) || state.activity;
  const grams = parseInt(fields.g, 10);
  if (!isNaN(grams)) { state.grams = Math.max(700, Math.min(2400, grams)); }

  if (decoded.dropped.length) {
    state.notice = 'This link named ' + dishCount(decoded.dropped.length)
      + ' the catalog no longer has (' + decoded.dropped.join(', ') + '). '
      + 'They are not on the menu that was restored, and every number you are '
      + 'looking at was worked out without them.';
  }
  return true;
}
