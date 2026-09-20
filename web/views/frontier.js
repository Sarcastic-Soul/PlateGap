/* What each rupee buys: the gap closed against the money spent. */

import { html } from '../vendor/preact.js';
import { money, preciseMoney } from '../lib/format.js';
import { solveKey } from '../lib/store.js';
import { post, known } from '../lib/api.js';
import { useAsync } from '../lib/hooks.js';
import { Icon } from '../lib/icons.js';
import { Stat, More, Skeleton, Failed, AskForDishes, emptyBuild } from './pieces.js';

const W = 720, H = 230, padL = 46, padR = 14, padT = 14, padB = 34;

function Chart({ curve, currency }) {
  const maxBudget = curve[curve.length - 1].budget || 1;
  const maxUnmet = curve[0].unmetFraction || 1;

  function x(value) { return padL + (value / maxBudget) * (W - padL - padR); }
  function y(value) { return padT + (1 - value / maxUnmet) * (H - padT - padB); }

  const points = curve.map(function (p) { return x(p.budget) + ',' + y(p.unmetFraction); });
  const area = 'M' + x(0) + ',' + y(0) + ' L' + points.join(' L')
    + ' L' + x(maxBudget) + ',' + y(0) + ' Z';

  return html`
    <svg class="chart" viewBox=${'0 0 ' + W + ' ' + H} preserveAspectRatio="none">
      <path class="chart-area" d=${area} />
      <polyline class="chart-line" points=${points.join(' ')} />
      <line class="chart-axis" x1=${padL} y1=${y(0)} x2=${W - padR} y2=${y(0)} />
      <line class="chart-axis" x1=${padL} y1=${padT} x2=${padL} y2=${y(0)} />
      <text class="chart-label" x=${padL} y=${H - 10}>${money(0, currency)}</text>
      <text class="chart-label" x=${W - padR} y=${H - 10} text-anchor="end">
        ${preciseMoney(maxBudget, currency) + ' a day'}</text>
      ${/* The axis is the share of the gap still open. "gap" used to be a
           third label here and it collided with "all of it"; the panel
           heading says the same thing with more room. */ ''}
      <text class="chart-label" x="2" y=${padT + 4}>all of it</text>
      <text class="chart-label" x="2" y=${y(0) - 4}>none left</text>
    </svg>`;
}

export function FrontierTab() {
  if (emptyBuild('day')) { return html`<${AskForDishes} scope="day" />`; }

  const { loading, data, error } = useAsync(
    function () { return post('frontier', { points: 24 }); }, solveKey(),
    function () { return known('frontier', { points: 24 }); });

  if (loading) { return html`<${Skeleton} kind="frontier" />`; }
  if (error) { return html`<${Failed} problem=${error} />`; }

  const currency = data.currency;
  const curve = data.curve;
  if (!curve.length) { return html`<p class="note">Nothing to plot.</p>`; }

  return html`
    <div class="headline">
      <${Stat} value=${preciseMoney(data.spendToCloseGap, currency)}
        label="a day closes every target" />
      <${Stat} value=${curve[0].targetsMissed + ''}
        label="targets missed spending nothing" />
      <${Stat} value=${data.floorCount + ''} label="targets in total" />
    </div>

    <section class="panel">
      <h2 class="with-icon">
        <${Icon} name="trending-down" />
        <span>${'How much of the gap each ' + (currency.symbol || 'unit') + ' closes'}</span>
      </h2>
      <${Chart} curve=${curve} currency=${currency} />
      <p class="note">The curve is convex and it flattens, which is the part
      worth reading. The first coins buy a great deal of nutrition and the last
      ones buy very little — the knee is where spending stops being worth it.</p>
    </section>

    <${More} label="The same thing as numbers">
      <table>
        <thead><tr>
          <th class="num">Spend a day</th>
          <th class="num">Targets met</th>
          <th class="num">Average of requirements met</th>
        </tr></thead>
        <tbody>
          ${curve.filter(function (_, index) { return index % 3 === 0; })
            .map(function (p) {
              return html`
                <tr key=${p.budget}>
                  <td class="num">${preciseMoney(p.budget, currency)}</td>
                  <td class="num">${p.targetsMet + ' of ' + data.floorCount}</td>
                  <td class="num">${p.averagePercentMet + '%'}</td>
                </tr>`;
            })}
        </tbody>
      </table>
    <//>`;
}
