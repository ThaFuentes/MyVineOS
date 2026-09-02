/**
 * Curriculum Studio — lesson builder UI helpers.
 * Opens add-block panels, multi-choice rows, study interactions.
 */
(function () {
  'use strict';

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  function qsa(sel, root) {
    return Array.from((root || document).querySelectorAll(sel));
  }

  function showPanel(id) {
    if (!id) return;
    // Close others first so only one add form is open
    qsa('.curr-add-panel').forEach(function (panel) {
      if (panel.id === id) {
        panel.hidden = false;
        panel.removeAttribute('hidden');
        panel.style.display = '';
        panel.classList.add('is-open');
        try {
          panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } catch (e) {
          panel.scrollIntoView(true);
        }
        var focusable = panel.querySelector('textarea, input:not([type=hidden]), select');
        if (focusable) {
          setTimeout(function () {
            try {
              focusable.focus();
            } catch (err) { /* ignore */ }
          }, 50);
        }
      } else {
        panel.hidden = true;
        panel.setAttribute('hidden', '');
        panel.classList.remove('is-open');
      }
    });
  }

  function closePanel(panel) {
    if (!panel) return;
    panel.hidden = true;
    panel.setAttribute('hidden', '');
    panel.classList.remove('is-open');
  }

  function closeAllPanels() {
    qsa('.curr-add-panel').forEach(closePanel);
  }

  function choiceRowHtml(index) {
    return (
      '<div class="curr-choice-row">' +
      '<input type="text" name="choice_label" class="form-input" placeholder="Choice ' +
      (index + 1) +
      '">' +
      '<label class="checkbox-label" style="display:flex;align-items:center;gap:0.35rem;font-weight:500;color:var(--text-primary);">' +
      '<input type="checkbox" name="choice_correct" value="' +
      index +
      '"> Correct' +
      '</label>' +
      '<button type="button" class="btn btn-secondary" style="min-height:auto;padding:0.3rem 0.5rem;" data-remove-choice>×</button>' +
      '</div>'
    );
  }

  function reindexChoices(container) {
    if (!container) return;
    qsa('.curr-choice-row', container).forEach(function (row, i) {
      var cb = row.querySelector('input[name="choice_correct"]');
      if (cb) cb.value = String(i);
      var input = row.querySelector('input[name="choice_label"]');
      if (input && !input.value) {
        input.placeholder = 'Choice ' + (i + 1);
      }
    });
  }

  function onReady() {
    // Toolbar: open add panels
    document.addEventListener('click', function (e) {
      var openBtn = e.target.closest('[data-curr-open]');
      if (openBtn) {
        e.preventDefault();
        e.stopPropagation();
        showPanel(openBtn.getAttribute('data-curr-open'));
        return;
      }

      var closeBtn = e.target.closest('[data-curr-close]');
      if (closeBtn) {
        e.preventDefault();
        closePanel(closeBtn.closest('.curr-add-panel'));
        return;
      }

      var addChoice = e.target.closest('[data-add-choice]');
      if (addChoice) {
        e.preventDefault();
        var sel = addChoice.getAttribute('data-add-choice');
        var box = qs(sel);
        if (!box) return;
        var idx = qsa('.curr-choice-row', box).length;
        box.insertAdjacentHTML('beforeend', choiceRowHtml(idx));
        reindexChoices(box);
        return;
      }

      var removeChoice = e.target.closest('[data-remove-choice]');
      if (removeChoice) {
        e.preventDefault();
        var row = removeChoice.closest('.curr-choice-row');
        var parent = row && row.parentElement;
        if (row) row.remove();
        reindexChoices(parent);
        return;
      }
    });

    // Escape closes open add panel
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeAllPanels();
    });

    // If URL hash points at a block, scroll to it
    if (window.location.hash && window.location.hash.indexOf('#block-') === 0) {
      var target = qs(window.location.hash);
      if (target) {
        setTimeout(function () {
          try {
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
          } catch (err) {
            target.scrollIntoView(true);
          }
        }, 100);
      }
    }

    bindAccessPicker();
    bindStudyAnswers();
  }

  function syncPublicNote(root) {
    var box = (root || document).querySelector('input[name="access_level"][value="public"]');
    var note = (root || document).querySelector('[data-public-note]');
    if (!note) return;
    var on = !!(box && box.checked);
    note.hidden = !on;
    if (on) note.removeAttribute('hidden');
    else note.setAttribute('hidden', '');
  }

  function bindAccessPicker() {
    qsa('[data-curr-access]').forEach(function (root) {
      syncPublicNote(root);
      root.addEventListener('change', function () {
        syncPublicNote(root);
      });
    });

    document.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-access-preset]');
      if (!btn) return;
      e.preventDefault();
      var root = btn.closest('[data-curr-access]') || document;
      var wanted = (btn.getAttribute('data-access-preset') || '')
        .split(',')
        .map(function (s) { return s.trim(); })
        .filter(Boolean);
      qsa('input[name="access_level"]', root).forEach(function (cb) {
        cb.checked = wanted.indexOf(cb.value) !== -1;
      });
      syncPublicNote(root);
    });
  }

  function bindStudyAnswers() {
    document.addEventListener('submit', function (e) {
      var form = e.target.closest && e.target.closest('form.study-answer-form');
      if (!form) return;
      if (form.getAttribute('data-preview') === '1') return;
      if (!form.getAttribute('action') || form.getAttribute('action') === '#') return;
      e.preventDefault();
      var result = form.querySelector('.study-result:not(.is-done)') || form.querySelector('.study-result');
      var btn = form.querySelector('button[type="submit"]');
      if (btn) btn.disabled = true;
      fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        credentials: 'same-origin',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          Accept: 'application/json',
        },
      })
        .then(function (r) {
          if (r.status === 401) {
            window.location.href = r.url || '/login';
            return null;
          }
          return r.json();
        })
        .then(function (data) {
          if (!data) return;
          if (!result) return;
          result.classList.remove('is-correct', 'is-wrong');
          var expl = data.feedback || '';
          if (data.correct) {
            result.classList.add('is-correct', 'is-done');
            result.innerHTML = '<strong>✓ Correct</strong> ' + expl;
            qsa('input', form).forEach(function (el) {
              el.disabled = true;
            });
            if (btn) btn.remove();
          } else {
            result.classList.add('is-wrong');
            result.innerHTML = '<strong>Not quite.</strong> ' + (expl || 'Try again.');
            if (btn) {
              btn.disabled = false;
              btn.textContent = 'Try again';
            }
          }
        })
        .catch(function () {
          if (btn) btn.disabled = false;
          if (result) {
            result.classList.add('is-wrong');
            result.innerHTML = 'Could not check that answer. Try again.';
          }
        });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', onReady);
  } else {
    onReady();
  }
})();
