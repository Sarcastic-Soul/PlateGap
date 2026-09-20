/* PlateGap front end.
 *
 * Preact and htm, both vendored in `vendor/preact.js` as one 13 KB module, so
 * there is still no build step and nothing is fetched from a CDN: the browser
 * loads the same files that are in the repository. htm is template literals
 * rather than JSX, which is what makes that possible.
 *
 * Every number on screen came out of the solver rather than out of this
 * directory. Where something is an assumption, it says so on screen.
 */

import { html, render, useState, useEffect } from './vendor/preact.js';
import {
  CUSTOM, DAY_NAMES, DAY_ORDER, DIET_NAMES, TABS
} from './lib/constants.js';
import { NAMES } from './lib/format.js';
import {
  state, update, useStore, currentMenu, isCustom, customTotal
} from './lib/store.js';
import { post } from './lib/api.js';
import { readFragment, updateFragment } from './lib/link.js';
import { PlanTab } from './views/plan.js';
import { FrontierTab } from './views/frontier.js';
import { AuditTab } from './views/audit.js';
import { BuildTab } from './views/build.js';
import { DataTab } from './views/data.js';

/* Changing anything the solver reads means the link has to say so too. */
function changed(fields) {
  Object.assign(state, fields);
  updateFragment();
  update();
}

/* A preset carries its own region and its own set of days, and a menu that
   does not serve Sunday must not be left showing Sunday. */
function chooseMenu(menuId) {
  state.menuId = menuId;
  state.prices = {};
  state.picker = null;
  const menu = currentMenu();
  state.region = menu.region;
  if (menu.days.indexOf(state.day) === -1) { state.day = menu.days[0]; }
  /* An empty menu of your own has nothing to solve, so go where the dishes
     are put on rather than to a tab that can only apologise. */
  if (isCustom() && !customTotal()) { state.tab = 'build'; }
  updateFragment();
  update();
}

function Sidebar() {
  const menu = currentMenu();
  const [grams, setGrams] = useState(state.grams);

  /* A shared link sets the slider from outside the slider. */
  useEffect(function () { setGrams(state.grams); }, [state.grams]);

  return html`
    <aside>
      <section class="panel">
        <h2>Menu</h2>
        <label class="field">
          <span>Preset</span>
          <select value=${state.menuId}
            onChange=${function (event) { chooseMenu(event.target.value); }}>
            ${state.presets.menus.map(function (preset) {
              return html`<option key=${preset.id} value=${preset.id}>${preset.name}</option>`;
            })}
            ${/* Not a preset the API knows. Choosing it sends the menu inline. */ ''}
            <option value=${CUSTOM}>${state.custom.name
              ? state.custom.name + ' (yours)'
              : 'Your own menu — build it'}</option>
          </select>
        </label>
        <p class="note">${menu.subtitle || ''}</p>
        <label class="field">
          <span>Day</span>
          <select value=${state.day}
            onChange=${function (event) {
              changed({ day: event.target.value, picker: null });
            }}>
            ${menu.days.map(function (day) {
              return html`<option key=${day} value=${day}>${DAY_NAMES[day] || day}</option>`;
            })}
          </select>
        </label>
      </section>

      <section class="panel">
        <h2>You</h2>
        <label class="field">
          <span>Diet</span>
          <div class="chips">
            ${state.presets.diets.map(function (diet) {
              return html`
                <button key=${diet} class="chip" type="button"
                  aria-pressed=${String(diet === state.diet)}
                  onClick=${function () { changed({ diet: diet }); }}>
                  ${DIET_NAMES[diet] || diet}
                </button>`;
            })}
          </div>
        </label>
        <label class="field">
          <span>Reference intakes</span>
          <select value=${state.region}
            onChange=${function (event) { changed({ region: event.target.value }); }}>
            ${state.presets.regions.map(function (region) {
              return html`<option key=${region.id} value=${region.id}>${region.name}</option>`;
            })}
          </select>
        </label>
        <div class="pair">
          <label class="field">
            <span>Sex</span>
            <select value=${state.sex}
              onChange=${function (event) { changed({ sex: event.target.value }); }}>
              <option value="male">Male</option>
              <option value="female">Female</option>
            </select>
          </label>
          <label class="field">
            <span>Activity</span>
            <select value=${state.activity}
              onChange=${function (event) { changed({ activity: event.target.value }); }}>
              <option value="sedentary">Sedentary</option>
              <option value="moderate">Moderate</option>
              <option value="active">Active</option>
            </select>
          </label>
        </div>
        <label class="field">
          <span>How much you can eat in a day: <b>${grams}</b> g</span>
          <input type="range" min="700" max="2400" step="50" value=${grams}
            onInput=${function (event) { setGrams(event.target.value); }}
            onChange=${function (event) {
              changed({ grams: parseInt(event.target.value, 10) });
            }} />
        </label>
        <p class="note">This one matters more than it looks. Without a limit on
        how much food a person can physically get through, the answer is often
        “eat twelve rotis” — technically correct and no use to anyone.</p>
      </section>
    </aside>`;
}

/* Anything the app has to say that is not an answer: a link it could not
   read, a limit it stopped someone at. It lives outside the view so that a
   tab re-rendering underneath it does not swallow it. */
function Notice() {
  return html`
    <div id="notice">
      ${state.notice ? html`
        <div class="error">
          <span>${state.notice}</span>
          <button class="chip" type="button"
            onClick=${function () { update({ notice: null }); }}>Dismiss</button>
        </div>` : null}
    </div>`;
}

const VIEWS = {
  plan: PlanTab, frontier: FrontierTab, audit: AuditTab,
  build: BuildTab, data: DataTab
};

function App() {
  useStore();

  if (state.failure) {
    return html`
      <main><section><div id="view">
        <div class="error">Could not work that out: ${state.failure.message}</div>
      </div></section></main>`;
  }
  if (!state.presets) {
    return html`
      <main><section><div id="view">
        <p class="loading">Loading…</p>
      </div></section></main>`;
  }

  const Tab = VIEWS[state.tab] || DataTab;

  return html`
    <main>
      <${Sidebar} />
      <section>
        <div class="tabs" role="tablist">
          ${TABS.map(function (tab) {
            return html`
              <button key=${tab.id} class="tab" role="tab" data-tab=${tab.id}
                aria-selected=${String(tab.id === state.tab)}
                onClick=${function () { update({ tab: tab.id }); }}>
                ${tab.label}
              </button>`;
          })}
        </div>
        <${Notice} />
        ${/* Keyed on the tab so switching tabs mounts a fresh view rather
             than reusing the last one's hooks. */ ''}
        <div id="view"><${Tab} key=${state.tab} /></div>
      </section>
    </main>`;
}

function boot() {
  /* index.html carries a static "Loading…" so the page says something before
     this module runs. Preact takes the container over from here. */
  const mount = document.getElementById('app');
  mount.textContent = '';
  render(html`<${App} />`, mount);

  Promise.all([post('presets'), post('catalog')]).then(function (both) {
    state.presets = both[0];
    state.catalog = both[1];

    state.presets.nutrients.forEach(function (n) {
      NAMES.nutrients[n.id] = n.name;
      NAMES.units[n.id] = n.unit;
    });
    state.catalog.dishes.forEach(function (d) { NAMES.dishes[d.id] = d.name; });
    state.catalog.market.forEach(function (m) { NAMES.dishes[m.id] = m.name; });

    state.region = currentMenu().region;

    /* A shared menu arrives in the fragment. It is read here, after the
       catalog has landed -- every dish id in it is checked against the
       catalog -- and before the first render, so the link opens on the
       answer rather than on a preset that flickers away. */
    readFragment();
    update();
  }).catch(function (problem) {
    update({ failure: problem });
  });

  /* Somebody pasting a link into the tab they already have open. The app
     writes the fragment with `replaceState`, which fires nothing, so anything
     arriving here came from outside. */
  window.addEventListener('hashchange', function () {
    if (window.location.hash === state.wroteFragment) { return; }
    if (!state.catalog) { return; }
    state.notice = null;
    state.picker = null;
    readFragment();
    update();
  });
}

boot();
