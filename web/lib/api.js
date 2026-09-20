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

export function post(action, extra) {
  const body = Object.assign({
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
     extra || {});

  return fetch(API, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body)
  }).then(function (response) {
    return response.json().then(function (data) {
      if (!response.ok) { throw new Error(data.error || 'request failed'); }
      return data;
    });
  });
}
