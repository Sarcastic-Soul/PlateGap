/* What each rupee buys: the gap closed against the money spent. */

import { html, useState } from '../vendor/preact.js';
import { money, preciseMoney } from '../lib/format.js';
import { solveKey } from '../lib/store.js';
import { post, known } from '../lib/api.js';
import { useAsync } from '../lib/hooks.js';
import { Icon } from '../lib/icons.js';
import { Stat, More, Skeleton, Failed, AskForDishes, emptyBuild } from './pieces.js';

/* The plot area, in viewBox units. `padL` is wide enough for "none left" at
   the label size: the axis captions sit outside the plot rather than on top
   of it, which is what they used to do. */
const W = 720, H = 230, padL = 74, padR = 16, padT = 16, padB = 36;

function Chart({ curve, currency }) {
  /* -1 is "nothing under the cursor", which is a real state rather than a
     missing one: the readout above says so instead of disappearing, so
     reading the curve never changes the height of the page. */
  const [at, setAt] = useState(-1);

  const maxBudget = curve[curve.length - 1].budget || 1;
  const maxUnmet = curve[0].unmetFraction || 1;

  function x(value) { return padL + (value / maxBudget) * (W - padL - padR); }
  function y(value) { return padT + (1 - value / maxUnmet) * (H - padT - padB); }

  const points = curve.map(function (p) { return x(p.budget) + ',' + y(p.unmetFraction); });
  const area = 'M' + x(0) + ',' + y(0) + ' L' + points.join(' L')
    + ' L' + x(maxBudget) + ',' + y(0) + ' Z';

  /* Pointer position to a point on the curve. The viewBox maps exactly onto
     the rendered box -- the SVG is `width: 100%; height: auto`, so there is
     no letterboxing to correct for -- which makes this one ratio. */
  function nearest(event) {
    const box = event.currentTarget.ownerSVGElement.getBoundingClientRect();
    const units = (event.clientX - box.left) / box.width * W;
    const budget = (units - padL) / (W - padL - padR) * maxBudget;
    let best = 0;
    for (let i = 1; i < curve.length; i++) {
      if (Math.abs(curve[i].budget - budget) < Math.abs(curve[best].budget - budget)) {
        best = i;
      }
    }
    return best;
  }

  /* Arrow keys walk the curve, because a chart you can only read with a mouse
     is a chart half the people who open it cannot read at all. */
  function onKeyDown(event) {
    const step = event.key === 'ArrowRight' ? 1 : (event.key === 'ArrowLeft' ? -1 : 0);
    if (!step) { return; }
    event.preventDefault();
    const from = at < 0 ? (step > 0 ? -1 : curve.length) : at;
    setAt(Math.max(0, Math.min(curve.length - 1, from + step)));
  }

  const here = at >= 0 ? curve[at] : null;

  return html`
    <div class="readout" aria-live="polite">
      ${here ? html`
        <span><b>${preciseMoney(here.budget, currency)}</b> a day</span>
        <span><b>${here.targetsMet + ' of ' + (here.targetsMet + here.targetsMissed)}</b> targets met</span>
        <span><b>${here.averagePercentMet + '%'}</b> of requirements met, on average</span>`
      : html`<span>Point at the curve, or drag across it, to read any amount
        of spending on it.</span>`}
    </div>

    <svg class="chart" viewBox=${'0 0 ' + W + ' ' + H}
      role="img" tabindex="0" onKeyDown=${onKeyDown}
      title="Arrow keys walk along the curve"
      onBlur=${function () { setAt(-1); }}
      aria-label=${'The share of the gap still open, against money spent, from '
        + money(0, currency) + ' to ' + preciseMoney(maxBudget, currency) + ' a day'}>
      <path class="chart-area" d=${area} />
      <polyline class="chart-line" points=${points.join(' ')} />
      <line class="chart-axis" x1=${padL} y1=${y(0)} x2=${W - padR} y2=${y(0)} />
      <line class="chart-axis" x1=${padL} y1=${padT} x2=${padL} y2=${y(0)} />

      ${here ? html`
        <line class="chart-guide" x1=${x(here.budget)} y1=${padT}
          x2=${x(here.budget)} y2=${y(0)} />
        <circle class="chart-dot" cx=${x(here.budget)} cy=${y(here.unmetFraction)} r="4.5" />`
      : null}

      <text class="chart-label" x=${padL} y=${H - 12}>${money(0, currency)}</text>
      <text class="chart-label" x=${W - padR} y=${H - 12} text-anchor="end">
        ${preciseMoney(maxBudget, currency) + ' a day'}</text>
      ${/* The axis is the share of the gap still open. These sit to the left
           of it, right-aligned, so they cannot land on the curve however
           wide the browser window is. */ ''}
      <text class="chart-label" x=${padL - 10} y=${padT + 4} text-anchor="end">all of it</text>
      <text class="chart-label" x=${padL - 10} y=${y(0) + 4} text-anchor="end">none left</text>

      ${/* Last, so it is on top of everything and catches every pointer. */ ''}
      <rect class="chart-hit" x=${padL} y=${padT}
        width=${W - padL - padR} height=${y(0) - padT}
        onPointerMove=${function (event) { setAt(nearest(event)); }}
        onPointerLeave=${function () { setAt(-1); }} />
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
