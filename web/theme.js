/* The stored theme, applied before anything is painted.
 *
 * A classic script rather than a module, and in <head> rather than at the end
 * of <body>, because a module is deferred: by the time one runs the browser
 * has already painted the light page once, and someone who chose dark sees it
 * flash white first. Three lines here costs nothing and removes that.
 *
 * Same-origin, so `script-src 'self'` covers it. Nothing inline anywhere.
 */
(function () {
  try {
    var chosen = window.localStorage.getItem('plategap-theme');
    if (chosen === 'dark' || chosen === 'light') {
      document.documentElement.setAttribute('data-theme', chosen);
    }
  } catch (ignored) {
    /* Private mode, or storage switched off. The system preference still
       applies -- it is the default -- so there is nothing to recover from. */
  }
})();
