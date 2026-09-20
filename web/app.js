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
  tab: 'plan'
};

var cache = {};

/* ---------------------------------------------------------------- plumbing */

function post(action, extra) {
  var body = Object.assign({
    action: action,
    menuId: state.menuId,
    day: state.day,
    diet: state.diet,
    prices: state.prices,
    profile: {
      region: state.region,
      sex: state.sex,
      activity: state.activity,
      maxPlateGrams: state.grams
    }
  }, extra || {});

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

function currentMenu() {
  if (!state.presets) { return null; }
  for (var i = 0; i < state.presets.menus.length; i++) {
    if (state.presets.menus[i].id === state.menuId) { return state.presets.menus[i]; }
  }
  return null;
}

/* What to call the place the food comes from. A hostel mess, a dining hall and
   a canteen are the same thing to the solver and three different words to the
   person reading the screen, so the menu carries its own noun. */
function providerNoun() {
  var menu = currentMenu();
  return (menu && menu.providerNoun) || 'your meal plan';
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

function renderPlan(view) {
  Promise.all([post('gap'), post('solve')]).then(function (answers) {
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

    view.appendChild(el('div', { class: 'headline' }, [
      stat(missed + ' of ' + total, 'targets the menu alone cannot reach'),
      stat(preciseMoney(answer.spendExact, currency), 'a day to close the gap'),
      stat(money(answer.spendExact * 30, currency), 'a month, on top of your fee'),
      stat(Math.round(answer.plateGrams) + ' g', 'of food on the plan')
    ]));

    if (missed === 0) {
      view.appendChild(el('p', { class: 'note' }, [
        'Eaten carefully, this menu meets every target on its own. That is a '
        + 'real result and worth knowing — the interesting question becomes '
        + 'what it takes to get there, below.'
      ]));
    } else {
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
  post('frontier', { points: 24 }).then(function (answer) {
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

function renderAudit(view) {
  view.innerHTML = '<p class="loading">Running the audit across all seven days…</p>';

  post('audit', { students: state.students }).then(function (answer) {
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
          })
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
      })
    ]));
  }).catch(showError(view));
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
      el('li', { text: 'Anything marked estimated: a few ingredients have no USDA entry and are hand-entered from published composition.' })
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

function render() {
  var view = document.getElementById('view');
  view.innerHTML = '<p class="loading">Solving…</p>';
  if (state.tab === 'plan') { renderPlan(view); }
  else if (state.tab === 'frontier') { renderFrontier(view); }
  else if (state.tab === 'audit') { renderAudit(view); }
  else { renderData(view); }
}

function fillMenuControls() {
  var menuSelect = document.getElementById('menu');
  menuSelect.innerHTML = '';
  state.presets.menus.forEach(function (menu) {
    menuSelect.appendChild(el('option', { value: menu.id, text: menu.name }));
  });
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
          render();
        }
      }));
    });

    fillMenuControls();
    state.region = document.getElementById('region').value;

    document.getElementById('menu').addEventListener('change', function (event) {
      state.menuId = event.target.value;
      state.prices = {};
      fillMenuControls();
      state.region = currentMenu().region;
      document.getElementById('region').value = state.region;
      render();
    });

    document.getElementById('day').addEventListener('change', function (event) {
      state.day = event.target.value;
      render();
    });

    ['region', 'sex', 'activity'].forEach(function (id) {
      document.getElementById(id).addEventListener('change', function (event) {
        state[id] = event.target.value;
        render();
      });
    });

    var grams = document.getElementById('grams');
    grams.addEventListener('input', function (event) {
      document.getElementById('grams-value').textContent = event.target.value;
    });
    grams.addEventListener('change', function (event) {
      state.grams = parseInt(event.target.value, 10);
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
