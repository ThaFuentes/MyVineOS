/**
 * Site-wide display preferences: theme, page font scale, Bible reader scale.
 * Instantly applies to <html> attributes and persists via /profile/ui-preferences.
 * Uses form-encoded POST + CSRF field (most reliable with security pipeline).
 */
(function () {
  const root = document.documentElement;
  const panel = document.getElementById('display-prefs-panel');
  const toggle = document.getElementById('display-prefs-toggle');
  if (!panel || !toggle) return;

  const statusEl = panel.querySelector('.pref-status');
  const saveUrl = panel.dataset.saveUrl;
  const csrf = panel.dataset.csrf || '';
  const themeSelect = document.getElementById('pref-theme-select');

  const THEME_META = {
    'cyan-glow': '#0a0a0a',
    'soft-light': '#f4f7fb',
    tropical: '#0a3d38',
    'purple-grace': '#120a1c',
    'amber-hope': '#1a0f00',
    forest: '#0a1610',
    'rose-dawn': '#1a0e16',
  };

  function current() {
    return {
      theme: root.getAttribute('data-theme') || 'cyan-glow',
      font_scale: root.getAttribute('data-font-scale') || 'md',
      bible_scale: root.getAttribute('data-bible-scale') || 'md',
    };
  }

  function setActiveButtons() {
    const c = current();
    if (themeSelect && [...themeSelect.options].some((o) => o.value === c.theme)) {
      themeSelect.value = c.theme;
    }
    panel.querySelectorAll('button[data-pref]').forEach((btn) => {
      const key = btn.getAttribute('data-pref');
      const val = btn.getAttribute('data-value');
      const active =
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

    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      const t = partial.theme || current().theme;
      meta.setAttribute('content', THEME_META[t] || '#0a0a0a');
    }
    setActiveButtons();
  }

  let saveTimer = null;
  let inflight = null;

  function scheduleSave(immediate) {
    if (statusEl) statusEl.textContent = 'Saving…';
    clearTimeout(saveTimer);
    if (immediate) {
      persist();
      return;
    }
    saveTimer = setTimeout(persist, 200);
  }

  async function persist() {
    if (!saveUrl) return;
    const body = current();

    // form-urlencoded so CSRF middleware always sees csrf_token in form body
    const params = new URLSearchParams();
    params.set('theme', body.theme);
    params.set('font_scale', body.font_scale);
    params.set('bible_scale', body.bible_scale);
    if (csrf) params.set('csrf_token', csrf);

    // Cancel previous in-flight save to avoid out-of-order overwrites
    if (inflight && typeof inflight.abort === 'function') {
      try { inflight.abort(); } catch (e) { /* ignore */ }
    }
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    inflight = controller;

    try {
      const res = await fetch(saveUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
          'X-CSRF-Token': csrf,
          'X-Requested-With': 'XMLHttpRequest',
          Accept: 'application/json',
        },
        credentials: 'same-origin',
        body: params.toString(),
        signal: controller ? controller.signal : undefined,
      });

      const text = await res.text();
      let data = {};
      try {
        data = text ? JSON.parse(text) : {};
      } catch (e) {
        // Server redirected HTML (old 403 handler) — treat as failure
        if (statusEl) {
          statusEl.textContent = res.ok
            ? 'Saved (reload if theme looks wrong).'
            : 'Could not save — reload the page and try again.';
        }
        return;
      }

      if (!res.ok || data.ok === false) {
        if (statusEl) statusEl.textContent = data.error || 'Could not save.';
        return;
      }

      // Authoritative values from server/DB
      applyLocal({
        theme: data.theme || body.theme,
        font_scale: data.font_scale || body.font_scale,
        bible_scale: data.bible_scale || body.bible_scale,
      });

      if (statusEl) {
        const guest = panel.dataset.guest === '1';
        const msg =
          data.persisted === 'session' || guest
            ? 'Saved for this device.'
            : 'Saved to your account.';
        statusEl.textContent = msg;
        setTimeout(() => {
          if (statusEl.textContent === msg) statusEl.textContent = '';
        }, 1800);
      }
    } catch (e) {
      if (e && e.name === 'AbortError') return;
      if (statusEl) statusEl.textContent = 'Network error — try again.';
    }
  }

  // Flush pending save if user navigates away quickly
  window.addEventListener('pagehide', () => {
    clearTimeout(saveTimer);
  });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden' && saveTimer) {
      clearTimeout(saveTimer);
      persist();
    }
  });

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

  // Theme dropdown — save immediately so it never races a navigation
  themeSelect?.addEventListener('change', () => {
    applyLocal({ theme: themeSelect.value });
    scheduleSave(true);
  });

  // Font size pills
  panel.querySelectorAll('button[data-pref]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const key = btn.getAttribute('data-pref');
      const val = btn.getAttribute('data-value');
      if (!key || !val) return;
      const partial = {};
      partial[key] = val;
      applyLocal(partial);
      scheduleSave(false);
    });
  });

  // Bible toolbar A+/A-
  function bibleStep(delta) {
    const order = ['sm', 'md', 'lg', 'xl', 'xxl'];
    const cur = current().bible_scale;
    let i = order.indexOf(cur);
    if (i < 0) i = 1;
    i = Math.max(0, Math.min(order.length - 1, i + delta));
    applyLocal({ bible_scale: order[i] });
    scheduleSave(true);
    const label = document.getElementById('bible-font-label');
    if (label) label.textContent = order[i].toUpperCase();
  }

  document.getElementById('bible-font-smaller')?.addEventListener('click', () => bibleStep(-1));
  document.getElementById('bible-font-larger')?.addEventListener('click', () => bibleStep(1));

  const label = document.getElementById('bible-font-label');
  if (label) label.textContent = (current().bible_scale || 'md').toUpperCase();

  setActiveButtons();
})();
