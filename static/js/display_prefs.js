/**
 * Site-wide display preferences: theme, page font scale, Bible reader scale.
 * Instantly applies to <html> attributes and persists via /profile/ui-preferences.
 */
(function () {
  const root = document.documentElement;
  const panel = document.getElementById('display-prefs-panel');
  const toggle = document.getElementById('display-prefs-toggle');
  if (!panel || !toggle) return;

  const statusEl = panel.querySelector('.pref-status');
  const saveUrl = panel.dataset.saveUrl;
  const csrf = panel.dataset.csrf || '';

  function current() {
    return {
      theme: root.getAttribute('data-theme') || 'cyan-glow',
      font_scale: root.getAttribute('data-font-scale') || 'md',
      bible_scale: root.getAttribute('data-bible-scale') || 'md',
    };
  }

  function setActiveButtons() {
    const c = current();
    panel.querySelectorAll('[data-pref]').forEach((btn) => {
      const key = btn.getAttribute('data-pref');
      const val = btn.getAttribute('data-value');
      const active =
        (key === 'theme' && val === c.theme) ||
        (key === 'font_scale' && val === c.font_scale) ||
        (key === 'bible_scale' && val === c.bible_scale);
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  function applyLocal(partial) {
    if (partial.theme) root.setAttribute('data-theme', partial.theme);
    if (partial.font_scale) root.setAttribute('data-font-scale', partial.font_scale);
    if (partial.bible_scale) root.setAttribute('data-bible-scale', partial.bible_scale);

    // theme-color meta for mobile chrome
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      const map = {
        'cyan-glow': '#0a0a0a',
        'soft-light': '#f4f7fb',
        tropical: '#062820',
      };
      meta.setAttribute('content', map[partial.theme || current().theme] || '#0a0a0a');
    }
    setActiveButtons();
  }

  let saveTimer = null;
  function scheduleSave() {
    if (statusEl) statusEl.textContent = 'Saving…';
    clearTimeout(saveTimer);
    saveTimer = setTimeout(persist, 280);
  }

  async function persist() {
    if (!saveUrl) return;
    const body = current();
    try {
      const res = await fetch(saveUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrf,
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'same-origin',
        body: JSON.stringify({
          theme: body.theme,
          font_scale: body.font_scale,
          bible_scale: body.bible_scale,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        if (statusEl) statusEl.textContent = data.error || 'Could not save.';
        return;
      }
      if (data.theme) applyLocal(data);
      if (statusEl) {
        statusEl.textContent = 'Saved to your account.';
        setTimeout(() => {
          if (statusEl.textContent === 'Saved to your account.') statusEl.textContent = '';
        }, 1800);
      }
    } catch (e) {
      if (statusEl) statusEl.textContent = 'Network error — try again.';
    }
  }

  function openPanel() {
    panel.classList.add('is-open');
    toggle.setAttribute('aria-expanded', 'true');
    setActiveButtons();
  }

  function closePanel() {
    panel.classList.remove('is-open');
    toggle.setAttribute('aria-expanded', 'false');
  }

  toggle.addEventListener('click', (e) => {
    e.stopPropagation();
    if (panel.classList.contains('is-open')) closePanel();
    else openPanel();
  });

  panel.addEventListener('click', (e) => e.stopPropagation());

  document.addEventListener('click', () => {
    if (panel.classList.contains('is-open')) closePanel();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closePanel();
  });

  panel.querySelectorAll('[data-pref]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const key = btn.getAttribute('data-pref');
      const val = btn.getAttribute('data-value');
      if (!key || !val) return;
      const partial = {};
      partial[key] = val;
      applyLocal(partial);
      scheduleSave();
    });
  });

  // Bible toolbar A+/A- (optional controls)
  function bibleStep(delta) {
    const order = ['sm', 'md', 'lg', 'xl', 'xxl'];
    const cur = current().bible_scale;
    let i = order.indexOf(cur);
    if (i < 0) i = 1;
    i = Math.max(0, Math.min(order.length - 1, i + delta));
    applyLocal({ bible_scale: order[i] });
    scheduleSave();
    const label = document.getElementById('bible-font-label');
    if (label) label.textContent = order[i].toUpperCase();
  }

  document.getElementById('bible-font-smaller')?.addEventListener('click', () => bibleStep(-1));
  document.getElementById('bible-font-larger')?.addEventListener('click', () => bibleStep(1));

  const label = document.getElementById('bible-font-label');
  if (label) label.textContent = (current().bible_scale || 'md').toUpperCase();

  setActiveButtons();
})();
