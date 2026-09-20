/* Build a menu: the catalog, a week of meals, and a link that carries it. */

import { html, useState, useRef, useEffect } from '../vendor/preact.js';
import {
  CUSTOM, DAY_NAMES, DAY_ORDER, MEALS, MEAL_NAMES, SHORT_DAY, MAX_DISHES_PER_MEAL
} from '../lib/constants.js';
import { dishCount, dishName, plural } from '../lib/format.js';
import {
  state, update, emptyCustom, seedFromPreset, isCustom,
  servedOn, dishesOn, customTotal
} from '../lib/store.js';
import { encodeMenu, shareUrl, updateFragment } from '../lib/link.js';
import { Icon } from '../lib/icons.js';
import { More } from './pieces.js';

/* Editing the menu changes what the link has to say, so the two move
   together and every other tab re-solves off the back of it. */
function changedMenu(change) {
  if (change) { Object.assign(state, change); }
  updateFragment();
  update();
}

function DishPicker({ meal }) {
  const [query, setQuery] = useState('');
  const search = useRef(null);

  /* Adding a dish re-renders the tab, so the box would otherwise lose the
     cursor underneath the person typing. Putting it back is what makes adding
     four things in a row feel like one action instead of four. */
  useEffect(function () {
    const box = search.current;
    if (!box) { return; }
    box.focus();
    const at = box.value.length;
    try { box.setSelectionRange(at, at); } catch (problem) { /* older browsers */ }
  }, []);

  const wanted = query.trim().toLowerCase();
  const served = servedOn(state.day, meal);
  const shown = state.catalog.dishes.filter(function (dish) {
    if (!wanted) { return true; }
    return (dish.name + ' ' + dish.tags.join(' ')).toLowerCase().indexOf(wanted) !== -1;
  });

  return html`
    <div class="picker">
      <div class="search">
        <${Icon} name="search" />
        <input type="text" ref=${search} value=${query}
          placeholder="Search by name or tag — paneer, dal, side"
          onInput=${function (event) { setQuery(event.target.value); }} />
      </div>
      <p class="why">${shown.length + ' of ' + state.catalog.dishes.length + ' dishes'}</p>
      <div class="picker-list">
        ${shown.map(function (dish) {
          const already = served.indexOf(dish.id) !== -1;
          return html`
            <button key=${dish.id} type="button"
              class=${'dish-option' + (already ? ' on' : '')}
              onClick=${function () { addDish(meal, dish.id); }}>
              <span>
                ${dish.name}
                ${already ? html`<span class="pill"> on</span>` : null}
                ${dish.proxy ? html`<span class="pill warn"> estimated</span>` : null}
              </span>
              <span class="why">${dish.servingGrams + ' g a serving · up to '
                + plural(dish.maxServings, 'serving') + ' · ' + dish.tags.join(', ')}</span>
            </button>`;
        })}
      </div>
    </div>`;
}

function addDish(meal, id) {
  const served = servedOn(state.day, meal);
  if (served.indexOf(id) !== -1) { return; }
  if (served.length >= MAX_DISHES_PER_MEAL) {
    update({
      notice: MEAL_NAMES[meal] + ' already carries ' + MAX_DISHES_PER_MEAL
        + ' dishes, which is as many as the API accepts and more than any real '
        + 'kitchen serves.'
    });
    return;
  }
  served.push(id);
  changedMenu();
}

function MealBlock({ meal }) {
  const served = servedOn(state.day, meal);
  const open = state.picker && state.picker.meal === meal;

  return html`
    <div class="meal">
      <div class="meal-head">
        <b>${MEAL_NAMES[meal]}</b>
        <span class="why">${dishCount(served.length)}</span>
      </div>
      ${served.length ? html`
        <div class="chips">
          ${served.map(function (id, index) {
            return html`
              <button key=${id} class="chip dish" type="button"
                title=${'Take ' + dishName(id) + ' off ' + MEAL_NAMES[meal].toLowerCase()}
                onClick=${function () { served.splice(index, 1); changedMenu(); }}>
                ${dishName(id)}<${Icon} name="x" size=${13} klass="x" />
              </button>`;
          })}
        </div>` : null}
      <button class="chip add" type="button"
        onClick=${function () {
          update({ picker: open ? null : { meal: meal } });
        }}>
        <${Icon} name=${open ? 'check' : 'plus'} size=${14} />
        <span>${open ? 'Done adding' : 'Add a dish'}</span>
      </button>
      ${open ? html`<${DishPicker} meal=${meal} />` : null}
    </div>`;
}

function CopyLink({ link }) {
  const [label, setLabel] = useState('Copy');
  return html`
    <button class="chip" type="button" onClick=${function () {
      const restore = function () { setLabel('Copy'); };
      /* Absent over plain http and in a few embedded browsers, which is why
         the link is in a box you can select whether this works or not. */
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(function () {
          setLabel('Copied');
          window.setTimeout(restore, 2000);
        }, function () {
          setLabel('Copy it from the box');
          window.setTimeout(restore, 2500);
        });
      } else {
        setLabel('Copy it from the box');
        window.setTimeout(restore, 2500);
      }
    }}><${Icon} name="copy" size=${14} /><span>${label}</span></button>`;
}

export function BuildTab() {
  if (!isCustom()) {
    return html`
      <section class="panel empty">
        <${Icon} name="square-pen" size=${28} />
        <h2>Build your own menu</h2>
        <p>The presets are three real timetables, and yours is not one of them.
        Pick dishes from the catalog, meal by meal and day by day, and every
        other tab solves against what you built instead of against a preset.</p>
        <p class="note">${'The catalog has ' + state.catalog.dishes.length
          + ' dishes, each costed from its ingredient recipe in stated grams. '
          + 'Nothing you build is sent anywhere or stored: it lives in this '
          + 'page, and in a link you can copy.'}</p>
        <button class="chip action" type="button" onClick=${function () {
          changedMenu({ menuId: CUSTOM, prices: {} });
        }}>Start an empty menu</button>
      </section>`;
  }

  const encoded = encodeMenu();
  const link = shareUrl();

  return html`
    <section class="panel">
      <h2 class="with-icon">
        <${Icon} name="square-pen" />
        <span>Your menu</span>
      </h2>
      <label class="field">
        <span>What to call it</span>
        <input type="text" value=${state.custom.name}
          placeholder="Block C mess, week 3"
          onInput=${function (event) {
            state.custom.name = event.target.value.slice(0, 120);
            updateFragment();
            update();
          }} />
      </label>
      ${encoded ? html`
        <label class="field">
          <span>Share it</span>
          <div class="share">
            <input type="text" readonly class="share-url" value=${link}
              onClick=${function (event) { event.target.select(); }} />
            <${CopyLink} link=${link} />
          </div>
        </label>` : null}
      <p class="note">${encoded
        ? dishCount(customTotal()) + ' across ' + plural(
            DAY_ORDER.filter(function (day) { return dishesOn(day); }).length, 'day')
          + '. The whole menu is inside that link — ' + link.length
          + ' characters of it — so there is nothing to store and nothing to '
          + 'sign into. The browser never sends the part after the # to a server.'
        : 'Add a dish and a link that restores this menu will appear here.'}</p>
    </section>

    <section class="panel">
      <h2 class="with-icon">
        <${Icon} name="calendar-days" />
        <span>${'What is served on ' + DAY_NAMES[state.day]}</span>
      </h2>
      <div class="daystrip">
        ${DAY_ORDER.map(function (day) {
          return html`
            <button key=${day} class="chip" type="button"
              aria-pressed=${String(day === state.day)}
              onClick=${function () { changedMenu({ day: day, picker: null }); }}>
              ${SHORT_DAY[day]}<span class="why">${' ' + dishesOn(day)}</span>
            </button>`;
        })}
      </div>

      <div class="mealgrid">
        ${MEALS.map(function (meal) {
          return html`<${MealBlock} key=${meal} meal=${meal} />`;
        })}
      </div>

      <div class="chips actions">
        <span class="note">Start from:</span>
        ${(state.presets ? state.presets.menus : []).map(function (preset) {
          return html`
            <button key=${preset.id} class="chip" type="button"
              onClick=${function () {
                changedMenu({
                  custom: seedFromPreset(preset, MAX_DISHES_PER_MEAL),
                  picker: null, notice: null
                });
              }}>${preset.name}</button>`;
        })}
      </div>

      <div class="chips actions">
        <button class="chip" type="button" onClick=${function () {
          DAY_ORDER.forEach(function (day) {
            if (day === state.day) { return; }
            MEALS.forEach(function (meal) {
              state.custom.days[day][meal] = servedOn(state.day, meal).slice();
            });
          });
          changedMenu();
        }}>${'Copy ' + DAY_NAMES[state.day] + ' to every day'}</button>
        <button class="chip" type="button" onClick=${function () {
          MEALS.forEach(function (meal) { state.custom.days[state.day][meal] = []; });
          changedMenu();
        }}>${'Clear ' + DAY_NAMES[state.day]}</button>
        <button class="chip" type="button" onClick=${function () {
          changedMenu({ custom: emptyCustom(), picker: null, notice: null });
        }}>Empty the whole menu</button>
      </div>

      <${More} label="How the menu and your diet interact">
        <p class="note">A mess serves a dish once a meal and can serve it at two,
        which is how the ration caps work: roti capped at six a meal is twelve
        across a day it appears twice. The menu belongs to the kitchen, not to
        you — put the omelette on it even if you do not eat eggs, and the diet
        you picked will leave it off your plate.</p>
      <//>
    </section>`;
}
