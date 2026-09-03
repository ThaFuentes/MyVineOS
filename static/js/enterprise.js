/* Shared list filters, compose type switch, and hero rotator. */
(function () {
  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function initListFilters(root) {
    const box = qs('[data-list-search]', root);
    const body = qs('[data-list-body]', root) || qs('#eventsBody', root);
    const empty = qs('[data-list-empty]', root) || qs('#noResults', root);
    if (!body) return;
    const chips = qsa('[data-filter]', root);
    let potluck = 'all';
    let dateFilter = 'all';
    let extra = 'all';
    const today = new Date().toISOString().slice(0, 10);

    function paint() {
      chips.forEach(function (btn) {
        const f = btn.getAttribute('data-filter');
        let on = false;
        if (f === 'all') on = potluck === 'all' && dateFilter === 'all' && extra === 'all';
        else if (f === 'potluck-yes') on = potluck === 'yes';
        else if (f === 'potluck-no') on = potluck === 'no';
        else if (f === 'upcoming' || f === 'today' || f === 'past') on = dateFilter === f;
        else on = extra === f;
        btn.classList.toggle('btn-primary', on);
        btn.classList.toggle('btn-secondary', !on);
        btn.classList.toggle('is-active', on);
      });
    }

    function apply() {
      const q = box ? box.value.toLowerCase().trim() : '';
      const rows = qsa('[data-list-row]', body);
      let shown = 0;
      rows.forEach(function (row) {
        const text = row.textContent.toLowerCase();
        const isPotluck = (row.getAttribute('data-potluck') || '') === 'yes';
        const eventDate = row.getAttribute('data-date') || '0000-00-00';
        const extraVal = row.getAttribute('data-extra') || '';
        const matchQ = !q || text.indexOf(q) !== -1;
        const matchP = potluck === 'all' || (potluck === 'yes' && isPotluck) || (potluck === 'no' && !isPotluck);
        let matchD = true;
        if (dateFilter === 'upcoming') matchD = eventDate >= today;
        else if (dateFilter === 'today') matchD = eventDate === today;
        else if (dateFilter === 'past') matchD = eventDate < today;
        const matchE = extra === 'all' || extraVal === extra;
        const show = matchQ && matchP && matchD && matchE;
        row.style.display = show ? '' : 'none';
        if (show) shown += 1;
      });
      if (empty) empty.style.display = shown === 0 ? 'block' : 'none';
    }

    if (box) box.addEventListener('input', apply);
    chips.forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        const f = btn.getAttribute('data-filter');
        if (f === 'all') { potluck = 'all'; dateFilter = 'all'; extra = 'all'; }
        else if (f === 'potluck-yes' || f === 'potluck-no') potluck = f === 'potluck-yes' ? 'yes' : 'no';
        else if (f === 'upcoming' || f === 'today' || f === 'past') dateFilter = f;
        else extra = f;
        paint();
        apply();
      });
    });
    paint();
    apply();
  }

  function initCompose(root) {
    const types = qsa('[data-compose-type]', root);
    const panels = qsa('[data-compose-panel]', root);
    if (!types.length) return;
    function show(kind) {
      types.forEach(function (btn) {
        btn.classList.toggle('is-active', btn.getAttribute('data-compose-type') === kind);
      });
      panels.forEach(function (panel) {
        const open = panel.getAttribute('data-compose-panel') === kind;
        panel.classList.toggle('is-open', open);
        qsa('input, textarea, select, button', panel).forEach(function (el) {
          el.disabled = !open;
        });
      });
      const hidden = qs('input[name="compose_type"]', root);
      if (hidden) hidden.value = kind;
    }
    types.forEach(function (btn) {
      btn.addEventListener('click', function () { show(btn.getAttribute('data-compose-type')); });
    });
    const first = types[0];
    if (first) show(first.getAttribute('data-compose-type'));
    initLinkPreview(root);
  }

  function looksLikeHttp(s) {
    return /^https?:\/\//i.test((s || '').trim());
  }
  function firstHttpUrl(s) {
    const m = String(s || '').match(/https?:\/\/[^\s<>"']+/i);
    return m ? m[0] : '';
  }
  function escTxt(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }
  function initLinkPreview(root) {
    qsa('[data-compose-panel]', root).forEach(function (panel) {
      const title = qs('input[name="title"]', panel);
      const url = qs('input[name="url"], input[name="external_link"]', panel);
      const body = qs('textarea[name="body"], textarea[name="details"], textarea[name="description"], [data-compose-text]', panel);
      const box = qs('[data-link-preview]', panel);
      if (!box) return;
      let timer = 0;
      let last = '';
      function currentUrl() {
        const u = ((url && url.value) || '').trim();
        if (u) return firstHttpUrl(u) || (looksLikeHttp(u) ? u.split(/\s/)[0] : '');
        return firstHttpUrl((title && title.value) || '') || firstHttpUrl((body && body.value) || '');
      }
      function render(data, href) {
        if (!data || !data.ok) {
          box.innerHTML = '<p class="compose-link-preview-miss">Will post as a link: ' + escTxt(href) + '</p>';
          box.hidden = false;
          return;
        }
        const img = data.image && /^https?:\/\//i.test(data.image)
          ? '<img src="' + escTxt(data.image) + '" alt="">'
          : '';
        box.innerHTML =
          '<div class="compose-link-preview-card">' +
          img +
          '<div class="compose-link-preview-copy">' +
          '<div class="compose-link-preview-host">' + escTxt(data.host || '') + '</div>' +
          '<div class="compose-link-preview-title">' + escTxt(data.title || 'Link') + '</div>' +
          '</div></div>';
        box.hidden = false;
      }
      function load() {
        const href = currentUrl();
        if (!href || !looksLikeHttp(href)) {
          box.hidden = true;
          box.innerHTML = '';
          last = '';
          return;
        }
        if (href === last) return;
        last = href;
        box.hidden = false;
        box.innerHTML = '<p class="compose-link-preview-wait">Looking up that page…</p>';
        fetch('/compose/link-preview?url=' + encodeURIComponent(href), {
          credentials: 'same-origin',
          headers: { Accept: 'application/json' },
        })
          .then(function (r) { return r.json(); })
          .then(function (data) { if (currentUrl() === href) render(data, href); })
          .catch(function () {
            if (currentUrl() === href) render({ ok: false }, href);
          });
      }
      function schedule() {
        clearTimeout(timer);
        timer = setTimeout(load, 400);
      }
      if (title) title.addEventListener('input', schedule);
      if (url) url.addEventListener('input', schedule);
      if (body) body.addEventListener('input', schedule);
    });
  }

  function initHero(root) {
    const slides = qsa('.site-hero-slide', root);
    if (slides.length < 2) return;
    const interval = parseInt(root.getAttribute('data-interval') || '6000', 10) || 6000;
    const dotsWrap = qs('.site-hero-dots', root);
    let i = 0;
    function go(n) {
      i = (n + slides.length) % slides.length;
      slides.forEach(function (s, idx) { s.classList.toggle('is-active', idx === i); });
      if (dotsWrap) {
        qsa('button', dotsWrap).forEach(function (d, idx) { d.classList.toggle('is-active', idx === i); });
      }
    }
    if (dotsWrap && !dotsWrap.children.length) {
      slides.forEach(function (_, idx) {
        const b = document.createElement('button');
        b.type = 'button';
        b.setAttribute('aria-label', 'Show image ' + (idx + 1));
        if (idx === 0) b.className = 'is-active';
        b.addEventListener('click', function () { go(idx); });
        dotsWrap.appendChild(b);
      });
    }
    setInterval(function () { go(i + 1); }, interval);
  }

  function initAppsToggle() {
    qsa('[data-apps-toggle]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const id = btn.getAttribute('data-apps-toggle');
        const panel = document.getElementById(id);
        if (!panel) return;
        const open = panel.hasAttribute('hidden');
        if (open) panel.removeAttribute('hidden');
        else panel.setAttribute('hidden', '');
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
    });
  }

  function initComposeSheet() {
    const sheet = document.getElementById('compose-sheet');
    if (!sheet || !sheet.showModal) return;

    function openSheet(kind) {
      sheet.showModal();
      if (kind) {
        const btn = qs('[data-compose-type="' + kind + '"]', sheet);
        if (btn) btn.click();
      }
      const text = qs('[data-compose-panel].is-open [data-compose-text], [data-compose-panel].is-open textarea', sheet);
      if (text && typeof text.focus === 'function') text.focus();
    }

    qsa('[data-open-compose]').forEach(function (el) {
      el.addEventListener('click', function (e) {
        e.preventDefault();
        openSheet(el.getAttribute('data-open-compose') || '');
      });
    });

    sheet.addEventListener('click', function (e) {
      if (e.target === sheet) sheet.close();
    });

    qsa('[data-mention]').forEach(function (chip) {
      chip.addEventListener('click', function () {
        const tag = chip.getAttribute('data-mention');
        if (!tag) return;
        const box = qs('[data-compose-panel].is-open [data-compose-text], [data-compose-panel].is-open textarea', sheet)
          || qs('[data-compose-text]:not([disabled])')
          || qs('textarea:not([disabled])', sheet);
        if (!box) return;
        const start = box.selectionStart || box.value.length;
        const end = box.selectionEnd || box.value.length;
        const before = box.value.slice(0, start);
        const after = box.value.slice(end);
        const pad = before && !/\s$/.test(before) ? ' ' : '';
        box.value = before + pad + tag + ' ' + after;
        box.focus();
        const pos = (before + pad + tag + ' ').length;
        if (box.setSelectionRange) box.setSelectionRange(pos, pos);
        chip.classList.add('is-on');
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    qsa('[data-list-root]').forEach(initListFilters);
    qsa('[data-compose]').forEach(initCompose);
    qsa('[data-hero]').forEach(initHero);
    initAppsToggle();
    initComposeSheet();
  });
})();
