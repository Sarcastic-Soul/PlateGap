/* Small things several tabs need. */

import { html } from '../vendor/preact.js';
import { DAY_NAMES } from '../lib/constants.js';
import {
  preciseMoney, round, dishName, nutrientName, nutrientUnit
} from '../lib/format.js';
import { state, update, isCustom, dishesOn, customTotal } from '../lib/store.js';

export function Stat({ value, label }) {
  return html`
    <div class="stat">
      <div class="value">${value}</div>
      <div class="label">${label}</div>
    </div>`;
}

export function NutrientTable({ nutrients }) {
  return html`
    <table>
      <thead><tr>
        <th>Nutrient</th>
        <th class="num">On the plan</th>
        <th></th>
        <th class="num"></th>
      </tr></thead>
      <tbody>
        ${nutrients.map(function (n) {
          const reference = n.floor || n.ceiling || 1;
          const fraction = Math.min(1.4, n.got / reference);
          const klass = n.status === 'short' ? 'bar short'
            : (n.status === 'over' ? 'bar over' : 'bar');
          const target = n.floor !== null && n.floor !== undefined
            ? 'at least ' + round(n.floor, 1)
            : 'at most ' + round(n.ceiling, 1);
          return html`
            <tr key=${n.id || n.name}>
              <td>
                <div>${n.name}</div>
                <div class="why">${target + ' ' + n.unit}</div>
              </td>
              <td class="num">${round(n.got, 1) + ' ' + n.unit}</td>
              <td style="width:36%">
                <div class=${klass}>
                  <i style=${'width:' + (fraction / 1.4 * 100).toFixed(1) + '%'}></i>
                </div>
              </td>
              <td class="num">
                ${n.status === 'ok'
                  ? html`<span class="pill">met</span>`
                  : html`<span class=${'pill ' + (n.status === 'short' ? 'short' : 'warn')}>
                      ${n.status === 'short' ? 'short' : 'over'}
                    </span>`}
              </td>
            </tr>`;
        })}
      </tbody>
    </table>`;
}

export function describeRow(row, currency) {
  const price = preciseMoney(row.shadowPrice, currency);
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

export function Loading({ what }) {
  return html`<p class="loading">${what || 'Solving…'}</p>`;
}

export function Failed({ problem }) {
  return html`<div class="error">Could not work that out: ${problem.message}</div>`;
}

/* A built menu with nothing on the day being asked about cannot be solved,
   and the handler says so in solver language. This says it in the language
   of the thing the person was doing. */
export function emptyBuild(scope) {
  if (!isCustom()) { return false; }
  return (scope === 'menu' ? customTotal() : dishesOn(state.day)) === 0;
}

export function AskForDishes({ scope }) {
  return html`
    <section class="panel">
      <h2>${scope === 'menu'
        ? 'Your menu is empty'
        : 'Nothing on ' + DAY_NAMES[state.day] + ' yet'}</h2>
      <p>${scope === 'menu'
        ? 'The audit reads a whole week, so it needs at least one dish '
          + 'somewhere in it.'
        : 'Put some dishes on ' + DAY_NAMES[state.day] + ' and this becomes '
          + 'the same screen the presets get.'}</p>
      <button class="chip action" type="button"
        onClick=${function () { update({ tab: 'build' }); }}>Build it</button>
    </section>`;
}
