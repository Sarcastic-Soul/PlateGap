/* Where the numbers come from. No solve: this tab is the sources. */

import { html } from '../vendor/preact.js';
import { state, currentMenu } from '../lib/store.js';
import { Icon } from '../lib/icons.js';
import { More } from './pieces.js';

export function DataTab() {
  const notes = state.presets.notes;
  const menu = currentMenu();

  return html`
    <section class="panel">
      <h2 class="with-icon">
        <${Icon} name="calendar-days" />
        <span>This menu</span>
      </h2>
      <p><b>${menu.name}</b>${' — ' + (menu.subtitle || '')}</p>
      ${menu.source && menu.source.note
        ? html`<p class="note">${menu.source.note}</p>` : null}
      ${menu.servingStyleNote
        ? html`<p class="note">${menu.servingStyleNote}</p>` : null}
    </section>

    <section class="panel">
      <h2 class="with-icon">
        <${Icon} name="book-open" />
        <span>Where the nutrition numbers come from</span>
      </h2>
      <ul>
        ${Object.keys(notes).map(function (key) {
          return html`<li key=${key}>${notes[key]}</li>`;
        })}
      </ul>
    </section>

    <section class="panel">
      <h2 class="with-icon">
        <${Icon} name="scale" />
        <span>Reference intakes</span>
      </h2>
      <ul>
        ${state.presets.regions.map(function (region) {
          return html`<li key=${region.id}><b>${region.name}</b>${' — ' + region.citation}</li>`;
        })}
      </ul>
      <p class="note">These disagree with each other, sometimes sharply. Iron
      for an adult man is 19 mg under the Indian reference and 8 mg under the
      American one, because the Indian figure assumes a largely plant-based
      diet and poorer absorption. Neither is the truth for everyone, which is
      why you pick.</p>
    </section>

    <section class="panel">
      <h2 class="with-icon">
        <${Icon} name="info" />
        <span>Things this does not know</span>
      </h2>
      <ul>
        <li>Whether the kitchen actually cooked the recipe we assumed.</li>
        <li>What you like eating. The plan is nutritionally cheapest, not nicest.</li>
        <li>Losses in cooking, serving and reheating.</li>
        <li>Anything marked estimated: paneer and jaggery come from the Indian
        Food Composition Tables 2017 instead of USDA, and keep the flag for one
        nutrient each — IFCT measures vitamin B12 for no food at all. Whey
        protein is the only ingredient still estimated outright.</li>
      </ul>
    </section>`;
}
