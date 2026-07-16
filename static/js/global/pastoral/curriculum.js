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
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', onReady);
  } else {
    onReady();
  }
})();
