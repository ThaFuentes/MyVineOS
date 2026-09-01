/**
 * Keep CSRF tokens fresh on real browser sessions.
 * - Inject missing csrf_token fields on POST forms
 * - Refresh empty / stale tokens from <meta name="csrf-token">
 * - On pageshow (bfcache) and focus, re-sync so multi-tab edits don't look like attacks
 */
(function () {
  function getToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? (meta.getAttribute('content') || '') : '';
  }

  function setMetaToken(token) {
    if (!token) return;
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) meta.setAttribute('content', token);
  }

  function ensureCsrfOnForm(form) {
    if (!form || !form.method) return;
    var method = String(form.method).toUpperCase();
    if (method !== 'POST' && method !== 'PUT' && method !== 'PATCH' && method !== 'DELETE') return;

    var token = getToken();
    if (!token) return;

    var input = form.querySelector('input[name="csrf_token"]');
    if (!input) {
      input = document.createElement('input');
      input.type = 'hidden';
      input.name = 'csrf_token';
      form.appendChild(input);
    }
    // Always refresh from meta so long-lived pages stay valid
    if (!input.value || input.value !== token) {
      input.value = token;
    }
  }

  function autofillAll() {
    document.querySelectorAll('form').forEach(ensureCsrfOnForm);
  }

  function refreshFromServer() {
    // Best-effort: only if same origin page is logged in (meta already present)
    if (!getToken()) return;
    try {
      fetch('/security/csrf-token', {
        method: 'GET',
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (data && data.csrf_token) {
            setMetaToken(data.csrf_token);
            autofillAll();
          }
        })
        .catch(function () { /* ignore */ });
    } catch (e) { /* ignore */ }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autofillAll);
  } else {
    autofillAll();
  }

  // Back-forward cache / multi-tab: re-sync tokens when page is shown again
  window.addEventListener('pageshow', function () {
    autofillAll();
  });
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') {
      autofillAll();
      // Soft refresh token after long idle (30+ minutes)
      try {
        var last = window.__pbtCsrfRefreshAt || 0;
        if (Date.now() - last > 30 * 60 * 1000) {
          window.__pbtCsrfRefreshAt = Date.now();
          refreshFromServer();
        }
      } catch (e) { /* ignore */ }
    }
  });

  // Before submit, force latest token into the form (catches stale open tabs)
  document.addEventListener('submit', function (ev) {
    ensureCsrfOnForm(ev.target);
  }, true);

  window.ensureCsrfOnForm = ensureCsrfOnForm;
  window.refreshCsrfToken = refreshFromServer;
})();
