/* Icons, as inline SVG.

   Lucide v0.544.0, ISC licensed, https://lucide.dev -- the path data below is
   copied verbatim from the `lucide-static` package, one entry per icon.

   Inline rather than an icon font, and vendored rather than fetched, because
   the site serves `default-src 'none'`: an icon font would need `font-src`
   opened up and a CDN would need `img-src` or `font-src` pointed at someone
   else's origin. An inline `<svg>` needs neither. It also inherits
   `currentColor`, so an icon is the colour of the text it sits in without
   anything having to say so.
*/

import { html } from '../vendor/preact.js';

const PATHS = {
  "book-open": '<path d="M12 7v14"/> <path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>',
  "calendar-days": '<path d="M8 2v4"/> <path d="M16 2v4"/> <rect width="18" height="18" x="3" y="4" rx="2"/> <path d="M3 10h18"/> <path d="M8 14h.01"/> <path d="M12 14h.01"/> <path d="M16 14h.01"/> <path d="M8 18h.01"/> <path d="M12 18h.01"/> <path d="M16 18h.01"/>',
  "check": '<path d="M20 6 9 17l-5-5"/>',
  "chef-hat": '<path d="M17 21a1 1 0 0 0 1-1v-5.35c0-.457.316-.844.727-1.041a4 4 0 0 0-2.134-7.589 5 5 0 0 0-9.186 0 4 4 0 0 0-2.134 7.588c.411.198.727.585.727 1.041V20a1 1 0 0 0 1 1Z"/> <path d="M6 17h12"/>',
  "chevron-right": '<path d="m9 18 6-6-6-6"/>',
  "circle-alert": '<circle cx="12" cy="12" r="10"/> <line x1="12" x2="12" y1="8" y2="12"/> <line x1="12" x2="12.01" y1="16" y2="16"/>',
  "coins": '<circle cx="8" cy="8" r="6"/> <path d="M18.09 10.37A6 6 0 1 1 10.34 18"/> <path d="M7 6h1v4"/> <path d="m16.71 13.88.7.71-2.82 2.82"/>',
  "copy": '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/> <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
  "info": '<circle cx="12" cy="12" r="10"/> <path d="M12 16v-4"/> <path d="M12 8h.01"/>',
  "link-2": '<path d="M9 17H7A5 5 0 0 1 7 7h2"/> <path d="M15 7h2a5 5 0 1 1 0 10h-2"/> <line x1="8" x2="16" y1="12" y2="12"/>',
  "plus": '<path d="M5 12h14"/> <path d="M12 5v14"/>',
  "scale": '<path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/> <path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/> <path d="M7 21h10"/> <path d="M12 3v18"/> <path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>',
  "search": '<path d="m21 21-4.34-4.34"/> <circle cx="11" cy="11" r="8"/>',
  "shopping-basket": '<path d="m15 11-1 9"/> <path d="m19 11-4-7"/> <path d="M2 11h20"/> <path d="m3.5 11 1.6 7.4a2 2 0 0 0 2 1.6h9.8a2 2 0 0 0 2-1.6l1.7-7.4"/> <path d="M4.5 15.5h15"/> <path d="m5 11 4-7"/> <path d="m9 11 1 9"/>',
  "square-pen": '<path d="M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/> <path d="M18.375 2.625a1 1 0 0 1 3 3l-9.013 9.014a2 2 0 0 1-.853.505l-2.873.84a.5.5 0 0 1-.62-.62l.84-2.873a2 2 0 0 1 .506-.852z"/>',
  "target": '<circle cx="12" cy="12" r="10"/> <circle cx="12" cy="12" r="6"/> <circle cx="12" cy="12" r="2"/>',
  "trending-down": '<path d="M16 17h6v-6"/> <path d="m22 17-8.5-8.5-5 5L2 7"/>',
  "triangle-alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/> <path d="M12 9v4"/> <path d="M12 17h.01"/>',
  "monitor": '<rect width="20" height="14" x="2" y="3" rx="2"/> <line x1="8" x2="16" y1="21" y2="21"/> <line x1="12" x2="12" y1="17" y2="21"/>',
  "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
  "sun": '<circle cx="12" cy="12" r="4"/> <path d="M12 2v2"/> <path d="M12 20v2"/> <path d="m4.93 4.93 1.41 1.41"/> <path d="m17.66 17.66 1.41 1.41"/> <path d="M2 12h2"/> <path d="M20 12h2"/> <path d="m6.34 17.66-1.41 1.41"/> <path d="m19.07 4.93-1.41 1.41"/>',
  "user": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/> <circle cx="12" cy="7" r="4"/>',
  "utensils": '<path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/> <path d="M7 2v20"/> <path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/>',
  "x": '<path d="M18 6 6 18"/> <path d="m6 6 12 12"/>',
};

/* `size` is in pixels and defaults to sitting on the text baseline at the
   surrounding font size. `aria-hidden` because every icon in this app sits
   beside its own label -- none of them is the only thing saying what a
   control does. */
export function Icon({ name, size, klass }) {
  const path = PATHS[name];
  if (!path) { return null; }
  return html`
    <svg class=${'icon' + (klass ? ' ' + klass : '')}
      width=${size || 16} height=${size || 16} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" stroke-width="2"
      stroke-linecap="round" stroke-linejoin="round"
      aria-hidden="true" dangerouslySetInnerHTML=${{ __html: path }} />`;
}
