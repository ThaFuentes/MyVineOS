/**
 * Site-wide display preferences: theme, page font scale, Bible reader scale.
 * Instantly applies to <html> attributes and persists via profile/public UI prefs.
 * On mobile the panel is portaled to <body> so it is not trapped by the top-bar
 * backdrop-filter (which breaks position:fixed descendants).
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
  const prefsRoot = document.getElementById('display-prefs') || toggle.parentElement;
  const churchTheme = panel.dataset.churchTheme || 'cyan-glow';

  function resolveThemeValue(val) {
    if (!val || val === 'church' || val === 'default' || val === 'church-default') {
      return churchTheme;
    }
    return val;
  }

  // Backdrop for mobile sheet (created once)
  let backdrop = document.getElementById('display-prefs-backdrop');
  if (!backdrop) {
    backdrop = document.createElement('div');
    backdrop.id = 'display-prefs-backdrop';
    backdrop.className = 'display-prefs-backdrop';
    backdrop.hidden = true;
    backdrop.setAttribute('aria-hidden', 'true');
    document.body.appendChild(backdrop);
  }

  // Remember original home so we can put the panel back on desktop if needed
  const panelHome = prefsRoot;
  let panelOnBody = false;
  let ignoreDocCloseUntil = 0;

  const THEME_META = {
    'cyan-glow': '#0a0a0a',
    'soft-light': '#f4f7fb',
    tropical: '#0a3d38',
    'purple-grace': '#120a1c',
    'amber-hope': '#1a0f00',
    forest: '#0a1610',
    'rose-dawn': '#1a0e16',
  };

  function isMobile() {
    return window.matchMedia('(max-width: 767px)').matches;
  }

  function current() {
    return {
      theme: root.getAttribute('data-theme') || 'cyan-glow',
      font_scale: root.getAttribute('data-font-scale') || 'md',
      bible_scale: root.getAttribute('data-bible-scale') || 'md',
    };
  }

  function setActiveButtons() {
    const c = current();
    if (themeSelect) {
      // Keep "church" selected when effective theme matches church default and user chose it
      const selected = themeSelect.value;
      if (selected !== 'church') {
        if ([...themeSelect.options].some((o) => o.value === c.theme)) {
          themeSelect.value = c.theme;
        }
      }
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
    if (partial.theme) {
      root.setAttribute('data-theme', resolveThemeValue(partial.theme));
    }
    if (partial.font_scale) root.setAttribute('data-font-scale', partial.font_scale);
    if (partial.bible_scale) root.setAttribute('data-bible-scale', partial.bible_scale);

    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      const t = resolveThemeValue(partial.theme || current().theme);
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
    // Prefer the select value so "church" is sent as church (not resolved classic name)
    const themeToSave = themeSelect ? themeSelect.value : body.theme;

    const params = new URLSearchParams();
    params.set('theme', themeToSave);
    params.set('font_scale', body.font_scale);
    params.set('bible_scale', body.bible_scale);
    if (csrf) params.set('csrf_token', csrf);

    if (inflight && typeof inflight.abort === 'function') {
      try {
        inflight.abort();
      } catch (e) {
        /* ignore */
      }
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

  window.addEventListener('pagehide', () => {
    clearTimeout(saveTimer);
  });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden' && saveTimer) {
      clearTimeout(saveTimer);
      persist();
    }
  });

  function placePanelForViewport() {
    if (isMobile()) {
      if (!panelOnBody) {
        document.body.appendChild(panel);
        panelOnBody = true;
      }
      panel.classList.add('display-prefs-panel--sheet');
    } else {
      panel.classList.remove('display-prefs-panel--sheet');
      if (panelOnBody && panelHome) {
        panelHome.appendChild(panel);
        panelOnBody = false;
      }
    }
  }

  function openPanel() {
    placePanelForViewport();
    panel.classList.add('is-open');
    toggle.setAttribute('aria-expanded', 'true');
    document.body.classList.add('display-prefs-open');
    if (isMobile()) {
      backdrop.hidden = false;
      backdrop.removeAttribute('hidden');
      backdrop.setAttribute('aria-hidden', 'false');
      backdrop.classList.add('is-open');
    }
    setActiveButtons();
    // Avoid the same touch/click that opened the panel also closing it
    ignoreDocCloseUntil = Date.now() + 350;
  }

  function closePanel() {
    panel.classList.remove('is-open');
    toggle.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('display-prefs-open');
    backdrop.classList.remove('is-open');
    backdrop.hidden = true;
    backdrop.setAttribute('hidden', '');
    backdrop.setAttribute('aria-hidden', 'true');
  }

  function onToggle(e) {
    e.preventDefault();
    e.stopPropagation();
    if (panel.classList.contains('is-open')) closePanel();
    else openPanel();
  }

  // click + pointerup for better mobile response
  toggle.addEventListener('click', onToggle);
  toggle.addEventListener(
    'pointerup',
    (e) => {
      // Only handle primary touch/pen if click is flaky (iOS sometimes)
      if (e.pointerType === 'touch') {
        // click still fires after; prevent double-toggle via ignore window
      }
    },
    { passive: true }
  );

  panel.addEventListener('click', (e) => e.stopPropagation());
  panel.addEventListener('touchstart', (e) => e.stopPropagation(), { passive: true });

  backdrop.addEventListener('click', (e) => {
    e.preventDefault();
    closePanel();
  });

  document.addEventListener('click', (e) => {
    if (Date.now() < ignoreDocCloseUntil) return;
    if (!panel.classList.contains('is-open')) return;
    // Keep open when interacting with toggle, panel, or backdrop (backdrop has own handler)
    const t = e.target;
    if (toggle.contains(t) || panel.contains(t) || backdrop.contains(t)) return;
    closePanel();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closePanel();
  });

  window.addEventListener('resize', () => {
    if (panel.classList.contains('is-open')) placePanelForViewport();
  });

  themeSelect?.addEventListener('change', () => {
    applyLocal({ theme: themeSelect.value });
    scheduleSave(true);
  });

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
