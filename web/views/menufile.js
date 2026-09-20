/* Read a menu in from a file, a photograph, or a paste.
 *
 * Typing a week's timetable in dish by dish is the reason nobody uses a tool
 * like this on their own mess. The menu already exists: it is a sheet taped
 * to the dining hall wall, a spreadsheet the warden exported, a photo of
 * either forwarded round a hostel group. So this takes it as it is.
 *
 * What comes back is never applied silently. The transcription is shown and
 * is editable, every dish we could not place is listed with the near misses
 * that were rejected, and nothing reaches the builder until somebody looks
 * at it and says so. Character recognition on a photographed noticeboard
 * gets things wrong, and the person holding the phone is the only one who
 * can tell which things.
 */

import { html, useState, useRef } from '../vendor/preact.js';
import { MAX_DISHES_PER_MEAL, MEAL_NAMES, DAY_NAMES } from '../lib/constants.js';
import { plural } from '../lib/format.js';
import { state, customFromMenu } from '../lib/store.js';
import { postBare } from '../lib/api.js';
import { Icon } from '../lib/icons.js';
import { Stat, More, Info } from './pieces.js';

/* What the browser may hand us, and what the API calls it. */
const KINDS = {
  'application/pdf': 'pdf',
  'image/png': 'png',
  'image/jpeg': 'jpeg',
  'image/webp': 'webp',
  'image/gif': 'gif'
};

/* The handler's own ceiling, less the third that base64 adds on the way. */
const MAX_BYTES = 2.5 * 1024 * 1024;

/* A photograph of a noticeboard is eight megapixels of wall. The words on it
 * survive being shrunk to this and the upload stops being the slow part on
 * campus wifi -- which matters, because the person doing this is standing in
 * front of the noticeboard. */
const MAX_SIDE = 1600;
const JPEG_QUALITY = 0.85;

function asBase64(blob) {
  return new Promise(function (done, fail) {
    const reader = new FileReader();
    reader.onerror = function () { fail(new Error('that file could not be read')); };
    reader.onload = function () {
      /* A data URL, so the payload is after the comma and already encoded.
         Doing it this way rather than with btoa over a byte string avoids
         building a megabyte-long intermediate string by hand. */
      const url = String(reader.result);
      done(url.slice(url.indexOf(',') + 1));
    };
    reader.readAsDataURL(blob);
  });
}

/* Shrink a photograph before sending it. Anything that goes wrong here --
   an image the browser will not decode, a canvas it will not export -- falls
   back to sending the original, which is a slower upload and not a failure. */
function shrink(file) {
  if (!window.createImageBitmap || !file.type || file.type.indexOf('image/') !== 0) {
    return Promise.resolve(null);
  }
  return window.createImageBitmap(file).then(function (bitmap) {
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
    if (scale === 1 && file.size <= MAX_BYTES) { return null; }
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    return new Promise(function (done) {
      canvas.toBlob(function (blob) { done(blob); }, 'image/jpeg', JPEG_QUALITY);
    });
  }).catch(function () { return null; });
}

function describe(problem) {
  return (problem && problem.message) || 'that file could not be read';
}

/* One row per name, not one per occurrence.
 *
 * A week of mess menu says "sambhar" at four breakfasts and "chutney" at
 * four more, and the parser reports each one, correctly -- they are four
 * separate places a dish is missing. But nobody wants to answer the same
 * question four times, so the screen groups them and a single answer is
 * applied everywhere the name appears. */
function groupMisses(unmatched) {
  const groups = [];
  const byText = {};
  unmatched.forEach(function (entry) {
    let group = byText[entry.text];
    if (!group) {
      group = byText[entry.text] = {
        text: entry.text,
        reason: entry.reason,
        suggestions: entry.suggestions || [],
        where: []
      };
      groups.push(group);
    }
    group.where.push(entry);
  });
  return groups;
}

function whereLabel(group) {
  const meals = [];
  group.where.forEach(function (entry) {
    const name = MEAL_NAMES[entry.meal];
    if (name && meals.indexOf(name) === -1) { meals.push(name); }
  });
  if (group.where.length === 1) {
    const one = group.where[0];
    const when = one.everyDay ? 'Every day' : (DAY_NAMES[one.day] || '');
    return when ? when + ' · ' + meals.join(', ') : meals.join(', ');
  }
  return meals.join(', ') + ' · ' + group.where.length + ' times';
}

export function MenuImport({ onUse, children }) {
  const [busy, setBusy] = useState('');
  const [problem, setProblem] = useState(null);
  const [reading, setReading] = useState(null);
  const [text, setText] = useState('');
  const [dragging, setDragging] = useState(false);
  const chooser = useRef(null);

  function failed(message) {
    setBusy('');
    setReading(null);
    setProblem(message);
  }

  function took(answer, typed) {
    setBusy('');
    if (answer.read === false) {
      failed(answer.reason);
      return;
    }
    setProblem(null);
    setReading(answer);
    setText(answer.text !== undefined ? answer.text : typed);
  }

  function upload(file) {
    if (!file) { return; }
    const kind = KINDS[file.type];
    if (!kind) {
      failed('That is a ' + (file.type || 'kind of file')
        + '. Send a PDF or a photograph of the menu.');
      return;
    }
    setProblem(null);
    setBusy('Reading ' + file.name);
    shrink(file).then(function (smaller) {
      const sending = smaller || file;
      if (sending.size > MAX_BYTES) {
        throw new Error('That file is ' + (sending.size / 1048576).toFixed(1)
          + ' MB and the limit is ' + (MAX_BYTES / 1048576).toFixed(1)
          + ' MB. A photograph of the page is usually much smaller than a scan.');
      }
      return asBase64(sending).then(function (encoded) {
        return postBare('scan', {
          file: encoded,
          kind: smaller ? 'jpeg' : kind,
          name: file.name.replace(/\.[^.]+$/, ''),
          region: state.region || undefined
        });
      });
    }).then(function (answer) { took(answer); },
            function (trouble) { failed(describe(trouble)); });
  }

  function reread() {
    const typed = text;
    if (!typed.trim()) { return; }
    setProblem(null);
    setBusy('Matching against the catalog');
    postBare('parse', {
      name: (reading && reading.menu && reading.menu.name) || undefined,
      region: state.region || undefined,
      text: typed
    }).then(function (answer) { took(answer, typed); },
            function (trouble) { failed(describe(trouble)); });
  }

  /* Accepting a near miss edits the menu we are about to hand over, not the
     one being solved: nothing here has reached the builder yet. */
  function accept(group, dish) {
    const menu = reading.menu;
    if (!menu) { return; }
    group.where.forEach(function (entry) {
      const into = entry.everyDay
        ? (menu.daily[entry.meal] = menu.daily[entry.meal] || [])
        : (menu.days[entry.day] && (menu.days[entry.day][entry.meal]
            = menu.days[entry.day][entry.meal] || []));
      if (!into) { return; }
      if (into.indexOf(dish.id) === -1 && into.length < MAX_DISHES_PER_MEAL) {
        into.push(dish.id);
      }
    });
    const fixed = group.where.length;
    setReading(Object.assign({}, reading, {
      unmatched: reading.unmatched.filter(function (other) {
        return group.where.indexOf(other) === -1;
      }),
      stats: Object.assign({}, reading.stats, {
        matched: reading.stats.matched + fixed,
        unmatched: reading.stats.unmatched - fixed
      })
    }));
  }

  if (busy) {
    return html`
      <section class="panel scan">
        <div class="loading scanning">
          <${Icon} name="sparkles" size=${26} />
          <p>${busy + '…'}</p>
          <div class="shim line" style="width:60%"></div>
          <div class="shim line" style="width:80%"></div>
          <div class="shim line" style="width:45%"></div>
        </div>
      </section>`;
  }

  if (reading) {
    return html`<${Review} reading=${reading} text=${text} setText=${setText}
      accept=${accept} reread=${reread} onUse=${onUse}
      again=${function () { setReading(null); setText(''); }} />`;
  }

  return html`
    <section class="panel scan">
      <div class=${'drop' + (dragging ? ' over' : '')}
        onDragOver=${function (event) { event.preventDefault(); setDragging(true); }}
        onDragLeave=${function () { setDragging(false); }}
        onDrop=${function (event) {
          event.preventDefault();
          setDragging(false);
          upload(event.dataTransfer.files && event.dataTransfer.files[0]);
        }}>
        <${Icon} name="upload" size=${28} />
        <h2>
          <span>Start from the menu on the wall</span>
          <${Info} label="What happens to your file">
            <p>The file is sent once, read, and not kept. Nothing is stored
            and there is nothing to sign into.</p>
            <p>A model does the typing and only the typing: it turns the page
            into text. Which catalog dish each written name means is decided
            here, by string matching against a fixed list, so anything we
            cannot place is reported rather than guessed at.</p>
          <//>
        </h2>
        <p>Photograph it, or drop the PDF your mess sent round.</p>
        <input type="file" ref=${chooser} class="hidden-file"
          accept="application/pdf,image/png,image/jpeg,image/webp,image/gif"
          onChange=${function (event) {
            upload(event.target.files && event.target.files[0]);
            event.target.value = '';
          }} />
        <button class="chip action" type="button"
          onClick=${function () { chooser.current.click(); }}>
          <${Icon} name="upload" size=${14} /><span>Choose a photo or PDF</span>
        </button>
      </div>

      ${problem ? html`
        <div class="error">
          <${Icon} name="circle-alert" />
          <span>${problem}</span>
        </div>` : null}

      <${More} label="Or paste it as text">
        <p class="note">However it is written — a table, a list, a WhatsApp
        forward. Days across the top or meals down the side, both are read.</p>
        <textarea class="menu-text" rows="8" value=${text}
          placeholder=${'Monday\nBreakfast: aloo paratha, curd\nLunch: chole, jeera rice, roti'}
          onInput=${function (event) { setText(event.target.value); }}></textarea>
        <button class="chip action" type="button" onClick=${reread}
          disabled=${!text.trim() || null}>Read this</button>
      <//>
    </section>

    ${/* Whatever else the page offers instead, shown only while nothing has
         been read. Once there is a menu on screen to check, an invitation to
         start a different one is just another thing to read past. */ ''}
    ${children}`;
}

function Review({ reading, text, setText, accept, reread, onUse, again }) {
  const stats = reading.stats;
  const menu = reading.menu;
  const days = reading.days || [];

  /* The ones worth a decision come first. A name with no near miss is not a
     question anybody can answer here, so it is folded out of the way. */
  const groups = groupMisses(reading.unmatched);
  const fixable = menu
    ? groups.filter(function (group) { return group.suggestions.length; })
    : [];
  const hopeless = groups.filter(function (group) {
    return fixable.indexOf(group) === -1;
  });

  return html`
    <section class="panel scan">
      <h2 class="with-icon">
        <${Icon} name="file-text" />
        <span>What we read</span>
        <${Info} label="Why you are being shown this">
          <p>Reading a photograph of a noticeboard gets things wrong, and the
          only person who can tell which things is you.</p>
          <p>Every name we could not place is below with the dishes that were
          nearly chosen instead. None of them was applied, because a menu
          quietly missing half its dishes would report a shortfall you do not
          have.</p>
        <//>
      </h2>

      <div class="headline">
        <${Stat} hero value=${stats.matched}
          label=${'dishes read off your menu' + (days.length
            ? ', across ' + plural(days.length, 'day') : '')} />
        <${Stat} value=${fixable.length}
          label=${(fixable.length === 1 ? 'name is' : 'names are')
            + ' a near miss — one tap each to settle them'} />
      </div>

      ${reading.warnings.map(function (warning) {
        return html`
          <div key=${warning} class="error warn">
            <${Icon} name="triangle-alert" />
            <span>${warning}</span>
          </div>`;
      })}

      ${fixable.length ? html`
        <div class="misses">
          ${fixable.map(function (group) {
            return html`
              <div key=${group.text} class="miss">
                <div class="miss-what">
                  <b>${group.text}</b>
                  <span class="why">${whereLabel(group)}</span>
                </div>
                <div class="chips">
                  ${group.suggestions.map(function (dish) {
                    return html`
                      <button key=${dish.id} class="chip" type="button"
                        title=${'Read ' + group.text + ' as ' + dish.name}
                        onClick=${function () { accept(group, dish); }}>
                        <${Icon} name="plus" size=${13} />
                        <span>${dish.name}</span>
                      </button>`;
                  })}
                </div>
              </div>`;
          })}
        </div>` : null}

      ${hopeless.length ? html`
        <${More} label=${plural(hopeless.length, 'name')
          + ' the catalog has nothing like'}>
          <p class="note">Sides, portions and brand names mostly — things a
          mess writes down that are not a dish anyone eats a plate of. They
          are listed because a menu quietly missing part of itself would
          report a shortfall you do not have.</p>
          <div class="misses">
            ${hopeless.map(function (group) {
              return html`
                <div key=${group.text} class="miss">
                  <div class="miss-what">
                    <b>${group.text}</b>
                    <span class="why">${whereLabel(group)}</span>
                  </div>
                  <span class="why">${group.reason}</span>
                </div>`;
            })}
          </div>
        <//>` : null}

      <${More} label="The text we read, and a chance to fix it">
        <textarea class="menu-text" rows="12" value=${text}
          onInput=${function (event) { setText(event.target.value); }}></textarea>
        <div class="chips actions">
          <button class="chip" type="button" onClick=${reread}>
            <${Icon} name="rotate-cw" size=${14} /><span>Read it again</span>
          </button>
        </div>
      <//>

      <div class="chips actions">
        <button class="chip action" type="button"
          disabled=${menu ? null : true}
          onClick=${function () { onUse(customFromMenu(menu, MAX_DISHES_PER_MEAL)); }}>
          ${menu ? 'Use this menu' : 'Nothing to use yet'}
        </button>
        <button class="chip" type="button" onClick=${again}>Start over</button>
      </div>

      ${menu ? null : html`
        <p class="note">No day came out of that with anything on it. Fix the
        text above and read it again, or build the menu by hand.</p>`}
    </section>`;
}
