/* The gap: what the menu leaves out, and the cheapest way to close it. */

import { html } from '../vendor/preact.js';
import { DAY_NAMES } from '../lib/constants.js';
import { money, preciseMoney, round } from '../lib/format.js';
import {
  state, update, solveKey, providerNoun, noMealPlanPayload
} from '../lib/store.js';
import { post, known } from '../lib/api.js';
import { useAsync } from '../lib/hooks.js';
import { Icon } from '../lib/icons.js';
import {
  Stat, More, Info, NutrientTable, describeRow, Skeleton, Failed,
  AskForDishes, emptyBuild
} from './pieces.js';

/* A list read as a sentence. Four shortfalls are "calcium, potassium, zinc
   and iron", not "Calcium, Potassium, Zinc, Iron". */
function sentence(words) {
  if (words.length === 1) { return words[0]; }
  return words.slice(0, -1).join(', ') + ' and ' + words[words.length - 1];
}

function ShortfallRow({ item }) {
  const met = Math.max(0, Math.min(100, 100 - item.percentShort));
  return html`
    <div class="shortfall">
      <div class="shortfall-name">${item.name}</div>
      <div class="bar short"><i style=${'width:' + met.toFixed(1) + '%'}></i></div>
      <div class="shortfall-gap">
        ${'short by ' + round(item.short, 1) + ' ' + item.unit}
        <span class="why">${' · ' + item.percentShort + '% of the requirement'}</span>
      </div>
    </div>`;
}

function Shortfalls({ shortfalls }) {
  const shown = shortfalls.slice(0, 3);
  const rest = shortfalls.slice(3);
  return html`
    <section class="panel">
      <h2 class="with-icon">
        <${Icon} name="triangle-alert" />
        <span>${'Short on ' + sentence(shortfalls.map(function (s) {
          return s.name.toLowerCase();
        }))}</span>
        <${Info} label="How this was worked out">
          <p>${'This is the menu eaten as well as it can possibly be eaten: '
            + 'the food from ' + providerNoun() + ' chosen optimally, within '
            + 'what is actually served and within what you could actually get '
            + 'through in a day.'}</p>
          <p>Nobody eats optimally, so a real shortfall is wider than this
          one. It is a lower bound, which is the honest direction for a number
          like this to be wrong in.</p>
        <//>
      </h2>
      ${shown.map(function (s) {
        return html`<${ShortfallRow} key=${s.name} item=${s} />`;
      })}
      ${rest.length ? html`
        <${More} label=${rest.length + ' more'}>
          ${rest.map(function (s) {
            return html`<${ShortfallRow} key=${s.name} item=${s} />`;
          })}
        <//>` : null}
    </section>`;
}

/* What the meal plan is worth: the same solve with nothing served at all, so
   the only way to reach a target is to pay for it. It costs one extra LP and
   only runs on the days that are actually covered.

   The headline needs the number too, so the fetch lives in `Covered` and the
   panel is handed what came back. Asking for it twice would be two solves for
   one answer. */
function WithoutThePlan({ result, currency }) {
  const { loading, data, error } = result;
  return html`
    <${More} label="What the meal plan is worth">
      ${loading ? html`
        <p class="loading">Working out what the same targets cost without it…</p>` : null}
      ${error ? html`
        <p class="note">Could not work that out: ${error.message}</p>` : null}
      ${data && !data.feasible ? html`
        <p>Nothing you could buy, inside the portion limits on the shop items,
        reaches every target on this diet without the menu. This menu does
        something a supermarket on its own cannot.</p>` : null}
      ${data && data.feasible ? html`
        <p>Take the meal plan away and buy the same targets yourself, and the
        cheapest way to do it costs ${preciseMoney(data.spendExact, currency)}
        ${' a day — ' + money(data.spendExact * 30, currency) + ' a month. That is what '
          + providerNoun() + ' is worth to you on ' + DAY_NAMES[state.day]
          + ', and none of it shows up on a bill.'}</p>
        <table>
          <thead><tr>
            <th>Instead of the menu, buy</th>
            <th class="num">Units</th>
            <th class="num">Cost</th>
          </tr></thead>
          <tbody>
            ${data.buy.map(function (item) {
              return html`
                <tr key=${item.id}>
                  <td>${item.name}<div class="why">${item.unit}</div></td>
                  <td class="num">${round(item.amount, 1) + '×'}</td>
                  <td class="num">${preciseMoney(item.cost, currency)}</td>
                </tr>`;
            })}
          </tbody>
        </table>
        <p class="note">This is the cheapest basket that hits the same floors at
        the same prices, not a grocery bill — nobody eats like a linear program.
        It is a lower bound on what the plan saves you, which is the honest
        direction for a number like this to be wrong in.</p>` : null}
    <//>`;
}

/* The number the panel above produces, said in four words for the headline.
   "Working" with a capital W is what `scripts/capture_demo.py` waits on
   before it shoots the page. */
function worthOfThePlan(result, currency) {
  if (result.loading) { return 'Working it out'; }
  if (result.error) { return '—'; }
  if (!result.data.feasible) { return 'out of reach'; }
  return preciseMoney(result.data.spendExact, currency);
}

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
function Covered({ shortfall, answer }) {
  const currency = answer.currency;
  const targets = shortfall.targetsMet + shortfall.targetsMissed;
  const eatLimit = answer.targets.limits.plateGrams;
  const usedShare = Math.round(100 * answer.plateGrams / eatLimit);

  const withoutThePlan = useAsync(
    function () { return post('solve', { menu: noMealPlanPayload() }); },
    solveKey(),
    function () { return known('solve', { menu: noMealPlanPayload() }); });

  const floors = answer.nutrients.filter(function (n) { return n.floor; })
    .slice().sort(function (a, b) { return a.got / a.floor - b.got / b.floor; });
  const onTheLine = floors.filter(function (n) { return n.got - n.floor < 0.02 * n.floor; });
  const clear = floors.filter(function (n) { return onTheLine.indexOf(n) === -1; });

  const ceilings = answer.nutrients.filter(function (n) { return n.ceiling; })
    .slice().sort(function (a, b) { return b.got / b.ceiling - a.got / a.ceiling; });

  return html`
    <div class="headline">
      <${Stat} hero value=${worthOfThePlan(withoutThePlan, currency)}
        label="a day to buy the same targets if the plan did not exist" />
      <${Stat} value=${targets + ' of ' + targets}
        label=${'targets met from ' + providerNoun() + ' alone'} />
      <${Stat} value=${Math.round(answer.plateGrams) + ' g'}
        label=${'of food it takes — ' + usedShare + '% of what you can eat'} />
    </div>

    <section class="panel">
      <h2 class="with-icon">
        <${Icon} name="check" />
        <span>Every target met</span>
      </h2>
      <p>${'The plate below is the lightest one that meets every target, and it '
        + 'weighs ' + Math.round(answer.plateGrams) + ' g against the '
        + Math.round(eatLimit) + ' g you said you could manage. Every target is '
        + 'met, and it takes most of a day of eating to meet them.'}</p>
      ${onTheLine.length ? html`
        <p class="note">${'Exactly on the line: ' + sentence(onTheLine.map(
          function (n) { return n.name.toLowerCase(); })) + '.'}</p>` : null}

      <${More} label="How much room that leaves">
        <h3>Tightest floors</h3>
        <ul>
          ${clear.slice(0, 4).map(function (n) {
            return html`
              <li key=${n.name}><b>${n.name}</b>${' — ' + round(n.got, 1) + ' '
                + n.unit + ', ' + Math.round(100 * (n.got - n.floor) / n.floor)
                + '% clear of the ' + round(n.floor, 1) + ' ' + n.unit + ' floor'}</li>`;
          })}
        </ul>
        ${ceilings.length ? html`<h3>Ceilings</h3>` : null}
        ${ceilings.length ? html`
          <ul>
            ${ceilings.map(function (n) {
              const room = n.ceiling - n.got;
              return html`
                <li key=${n.name}><b>${n.name}</b>${room < 0.02 * n.ceiling
                  ? ' — ' + round(n.got, 1) + ' of ' + round(n.ceiling, 1) + ' '
                    + n.unit + ', with no headroom left at all'
                  : ' — ' + round(n.got, 1) + ' of ' + round(n.ceiling, 1) + ' '
                    + n.unit + ', ' + round(room, 1) + ' ' + n.unit + ' spare'}</li>`;
            })}
          </ul>` : null}
        <p class="note">A floor sitting exactly on its line is the solver being
        frugal rather than the menu being thin: this plate is minimised for
        weight, so it never takes a gram more of anything than it has to. A
        ceiling on its line is the opposite — that one really is full.</p>
      <//>

      <${WithoutThePlan} result=${withoutThePlan} currency=${currency} />
    </section>`;
}

export function PlanTab() {
  if (emptyBuild('day')) { return html`<${AskForDishes} scope="day" />`; }

  const { loading, data, error } = useAsync(
    function () { return Promise.all([post('gap'), post('solve')]); },
    solveKey(),
    function () {
      const gap = known('gap');
      const solve = known('solve');
      return gap && solve ? [gap, solve] : null;
    });

  if (loading) { return html`<${Skeleton} kind="plan" />`; }
  if (error) { return html`<${Failed} problem=${error} />`; }

  const shortfall = data[0];
  const answer = data[1];

  if (!answer.feasible) {
    return html`
      <div class="error">
        <${Icon} name="circle-alert" />
        <span>Even with purchases there is no way to reach every target inside
        the portion limits on this day. ${answer.reason || ''}</span>
      </div>`;
  }

  const currency = answer.currency;
  const missed = shortfall.targetsMissed;
  const total = shortfall.targetsMet + shortfall.targetsMissed;

  return html`
    ${missed === 0
      ? html`<${Covered} shortfall=${shortfall} answer=${answer} />`
      : html`
        <div class="headline">
          <${Stat} hero value=${money(answer.spendExact * 30, currency)}
            label="a month, on top of a fee you have already paid" />
          <${Stat} value=${preciseMoney(answer.spendExact, currency)}
            label="a day to close the gap" />
          <${Stat} value=${missed + ' of ' + total}
            label="targets the menu alone cannot reach" />
        </div>
        <${Shortfalls} shortfalls=${shortfall.shortfalls} />`}

    <div class="grid2">
      <section class="panel">
        <h2 class="with-icon">
          <${Icon} name="utensils" />
          <span>${'From ' + providerNoun() + ', free'}</span>
        </h2>
        <table>
          <thead><tr>
            <th>Dish</th>
            <th class="num">Servings</th>
            <th class="num">Weight</th>
          </tr></thead>
          <tbody>
            ${answer.plate.map(function (item) {
              return html`
                <tr key=${item.id}>
                  <td>
                    ${item.name}
                    ${item.atCap ? html`<span class="pill warn"> at the limit</span>` : null}
                    ${item.proxy ? html`<span class="pill warn"> estimated</span>` : null}
                  </td>
                  <td class="num">${round(item.amount, 1) + '×'}</td>
                  <td class="num">${Math.round(item.grams) + ' g'}</td>
                </tr>`;
            })}
          </tbody>
        </table>
      </section>

      <section class="panel">
        <h2 class="with-icon">
          <${Icon} name="shopping-basket" />
          <span>${'Buy yourself — ' + preciseMoney(answer.spendExact, currency)}</span>
          <${Info} label="About these prices">
            <p>Prices are seed defaults for your region and are almost
            certainly wrong for your campus. They are not survey data.</p>
            <p>Change one and everything re-solves — including which items get
            bought at all, since the cheapest way to reach a target depends on
            what the things cost.</p>
          <//>
        </h2>
        ${answer.buy.length ? html`
          <table>
            <thead><tr>
              <th>Item</th>
              <th class="num">Units</th>
              <th class="num">Price</th>
              <th class="num">Cost</th>
            </tr></thead>
            <tbody>
              ${answer.buy.map(function (item) {
                return html`
                  <tr key=${item.id}>
                    <td>${item.name}<div class="why">${item.unit}</div></td>
                    <td class="num">${round(item.amount, 1) + '×'}</td>
                    <td class="num">
                      <input type="number" class="price-input" min="0" step="0.5"
                        value=${item.unitPrice}
                        title=${item.priceIsDefault
                          ? 'A seed default. Change it.' : 'Your price.'}
                        onChange=${function (event) {
                          const value = parseFloat(event.target.value);
                          if (!isNaN(value) && value >= 0) {
                            state.prices[item.id] = value;
                            update();
                          }
                        }} />
                    </td>
                    <td class="num">${preciseMoney(item.cost, currency)}</td>
                  </tr>`;
              })}
            </tbody>
          </table>`
        : html`<p class="note">Nothing. The menu covers it.</p>`}
      </section>
    </div>

    <${More} label=${'All ' + answer.nutrients.length + ' nutrients'}>
      <${NutrientTable} nutrients=${answer.nutrients} />
      <p class="note">${'Measured against ' + answer.targets.reference + '. '
        + answer.targets.citation}</p>
    <//>

    ${answer.binding.length ? html`
      <${More} label="What is actually limiting you">
        <ul>
          ${answer.binding.slice(0, 6).map(function (row) {
            return html`<li key=${row.kind + row.key}>${describeRow(row, currency)}</li>`;
          })}
        </ul>
        <p class="note">These are shadow prices from the solver, not estimates.
        Only limits you are actually up against appear here — a limit you are
        nowhere near is worth nothing to loosen.</p>
      <//>` : null}`;
}
