/* Running a solve from inside a render, without showing yesterday's answer.
 *
 * Every tab is one or more POSTs and nothing sequences them, so moving two
 * controls quickly can land the first answer after the second and leave the
 * screen showing numbers for a question nobody asked. The fetch belongs to
 * the effect that started it: when the key changes the old effect is torn
 * down, its `live` flag goes false, and whatever it was waiting for is
 * dropped on arrival.
 */

import { useState, useEffect } from '../vendor/preact.js';

const PENDING = { loading: true, data: null, error: null };

/* `primed` is the synchronous "do we already have this?" question. Answering
   it before the first render is what keeps a cached tab from flashing a
   skeleton on the way to an answer it already had. */
function ready(primed) {
  const answer = primed ? primed() : undefined;
  return answer === undefined || answer === null ? null
    : { loading: false, data: answer, error: null };
}

export function useAsync(run, key, primed) {
  const [result, setResult] = useState(function () {
    return ready(primed) || PENDING;
  });

  useEffect(function () {
    let live = true;
    const already = ready(primed);
    if (already) { setResult(already); return function () { live = false; }; }

    setResult(PENDING);
    run().then(function (data) {
      if (live) { setResult({ loading: false, data: data, error: null }); }
    }, function (error) {
      if (live) { setResult({ loading: false, data: null, error: error }); }
    });
    return function () { live = false; };
  }, [key]);

  return result;
}
