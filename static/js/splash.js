/* Shows the logo splash once per browser session, then removes it. */
(function () {
  'use strict';
  var splash = document.getElementById('splash');
  if (!splash) { return; }

  var seen = false;
  try { seen = sessionStorage.getItem('ssc_splash') === '1'; } catch (e) { /* ignore */ }

  if (seen) {
    splash.parentNode.removeChild(splash);
    return;
  }
  try { sessionStorage.setItem('ssc_splash', '1'); } catch (e) { /* ignore */ }

  // The CSS animation fades it out after ~3s; remove it from the page afterwards.
  setTimeout(function () {
    if (splash.parentNode) { splash.parentNode.removeChild(splash); }
  }, 3400);
})();
