/* Small things several tabs need. */

import { html, useState } from '../vendor/preact.js';
import { DAY_NAMES } from '../lib/constants.js';
import {
  preciseMoney, round, dishName, nutrientName, nutrientUnit
} from '../lib/format.js';
import { state, update, isCustom, dishesOn, customTotal } from '../lib/store.js';
import { Icon } from '../lib/icons.js';

export function Stat({ value, label, hero }) {
  return html`
    <div class=${'stat' + (hero ? ' hero' : '')}>
      <div class="value">${value}</div>
      <div class="label">${label}</div>
    </div>`;
}

/* An explanation, out of the way until it is wanted.
 *
 * Every panel on this page used to carry a paragraph saying what it meant,
 * and all of them together were the first four hundred words a new reader
 * met -- before a single number. The paragraphs are unchanged; they are
 * behind this.
 *
 * `popovertarget` and `popover` are the browser's own, so there is no
 * JavaScript here at all: no open state, no outside-click listener, no
 * z-index, and nothing that can leave a panel stuck open. The popover goes
 * in the top layer, so opening one never moves the page underneath it. */
let popovers = 0;

export function Info({ label, children }) {
  const [id] = useState(function () { popovers += 1; return 'info-' + popovers; });
  const said = label || 'What this means';
  return html`
    <button class="info" type="button" popovertarget=${id}
      aria-label=${said} title=${said}>
      <${Icon} name="info" size=${14} />
    </button>
    ${/* "auto" spelled out, not a bare `popover` attribute: `popover` is an
         enumerated attribute whose invalid-value default is "manual", and a
         bare one arrives here as the string "true" -- which is invalid, so
         the popover would neither close on Escape nor on a click outside. */ ''}
    <div id=${id} popover="auto">${children}</div>`;
}

/* Everything that is true but not the answer.
 *
 * The page had grown into a wall: four headline numbers, a shortfall list,
 * two tables, fourteen nutrient rows of which thirteen said "met", a list of
 * shadow prices and four paragraphs explaining the method -- all of it open
 * at once, so the one sentence a person came for had to be found. None of it
 * was wrong, which is why none of it is deleted. It is folded instead, and a
 * `<details>` does that with no JavaScript and no state to keep. */
export function More({ label, children, open }) {
  return html`
    <details class="more" open=${open || null}>
      <summary>
        <${Icon} name="chevron-right" klass="marker" />
        <span>${label}</span>
      </summary>
      <div class="more-body">${children}</div>
    </details>`;
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
                  ? html`<span class="pill"><${Icon} name="check" size=${12} /> met</span>`
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

/* ----------------------------------------------------------- skeletons
 *
 * A solve is most of a second and the audit is three, which is long enough
 * for a single centred "Solving…" to read as a stall. These stand in for the
 * shape of the answer instead, so the page does not jump when it lands.
 *
 * They keep the class `loading`, because that is how `scripts/capture_demo.py`
 * and `scripts/smoke_ui.py` know the page is still busy: the screenshot and
 * the smoke test both wait until no `.loading` element is left. A skeleton
 * that did not answer to that name would be photographed. */
function Lines({ count }) {
  const widths = ['92%', '78%', '85%', '64%', '88%', '71%'];
  const rows = [];
  for (let i = 0; i < count; i++) {
    rows.push(html`<div key=${i} class="shim line" style=${'width:' + widths[i % 6]}></div>`);
  }
  return rows;
}

function SkeletonStats({ count }) {
  const boxes = [];
  for (let i = 0; i < count; i++) {
    boxes.push(html`
      <div key=${i} class="stat">
        <div class="shim value"></div>
        <div class="shim label"></div>
      </div>`);
  }
  return html`<div class="headline">${boxes}</div>`;
}

function SkeletonPanel({ lines, wide }) {
  return html`
    <section class=${'panel' + (wide ? '' : ' half')}>
      <div class="shim head"></div>
      <${Lines} count=${lines} />
    </section>`;
}

/* A folded section is one line high whether or not it is open, so this is
   what one looks like before its contents exist. */
function SkeletonFold() {
  return html`<div class="shim fold"></div>`;
}

export function Skeleton({ kind }) {
  if (kind === 'audit') {
    return html`
      <div class="loading skeleton">
        ${/* The "Who eats here" panel: a heading and a slider. */ ''}
        <section class="panel">
          <div class="shim head"></div>
          <div class="shim label"></div>
          <div class="shim field"></div>
        </section>
        <${SkeletonStats} count=${3} />
        <${SkeletonPanel} lines=${6} wide />
      </div>`;
  }
  if (kind === 'frontier') {
    return html`
      <div class="loading skeleton">
        <${SkeletonStats} count=${3} />
        <section class="panel">
          <div class="shim head"></div>
          <div class="shim readout"></div>
          <div class="shim chart"></div>
          <${Lines} count=${2} />
        </section>
        <${SkeletonFold} />
      </div>`;
  }
  return html`
    <div class="loading skeleton">
      <${SkeletonStats} count=${4} />
      <${SkeletonPanel} lines=${4} wide />
      <div class="grid2">
        <${SkeletonPanel} lines=${5} />
        <${SkeletonPanel} lines=${5} />
      </div>
      <${SkeletonFold} />
      <${SkeletonFold} />
    </div>`;
}

export function Failed({ problem }) {
  return html`
    <div class="error">
      <${Icon} name="circle-alert" />
      <span>Could not work that out: ${problem.message}</span>
    </div>`;
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
    <section class="panel empty">
      <${Icon} name="square-pen" size=${28} />
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
