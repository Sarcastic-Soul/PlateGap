/* One POST, one action, one JSON body back.
 *
 * There is no routing and no client library because there is no API to
 * speak of: the Lambda takes `{"action": ...}` and answers with the result.
 */

import { state, isCustom, customPayload } from './store.js';

/* In production config.js carries the Function URL. Falling back to this
 * page's own origin is what makes `scripts/dev_server.py` work: it serves the
 * files and answers the POSTs on the same port, whatever port that is. */
export const API = window.PLATEGAP_API || (window.location.origin + '/');

/* Retrying a throttle, because the burst is shorter than the patience.
 *
 * The account runs at ten concurrent Lambda executions, and opening the page
 * costs four calls -- presets, catalog, gap, solve -- so three or four people
 * clicking a shared link in the same second is the whole ceiling. Measured
 * with ten browsers against the live site: ten simultaneous arrivals threw
 * away 4 of 40 calls with a 429, and the entire burst was over in 5.6
 * seconds. Ten arrivals spread over a minute lost nothing at all.
 *
 * A burst that short does not want a bigger quota, it wants a second attempt.
 * The delays below outlast the burst, and each is jittered because every
 * client that was throttled was throttled at the same instant -- retrying all
 * of them on the same schedule would rebuild the burst it is recovering from.
 */
const RETRY_DELAYS = [400, 1200, 3000];

function pause(milliseconds) {
  const jittered = milliseconds * (0.5 + Math.random());
  return new Promise(function (resume) { window.setTimeout(resume, jittered); });
}

/* A throttled Function URL answers with `{"message": "Rate Exceeded."}` and
   no `error` key, so without this the screen said "request failed", which
   reads like the solver is broken rather than like the site is busy. */
function complaint(response, data) {
  if (response.status === 429) {
    return 'the site is busy — several people are solving at once. '
      + 'Give it a moment and try again.';
  }
  return data.error || 'request failed';
}

function send(body, attempt) {
  return fetch(API, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: body
  }).then(function (response) {
    return response.json().catch(function () { return {}; })
      .then(function (data) {
        if (response.ok) { return data; }
        if (response.status === 429 && attempt < RETRY_DELAYS.length) {
          return pause(RETRY_DELAYS[attempt]).then(function () {
            return send(body, attempt + 1);
          });
        }
        throw new Error(complaint(response, data));
      });
  });
}

/* Answers that cannot have changed.
 *
 * The request body names everything the answer depends on -- the action, the
 * menu, the day, the diet, the profile, every edited price -- so two requests
 * with the same body have the same answer by construction, and the body is
 * its own cache key. Nothing needs invalidating: change a control and the
 * body changes with it.
 *
 * What this buys is tab switching. Moving between the gap and the frontier
 * and back used to be three solves; now the second visit is free and the
 * page paints immediately. `presets` and `catalog` are covered by the same
 * rule, which is why they survive a shared link replacing the whole menu.
 *
 * Only successes are kept -- a failure is a thing to retry, not a thing to
 * remember -- and the map is bounded, because a long session editing prices
 * would otherwise keep every intermediate answer alive. Insertion order is
 * eviction order, which is the oldest rather than the least used; for a cache
 * this size the difference does not pay for the bookkeeping.
 */
const CACHE_LIMIT = 48;
const cache = new Map();

export function clearCache() { cache.clear(); }

function remember(key, answer) {
  cache.set(key, answer);
  while (cache.size > CACHE_LIMIT) {
    cache.delete(cache.keys().next().value);
  }
  return answer;
}

function bodyFor(action, extra) {
  return JSON.stringify(Object.assign({
    action: action,
    day: state.day,
    diet: state.diet,
    prices: state.prices,
    profile: {
      region: state.region,
      sex: state.sex,
      activity: state.activity,
      maxPlateGrams: state.grams
    }
  }, isCustom() ? { menu: customPayload() } : { menuId: state.menuId },
     extra || {}));
}

/* The answer if it is already known, and nothing if it is not.
 *
 * Synchronous on purpose. A cached answer handed back through a promise still
 * paints a skeleton for one frame before it resolves, and a skeleton that
 * flashes on a tab you have already visited is worse than no skeleton at all.
 * `useAsync` asks this first and only renders a loading state when the answer
 * really does have to be fetched. */
export function known(action, extra) {
  return cache.get(bodyFor(action, extra));
}

export function post(action, extra) {
  const key = bodyFor(action, extra);
  if (cache.has(key)) { return Promise.resolve(cache.get(key)); }
  return send(key, 0).then(function (answer) { return remember(key, answer); });
}
