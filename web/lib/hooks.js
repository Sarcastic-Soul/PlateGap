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

export function useAsync(run, key) {
  const [result, setResult] = useState({ loading: true, data: null, error: null });

  useEffect(function () {
    let live = true;
    setResult(function (previous) {
      return previous.loading && !previous.data ? previous
        : { loading: true, data: null, error: null };
    });
    run().then(function (data) {
      if (live) { setResult({ loading: false, data: data, error: null }); }
    }, function (error) {
      if (live) { setResult({ loading: false, data: null, error: error }); }
    });
    return function () { live = false; };
  }, [key]);

  return result;
}
