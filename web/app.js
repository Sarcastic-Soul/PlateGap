/* PlateGap front end.
 *
 * No framework and no build step. The whole app is three files, served as
 * static objects from CloudFront, and every number it shows came out of the
 * solver rather than out of this file. Where something is an assumption, it
 * says so on screen.
 */
'use strict';

/* In production config.js carries the Function URL. Falling back to this
 * page's own origin is what makes `scripts/dev_server.py` work: it serves the
 * files and answers the POSTs on the same port, whatever port that is. */
var API = window.PLATEGAP_API || (window.location.origin + '/');

var DAY_NAMES = {
  mon: 'Monday', tue: 'Tuesday', wed: 'Wednesday', thu: 'Thursday',
  fri: 'Friday', sat: 'Saturday', sun: 'Sunday'
};

var DIET_NAMES = {
  all: 'Everything', egg: 'Egg, no meat', veg: 'Vegetarian', vegan: 'Vegan'
};

/* The solver's own vocabulary, repeated here only where the interface has to
 * order things. `MEALS` is the order `model.MEALS` uses and the order the
 * share link encodes positionally, so the two must not drift. */
var MEALS = ['breakfast', 'lunch', 'snacks', 'dinner'];
var MEAL_NAMES = {
  breakfast: 'Breakfast', lunch: 'Lunch', snacks: 'Snacks', dinner: 'Dinner'
};
var DAY_ORDER = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
var SHORT_DAY = {
  mon: 'Mon', tue: 'Tue', wed: 'Wed', thu: 'Thu', fri: 'Fri', sat: 'Sat', sun: 'Sun'
};

/* The preset select carries this alongside the real presets. It is not a
 * menu id the API knows: choosing it makes every request send the menu
 * inline instead. */
var CUSTOM = 'custom';

/* The handler refuses a meal with more than this many dishes. Stopping here
 * gives a sentence instead of a 400. */
var MAX_DISHES_PER_MEAL = 40;

/* Seed the builder from a preset, so "start from my mess menu and change
   three things" is possible. The everyday items a preset serves regardless of
   the day are folded into each day rather than kept as a separate list: in the
   builder they are chips you can see and remove, which is the whole point of
   opening a menu up to editing. */
function seedFromPreset(preset) {
  var seeded = emptyCustom();
  seeded.name = preset.name;
  DAY_ORDER.forEach(function (day) {
    var offered = (preset.offerings || {})[day] || {};
    MEALS.forEach(function (meal) {
      var everyDay = (preset.daily || {})[meal] || [];
      var thisDay = offered[meal] || [];
      var dishes = [];
      everyDay.concat(thisDay).forEach(function (id) {
        if (dishes.indexOf(id) === -1 && dishes.length < MAX_DISHES_PER_MEAL) {
          dishes.push(id);
        }
      });
      seeded.days[day][meal] = dishes;
    });
  });
  return seeded;
}

function emptyCustom() {
  var days = {};
  DAY_ORDER.forEach(function (day) {
    days[day] = {};
    MEALS.forEach(function (meal) { days[day][meal] = []; });
  });
  return { name: '', days: days };
}

var state = {
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
  wroteFragment: ''
};

var cache = {};

/* Which render the answers on their way back belong to.
 *
 * Every tab is one or more POSTs and nothing sequences them, so moving two
 * controls quickly can land the first answer after the second and leave the
 * screen showing numbers for a question nobody asked. Each render takes a
 * ticket and a reply with a stale one is dropped. */
var generation = 0;

function stale(token) { return token !== generation; }

/* ---------------------------------------------------------------- plumbing */

function post(action, extra) {
  var body = Object.assign({
    action: action,
    day: state.day,
    diet: state.diet,
    prices: state.prices,
    profile: {
      region: state.region,
      sex: state.sex,
      activity: state.activity,
      maxPlateGrams: state.grams
    }
  }, isCustom() ? { menu: customPayload() } : { menuId: state.menuId },
     extra || {});

  return fetch(API, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body)
  }).then(function (response) {
    return response.json().then(function (data) {
      if (!response.ok) { throw new Error(data.error || 'request failed'); }
      return data;
    });
  });
}

function el(tag, attrs, children) {
  var node = document.createElement(tag);
  Object.keys(attrs || {}).forEach(function (key) {
    if (key === 'class') { node.className = attrs[key]; }
    else if (key === 'html') { node.innerHTML = attrs[key]; }
    else if (key === 'text') { node.textContent = attrs[key]; }
    else if (key.slice(0, 2) === 'on') { node.addEventListener(key.slice(2), attrs[key]); }
    else if (attrs[key] !== null && attrs[key] !== undefined) {
      node.setAttribute(key, attrs[key]);
    }
  });
  (children || []).forEach(function (child) {
    if (child === null || child === undefined) { return; }
    node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
  });
  return node;
}

function money(value, currency) {
  if (value === null || value === undefined) { return '—'; }
  var decimals = currency ? currency.decimals : 2;
  var symbol = currency ? currency.symbol : '';
  return symbol + value.toFixed(decimals);
}

/* Shadow prices are often far smaller than one unit of currency. Rounding a
 * marginal of 0.0422 to the nearest rupee prints "0", which reads as "this is
 * worth nothing" when it means the opposite. So small amounts get however
 * many places they need to say something. */
function preciseMoney(value, currency) {
  if (value === null || value === undefined) { return '—'; }
  var symbol = currency ? currency.symbol : '';
  var decimals = currency ? currency.decimals : 2;
  var magnitude = Math.abs(value);
  /* A spend that came back as 4e-17 is a floating point residue, not a
     price. Left alone the rule below dutifully prints it as "$0.0000",
     which reads like a number that was measured. */
  if (magnitude < 1e-9) { return symbol + (0).toFixed(decimals); }
  if (magnitude > 0 && magnitude < 1) {
    decimals = Math.max(decimals, Math.min(4, 2 - Math.floor(Math.log(magnitude) / Math.LN10)));
  } else {
    decimals = Math.max(decimals, magnitude < 10 ? 2 : 0);
  }
  return symbol + value.toFixed(decimals);
}

function plural(count, word) {
  return count + ' ' + word + (count === 1 ? '' : 's');
}

/* `plural` would say "7 dishs". */
function dishCount(count) {
  return count + (count === 1 ? ' dish' : ' dishes');
}

/* Names for the identifiers the solver speaks in. A shadow price on "vitc" is
 * not something to put in front of a person. */
var NAMES = { nutrients: {}, units: {}, dishes: {} };

function nutrientName(id) { return NAMES.nutrients[id] || id; }
function nutrientUnit(id) { return NAMES.units[id] || ''; }
function dishName(id) { return NAMES.dishes[id] || id; }

function round(value, places) {
  var factor = Math.pow(10, places || 0);
  return Math.round(value * factor) / factor;
}

function isCustom() { return state.menuId === CUSTOM; }

function currentMenu() {
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
  for (var i = 0; i < state.presets.menus.length; i++) {
    if (state.presets.menus[i].id === state.menuId) { return state.presets.menus[i]; }
  }
  return null;
}

/* ------------------------------------------------------- the built menu */

function servedOn(day, meal) { return state.custom.days[day][meal]; }

function dishesOn(day) {
  return MEALS.reduce(function (total, meal) {
    return total + servedOn(day, meal).length;
  }, 0);
}

function customTotal() {
  return DAY_ORDER.reduce(function (total, day) { return total + dishesOn(day); }, 0);
}

/* The inline menu the API takes in place of a preset id.
 *
 * Only days with something on them are sent, plus the day being asked about
 * -- the handler checks that the day it is given is one the menu carries,
 * and it wants between one and seven of them. An empty day is legal and
 * means exactly what it says: nothing is served, so everything is bought. */
function customPayload() {
  var days = {};
  DAY_ORDER.forEach(function (day) {
    var meals = {};
    var any = false;
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
function noMealPlanPayload() {
  var days = {};
  days[state.day] = {};
  return { name: 'No meal plan', region: state.region || 'IN', days: days };
}

/* What to call the place the food comes from. A hostel mess, a dining hall and
   a canteen are the same thing to the solver and three different words to the
   person reading the screen, so the menu carries its own noun. */
function providerNoun() {
  var menu = currentMenu();
  return (menu && menu.providerNoun) || 'your meal plan';
}

/* ------------------------------------------------------ menus in a link
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

var LINK_VERSION = '1';

function encodeText(text) {
  /* encodeURIComponent leaves `~` alone and `~` is our separator. */
  return encodeURIComponent(text).replace(/~/g, '%7E');
}

function encodeMenu() {
  var index = {};
  var dictionary = [];
  function reference(id) {
    if (!(id in index)) { index[id] = dictionary.length; dictionary.push(id); }
    return index[id];
  }

  var days = [];
  DAY_ORDER.forEach(function (day) {
    var meals = MEALS.map(function (meal) {
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
function decodeMenu(text) {
  var parts = text.split('~');
  if (parts.length < 4 || parts[0] !== LINK_VERSION) {
    throw new Error('not a menu link this version understands');
  }

  var known = {};
  state.catalog.dishes.forEach(function (dish) { known[dish.id] = true; });

  var dictionary = parts[2] ? parts[2].split(',') : [];
  var custom = emptyCustom();
  custom.name = decodeURIComponent(parts[1]).slice(0, 120);
  var dropped = [];

  parts[3].split(';').forEach(function (chunk) {
    var colon = chunk.indexOf(':');
    var day = chunk.slice(0, colon);
    if (DAY_ORDER.indexOf(day) === -1) { throw new Error('unknown day ' + day); }
    chunk.slice(colon + 1).split('.').forEach(function (list, position) {
      var meal = MEALS[position];
      if (!meal) { throw new Error('too many meals in ' + day); }
      if (!list) { return; }
      list.split(',').forEach(function (token) {
        var at = parseInt(token, 10);
        if (isNaN(at) || at < 0 || at >= dictionary.length) {
          throw new Error('a dish reference points nowhere');
        }
        var id = dictionary[at];
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

function fragment() {
  if (!isCustom()) { return ''; }
  var encoded = encodeMenu();
  if (!encoded) { return ''; }
  return '#' + ['m=' + encoded, 'd=' + state.day, 'diet=' + state.diet,
    'r=' + state.region, 'sex=' + state.sex, 'act=' + state.activity,
    'g=' + state.grams].join('&');
}

function shareUrl() {
  return window.location.origin + window.location.pathname
    + window.location.search + fragment();
}

/* Keep the address bar holding the menu, so copying the URL is enough.
   `replaceState` leaves no history entry and fires no `hashchange`. */
function updateFragment() {
  var target = window.location.pathname + window.location.search + fragment();
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
   a sentence rather than allowed to half-apply. */
function readFragment() {
  var hash = window.location.hash.replace(/^#/, '');
  if (!hash) { return false; }

  var fields = {};
  hash.split('&').forEach(function (pair) {
    var at = pair.indexOf('=');
    if (at > 0) { fields[pair.slice(0, at)] = pair.slice(at + 1); }
  });
  if (!fields.m) { return false; }

  var decoded;
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

  var regions = state.presets.regions.map(function (region) { return region.id; });
  state.day = oneOf(DAY_ORDER, fields.d) || state.day;
  state.diet = oneOf(state.presets.diets, fields.diet) || state.diet;
  state.region = oneOf(regions, fields.r) || state.region;
  state.sex = oneOf(['male', 'female'], fields.sex) || state.sex;
  state.activity = oneOf(['sedentary', 'moderate', 'active'], fields.act) || state.activity;
  var grams = parseInt(fields.g, 10);
  if (!isNaN(grams)) { state.grams = Math.max(700, Math.min(2400, grams)); }

  if (decoded.dropped.length) {
    state.notice = 'This link named ' + dishCount(decoded.dropped.length)
      + ' the catalog no longer has (' + decoded.dropped.join(', ') + '). '
      + 'They are not on the menu that was restored, and every number you are '
      + 'looking at was worked out without them.';
  }
  return true;
}

/* ------------------------------------------------------------------ pieces */

function stat(value, label) {
  return el('div', { class: 'stat' }, [
    el('div', { class: 'value', text: value }),
    el('div', { class: 'label', text: label })
  ]);
}

function nutrientTable(nutrients) {
  var rows = nutrients.map(function (n) {
    var reference = n.floor || n.ceiling || 1;
    var fraction = Math.min(1.4, n.got / reference);
    var klass = n.status === 'short' ? 'bar short' : (n.status === 'over' ? 'bar over' : 'bar');
    var target = n.floor !== null && n.floor !== undefined
      ? 'at least ' + round(n.floor, 1)
      : 'at most ' + round(n.ceiling, 1);

    return el('tr', {}, [
      el('td', {}, [
        el('div', {}, [n.name]),
        el('div', { class: 'why', text: target + ' ' + n.unit })
      ]),
      el('td', { class: 'num' }, [round(n.got, 1) + ' ' + n.unit]),
      el('td', { style: 'width:36%' }, [
        el('div', { class: klass }, [
          el('i', { style: 'width:' + (fraction / 1.4 * 100).toFixed(1) + '%' })
        ])
      ]),
      el('td', { class: 'num' }, [
        n.status === 'ok'
          ? el('span', { class: 'pill', text: 'met' })
          : el('span', {
            class: 'pill ' + (n.status === 'short' ? 'short' : 'warn'),
            text: n.status === 'short' ? 'short' : 'over'
          })
      ])
    ]);
  });

  return el('table', {}, [
    el('thead', {}, [el('tr', {}, [
      el('th', {}, ['Nutrient']),
      el('th', { class: 'num' }, ['On the plan']),
      el('th', {}, ['']),
      el('th', { class: 'num' }, [''])
    ])]),
    el('tbody', {}, rows)
  ]);
}

function describeRow(row, currency) {
  var price = preciseMoney(row.shadowPrice, currency);
  if (row.kind === 'limit') {
    return 'Room for another 100 g of food would save '
      + preciseMoney(row.shadowPrice * 100, currency) + ' a day.';
  }
  if (row.kind === 'cap') {
    return 'One more serving of ' + dishName(row.key) + ' — you are at the '
      + 'limit of ' + row.target + ' — would save ' + price + '.';
  }
  if (row.kind === 'floor') {
    return 'The last ' + (nutrientUnit(row.key) || 'unit') + ' of '
      + nutrientName(row.key) + ' costs you ' + price + '.';
  }
  if (row.kind === 'ceiling') {
    return 'You are up against the ' + nutrientName(row.key) + ' ceiling; one '
      + (nutrientUnit(row.key) || 'unit') + ' more headroom would save ' + price + '.';
  }
  if (row.kind === 'budget') {
    return 'Your budget is binding: one more ' + (currency.symbol || 'unit')
      + ' would close ' + price + ' worth of the gap.';
  }
  return row.kind + ' ' + row.key;
}

/* -------------------------------------------------------------------- tabs */

/* The screen for a menu that already meets everything.
 *
 * It is a real answer and a rare one -- the US dining hall on a Friday, for a
 * vegetarian woman who can get through 1800 g -- and the obvious rendering of
 * it is a blank space where the shortfall list would be, which reads like the
 * app broke. Three things are true instead and all three are worth saying:
 * nothing needs buying, the margin is thinner than "every target met" sounds,
 * and the plan is quietly saving real money, which is only visible against
 * what the same targets would cost with no plan at all.
 */
function renderCovered(view, shortfall, answer) {
  var currency = answer.currency;
  var targets = shortfall.targetsMet + shortfall.targetsMissed;
  var eatLimit = answer.targets.limits.plateGrams;
  var usedShare = Math.round(100 * answer.plateGrams / eatLimit);

  /* Filled in when the counterfactual solve lands. The capitalised "Working"
     is what `scripts/capture_demo.py` waits on before it shoots the page. */
  var worth = stat('Working it out',
    'a day to buy the same targets if the plan did not exist');

  view.appendChild(el('div', { class: 'headline' }, [
    stat(targets + ' of ' + targets, 'targets met from ' + providerNoun() + ' alone'),
    stat(preciseMoney(0, currency), 'you need to spend on top of your fee'),
    stat(Math.round(answer.plateGrams) + ' g', 'of food it takes — ' + usedShare
      + '% of what you said you can eat'),
    worth
  ]));

  var floors = answer.nutrients.filter(function (n) { return n.floor; });
  var ceilings = answer.nutrients.filter(function (n) { return n.ceiling; });

  floors.sort(function (a, b) { return a.got / a.floor - b.got / b.floor; });
  var onTheLine = floors.filter(function (n) { return n.got - n.floor < 0.02 * n.floor; });
  var clear = floors.filter(function (n) { return onTheLine.indexOf(n) === -1; });

  var floorItems = clear.slice(0, 4).map(function (n) {
    return el('li', {}, [
      el('b', { text: n.name }),
      ' — ' + round(n.got, 1) + ' ' + n.unit + ', '
        + Math.round(100 * (n.got - n.floor) / n.floor) + '% clear of the '
        + round(n.floor, 1) + ' ' + n.unit + ' floor'
    ]);
  });
  if (onTheLine.length) {
    floorItems.unshift(el('li', {}, [
      el('b', { text: 'Exactly on the line' }),
      ' — ' + onTheLine.map(function (n) { return n.name.toLowerCase(); }).join(', ')
    ]));
  }

  ceilings.sort(function (a, b) { return b.got / b.ceiling - a.got / a.ceiling; });
  var ceilingItems = ceilings.map(function (n) {
    var room = n.ceiling - n.got;
    return el('li', {}, [
      el('b', { text: n.name }),
      room < 0.02 * n.ceiling
        ? ' — ' + round(n.got, 1) + ' of ' + round(n.ceiling, 1) + ' ' + n.unit
          + ', with no headroom left at all'
        : ' — ' + round(n.got, 1) + ' of ' + round(n.ceiling, 1) + ' ' + n.unit
          + ', ' + round(room, 1) + ' ' + n.unit + ' spare'
    ]);
  });

  view.appendChild(el('section', { class: 'panel' }, [
    el('h2', { text: 'How much room that leaves' }),
    el('p', {
      text: 'The plate below is the lightest one that meets every target, and '
        + 'it weighs ' + Math.round(answer.plateGrams) + ' g against the '
        + Math.round(eatLimit) + ' g you said you could manage. Every target '
        + 'is met, and it takes most of a day of eating to meet them.'
    }),
    el('h2', { text: 'Tightest floors' }),
    el('ul', {}, floorItems),
    ceilingItems.length ? el('h2', { text: 'Ceilings' }) : null,
    ceilingItems.length ? el('ul', {}, ceilingItems) : null,
    el('p', {
      class: 'note',
      text: 'A floor sitting exactly on its line is the solver being frugal '
        + 'rather than the menu being thin: this plate is minimised for '
        + 'weight, so it never takes a gram more of anything than it has to. '
        + 'A ceiling on its line is the opposite — that one really is full.'
    })
  ]));

  var panel = el('section', { class: 'panel' }, [
    el('h2', { text: 'What the meal plan is worth' }),
    el('p', { class: 'loading', text: 'Working out what the same targets cost without it…' })
  ]);
  view.appendChild(panel);

  /* The counterfactual: the same solve with nothing served at all, so the
     only way to reach a target is to pay for it. It costs one extra LP and
     only runs on the days that are actually covered. */
  var token = generation;
  post('solve', { menu: noMealPlanPayload() }).then(function (alone) {
    if (stale(token)) { return; }
    panel.innerHTML = '';
    panel.appendChild(el('h2', { text: 'What the meal plan is worth' }));

    if (!alone.feasible) {
      worth.querySelector('.value').textContent = 'out of reach';
      panel.appendChild(el('p', {
        text: 'Nothing you could buy, inside the portion limits on the shop '
          + 'items, reaches every target on this diet without the menu. This '
          + 'menu does something a supermarket on its own cannot.'
      }));
      return;
    }

    worth.querySelector('.value').textContent = preciseMoney(alone.spendExact, currency);
    panel.appendChild(el('p', {
      text: 'Take the meal plan away and buy the same targets yourself, and '
        + 'the cheapest way to do it costs ' + preciseMoney(alone.spendExact, currency)
        + ' a day — ' + money(alone.spendExact * 30, currency) + ' a month. That '
        + 'is what ' + providerNoun() + ' is worth to you on ' + DAY_NAMES[state.day]
        + ', and none of it shows up on a bill.'
    }));
    panel.appendChild(el('table', {}, [
      el('thead', {}, [el('tr', {}, [
        el('th', {}, ['Instead of the menu, buy']),
        el('th', { class: 'num' }, ['Units']),
        el('th', { class: 'num' }, ['Cost'])
      ])]),
      el('tbody', {}, alone.buy.map(function (item) {
        return el('tr', {}, [
          el('td', {}, [item.name, el('div', { class: 'why', text: item.unit })]),
          el('td', { class: 'num', text: round(item.amount, 1) + '×' }),
          el('td', { class: 'num', text: preciseMoney(item.cost, currency) })
        ]);
      }))
    ]));
    panel.appendChild(el('p', {
      class: 'note',
      text: 'This is the cheapest basket that hits the same floors at the same '
        + 'prices, not a grocery bill — nobody eats like a linear program. It '
        + 'is a lower bound on what the plan saves you, which is the honest '
        + 'direction for a number like this to be wrong in.'
    }));
  }).catch(function (problem) {
    if (stale(token)) { return; }
    panel.innerHTML = '';
    worth.querySelector('.value').textContent = '—';
    panel.appendChild(el('h2', { text: 'What the meal plan is worth' }));
    panel.appendChild(el('p', { class: 'note', text: 'Could not work that out: ' + problem.message }));
  });
}

function renderPlan(view) {
  if (askForDishes(view, 'day')) { return; }
  var token = generation;
  Promise.all([post('gap'), post('solve')]).then(function (answers) {
    if (stale(token)) { return; }
    var shortfall = answers[0];
    var answer = answers[1];
    view.innerHTML = '';

    if (!answer.feasible) {
      view.appendChild(el('div', { class: 'error' }, [
        'Even with purchases there is no way to reach every target inside the '
        + 'portion limits on this day. ' + (answer.reason || '')
      ]));
      return;
    }

    var currency = answer.currency;
    var missed = shortfall.targetsMissed;
    var total = shortfall.targetsMet + shortfall.targetsMissed;

    if (missed === 0) {
      renderCovered(view, shortfall, answer);
    } else {
      view.appendChild(el('div', { class: 'headline' }, [
        stat(missed + ' of ' + total, 'targets the menu alone cannot reach'),
        stat(preciseMoney(answer.spendExact, currency), 'a day to close the gap'),
        stat(money(answer.spendExact * 30, currency), 'a month, on top of your fee'),
        stat(Math.round(answer.plateGrams) + ' g', 'of food on the plan')
      ]));

      var items = shortfall.shortfalls.map(function (s) {
        return el('li', {}, [
          el('b', { text: s.name }), ' — short by ' + round(s.short, 1) + ' '
          + s.unit + ' (' + s.percentShort + '% of the requirement)'
        ]);
      });
      view.appendChild(el('div', { class: 'panel' }, [
        el('h2', { text: 'Eat this menu as well as it can be eaten, and you are still missing' }),
        el('ul', {}, items),
        el('p', {
          class: 'note',
          text: 'That is the best case: the food from ' + providerNoun()
            + ' chosen optimally, within what is actually served and what you '
            + 'could actually eat.'
        })
      ]));
    }

    var plateRows = answer.plate.map(function (item) {
      return el('tr', {}, [
        el('td', {}, [
          item.name,
          item.atCap ? el('span', { class: 'pill warn', text: ' at the limit' }) : null,
          item.proxy ? el('span', { class: 'pill warn', text: ' estimated' }) : null
        ]),
        el('td', { class: 'num', text: round(item.amount, 1) + '×' }),
        el('td', { class: 'num', text: Math.round(item.grams) + ' g' })
      ]);
    });

    var buyRows = answer.buy.map(function (item) {
      return el('tr', {}, [
        el('td', {}, [item.name, el('div', { class: 'why', text: item.unit })]),
        el('td', { class: 'num', text: round(item.amount, 1) + '×' }),
        el('td', { class: 'num' }, [
          el('input', {
            type: 'number', class: 'price-input', min: '0', step: '0.5',
            value: item.unitPrice,
            title: item.priceIsDefault ? 'A seed default. Change it.' : 'Your price.',
            onchange: function (event) {
              var value = parseFloat(event.target.value);
              if (!isNaN(value) && value >= 0) {
                state.prices[item.id] = value;
                render();
              }
            }
          })
        ]),
        el('td', { class: 'num', text: preciseMoney(item.cost, currency) })
      ]);
    });

    view.appendChild(el('div', { class: 'grid2' }, [
      el('section', { class: 'panel' }, [
        el('h2', { text: 'From ' + providerNoun() + ', free' }),
        el('table', {}, [
          el('thead', {}, [el('tr', {}, [
            el('th', {}, ['Dish']),
            el('th', { class: 'num' }, ['Servings']),
            el('th', { class: 'num' }, ['Weight'])
          ])]),
          el('tbody', {}, plateRows)
        ])
      ]),
      el('section', { class: 'panel' }, [
        el('h2', { text: 'Buy yourself — ' + preciseMoney(answer.spendExact, currency) }),
        buyRows.length
          ? el('table', {}, [
            el('thead', {}, [el('tr', {}, [
              el('th', {}, ['Item']),
              el('th', { class: 'num' }, ['Units']),
              el('th', { class: 'num' }, ['Price']),
              el('th', { class: 'num' }, ['Cost'])
            ])]),
            el('tbody', {}, buyRows)
          ])
          : el('p', { class: 'note', text: 'Nothing. The menu covers it.' }),
        el('p', {
          class: 'note',
          text: 'Prices are seed defaults for your region. They are almost '
            + 'certainly wrong for your campus — change one and everything '
            + 're-solves.'
        })
      ])
    ]));

    view.appendChild(el('section', { class: 'panel' }, [
      el('h2', { text: 'What the plan actually delivers' }),
      nutrientTable(answer.nutrients),
      el('p', {
        class: 'note',
        text: 'Measured against ' + answer.targets.reference + '. '
          + answer.targets.citation
      })
    ]));

    if (answer.binding.length) {
      view.appendChild(el('section', { class: 'panel' }, [
        el('h2', { text: 'What is actually limiting you' }),
        el('ul', {}, answer.binding.slice(0, 6).map(function (row) {
          return el('li', { text: describeRow(row, currency) });
        })),
        el('p', {
          class: 'note',
          text: 'These are shadow prices from the solver, not estimates. Only '
            + 'limits you are actually up against appear here — a limit you '
            + 'are nowhere near is worth nothing to loosen.'
        })
      ]));
    }
  }).catch(showError(view));
}

function renderFrontier(view) {
  if (askForDishes(view, 'day')) { return; }
  var token = generation;
  post('frontier', { points: 24 }).then(function (answer) {
    if (stale(token)) { return; }
    view.innerHTML = '';
    var currency = answer.currency;
    var curve = answer.curve;

    if (!curve.length) {
      view.appendChild(el('p', { class: 'note', text: 'Nothing to plot.' }));
      return;
    }

    var maxBudget = curve[curve.length - 1].budget || 1;
    var maxUnmet = curve[0].unmetFraction || 1;

    var W = 720, H = 230, padL = 46, padR = 14, padT = 14, padB = 34;
    function x(value) { return padL + (value / maxBudget) * (W - padL - padR); }
    function y(value) { return padT + (1 - value / maxUnmet) * (H - padT - padB); }

    var points = curve.map(function (p) { return x(p.budget) + ',' + y(p.unmetFraction); });
    var area = 'M' + x(0) + ',' + y(0) + ' L' + points.join(' L')
      + ' L' + x(maxBudget) + ',' + y(0) + ' Z';

    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'chart');
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.innerHTML =
      '<path class="chart-area" d="' + area + '"/>' +
      '<polyline class="chart-line" points="' + points.join(' ') + '"/>' +
      '<line class="chart-axis" x1="' + padL + '" y1="' + y(0) + '" x2="' + (W - padR) + '" y2="' + y(0) + '"/>' +
      '<line class="chart-axis" x1="' + padL + '" y1="' + padT + '" x2="' + padL + '" y2="' + y(0) + '"/>' +
      '<text class="chart-label" x="' + padL + '" y="' + (H - 10) + '">' + money(0, currency) + '</text>' +
      '<text class="chart-label" x="' + (W - padR) + '" y="' + (H - 10) + '" text-anchor="end">' +
      preciseMoney(maxBudget, currency) + ' a day</text>' +
      '<text class="chart-label" x="2" y="' + (padT + 4) + '">all of it</text>' +
      '<text class="chart-label" x="2" y="' + (y(0) - 4) + '">none left</text>' +
      '<text class="chart-label" x="2" y="' + (padT + 18) + '">gap</text>';

    view.appendChild(el('div', { class: 'headline' }, [
      stat(preciseMoney(answer.spendToCloseGap, currency), 'a day closes every target'),
      stat(curve[0].targetsMissed + '', 'targets missed spending nothing'),
      stat(answer.floorCount + '', 'targets in total')
    ]));

    view.appendChild(el('section', { class: 'panel' }, [
      el('h2', { text: 'How much of the gap each ' + (currency.symbol || 'unit') + ' closes' }),
      svg,
      el('p', {
        class: 'note',
        text: 'The curve is convex and it flattens, which is the part worth '
          + 'reading. The first coins buy a great deal of nutrition and the '
          + 'last ones buy very little — the knee is where spending stops '
          + 'being worth it.'
      })
    ]));

    var rows = curve.filter(function (_, index) { return index % 3 === 0; }).map(function (p) {
      return el('tr', {}, [
        el('td', { class: 'num', text: preciseMoney(p.budget, currency) }),
        el('td', { class: 'num', text: p.targetsMet + ' of ' + answer.floorCount }),
        el('td', { class: 'num', text: p.averagePercentMet + '%' })
      ]);
    });

    view.appendChild(el('section', { class: 'panel' }, [
      el('h2', { text: 'The same thing as numbers' }),
      el('table', {}, [
        el('thead', {}, [el('tr', {}, [
          el('th', { class: 'num' }, ['Spend a day']),
          el('th', { class: 'num' }, ['Targets met']),
          el('th', { class: 'num' }, ['Average of requirements met'])
        ])]),
        el('tbody', {}, rows)
      ])
    ]));
  }).catch(showError(view));
}

/* What a recommendation costs, set beside what it saves.
 *
 * The audit ranks additions by money saved, and on the US dining hall the
 * second one is french fries. That is honest arithmetic -- cheap energy,
 * potassium and fibre -- and printed on its own it reads as advice to serve
 * more chips. Deleting the row would be editing the answer, so the row stays
 * and says what a serving puts against the day's ceilings instead.
 *
 * Note what is not conditioned on: whether the ceiling binds. A ceiling with
 * slack contributes nothing to the reduced cost, which is exactly when the
 * dish looks free in the arithmetic and still costs the person eating it.
 */
function costsLine(costs) {
  if (!costs || !costs.length) { return null; }
  var pills = costs.map(function (cost) {
    var label;
    if (cost.kind === 'limit') {
      label = Math.round(cost.perServing) + ' g of what you can eat in a day';
    } else if (nutrientUnit(cost.key) === 'kcal') {
      label = Math.round(cost.perServing) + ' kcal';
    } else {
      label = round(cost.perServing, cost.perServing < 10 ? 1 : 0) + ' '
        + nutrientUnit(cost.key) + ' ' + nutrientName(cost.key).toLowerCase();
    }
    return el('span', {
      class: 'cost-pill' + (cost.percentOfTarget >= 20 ? ' heavy' : ''),
      title: cost.binding
        ? 'This limit is already binding, so the solver was counting it against the dish.'
        : 'This limit has room, so it costs the arithmetic nothing — and still costs you.'
    }, [label, el('b', { text: ' ' + cost.percentOfTarget + '%' })]);
  });
  return el('div', { class: 'costs' }, [
    el('span', { class: 'why', text: 'One serving spends ' })
  ].concat(pills));
}

function renderAudit(view) {
  if (askForDishes(view, 'menu')) { return; }
  view.innerHTML = '<p class="loading">Running the audit across all seven days…</p>';

  var token = generation;
  post('audit', { students: state.students }).then(function (answer) {
    if (stale(token)) { return; }
    view.innerHTML = '';
    var currency = answer.currency;

    view.appendChild(el('section', { class: 'panel' }, [
      el('h2', { text: 'Who eats here' }),
      el('label', { class: 'field' }, [
        el('span', {}, ['Students on this meal plan: ',
          el('b', { id: 'students-value', text: String(state.students) })]),
        el('input', {
          type: 'range', min: '1', max: '5000', step: '1',
          value: String(state.students),
          oninput: function (event) {
            document.getElementById('students-value').textContent = event.target.value;
          },
          onchange: function (event) {
            state.students = parseInt(event.target.value, 10);
            render();
          }
        })
      ])
    ]));

    view.appendChild(el('div', { class: 'headline' }, [
      stat(money(answer.baselineMonthlySpendAllStudents, currency),
        'spent out of pocket each month, across everyone'),
      stat(money(answer.baselineMonthlySpend, currency), 'per student per month'),
      stat(answer.recommendations.length + '', 'menu changes worth making')
    ]));

    if (!answer.recommendations.length) {
      view.appendChild(el('p', {
        class: 'note',
        text: 'Nothing in the catalog would reduce what students have to spend '
          + 'on this menu.'
      }));
      return;
    }

    var rows = answer.recommendations.slice(0, 10).map(function (r) {
      var why = r.drivers.filter(function (d) { return d.contribution < 0; })
        .map(function (d) {
          return d.kind === 'floor' ? nutrientName(d.key) : d.key;
        }).join(', ');
      return el('tr', {}, [
        el('td', {}, [
          el('div', {}, [r.name, r.proxy
            ? el('span', { class: 'pill warn', text: ' estimated' }) : null]),
          el('div', {
            class: 'why',
            text: why ? 'mainly a cheap route to ' + why : ''
          }),
          costsLine(r.costs)
        ]),
        el('td', { class: 'num', text: plural(r.days.length, 'day') }),
        el('td', { class: 'num', text: money(r.monthlySaving, currency) }),
        el('td', { class: 'num' }, [
          el('b', { text: money(r.monthlySavingAllStudents, currency) })
        ])
      ]);
    });

    view.appendChild(el('section', { class: 'panel' }, [
      el('h2', { text: 'Add one of these, and students stop paying for it themselves' }),
      el('table', {}, [
        el('thead', {}, [el('tr', {}, [
          el('th', {}, ['Put this on the menu']),
          el('th', { class: 'num' }, ['On']),
          el('th', { class: 'num' }, ['Saves each student']),
          el('th', { class: 'num' }, ['Saves everyone, a month'])
        ])]),
        el('tbody', {}, rows)
      ]),
      el('p', {
        class: 'note',
        text: 'Found by pricing every dish in the catalog against the dual '
          + 'values of the solved menu. A dish only improves things if its '
          + 'reduced cost is negative, so most of the catalog is ruled out '
          + 'without solving anything, and only the survivors are re-solved '
          + 'exactly. The reason each one helps falls out of the same '
          + 'arithmetic.'
      }),
      el('p', {
        class: 'note',
        text: 'Every percentage above is one serving as a share of the day\'s '
          + 'ceiling for that nutrient, and of how much you can eat. They are '
          + 'here because "saves the most money" and "is good for anyone" are '
          + 'different claims, and this page can only make the first one. '
          + 'Nothing is filtered out on the strength of the second: a menu '
          + 'tool that quietly dropped the recommendations it found '
          + 'embarrassing would be telling you what you wanted to hear.'
      })
    ]));
  }).catch(showError(view));
}

/* ---------------------------------------------------------- the builder */

function goToTab(name) {
  state.tab = name;
  Array.prototype.forEach.call(document.querySelectorAll('.tab'), function (tab) {
    tab.setAttribute('aria-selected', String(tab.dataset.tab === name));
  });
  render();
}

/* A built menu with nothing on the day being asked about cannot be solved,
   and the handler says so in solver language. This says it in the language
   of the thing the person was doing. */
function askForDishes(view, scope) {
  if (!isCustom()) { return false; }
  if (scope === 'menu' ? customTotal() : dishesOn(state.day)) { return false; }
  view.innerHTML = '';
  view.appendChild(el('section', { class: 'panel' }, [
    el('h2', {
      text: scope === 'menu'
        ? 'Your menu is empty'
        : 'Nothing on ' + DAY_NAMES[state.day] + ' yet'
    }),
    el('p', {
      text: scope === 'menu'
        ? 'The audit reads a whole week, so it needs at least one dish '
          + 'somewhere in it.'
        : 'Put some dishes on ' + DAY_NAMES[state.day] + ' and this becomes '
          + 'the same screen the presets get.'
    }),
    el('button', {
      class: 'chip action', type: 'button', text: 'Build it',
      onclick: function () { goToTab('build'); }
    })
  ]));
  return true;
}

function changedMenu() {
  updateFragment();
  render();
}

function dishPicker(meal) {
  var list = el('div', { class: 'picker-list' });
  var count = el('p', { class: 'why' });

  function fill() {
    var query = (state.picker.query || '').trim().toLowerCase();
    var served = servedOn(state.day, meal);
    list.innerHTML = '';
    var shown = 0;
    state.catalog.dishes.forEach(function (dish) {
      var haystack = (dish.name + ' ' + dish.tags.join(' ')).toLowerCase();
      if (query && haystack.indexOf(query) === -1) { return; }
      shown++;
      var already = served.indexOf(dish.id) !== -1;
      list.appendChild(el('button', {
        class: 'dish-option' + (already ? ' on' : ''),
        type: 'button',
        onclick: function () { addDish(meal, dish.id); }
      }, [
        el('span', {}, [
          dish.name,
          already ? el('span', { class: 'pill', text: ' on' }) : null,
          dish.proxy ? el('span', { class: 'pill warn', text: ' estimated' }) : null
        ]),
        el('span', {
          class: 'why',
          text: dish.servingGrams + ' g a serving · up to '
            + plural(dish.maxServings, 'serving') + ' · ' + dish.tags.join(', ')
        })
      ]));
    });
    count.textContent = shown + ' of ' + state.catalog.dishes.length + ' dishes';
  }

  var search = el('input', {
    type: 'text', placeholder: 'Search by name or tag — paneer, dal, side',
    value: state.picker.query || '',
    oninput: function (event) { state.picker.query = event.target.value; fill(); }
  });
  fill();

  /* Adding a dish re-renders the tab, so the box is rebuilt underneath the
     person typing. Putting the cursor back is what makes adding four things
     in a row feel like one action instead of four. */
  window.setTimeout(function () {
    search.focus();
    var at = search.value.length;
    try { search.setSelectionRange(at, at); } catch (problem) { /* older browsers */ }
  }, 0);

  return el('div', { class: 'picker' }, [search, count, list]);
}

function addDish(meal, id) {
  var served = servedOn(state.day, meal);
  if (served.indexOf(id) !== -1) { return; }
  if (served.length >= MAX_DISHES_PER_MEAL) {
    state.notice = MEAL_NAMES[meal] + ' already carries ' + MAX_DISHES_PER_MEAL
      + ' dishes, which is as many as the API accepts and more than any real '
      + 'kitchen serves.';
    render();
    return;
  }
  served.push(id);
  changedMenu();
}

function mealBlock(meal) {
  var served = servedOn(state.day, meal);
  var open = state.picker && state.picker.meal === meal;

  var chips = served.map(function (id, index) {
    return el('button', {
      class: 'chip dish', type: 'button',
      title: 'Take ' + dishName(id) + ' off ' + MEAL_NAMES[meal].toLowerCase(),
      onclick: function () { served.splice(index, 1); changedMenu(); }
    }, [dishName(id), el('span', { class: 'x', text: '×' })]);
  });

  return el('div', { class: 'meal' }, [
    el('div', { class: 'meal-head' }, [
      el('b', { text: MEAL_NAMES[meal] }),
      el('span', {
        class: 'why',
        text: dishCount(served.length)
      })
    ]),
    chips.length ? el('div', { class: 'chips' }, chips) : null,
    el('button', {
      class: 'chip add', type: 'button', text: open ? 'Done adding' : '+ Add a dish',
      onclick: function () {
        state.picker = open ? null : { meal: meal, query: '' };
        render();
      }
    }),
    open ? dishPicker(meal) : null
  ]);
}

function renderBuild(view) {
  view.innerHTML = '';

  if (!isCustom()) {
    view.appendChild(el('section', { class: 'panel' }, [
      el('h2', { text: 'Build your own menu' }),
      el('p', {
        text: 'The presets are three real timetables, and yours is not one of '
          + 'them. Pick dishes from the catalog, meal by meal and day by day, '
          + 'and every other tab solves against what you built instead of '
          + 'against a preset.'
      }),
      el('p', {
        class: 'note',
        text: 'The catalog has ' + state.catalog.dishes.length + ' dishes, '
          + 'each costed from its ingredient recipe in stated grams. Nothing '
          + 'you build is sent anywhere or stored: it lives in this page, and '
          + 'in a link you can copy.'
      }),
      el('button', {
        class: 'chip action', type: 'button', text: 'Start an empty menu',
        onclick: function () {
          state.menuId = CUSTOM;
          state.prices = {};
          fillMenuControls();
          document.getElementById('menu').value = CUSTOM;
          updateFragment();
          render();
        }
      })
    ]));
    return;
  }

  var encoded = encodeMenu();
  var link = shareUrl();

  view.appendChild(el('section', { class: 'panel' }, [
    el('h2', { text: 'Your menu' }),
    el('label', { class: 'field' }, [
      el('span', {}, ['What to call it']),
      el('input', {
        type: 'text', value: state.custom.name,
        placeholder: 'Block C mess, week 3',
        oninput: function (event) {
          state.custom.name = event.target.value.slice(0, 120);
          updateFragment();
        }
      })
    ]),
    encoded ? el('label', { class: 'field' }, [
      el('span', {}, ['Share it']),
      el('div', { class: 'share' }, [
        el('input', {
          type: 'text', readonly: 'readonly', class: 'share-url', value: link,
          onclick: function (event) { event.target.select(); }
        }),
        el('button', {
          class: 'chip', type: 'button', text: 'Copy',
          onclick: function (event) { copyLink(event.target, link); }
        })
      ])
    ]) : null,
    el('p', {
      class: 'note',
      text: encoded
        ? dishCount(customTotal()) + ' across ' + plural(
          DAY_ORDER.filter(function (day) { return dishesOn(day); }).length, 'day')
          + '. The whole menu is inside that link — ' + link.length
          + ' characters of it — so there is nothing to store and nothing to '
          + 'sign into. The browser never sends the part after the # to a server.'
        : 'Add a dish and a link that restores this menu will appear here.'
    })
  ]));

  var strip = el('div', { class: 'daystrip' }, DAY_ORDER.map(function (day) {
    var count = dishesOn(day);
    return el('button', {
      class: 'chip', type: 'button', 'aria-pressed': String(day === state.day),
      onclick: function () {
        state.day = day;
        state.picker = null;
        document.getElementById('day').value = day;
        changedMenu();
      }
    }, [SHORT_DAY[day], el('span', { class: 'why', text: ' ' + count })]);
  }));

  view.appendChild(el('section', { class: 'panel' }, [
    el('h2', { text: 'What is served on ' + DAY_NAMES[state.day] }),
    strip,
    el('div', { class: 'mealgrid' }, MEALS.map(mealBlock)),
    el('div', { class: 'chips actions' }, [el('span', {
      class: 'note', text: 'Start from:'
    })].concat((state.presets ? state.presets.menus : []).map(function (preset) {
      return el('button', {
        class: 'chip', type: 'button', text: preset.name,
        onclick: function () {
          state.custom = seedFromPreset(preset);
          state.picker = null;
          state.notice = null;
          changedMenu();
        }
      });
    }))),
    el('div', { class: 'chips actions' }, [
      el('button', {
        class: 'chip', type: 'button',
        text: 'Copy ' + DAY_NAMES[state.day] + ' to every day',
        onclick: function () {
          DAY_ORDER.forEach(function (day) {
            if (day === state.day) { return; }
            MEALS.forEach(function (meal) {
              state.custom.days[day][meal] = servedOn(state.day, meal).slice();
            });
          });
          changedMenu();
        }
      }),
      el('button', {
        class: 'chip', type: 'button', text: 'Clear ' + DAY_NAMES[state.day],
        onclick: function () {
          MEALS.forEach(function (meal) { state.custom.days[state.day][meal] = []; });
          changedMenu();
        }
      }),
      el('button', {
        class: 'chip', type: 'button', text: 'Empty the whole menu',
        onclick: function () {
          state.custom = emptyCustom();
          state.picker = null;
          state.notice = null;
          changedMenu();
        }
      })
    ]),
    el('p', {
      class: 'note',
      text: 'A mess serves a dish once a meal and can serve it at two, which '
        + 'is how the ration caps work: roti capped at six a meal is twelve '
        + 'across a day it appears twice. The menu belongs to the kitchen, '
        + 'not to you — put the omelette on it even if you do not eat eggs, '
        + 'and the diet you picked will leave it off your plate.'
    })
  ]));
}

function copyLink(button, link) {
  var restore = function () { button.textContent = 'Copy'; };
  var done = function () {
    button.textContent = 'Copied';
    window.setTimeout(restore, 2000);
  };
  var failed = function () {
    button.textContent = 'Copy it from the box';
    window.setTimeout(restore, 2500);
  };
  /* Absent over plain http and in a few embedded browsers, which is why the
     link is in a box you can select whether this works or not. */
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(link).then(done, failed);
  } else {
    failed();
  }
}

function renderData(view) {
  var notes = state.presets.notes;
  var menu = currentMenu();
  view.innerHTML = '';

  view.appendChild(el('section', { class: 'panel' }, [
    el('h2', { text: 'This menu' }),
    el('p', {}, [el('b', { text: menu.name }), ' — ' + (menu.subtitle || '')]),
    menu.source && menu.source.note
      ? el('p', { class: 'note', text: menu.source.note }) : null,
    menu.servingStyleNote
      ? el('p', { class: 'note', text: menu.servingStyleNote }) : null
  ]));

  view.appendChild(el('section', { class: 'panel' }, [
    el('h2', { text: 'Where the nutrition numbers come from' }),
    el('ul', {}, Object.keys(notes).map(function (key) {
      return el('li', { text: notes[key] });
    }))
  ]));

  view.appendChild(el('section', { class: 'panel' }, [
    el('h2', { text: 'Reference intakes' }),
    el('ul', {}, state.presets.regions.map(function (region) {
      return el('li', {}, [el('b', { text: region.name }), ' — ' + region.citation]);
    })),
    el('p', {
      class: 'note',
      text: 'These disagree with each other, sometimes sharply. Iron for an '
        + 'adult man is 19 mg under the Indian reference and 8 mg under the '
        + 'American one, because the Indian figure assumes a largely '
        + 'plant-based diet and poorer absorption. Neither is the truth for '
        + 'everyone, which is why you pick.'
    })
  ]));

  view.appendChild(el('section', { class: 'panel' }, [
    el('h2', { text: 'Things this does not know' }),
    el('ul', {}, [
      el('li', { text: 'Whether the kitchen actually cooked the recipe we assumed.' }),
      el('li', { text: 'What you like eating. The plan is nutritionally cheapest, not nicest.' }),
      el('li', { text: 'Losses in cooking, serving and reheating.' }),
      el('li', { text: 'Anything marked estimated: paneer and jaggery come from the Indian Food Composition Tables 2017 instead of USDA, and keep the flag for one nutrient each — IFCT measures vitamin B12 for no food at all. Whey protein is the only ingredient still estimated outright.' })
    ])
  ]));
}

function showError(view) {
  return function (problem) {
    view.innerHTML = '';
    view.appendChild(el('div', { class: 'error' }, [
      'Could not work that out: ' + problem.message
    ]));
  };
}

/* ------------------------------------------------------------------ chrome */

/* Anything the app has to say that is not an answer: a link it could not
   read, a limit it stopped someone at. It lives outside the view so that a
   tab re-rendering underneath it does not swallow it. */
function showNotice() {
  var box = document.getElementById('notice');
  box.innerHTML = '';
  if (!state.notice) { return; }
  box.appendChild(el('div', { class: 'error' }, [
    el('span', { text: state.notice }),
    el('button', {
      class: 'chip', type: 'button', text: 'Dismiss',
      onclick: function () { state.notice = null; showNotice(); }
    })
  ]));
}

function render() {
  generation += 1;
  showNotice();
  var view = document.getElementById('view');
  view.innerHTML = '<p class="loading">Solving…</p>';
  if (state.tab === 'plan') { renderPlan(view); }
  else if (state.tab === 'frontier') { renderFrontier(view); }
  else if (state.tab === 'audit') { renderAudit(view); }
  else if (state.tab === 'build') { renderBuild(view); }
  else { renderData(view); }
}

function fillMenuControls() {
  var menuSelect = document.getElementById('menu');
  menuSelect.innerHTML = '';
  state.presets.menus.forEach(function (menu) {
    menuSelect.appendChild(el('option', { value: menu.id, text: menu.name }));
  });
  /* Not a preset the API knows. Choosing it sends the menu inline instead. */
  menuSelect.appendChild(el('option', {
    value: CUSTOM,
    text: state.custom.name
      ? state.custom.name + ' (yours)'
      : 'Your own menu — build it'
  }));
  menuSelect.value = state.menuId;

  var menu = currentMenu();
  document.getElementById('menu-note').textContent = menu.subtitle || '';

  var daySelect = document.getElementById('day');
  daySelect.innerHTML = '';
  menu.days.forEach(function (day) {
    daySelect.appendChild(el('option', { value: day, text: DAY_NAMES[day] || day }));
  });
  if (menu.days.indexOf(state.day) === -1) { state.day = menu.days[0]; }
  daySelect.value = state.day;

  document.getElementById('region').value = state.region || menu.region;
}

/* Push the whole of `state` back into the controls. Only a shared link needs
   this -- everything else changes state because a control changed first. */
function syncControls() {
  document.getElementById('menu').value = state.menuId;
  document.getElementById('day').value = state.day;
  document.getElementById('region').value = state.region;
  document.getElementById('sex').value = state.sex;
  document.getElementById('activity').value = state.activity;
  document.getElementById('grams').value = state.grams;
  document.getElementById('grams-value').textContent = state.grams;
  var chosen = DIET_NAMES[state.diet] || state.diet;
  Array.prototype.forEach.call(document.getElementById('diet').children,
    function (chip) {
      chip.setAttribute('aria-pressed', String(chip.textContent === chosen));
    });
}

function boot() {
  Promise.all([post('presets'), post('catalog')]).then(function (both) {
    var presets = both[0];
    state.presets = presets;
    state.catalog = both[1];
    state.region = null;

    presets.nutrients.forEach(function (n) {
      NAMES.nutrients[n.id] = n.name;
      NAMES.units[n.id] = n.unit;
    });
    state.catalog.dishes.forEach(function (d) { NAMES.dishes[d.id] = d.name; });
    state.catalog.market.forEach(function (m) { NAMES.dishes[m.id] = m.name; });

    var regionSelect = document.getElementById('region');
    presets.regions.forEach(function (region) {
      regionSelect.appendChild(el('option', { value: region.id, text: region.name }));
    });

    var diets = document.getElementById('diet');
    presets.diets.forEach(function (diet) {
      diets.appendChild(el('button', {
        class: 'chip',
        type: 'button',
        'aria-pressed': String(diet === state.diet),
        text: DIET_NAMES[diet] || diet,
        onclick: function () {
          state.diet = diet;
          Array.prototype.forEach.call(diets.children, function (chip) {
            chip.setAttribute('aria-pressed', String(chip.textContent === (DIET_NAMES[diet] || diet)));
          });
          updateFragment();
          render();
        }
      }));
    });

    fillMenuControls();
    state.region = document.getElementById('region').value;

    /* A shared menu arrives in the fragment. It is read here, after the
       catalog has landed -- every dish id in it is checked against the
       catalog -- and before the first solve, so the link opens on the
       answer rather than on a preset that flickers away. */
    if (readFragment()) {
      fillMenuControls();
      syncControls();
    }

    document.getElementById('menu').addEventListener('change', function (event) {
      state.menuId = event.target.value;
      state.prices = {};
      state.picker = null;
      fillMenuControls();
      state.region = currentMenu().region;
      document.getElementById('region').value = state.region;
      updateFragment();
      if (isCustom() && !customTotal()) { goToTab('build'); return; }
      render();
    });

    document.getElementById('day').addEventListener('change', function (event) {
      state.day = event.target.value;
      state.picker = null;
      updateFragment();
      render();
    });

    ['region', 'sex', 'activity'].forEach(function (id) {
      document.getElementById(id).addEventListener('change', function (event) {
        state[id] = event.target.value;
        updateFragment();
        render();
      });
    });

    var grams = document.getElementById('grams');
    grams.addEventListener('input', function (event) {
      document.getElementById('grams-value').textContent = event.target.value;
    });
    grams.addEventListener('change', function (event) {
      state.grams = parseInt(event.target.value, 10);
      updateFragment();
      render();
    });

    /* Somebody pasting a link into the tab they already have open. The app
       writes the fragment with `replaceState`, which fires nothing, so
       anything arriving here came from outside. */
    window.addEventListener('hashchange', function () {
      if (window.location.hash === state.wroteFragment) { return; }
      state.notice = null;
      state.picker = null;
      if (readFragment()) {
        fillMenuControls();
        syncControls();
      }
      render();
    });

    Array.prototype.forEach.call(document.querySelectorAll('.tab'), function (tab) {
      tab.addEventListener('click', function () {
        state.tab = tab.dataset.tab;
        Array.prototype.forEach.call(document.querySelectorAll('.tab'), function (other) {
          other.setAttribute('aria-selected', String(other === tab));
        });
        render();
      });
    });

    render();
  }).catch(showError(document.getElementById('view')));
}

boot();
