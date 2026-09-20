/* Turning solver output into something a person can read.
 *
 * Nothing here touches state or the DOM: these are the same functions the
 * old single-file app carried, moved so that a component can import one
 * without importing a render tree.
 */

export function money(value, currency) {
  if (value === null || value === undefined) { return '—'; }
  const decimals = currency ? currency.decimals : 2;
  const symbol = currency ? currency.symbol : '';
  return symbol + value.toFixed(decimals);
}

/* Shadow prices are often far smaller than one unit of currency. Rounding a
 * marginal of 0.0422 to the nearest rupee prints "0", which reads as "this is
 * worth nothing" when it means the opposite. So small amounts get however
 * many places they need to say something. */
export function preciseMoney(value, currency) {
  if (value === null || value === undefined) { return '—'; }
  const symbol = currency ? currency.symbol : '';
  let decimals = currency ? currency.decimals : 2;
  const magnitude = Math.abs(value);
  /* A spend that came back as 4e-17 is a floating point residue, not a
     price. Left alone the rule below dutifully prints it as "$0.0000",
     which reads like a number that was measured. */
  if (magnitude < 1e-9) { return symbol + (0).toFixed(decimals); }
  if (magnitude > 0 && magnitude < 1) {
    decimals = Math.max(decimals, Math.min(4, 2 - Math.floor(Math.log(magnitude) / Math.LN10)));
  } else {
    decimals = Math.max(decimals, magnitude < 10 ? 2 : 0);
  }
  return symbol + value.toFixed(decimals);
}

export function plural(count, word) {
  return count + ' ' + word + (count === 1 ? '' : 's');
}

/* `plural` would say "7 dishs". */
export function dishCount(count) {
  return count + (count === 1 ? ' dish' : ' dishes');
}

export function round(value, places) {
  const factor = Math.pow(10, places || 0);
  return Math.round(value * factor) / factor;
}

/* Names for the identifiers the solver speaks in. A shadow price on "vitc" is
   not something to put in front of a person. The tables are filled once, from
   the `presets` and `catalog` answers, as the app boots. */
export const NAMES = { nutrients: {}, units: {}, dishes: {} };

export function nutrientName(id) { return NAMES.nutrients[id] || id; }
export function nutrientUnit(id) { return NAMES.units[id] || ''; }
export function dishName(id) { return NAMES.dishes[id] || id; }
