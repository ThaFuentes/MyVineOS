/**
 * Inject CSRF token into POST forms that lack a csrf_token field.
 */
(function () {
  function getToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') || '' : '';
  }

  function ensureCsrfOnForm(form) {
    if (!form || !form.method) return;
    const method = String(form.method).toUpperCase();
    if (method !== 'POST') return;
    if (form.querySelector('input[name="csrf_token"]')) return;
    const token = getToken();
    if (!token) return;
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'csrf_token';
    input.value = token;
    form.appendChild(input);
  }

  function autofillAll() {
    document.querySelectorAll('form').forEach(ensureCsrfOnForm);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autofillAll);
  } else {
    autofillAll();
  }

  window.ensureCsrfOnForm = ensureCsrfOnForm;
})();