/**
 * Show “AI is thinking…” while a form POST waits for the model.
 *
 * Usage:
 *   <form data-ai-wait ...>
 *   Optional: data-ai-wait-title="AI is thinking…"
 *             data-ai-wait-sub="Please wait — this can take a few seconds."
 *             data-ai-wait-btn="Waiting for AI…"
 */
(function () {
  'use strict';

  function ensureOverlay(title, sub) {
    var el = document.getElementById('ai-wait-overlay');
    if (!el) {
      el = document.createElement('div');
      el.id = 'ai-wait-overlay';
      el.setAttribute('role', 'alertdialog');
      el.setAttribute('aria-live', 'assertive');
      el.setAttribute('aria-busy', 'true');
      el.innerHTML =
        '<div class="ai-wait-card">' +
        '  <div class="ai-wait-spinner" aria-hidden="true"></div>' +
        '  <p class="ai-wait-title" id="ai-wait-title">AI is thinking…</p>' +
        '  <p class="ai-wait-sub" id="ai-wait-sub">Please wait — this can take a few seconds.</p>' +
        '</div>';
      document.body.appendChild(el);
    }
    var t = el.querySelector('#ai-wait-title');
    var s = el.querySelector('#ai-wait-sub');
    if (t && title) t.textContent = title;
    if (s && sub) s.textContent = sub;
    return el;
  }

  function showWait(form) {
    var title = form.getAttribute('data-ai-wait-title') || 'AI is thinking…';
    var sub =
      form.getAttribute('data-ai-wait-sub') ||
      'Please wait — this can take a few seconds. Do not close this page.';
    var overlay = ensureOverlay(title, sub);
    overlay.classList.add('is-open');
    document.body.style.cursor = 'wait';

    var btnLabel = form.getAttribute('data-ai-wait-btn') || 'Waiting for AI…';
    var buttons = form.querySelectorAll('button[type="submit"], input[type="submit"]');
    buttons.forEach(function (btn) {
      if (btn.dataset.aiWaitLocked) return;
      btn.dataset.aiWaitLocked = '1';
      if (btn.tagName === 'BUTTON') {
        btn.dataset.aiWaitOriginal = btn.innerHTML;
        btn.innerHTML =
          '<i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i> ' +
          btnLabel;
      } else {
        btn.dataset.aiWaitOriginal = btn.value;
        btn.value = btnLabel;
      }
      btn.disabled = true;
      btn.classList.add('is-ai-waiting');
    });
  }

  function bindForm(form) {
    if (!form || form.dataset.aiWaitBound) return;
    form.dataset.aiWaitBound = '1';
    form.addEventListener('submit', function () {
      if (form.dataset.aiWaitActive === '1') {
        // Already submitting — block double-clicks without canceling the first submit.
        return;
      }
      form.dataset.aiWaitActive = '1';
      // Show overlay immediately; delay disabling the button so the browser
      // can finish submitting the form (some browsers cancel if the button
      // is disabled in the same tick as submit).
      ensureOverlay(
        form.getAttribute('data-ai-wait-title') || 'AI is thinking…',
        form.getAttribute('data-ai-wait-sub') ||
          'Please wait — this can take a few seconds. Do not close this page.'
      ).classList.add('is-open');
      document.body.style.cursor = 'wait';
      setTimeout(function () {
        showWait(form);
      }, 50);
    });
  }

  function init() {
    document.querySelectorAll('form[data-ai-wait]').forEach(bindForm);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Expose for dynamic forms
  window.MyVineAiWait = { bind: bindForm, show: showWait };
})();
