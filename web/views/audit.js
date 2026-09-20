/* For whoever writes the menu: what one addition would save everybody. */

import { html, useState } from '../vendor/preact.js';
import {
  money, plural, round, nutrientName, nutrientUnit
} from '../lib/format.js';
import { state, update, solveKey } from '../lib/store.js';
import { post, known } from '../lib/api.js';
import { useAsync } from '../lib/hooks.js';
import { Icon } from '../lib/icons.js';
import { Stat, More, Skeleton, Failed, AskForDishes, emptyBuild } from './pieces.js';

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
function Costs({ costs }) {
  if (!costs || !costs.length) { return null; }
  return html`
    <div class="costs">
      <span class="why">One serving spends </span>
      ${costs.map(function (cost) {
        let label;
        if (cost.kind === 'limit') {
          label = Math.round(cost.perServing) + ' g of what you can eat in a day';
        } else if (nutrientUnit(cost.key) === 'kcal') {
          label = Math.round(cost.perServing) + ' kcal';
        } else {
          label = round(cost.perServing, cost.perServing < 10 ? 1 : 0) + ' '
            + nutrientUnit(cost.key) + ' ' + nutrientName(cost.key).toLowerCase();
        }
        return html`
          <span key=${cost.kind + cost.key}
            class=${'cost-pill' + (cost.percentOfTarget >= 20 ? ' heavy' : '')}
            title=${cost.binding
              ? 'This limit is already binding, so the solver was counting it against the dish.'
              : 'This limit has room, so it costs the arithmetic nothing — and still costs you.'}>
            ${label}<b>${' ' + cost.percentOfTarget + '%'}</b>
          </span>`;
      })}
    </div>`;
}

/* One recommendation, in the shape the table wants it. A function rather
   than a component because it returns a <tr>, and a <tr> has to be a direct
   child of the <tbody> it belongs to. */
function Row(r, currency) {
  const why = r.drivers.filter(function (d) { return d.contribution < 0; })
    .map(function (d) {
      return d.kind === 'floor' ? nutrientName(d.key) : d.key;
    }).join(', ');
  return html`
    <tr key=${r.id || r.name}>
      <td>
        <div>${r.name}${r.proxy
          ? html`<span class="pill warn"> estimated</span>` : null}</div>
        <div class="why">${why ? 'mainly a cheap route to ' + why : ''}</div>
        <${Costs} costs=${r.costs} />
      </td>
      <td class="num">${plural(r.days.length, 'day')}</td>
      <td class="num">${money(r.monthlySaving, currency)}</td>
      <td class="num"><b>${money(r.monthlySavingAllStudents, currency)}</b></td>
    </tr>`;
}

/* A strip rather than a panel. It used to be a panel with a heading, which
   put a control above the answer and made the first thing on the tab a thing
   to fiddle with rather than a number to read. */
function Students() {
  const [shown, setShown] = useState(state.students);
  return html`
    <label class="field strip">
      <span><${Icon} name="user" /> Students on this meal plan: <b>${shown}</b></span>
      <input type="range" min="1" max="5000" step="1" value=${shown}
        onInput=${function (event) { setShown(event.target.value); }}
        onChange=${function (event) {
          update({ students: parseInt(event.target.value, 10) });
        }} />
    </label>`;
}

export function AuditTab() {
  if (emptyBuild('menu')) { return html`<${AskForDishes} scope="menu" />`; }

  const { loading, data, error } = useAsync(
    function () { return post('audit', { students: state.students }); },
    solveKey() + '|' + state.students,
    function () { return known('audit', { students: state.students }); });

  if (loading) { return html`<${Skeleton} kind="audit" />`; }
  if (error) { return html`<${Failed} problem=${error} />`; }

  const currency = data.currency;

  /* The heading says "the one addition that saves the most", and the answer
     is the first row. Five is enough to see the shape of the ranking and to
     notice that the second and third are close; the other five are a fold
     away for anyone actually writing a menu. */
  const top = data.recommendations.slice(0, 5);
  const rest = data.recommendations.slice(5, 10);

  return html`
    <div class="headline">
      <${Stat} hero value=${money(data.baselineMonthlySpendAllStudents, currency)}
        label=${'a month, out of the pockets of ' + state.students
          + ' students, to patch what this menu leaves out'} />
      <${Stat} value=${money(data.baselineMonthlySpend, currency)}
        label="per student, per month" />
      <${Stat} value=${data.recommendations.length + ''}
        label="menu changes worth making" />
    </div>

    <${Students} />

    ${!data.recommendations.length ? html`
      <p class="note">Nothing in the catalog would reduce what students have to
      spend on this menu.</p>` : html`
      <section class="panel">
        <h2 class="with-icon">
          <${Icon} name="chef-hat" />
          <span>Add one of these, and students stop paying for it themselves</span>
        </h2>
        <table>
          <thead><tr>
            <th>Put this on the menu</th>
            <th class="num">On</th>
            <th class="num">Saves each student</th>
            <th class="num">Saves everyone, a month</th>
          </tr></thead>
          <tbody>${top.map(function (r) { return Row(r, currency); })}</tbody>
        </table>
        ${rest.length ? html`
          <${More} label=${rest.length + ' more worth making'}>
            <table>
              <tbody>${rest.map(function (r) { return Row(r, currency); })}</tbody>
            </table>
          <//>` : null}
        <${More} label="How these were found">
          <p class="note">Found by pricing every dish in the catalog against the
          dual values of the solved menu. A dish only improves things if its
          reduced cost is negative, so most of the catalog is ruled out without
          solving anything, and only the survivors are re-solved exactly. The
          reason each one helps falls out of the same arithmetic.</p>
          <p class="note">Every percentage above is one serving as a share of the
          day's ceiling for that nutrient, and of how much you can eat. They are
          here because "saves the most money" and "is good for anyone" are
          different claims, and this page can only make the first one. Nothing is
          filtered out on the strength of the second: a menu tool that quietly
          dropped the recommendations it found embarrassing would be telling you
          what you wanted to hear.</p>
        <//>
      </section>`}`;
}
