/**
 * Aeria CRM Tracking Snippet
 * ============================
 * Add this to your site's <head> or before </body> to track page views.
 *
 * Usage:
 *   <script defer src="https://crm.aeria-apps.com.br/static/tracker.js"
 *           data-api="https://crm.aeria-apps.com.br/api/track"></script>
 *
 * Or copy/paste inline:
 *   <script>(function(){var e=document.currentScript;var a=e&&e.getAttribute('data-api')||'/_crm/api/track';var i=new Image();i.src=a+'?path='+encodeURIComponent(window.location.pathname)+'&r='+encodeURIComponent(document.referrer)+'&_t='+Date.now();})();</script>
 */
(function() {
  'use strict';
  var script = document.currentScript;
  var apiUrl = (script && script.getAttribute('data-api')) || '/_crm/api/track';

  // --- Page view tracking ---
  function trackPage() {
    var data = {
      path: window.location.pathname + window.location.search,
      referrer: document.referrer,
      screen: screen.width + 'x' + screen.height,
      language: navigator.language
    };
    // Use sendBeacon for reliability on page unload
    if (navigator.sendBeacon) {
      var blob = new Blob([JSON.stringify(data)], { type: 'application/json' });
      navigator.sendBeacon(apiUrl, blob);
    } else {
      var xhr = new XMLHttpRequest();
      xhr.open('POST', apiUrl, true);
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.send(JSON.stringify(data));
    }
  }

  // Track on initial load
  if (document.readyState === 'complete') {
    trackPage();
  } else {
    window.addEventListener('load', trackPage);
  }

  // Track Single Page App navigations
  var lastPath = window.location.pathname;
  var observer = new MutationObserver(function() {
    if (window.location.pathname !== lastPath) {
      lastPath = window.location.pathname;
      trackPage();
    }
  });
  observer.observe(document.querySelector('title') || document.documentElement, {
    subtree: true, childList: true, characterData: true
  });
})();
