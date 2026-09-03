// Member + public Bible Study — online reading for everyone.
// Highlights / notes / favorites / saved place require login.
(function () {
  const cfg = window.MEMBER_BIBLE || {};
  const books = cfg.books || [];
  const urls = cfg.urls || {};
  const isLoggedIn = !!cfg.isLoggedIn;
  const loginUrl = cfg.loginUrl || '/auth/login?next=/bible/';

  let currentBook = 'John';
  let currentChapter = 1;
  let maxChapter = 0;
  let mainView = 'chapter';
  let lastChapterHtml = '';
  let annotationKey = null;
  let chapterData = null;
  let currentNotes = [];
  let allNotesCache = [];
  let notesPanelTab = 'passage'; // 'passage' | 'all'
  let notesPanelOpen = false;
  let selectedVerses = new Set();
  let favoriteVerses = new Set();
  let favChapter = false;
  let favBook = false;
  let pickerMode = 'chapter';
  let verseNums = [];
  let compareTranslation = '';
  let compareChapter = null;
  let studyModeWanted = false;

  const el = (id) => document.getElementById(id);
  const base = '/bible';
  const main = () => el('member-bible-content');

  /** Guests may read / Strong's; personal study features need an account. */
  function requireLogin(feature) {
    if (isLoggedIn) return true;
    const label = feature || 'this feature';
    toast(`Log in to use ${label}`);
    // Highlight the guest banner / login CTA if present (no forced redirect)
    const cta = el('member-bible-login-cta');
    if (cta) {
      cta.classList.add('member-bible-login-pulse');
      cta.focus?.();
      window.setTimeout(() => cta.classList.remove('member-bible-login-pulse'), 1800);
    }
    return false;
  }

  function csrfToken() {
    // PBT security expects header "X-CSRF-Token" or form field csrf_token
    if (cfg.csrf) return cfg.csrf;
    const m = document.querySelector('meta[name="csrf-token"]');
    if (m && m.content) return m.content;
    const byId = document.getElementById('member-bible-csrf');
    if (byId && byId.value) return byId.value;
    const i = document.querySelector('input[name="csrf_token"]');
    return i ? i.value : '';
  }

  function apiHeaders(jsonBody) {
    const h = {
      'X-CSRF-Token': csrfToken(),
      'X-Requested-With': 'XMLHttpRequest',
      Accept: 'application/json',
    };
    if (jsonBody) h['Content-Type'] = 'application/json';
    return h;
  }

  async function apiPost(url, bodyObj) {
    const token = csrfToken();
    if (!token) {
      throw new Error('Security token missing — refresh the page and try again');
    }
    const resp = await fetch(url, {
      method: 'POST',
      headers: apiHeaders(true),
      credentials: 'same-origin',
      body: JSON.stringify(bodyObj || {}),
    });
    const text = await resp.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (e) {
      // HTML error page (403 security block, etc.)
      if (resp.status === 403 || /security check failed/i.test(text)) {
        throw new Error('Security check failed — refresh the page and try again');
      }
      throw new Error('Request failed (' + resp.status + ')');
    }
    if (resp.status === 403 || (!resp.ok && /security/i.test(data.error || ''))) {
      throw new Error(data.error || 'Security check failed — refresh the page and try again');
    }
    if (!resp.ok && data.error) {
      throw new Error(data.error);
    }
    return data;
  }

  function translation() {
    return el('member-translation-toolbar')?.value
      || el('member-bible-translation')?.value
      || cfg.selectedTranslation
      || null;
  }

  function setTranslationValue(val) {
    if (!val) return;
    [el('member-bible-translation'), el('member-translation-toolbar')].forEach((sel) => {
      if (!sel) return;
      if (!Array.from(sel.options).some((o) => o.value === val)) {
        const opt = document.createElement('option');
        opt.value = val;
        opt.textContent = val.replace(/^online:/, '') + (String(val).startsWith('online:') ? ' · online' : '');
        sel.appendChild(opt);
      }
      sel.value = val;
    });
  }

  function toast(msg) {
    const t = el('member-bible-toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(toast._t);
    toast._t = setTimeout(() => t.classList.remove('show'), 2200);
  }

  function escapeHtml(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  function escapeAttr(s) { return escapeHtml(s).replace(/"/g, '&quot;'); }
  function escapeRegex(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  function setMainView(view) {
    mainView = view;
    const back = el('member-bible-back');
    if (back) back.style.display = view === 'chapter' ? 'none' : 'inline-block';
  }

  function openFlyout(which) {
    setNotesPanelOpen(false);
    if (isDesktopStudy()) return;
    const canon = el('member-canon-flyout');
    const tools = el('member-tools-flyout');
    const backdrop = el('member-bible-backdrop');
    const openCanon = el('member-open-canon');
    const openTools = el('member-open-tools');
    if (which === 'canon') {
      tools?.classList.remove('open');
      tools?.setAttribute('aria-hidden', 'true');
      openTools?.classList.remove('active');
      canon?.classList.add('open');
      canon?.setAttribute('aria-hidden', 'false');
      openCanon?.classList.add('active');
    } else {
      canon?.classList.remove('open');
      canon?.setAttribute('aria-hidden', 'true');
      openCanon?.classList.remove('active');
      tools?.classList.add('open');
      tools?.setAttribute('aria-hidden', 'false');
      openTools?.classList.add('active');
      // Auto-load notes library in Study tools
      if (isLoggedIn) loadNotesLibrary();
    }
    backdrop?.classList.add('open');
    backdrop?.setAttribute('aria-hidden', 'false');
  }

  function isDesktopStudy() {
    return !!(el('member-bible-stage')?.classList.contains('is-study')
      && window.matchMedia('(min-width: 960px)').matches);
  }

  function applyStudyMode(on) {
    const stage = el('member-bible-stage');
    if (!stage) return;
    studyModeWanted = !!on;
    const desktop = window.matchMedia('(min-width: 960px)').matches;
    const useStudy = on && desktop;
    stage.classList.toggle('is-study', useStudy);
    el('member-mode-study')?.classList.toggle('active', useStudy);
    el('member-mode-read')?.classList.toggle('active', !useStudy);
    try { localStorage.setItem('member_bible_mode', on ? 'study' : 'read'); } catch (e) { /* ignore */ }
    if (useStudy) {
      el('member-canon-flyout')?.classList.add('open');
      el('member-tools-flyout')?.classList.add('open');
      el('member-canon-flyout')?.setAttribute('aria-hidden', 'false');
      el('member-tools-flyout')?.setAttribute('aria-hidden', 'false');
      el('member-bible-backdrop')?.classList.remove('open');
      el('member-bible-backdrop')?.setAttribute('aria-hidden', 'true');
    }
  }

  function closeFlyouts() {
    if (isDesktopStudy()) {
      el('member-bible-backdrop')?.classList.remove('open');
      el('member-bible-backdrop')?.setAttribute('aria-hidden', 'true');
      return;
    }
    el('member-canon-flyout')?.classList.remove('open');
    el('member-tools-flyout')?.classList.remove('open');
    el('member-bible-backdrop')?.classList.remove('open');
    el('member-open-canon')?.classList.remove('active');
    el('member-open-tools')?.classList.remove('active');
    el('member-canon-flyout')?.setAttribute('aria-hidden', 'true');
    el('member-tools-flyout')?.setAttribute('aria-hidden', 'true');
    el('member-bible-backdrop')?.setAttribute('aria-hidden', 'true');
  }

  function compareTextForVerse(verseNum) {
    if (!compareChapter || !compareTranslation) return '';
    const row = (compareChapter.verses || []).find((v) => Number(v.verse) === Number(verseNum));
    if (!row || !row.text) return '';
    const code = (compareChapter.translation || compareTranslation || '').replace(/^online:/, '');
    return `<div class="member-bible-compare"><span class="small text-muted">${escapeHtml(code)}</span> ${escapeHtml(row.text)}</div>`;
  }

  async function loadCompareChapter() {
    compareChapter = null;
    const other = (el('member-compare-translation')?.value || '').trim();
    compareTranslation = other;
    if (!other || other === translation()) {
      if (chapterData) renderChapter(chapterData);
      fillStudyFocus();
      return;
    }
    try {
      const bookSlug = encodeURIComponent(currentBook);
      const resp = await fetch(`${base}/chapter/${bookSlug}/${currentChapter}?translation=${encodeURIComponent(other)}`, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      });
      if (resp.ok) compareChapter = await resp.json();
    } catch (e) {
      compareChapter = null;
    }
    if (chapterData) renderChapter(chapterData);
    fillStudyFocus();
  }

  function fillStudyFocus() {
    const host = el('member-study-focus-body');
    if (!host) return;
    const nums = Array.from(selectedVerses).sort((a, b) => a - b);
    if (!nums.length) {
      host.innerHTML = '<p class="small text-muted mb-0">The first verse of the chapter opens here. Tap another verse to move study tools to it.</p>';
      return;
    }
    const v = nums[0];
    const line = main()?.querySelector(`.member-bible-verse[data-verse="${v}"]`);
    const text = line?.dataset.text || '';
    const ref = `${currentBook} ${currentChapter}:${nums.length === 1 ? v : nums[0] + '–' + nums[nums.length - 1]}`;
    const strongs = (chapterData?.strongs && (chapterData.strongs[v] || chapterData.strongs[String(v)])) || [];
    const xrefs = (chapterData?.cross_refs && (chapterData.cross_refs[v] || chapterData.cross_refs[String(v)])) || [];
    const wojRow = (chapterData?.verses || []).find((row) => Number(row.verse) === Number(v));
    let html = `<div class="study-focus-ref">${escapeHtml(ref)}</div>`;
    html += `<p class="study-focus-text">${renderVerseText(text, strongs, wojRow?.woj)}</p>`;
    html += compareTextForVerse(v);
    if (strongs.length) {
      html += '<p class="small text-muted mb-1">Original words</p><div class="strongs-chips">';
      strongs.forEach((s) => {
        const num = s.strongs_number || '';
        const tip = [num, s.transliteration, s.lemma].filter(Boolean).join(' · ');
        html += `<button type="button" class="strongs-chip" data-strongs="${escapeAttr(num)}" title="${escapeAttr(tip)}">${escapeHtml(s.surface_word || s.lemma || num)}</button>`;
      });
      html += '</div>';
    }
    if (xrefs.length) {
      html += '<p class="small text-muted mt-2 mb-1">Related</p>';
      xrefs.slice(0, 8).forEach((r) => {
        html += `<button type="button" class="member-xref-link${r.kind === 'messianic' ? ' messianic' : ''}" data-book="${escapeAttr(r.book)}" data-chapter="${r.chapter}" data-verse="${r.verse}" data-end-verse="${r.end_verse || ''}">${escapeHtml(r.reference)}</button> `;
      });
    }
    host.innerHTML = html;
    host.querySelectorAll('[data-strongs]').forEach((node) => {
      node.addEventListener('click', (e) => {
        e.preventDefault();
        showStrongs(node.dataset.strongs);
      });
    });
    host.querySelectorAll('.member-xref-link').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        openXrefFromButton(btn);
      });
    });
  }

  function scrollToChapterSection() {
    const section = el('member-bible-chapter-section');
    if (!section) return;
    requestAnimationFrame(() => section.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  }

  function renderBooks(testament) {
    const list = el('member-bible-book-list');
    if (!list) return;
    list.innerHTML = '';
    books.filter((b) => b.testament === testament).forEach((b) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = b.name;
      btn.dataset.book = b.name;
      if (b.name === currentBook) btn.classList.add('active');
      btn.addEventListener('click', () => {
        currentBook = b.name;
        list.querySelectorAll('button').forEach((x) => x.classList.remove('active'));
        btn.classList.add('active');
        verseNums = [];
        setPickerMode('chapter');
        scrollToChapterSection();
        prepareBook(currentBook);
      });
      list.appendChild(btn);
    });
  }

  function populateChapters(max) {
    maxChapter = Math.max(1, max || 1);
    // Keep hidden select in sync (toolbar prev/next still use it)
    const sel = el('member-bible-chapter');
    if (sel) {
      sel.innerHTML = '';
      for (let i = 1; i <= maxChapter; i++) {
        const o = document.createElement('option');
        o.value = String(i);
        o.textContent = String(i);
        sel.appendChild(o);
      }
      sel.value = String(Math.min(Math.max(1, currentChapter), maxChapter));
    }
    if (pickerMode === 'chapter') renderNumberGrid();
  }

  function setPickerMode(mode) {
    pickerMode = mode === 'verse' ? 'verse' : 'chapter';
    const chTab = el('member-nav-mode-chapter');
    const vTab = el('member-nav-mode-verse');
    chTab?.classList.toggle('active', pickerMode === 'chapter');
    vTab?.classList.toggle('active', pickerMode === 'verse');
    if (chTab) chTab.setAttribute('aria-selected', pickerMode === 'chapter' ? 'true' : 'false');
    if (vTab) vTab.setAttribute('aria-selected', pickerMode === 'verse' ? 'true' : 'false');
    renderNumberGrid();
  }

  function storeVerses(verses) {
    verseNums = (verses || []).map((v) => Number(v.verse) || 0).filter((n) => n > 0);
    if (pickerMode === 'verse') renderNumberGrid();
  }

  function pickChapter(n) {
    const sel = el('member-bible-chapter');
    if (sel) sel.value = String(n);
    if (n === currentChapter && verseNums.length) {
      setPickerMode('verse');
      return;
    }
    loadChapter(n, { scrollToVerse: 1 }).then(() => setPickerMode('verse'));
  }

  function pickVerse(n) {
    if (mainView !== 'chapter') restoreChapter();
    selectAndFocusVerse(n);
    closeFlyouts();
  }

  function renderNumberGrid() {
    const grid = el('member-bible-num-grid');
    const meta = el('member-bible-chapter-meta');
    if (!grid) return;
    grid.innerHTML = '';

    if (pickerMode === 'verse') {
      if (meta) {
        meta.textContent = verseNums.length
          ? `${currentBook} ${currentChapter} · tap a verse`
          : 'Pick a chapter first.';
      }
      verseNums.forEach((n) => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'bible-chapter-num';
        b.textContent = String(n);
        b.setAttribute('aria-label', `Verse ${n}`);
        b.setAttribute('role', 'option');
        b.addEventListener('click', () => pickVerse(n));
        grid.appendChild(b);
      });
      return;
    }

    const total = Math.max(0, maxChapter || 0);
    if (meta) {
      meta.textContent = total
        ? `${currentBook} · tap a chapter`
        : 'Pick a book to begin.';
    }
    for (let i = 1; i <= total; i++) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'bible-chapter-num' + (i === currentChapter ? ' active' : '');
      b.textContent = String(i);
      b.setAttribute('aria-label', `Chapter ${i}`);
      b.setAttribute('role', 'option');
      b.setAttribute('aria-selected', i === currentChapter ? 'true' : 'false');
      b.addEventListener('click', () => pickChapter(i));
      grid.appendChild(b);
    }
  }

  function updateNav() {
    const prev = el('member-bible-prev');
    const next = el('member-bible-next');
    if (prev) prev.disabled = currentChapter <= 1;
    if (next) next.disabled = maxChapter > 0 ? currentChapter >= maxChapter : true;
  }

  function updateFavButtons() {
    const ch = el('member-fav-chapter');
    const bk = el('member-fav-book');
    if (ch) {
      ch.textContent = favChapter ? '♥ Ch' : '♡ Ch';
      ch.classList.toggle('is-faved', favChapter);
    }
    if (bk) {
      bk.textContent = favBook ? '♥ Book' : '♡ Book';
      bk.classList.toggle('is-faved', favBook);
    }
  }

  function getVisibleVerseAnchor() {
    const lines = Array.from(main()?.querySelectorAll('.member-bible-verse') || []);
    if (!lines.length) return null;
    const offset = 140;
    for (const line of lines) {
      const rect = line.getBoundingClientRect();
      if (rect.bottom > offset && rect.top < window.innerHeight * 0.7) {
        return parseInt(line.dataset.verse, 10) || null;
      }
    }
    return parseInt(lines[0].dataset.verse, 10) || null;
  }

  async function prepareBook(book, opts = {}) {
    currentBook = book;
    const tr = translation();
    const startChapter = opts.chapter || 1;
    try {
      const url = `${base}/chapter/${encodeURIComponent(book)}/${startChapter}` +
        (tr ? `?translation=${encodeURIComponent(tr)}` : '');
      const resp = await fetch(url);
      if (!resp.ok) throw new Error('empty');
      const data = await resp.json();
      maxChapter = data.max_chapter || startChapter || 1;
      populateChapters(maxChapter);
      await loadChapter(startChapter, { scrollToVerse: opts.scrollToVerse || null });
    } catch (e) {
      maxChapter = 0;
      populateChapters(0);
      if (main()) main().innerHTML = '<p class="text-muted">No text for this book in the selected translation.</p>';
    }
  }

  function placePayload(extra = {}) {
    return {
      translation: translation(),
      book: currentBook,
      chapter: currentChapter || 1,
      verse: getVisibleVerseAnchor() || extra.verse || 1,
      ...extra,
    };
  }

  async function savePreferredTranslation(val) {
    if (!isLoggedIn) return null;
    if (!val || !csrfToken()) return null;
    try {
      const data = await apiPost(urls.preferred || `${base}/preferred`, {
        translation: val,
        book: currentBook,
        chapter: currentChapter || 1,
        verse: getVisibleVerseAnchor() || 1,
      });
      updateDefaultBadge(val);
      return data;
    } catch (e) {
      console.warn('Could not save preferred translation', e);
      toast(e.message || 'Could not save your Bible version — try again');
      return null;
    }
  }

  async function saveReadingPlace(extra = {}) {
    const body = placePayload(extra);
    try {
      localStorage.setItem('member_bible_place', JSON.stringify(body));
      if (body.translation) localStorage.setItem('member_bible_translation', body.translation);
    } catch (e) { /* ignore */ }
    if (!isLoggedIn) return;
    if (!csrfToken()) return;
    try {
      await apiPost(urls.place || `${base}/place`, body);
    } catch (e) {
      // Quiet — place is best-effort; preferred endpoint also saves on version change
    }
  }

  function updateDefaultBadge(val) {
    const badge = el('member-my-version-badge');
    if (!badge) return;
    const label = String(val || '').replace(/^online:/, '') || '—';
    badge.textContent = `My Bible: ${label}`;
    badge.style.display = val ? '' : 'none';
  }

  async function switchTranslationSeamless(fromControl) {
    const val = fromControl?.value || translation();
    setTranslationValue(val);
    // Logged-in: persist personal study version. Guests: this visit only.
    let saved = null;
    if (isLoggedIn) {
      saved = await savePreferredTranslation(val);
      try {
        localStorage.setItem('member_bible_translation', val);
      } catch (e) { /* ignore */ }
    }
    const anchor = getVisibleVerseAnchor();
    await prepareBook(currentBook, {
      chapter: currentChapter || 1,
      scrollToVerse: anchor,
    });
    if (saved && saved.ok) {
      toast(saved.message || `Saved as your study Bible: ${String(val).replace(/^online:/, '')}`);
    } else if (!isLoggedIn) {
      toast(anchor
        ? `This browser will reopen at ${currentBook} ${currentChapter}:${anchor}`
        : `This browser will reopen at ${currentBook} ${currentChapter}`);
    } else {
      toast(anchor
        ? `Switched · stayed at ${currentBook} ${currentChapter}:${anchor}`
        : `Switched · stayed at ${currentBook} ${currentChapter}`);
    }
  }

  async function loadChapter(chapter, opts = {}) {
    const tr = translation();
    if (maxChapter > 0) chapter = Math.max(1, Math.min(chapter, maxChapter));
    currentChapter = chapter;
    selectedVerses = new Set();
    const chSel = el('member-bible-chapter');
    if (chSel?.options.length) chSel.value = String(chapter);
    if (main()) main().innerHTML = '<p class="small text-muted">Loading…</p>';
    const title = el('member-bible-title');

    try {
      const url = `${base}/chapter/${encodeURIComponent(currentBook)}/${chapter}` +
        (tr ? `?translation=${encodeURIComponent(tr)}` : '');
      const resp = await fetch(url);
      if (!resp.ok) throw new Error('404');
      const data = await resp.json();
      chapterData = data;
      annotationKey = data.annotation_key || data.translation || tr;
      maxChapter = data.max_chapter || chapter;
      populateChapters(maxChapter);
      if (chSel) chSel.value = String(chapter);
      if (title) {
        const trLabel = data.translation || '';
        title.textContent = `${data.book} ${data.chapter}${trLabel ? ' · ' + trLabel : ''}`;
      }
      const favs = data.favorites || {};
      favoriteVerses = new Set(favs.verses || []);
      favChapter = !!favs.chapter;
      favBook = !!favs.book;
      updateFavButtons();
      storeVerses(data.verses);
      currentNotes = data.notes || [];
      selectedVerses = new Set([resolveFocusVerse(opts.scrollToVerse)]);
      // Chapter render uses currentNotes for 📝 markers
      await loadCompareChapter();
      if (notesPanelTab === 'all') {
        loadAllNotesPanel();
      } else {
        renderNotesPanel(currentNotes, { mode: 'passage' });
      }
      updateNav();
      const focusV = resolveFocusVerse(opts.scrollToVerse);
      selectedVerses = new Set([focusV]);
      selectAndFocusVerse(focusV);
      // Remember place so reopening Bible continues here (version + book + chapter)
      saveReadingPlace({ verse: focusV });
    } catch (e) {
      if (main()) main().innerHTML = '<p class="text-muted">Chapter not found.</p>';
      storeVerses([]);
      currentNotes = [];
      renderNotesPanel([], { mode: 'passage' });
      if (title) title.textContent = `${currentBook} ${chapter}`;
      updateNav();
    }
  }

  function highlightClass(verseNum, highlights) {
    const hits = (highlights || []).filter((h) => verseNum >= h.verse_start && verseNum <= h.verse_end);
    if (!hits.length) return '';
    return ' hl-' + (hits[hits.length - 1].color || 'yellow');
  }

  function xrefHtml(verseNum, crossRefs) {
    const refs = (crossRefs && (crossRefs[String(verseNum)] || crossRefs[verseNum])) || [];
    if (!refs.length) return '';
    const messianic = refs.filter((r) => r.kind === 'messianic');
    const related = refs.filter((r) => r.kind !== 'messianic').slice(0, 4);
    let html = '<div class="member-xrefs">';
    if (messianic.length) {
      html += '<div class="member-xref-row"><span class="member-xref-label messianic">✝ Related to Jesus</span> ';
      messianic.slice(0, 4).forEach((r) => {
        html += `<button type="button" class="member-xref-link messianic" data-book="${escapeAttr(r.book)}" data-chapter="${r.chapter}" data-verse="${r.verse}" data-end-verse="${r.end_verse || ''}" title="${escapeAttr(r.label || r.reference)}">${escapeHtml(r.reference)}</button> `;
      });
      html += '</div>';
    }
    if (related.length) {
      html += '<div class="member-xref-row"><span class="member-xref-label">See also</span> ';
      related.forEach((r) => {
        html += `<button type="button" class="member-xref-link" data-book="${escapeAttr(r.book)}" data-chapter="${r.chapter}" data-verse="${r.verse}" data-end-verse="${r.end_verse || ''}">${escapeHtml(r.reference)}</button> `;
      });
      html += '</div>';
    }
    html += '</div>';
    return html;
  }

  /** Verse numbers in the current chapter that have a personal note */
  function noteVerseSet(notes) {
    const set = new Set();
    (notes || []).forEach((n) => {
      const scope = (n.scope || 'verse').toLowerCase();
      if (scope === 'book' || scope === 'chapter') return;
      const ch = Number(n.chapter) || 0;
      if (ch && ch !== Number(currentChapter)) return;
      const a = Number(n.verse_start) || 0;
      const b = Number(n.verse_end) || a;
      if (a < 1) return;
      for (let i = a; i <= b; i += 1) set.add(i);
    });
    return set;
  }

  function firstNoteIdForVerse(verseNum) {
    const n = findExistingNote('verse', verseNum, verseNum);
    return n ? n.id : null;
  }

  function renderChapter(data) {
    const content = main();
    if (!content) return;
    const highlights = data.highlights || [];
    const crossRefs = data.cross_refs || {};
    // Prefer notes already loaded for this chapter; fall back to chapter payload
    const notesForMarkers = (currentNotes && currentNotes.length)
      ? currentNotes
      : (data.notes || []);
    const noted = noteVerseSet(notesForMarkers);
    let html = '';
    (data.verses || []).forEach((v) => {
      const ref = `${data.book} ${data.chapter}:${v.verse}`;
      const strongs = (data.strongs && (data.strongs[v.verse] || data.strongs[String(v.verse)])) || [];
      const hl = highlightClass(v.verse, highlights);
      const isFav = favoriteVerses.has(v.verse);
      const hasNote = noted.has(v.verse);
      const isSel = selectedVerses.has(Number(v.verse));
      html += `<div class="member-bible-verse${hl}${isFav ? ' is-favorite' : ''}${hasNote ? ' has-note' : ''}${isSel ? ' verse-selected' : ''}" data-verse="${v.verse}" data-text="${escapeAttr(v.text)}">`;
      html += `<span class="member-bible-verse-num">${v.verse}</span>`;
      if (isLoggedIn && hasNote) {
        html += `<button type="button" class="member-note-marker" data-open-note-verse="${v.verse}" title="Open your note on this verse" aria-label="Open note">📝</button>`;
      }
      if (isLoggedIn) {
        html += `<button type="button" class="member-verse-heart${isFav ? ' on' : ''}" data-heart-verse="${v.verse}" title="Favorite verse" aria-label="Favorite">${isFav ? '♥' : '♡'}</button>`;
      }
      html += `<span class="member-bible-verse-text">${renderVerseText(v.text, strongs, v.woj)}</span>`;
      html += xrefHtml(v.verse, crossRefs);
      html += compareTextForVerse(v.verse);
      html += `<div class="member-verse-actions">`;
      if (isLoggedIn) {
        html += `<button type="button" class="btn btn-warning btn-sm" data-hl-verse="${v.verse}" title="Highlight with your default color">Highlight</button>
        <button type="button" class="btn btn-secondary btn-sm" data-hl-clear-verse="${v.verse}" title="Clear highlight">Clear</button>`;
      }
      html += `<button type="button" class="btn btn-secondary btn-sm" data-copy="${escapeAttr(ref)}" data-copy-text="${escapeAttr(v.text)}">Copy</button>`;
      if (isLoggedIn) {
        html += `<button type="button" class="btn btn-secondary btn-sm" data-note-verse="${v.verse}">${hasNote ? 'Edit note' : 'Note'}</button>`;
      }
      html += `</div>`;
      html += '</div>';
    });
    content.innerHTML = html || '<p class="text-muted">Empty chapter.</p>';
    lastChapterHtml = content.innerHTML;
    setMainView('chapter');
    bindMainChapterEvents();
  }

  function segmentsFromWoj(text, spans) {
    const raw = String(text || '');
    const list = (spans || [])
      .map((s) => ({ start: Number(s.start) || 0, end: Number(s.end) || 0 }))
      .filter((s) => s.end > s.start && s.start < raw.length)
      .sort((a, b) => a.start - b.start);
    if (!list.length) return [{ text: raw, woj: false }];
    const out = [];
    let i = 0;
    list.forEach((s) => {
      const a = Math.max(0, Math.min(raw.length, s.start));
      const b = Math.max(a, Math.min(raw.length, s.end));
      if (a > i) out.push({ text: raw.slice(i, a), woj: false });
      if (b > a) out.push({ text: raw.slice(a, b), woj: true });
      i = Math.max(i, b);
    });
    if (i < raw.length) out.push({ text: raw.slice(i), woj: false });
    return out.filter((s) => s.text);
  }

  function renderVerseText(text, strongsList, woj) {
    const segs = segmentsFromWoj(text, woj);
    const used = new Set();
    return segs.map((seg, idx) => {
      const inner = linkStrongs(seg.text, strongsList, { used, chips: idx === segs.length - 1 });
      return seg.woj ? `<span class="words-of-jesus">${inner}</span>` : inner;
    }).join('');
  }

  function linkStrongs(text, strongsList, opts) {
    opts = opts || {};
    if (!text) return '';
    if (!strongsList?.length) return escapeHtml(text);
    let result = escapeHtml(text);
    const used = opts.used || new Set();
    const sorted = [...strongsList].sort((a, b) =>
      String(b.surface_word || '').length - String(a.surface_word || '').length
    );
    sorted.forEach((s) => {
      const word = (s.surface_word || '').trim();
      const num = (s.strongs_number || '').trim();
      if (!word || !num || used.has(num)) return;
      const re = new RegExp(`(?<![\\w-])(${escapeRegex(word)})(?![\\w-])`, 'i');
      let replaced = false;
      result = result.replace(re, (m) => {
        if (replaced) return m;
        replaced = true;
        used.add(num);
        const tip = [num, s.transliteration, s.lemma].filter(Boolean).join(' · ');
        return `<button type="button" class="member-bible-strongs-word" data-strongs="${escapeAttr(num)}" title="${escapeAttr(tip)}">${m}<sup class="strongs-num">${escapeHtml(num)}</sup></button>`;
      });
    });
    if (opts.chips !== false) {
      const leftover = strongsList.filter((s) => s.strongs_number && !used.has(s.strongs_number));
      if (leftover.length) {
        result += '<span class="strongs-chips">';
        leftover.forEach((s) => {
          const tip = [s.strongs_number, s.transliteration, s.lemma].filter(Boolean).join(' · ');
          result += `<button type="button" class="strongs-chip" data-strongs="${escapeAttr(s.strongs_number)}" title="${escapeAttr(tip)}">${escapeHtml(s.surface_word || s.lemma || s.strongs_number)}</button>`;
        });
        result += '</span>';
      }
    }
    return result;
  }

  function resolveFocusVerse(requested) {
    const nums = verseNums.length
      ? verseNums
      : Array.from(main()?.querySelectorAll('.member-bible-verse') || [])
        .map((l) => parseInt(l.dataset.verse, 10))
        .filter((n) => n > 0);
    const want = parseInt(requested, 10) || 0;
    if (want && nums.includes(want)) return want;
    return nums[0] || 1;
  }

  function paintSelectedVerses() {
    main()?.querySelectorAll('.member-bible-verse').forEach((l) => {
      const n = parseInt(l.dataset.verse, 10);
      l.classList.toggle('verse-selected', selectedVerses.has(n));
    });
  }

  function scrollChapterToVerse(n) {
    const content = main();
    const line = content?.querySelector(`.member-bible-verse[data-verse="${n}"]`);
    if (!content) return;
    const first = verseNums[0] || 1;
    if (!line || n === first) {
      content.scrollTop = 0;
      return;
    }
    const cRect = content.getBoundingClientRect();
    const lRect = line.getBoundingClientRect();
    const pad = parseInt(getComputedStyle(content).paddingTop, 10) || 0;
    content.scrollTop = Math.max(0, content.scrollTop + (lRect.top - cRect.top) - pad);
  }

  function selectAndFocusVerse(n) {
    const v = resolveFocusVerse(n);
    selectedVerses = new Set([v]);
    paintSelectedVerses();
    el('member-bible-num-grid')?.querySelectorAll('button').forEach((b) => {
      b.classList.toggle('active', pickerMode === 'verse' && parseInt(b.textContent, 10) === v);
    });
    main()?.querySelectorAll('.member-bible-verse').forEach((l) => {
      l.classList.toggle('highlight', parseInt(l.dataset.verse, 10) === v);
    });
    fillStudyFocus();
    requestAnimationFrame(() => scrollChapterToVerse(v));
  }

  function updateSelectionBar() {
    paintSelectedVerses();
  }

  function selectedScripture() {
    const nums = Array.from(selectedVerses).sort((a, b) => a - b);
    if (!nums.length) return null;
    const texts = [];
    nums.forEach((v) => {
      const line = main()?.querySelector(`.member-bible-verse[data-verse="${v}"]`);
      const t = line?.dataset.text || '';
      if (t) texts.push(`${v} ${t}`);
    });
    return {
      verse_start: nums[0],
      verse_end: nums[nums.length - 1],
      reference: nums.length === 1
        ? `${currentBook} ${currentChapter}:${nums[0]}`
        : `${currentBook} ${currentChapter}:${nums[0]}-${nums[nums.length - 1]}`,
      scripture_text: texts.join('\n'),
    };
  }

  function bindMainChapterEvents() {
    const content = main();
    if (!content) return;
    content.querySelectorAll('.member-bible-strongs-word, .strongs-chip').forEach((node) => {
      node.addEventListener('click', (e) => {
        e.stopPropagation();
        e.preventDefault();
        showStrongs(node.dataset.strongs);
      });
    });
    content.querySelectorAll('.member-xref-link').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        e.preventDefault();
        openXrefFromButton(btn);
      });
    });
    content.querySelectorAll('[data-heart-verse]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const v = parseInt(btn.dataset.heartVerse, 10);
        const line = btn.closest('.member-bible-verse');
        toggleFavorite('verse', { verse: v, text: line?.dataset.text || '' });
      });
    });
    content.querySelectorAll('[data-hl-verse]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const v = parseInt(btn.dataset.hlVerse, 10);
        const color = el('member-hl-color')?.value || 'yellow';
        applyHighlightVerse(v, v, color);
      });
    });
    content.querySelectorAll('[data-hl-clear-verse]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const v = parseInt(btn.dataset.hlClearVerse, 10);
        clearHighlightVerse(v);
      });
    });
    content.querySelectorAll('[data-note-verse]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const v = parseInt(btn.dataset.noteVerse, 10);
        selectedVerses = new Set([v]);
        updateSelectionBar();
        // Reopen previous note for this verse when one exists (edit / add to it)
        openNoteModal({ scope: 'verse', verse_start: v, verse_end: v });
      });
    });
    content.querySelectorAll('[data-open-note-verse]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const v = parseInt(btn.dataset.openNoteVerse, 10);
        selectedVerses = new Set([v]);
        updateSelectionBar();
        openNoteModal({ scope: 'verse', verse_start: v, verse_end: v });
      });
    });
    content.querySelectorAll('[data-copy]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const payload = `${btn.dataset.copy} — ${btn.dataset.copyText || ''}`;
        navigator.clipboard.writeText(payload).then(() => toast('Copied'));
      });
    });
    content.querySelectorAll('.member-bible-verse').forEach((line) => {
      line.addEventListener('click', (e) => {
        if (e.target.closest('.member-verse-actions')
          || e.target.closest('.member-verse-heart')
          || e.target.closest('.member-note-marker')
          || e.target.closest('.member-hl-swatches')
          || e.target.closest('.member-xrefs')
          || e.target.closest('.member-bible-strongs-word')
          || e.target.closest('.strongs-chip')) return;
        const v = parseInt(line.dataset.verse, 10);
        if (!v) return;
        if (e.shiftKey && selectedVerses.size) {
          const anchor = Array.from(selectedVerses).pop();
          const lo = Math.min(anchor, v);
          const hi = Math.max(anchor, v);
          for (let i = lo; i <= hi; i++) selectedVerses.add(i);
        } else if (e.ctrlKey || e.metaKey) {
          if (selectedVerses.has(v)) selectedVerses.delete(v);
          else selectedVerses.add(v);
        } else {
          selectedVerses = new Set([v]);
        }
        if (!selectedVerses.size) selectedVerses = new Set([v]);
        paintSelectedVerses();
        fillStudyFocus();
      });
    });
  }

  function scrollToVerse(n) {
    selectAndFocusVerse(n);
  }

  function restoreChapter() {
    if (lastChapterHtml) {
      main().innerHTML = lastChapterHtml;
      bindMainChapterEvents();
      setMainView('chapter');
    } else loadChapter(currentChapter);
  }

  // ---- Favorites ----
  async function toggleFavorite(scope, extra = {}) {
    if (!requireLogin('favorites')) return;
    const body = {
      scope,
      book: currentBook,
      chapter: scope === 'book' ? 0 : currentChapter,
      verse: scope === 'verse' ? (extra.verse || Array.from(selectedVerses)[0] || 0) : 0,
      translation: annotationKey || translation(),
      scripture_text: extra.text || '',
    };
    if (scope === 'verse' && !body.verse) return toast('Select a verse first');
    try {
      if (!csrfToken()) {
        throw new Error('Security token missing — refresh the page and try again');
      }
      const data = await apiPost(urls.favorite || `${base}/favorite`, body);
      if (!data.ok) throw new Error(data.error || 'Failed');
      if (scope === 'verse') {
        if (data.favorited) favoriteVerses.add(body.verse);
        else favoriteVerses.delete(body.verse);
      } else if (scope === 'chapter') {
        favChapter = !!data.favorited;
      } else if (scope === 'book') {
        favBook = !!data.favorited;
      }
      updateFavButtons();
      if (scope === 'verse') {
        const line = main()?.querySelector(`.member-bible-verse[data-verse="${body.verse}"]`);
        const heart = line?.querySelector('.member-verse-heart');
        if (line) line.classList.toggle('is-favorite', !!data.favorited);
        if (heart) {
          heart.textContent = data.favorited ? '♥' : '♡';
          heart.classList.toggle('on', !!data.favorited);
        }
      }
      toast(data.favorited
        ? `Favorited ${data.label || scope}`
        : `Removed ${data.label || scope} from favorites`);
    } catch (e) {
      toast(e.message || 'Could not update favorite');
    }
  }

  // ---- Highlights (inline swatches or selection bar) ----
  async function applyHighlightVerse(verseStart, verseEnd, color) {
    if (!requireLogin('highlights')) return;
    try {
      if (!csrfToken()) throw new Error('Security token missing — refresh the page');
      const data = await apiPost(urls.highlight || `${base}/highlight`, {
        translation: annotationKey || translation(),
        book: currentBook,
        chapter: currentChapter,
        verse_start: verseStart,
        verse_end: verseEnd || verseStart,
        color: color || 'yellow',
      });
      if (!data.ok) throw new Error(data.error || 'Failed');
      for (let v = verseStart; v <= (verseEnd || verseStart); v++) {
        const line = main()?.querySelector(`.member-bible-verse[data-verse="${v}"]`);
        if (!line) continue;
        ['yellow','green','blue','pink','orange','purple'].forEach((c) => line.classList.remove('hl-' + c));
        line.classList.add('hl-' + (color || 'yellow'));
      }
      toast(`Highlighted ${color || 'yellow'}`);
    } catch (e) {
      toast(e.message || 'Could not highlight');
    }
  }

  async function clearHighlightVerse(verse) {
    if (!requireLogin('highlights')) return;
    try {
      if (!csrfToken()) throw new Error('Security token missing — refresh the page');
      await apiPost(urls.highlightClear || `${base}/highlight/clear`, {
        translation: annotationKey || translation(),
        book: currentBook,
        chapter: currentChapter,
        verse,
      });
      const line = main()?.querySelector(`.member-bible-verse[data-verse="${verse}"]`);
      if (line) {
        ['yellow','green','blue','pink','orange','purple'].forEach((c) => line.classList.remove('hl-' + c));
      }
      toast('Highlight cleared');
    } catch (e) {
      toast(e.message || 'Could not clear highlight');
    }
  }

  async function applyHighlight() {
    if (!selectedVerses.size) return toast('Select a verse first');
    const nums = Array.from(selectedVerses).sort((a, b) => a - b);
    const color = el('member-hl-color')?.value || 'yellow';
    await applyHighlightVerse(nums[0], nums[nums.length - 1], color);
  }

  async function clearHighlight() {
    if (!selectedVerses.size) return toast('Select a verse first');
    for (const v of selectedVerses) {
      await clearHighlightVerse(v);
    }
  }

  // ---- Notes ----
  function syncNoteScriptureVisibility() {
    const include = el('member-note-include-verse');
    const wrap = el('member-note-scripture-wrap');
    if (!wrap) return;
    const show = !include || include.checked;
    wrap.style.display = show ? '' : 'none';
  }

  /**
   * Find an existing note for this scope/passage so reopening loads it for edit/append.
   * Prefer exact verse match, then overlapping range, newest first.
   */
  function findExistingNote(scope, verseStart, verseEnd) {
    const list = currentNotes || [];
    if (!list.length) return null;
    const sc = (scope || 'verse').toLowerCase();
    let matches = [];
    if (sc === 'book') {
      matches = list.filter((n) => (n.scope || 'verse').toLowerCase() === 'book');
    } else if (sc === 'chapter') {
      matches = list.filter((n) => (n.scope || '').toLowerCase() === 'chapter');
    } else {
      const vs = Number(verseStart) || 0;
      const ve = Number(verseEnd) || vs;
      matches = list.filter((n) => {
        const s = (n.scope || 'verse').toLowerCase();
        if (s !== 'verse') return false;
        const a = Number(n.verse_start) || 0;
        const b = Number(n.verse_end) || a;
        if (!a) return false;
        // overlapping ranges on this chapter's notes list
        return a <= ve && b >= vs;
      });
      // exact start first, then newest id
      matches.sort((x, y) => {
        const xExact = Number(x.verse_start) === vs && Number(x.verse_end || x.verse_start) === ve ? 0 : 1;
        const yExact = Number(y.verse_start) === vs && Number(y.verse_end || y.verse_start) === ve ? 0 : 1;
        if (xExact !== yExact) return xExact - yExact;
        return (Number(y.id) || 0) - (Number(x.id) || 0);
      });
      return matches[0] || null;
    }
    matches.sort((x, y) => (Number(y.id) || 0) - (Number(x.id) || 0));
    return matches[0] || null;
  }

  function setNoteModalEditingState(isEditing, extraMsg) {
    const heading = el('member-note-heading');
    const status = el('member-note-status');
    const saveBtn = el('member-note-save');
    const newBtn = el('member-note-new');
    if (heading) heading.textContent = isEditing ? 'Edit study note' : 'Study note';
    if (saveBtn) saveBtn.textContent = isEditing ? 'Update note' : 'Save note';
    if (newBtn) newBtn.style.display = isEditing ? '' : 'none';
    if (status) {
      if (isEditing) {
        status.style.display = '';
        status.className = 'small mb-3 text-primary';
        status.textContent = extraMsg
          || 'Previous note loaded — edit the text or add more at the end, then Update.';
      } else {
        status.style.display = 'none';
        status.textContent = '';
      }
    }
  }

  function focusBodyAtEnd() {
    const body = el('member-note-body');
    if (!body) return;
    body.focus();
    try {
      const len = body.value.length;
      body.setSelectionRange(len, len);
      // leave a blank line ready for "add to it"
      if (len > 0 && !body.value.endsWith('\n')) {
        // don't mutate silently; user can type — just place caret at end
      }
    } catch (e) { /* ignore */ }
  }

  function openNoteModal(opts = {}) {
    if (!requireLogin('notes')) return;
    let scope = opts.scope || 'verse';
    const modal = el('member-note-modal');
    const ref = el('member-note-ref');
    const scopeSel = el('member-note-scope');
    const title = el('member-note-title');
    const scripture = el('member-note-scripture');
    const body = el('member-note-body');
    const tags = el('member-note-tags');
    const include = el('member-note-include-verse');

    let bundle = null;
    if (scope === 'verse') {
      if (!selectedVerses.size && !opts.verse_start) {
        return toast('Select a verse first (or use Note chapter / Note book)');
      }
      bundle = selectedScripture() || {
        verse_start: opts.verse_start,
        verse_end: opts.verse_end || opts.verse_start,
        reference: `${currentBook} ${currentChapter}:${opts.verse_start}`,
        scripture_text: opts.scripture_text || '',
      };
    } else if (scope === 'chapter') {
      bundle = {
        verse_start: 0,
        verse_end: 0,
        reference: `${currentBook} ${currentChapter}`,
        scripture_text: '',
      };
    } else {
      bundle = {
        verse_start: 0,
        verse_end: 0,
        reference: `${currentBook} (whole book)`,
        scripture_text: '',
      };
    }

    // Load previous note for this passage unless starting fresh or explicitly editing another id
    let existing = null;
    if (!opts.forceNew) {
      if (opts.editId) {
        existing = (currentNotes || []).find((n) => Number(n.id) === Number(opts.editId)) || null;
        if (existing && existing.scope) scope = (existing.scope || scope).toLowerCase();
      } else {
        existing = findExistingNote(scope, bundle.verse_start, bundle.verse_end);
      }
    }

    if (scopeSel) scopeSel.value = scope;
    if (ref) {
      ref.textContent = (existing && existing.reference) || bundle.reference;
      ref.dataset.vStart = String(
        existing ? (existing.verse_start || bundle.verse_start || 0) : (bundle.verse_start || 0)
      );
      ref.dataset.vEnd = String(
        existing ? (existing.verse_end || existing.verse_start || bundle.verse_end || 0)
          : (bundle.verse_end || 0)
      );
      ref.dataset.editId = existing ? String(existing.id) : (opts.editId ? String(opts.editId) : '');
      ref.dataset.scripture = (existing && existing.scripture_text) || bundle.scripture_text || '';
    }
    if (title) {
      title.value = opts.title
        || (existing && (existing.title || existing.display_title))
        || bundle.reference
        || '';
    }
    if (scripture) {
      scripture.value = opts.scripture_text
        || (existing && existing.scripture_text)
        || bundle.scripture_text
        || '';
    }
    if (body) {
      body.value = opts.body != null ? opts.body : (existing ? (existing.body || '') : '');
    }
    if (tags) tags.value = opts.tags != null ? opts.tags : (existing ? (existing.tags || '') : '');
    // Include verse text by default when we have scripture for a verse note
    if (include) {
      const hasScripture = !!(
        opts.scripture_text
        || (existing && existing.scripture_text)
        || bundle.scripture_text
      );
      include.checked = scope === 'verse' ? hasScripture : false;
    }
    syncNoteScriptureVisibility();
    setNoteModalEditingState(!!(existing || opts.editId));

    if (modal) {
      modal.style.display = 'flex';
      modal.setAttribute('aria-hidden', 'false');
    }
    // Cursor at end so user can immediately add to previous note
    requestAnimationFrame(() => focusBodyAtEnd());
  }

  /** Clear edit mode and blank body while keeping the same passage reference. */
  function startNewNoteFromModal() {
    const ref = el('member-note-ref');
    const scope = el('member-note-scope')?.value || 'verse';
    if (ref) ref.dataset.editId = '';
    const title = el('member-note-title');
    const body = el('member-note-body');
    const tags = el('member-note-tags');
    if (body) body.value = '';
    if (tags) tags.value = '';
    if (title && !title.value) {
      title.value = ref?.textContent || `${currentBook} ${currentChapter}`;
    }
    setNoteModalEditingState(false);
    const status = el('member-note-status');
    if (status) {
      status.style.display = '';
      status.className = 'small mb-3 text-muted';
      status.textContent = 'Writing a new note (previous note is kept).';
    }
    // stay on same scope/passage
    void scope;
    focusBodyAtEnd();
  }

  function closeNoteModal() {
    const modal = el('member-note-modal');
    if (modal) {
      modal.style.display = 'none';
      modal.setAttribute('aria-hidden', 'true');
    }
  }

  async function openNoteModalForEdit(noteId) {
    if (!requireLogin('notes')) return;
    let n = (currentNotes || []).find((x) => Number(x.id) === Number(noteId));
    if (!n) {
      try {
        const resp = await fetch(`${base}/note/${noteId}`, {
          headers: apiHeaders(false),
          credentials: 'same-origin',
        });
        const data = await resp.json().catch(() => ({}));
        if (!data.ok || !data.note) throw new Error(data.error || 'Not found');
        n = data.note;
      } catch (e) {
        return toast(e.message || 'Could not load note');
      }
    }
    openNoteModal({
      editId: n.id,
      scope: (n.scope || 'verse').toLowerCase(),
      verse_start: n.verse_start,
      verse_end: n.verse_end,
      title: n.title || n.display_title || '',
      scripture_text: n.scripture_text || '',
      body: n.body || '',
      tags: n.tags || '',
    });
  }

  async function saveNoteFromModal() {
    if (!requireLogin('notes')) return;
    const ref = el('member-note-ref');
    const scope = el('member-note-scope')?.value || 'verse';
    const body = (el('member-note-body')?.value || '').trim();
    if (!body) return toast('Write a note first');
    try {
      if (!csrfToken()) throw new Error('Security token missing — refresh the page');
      const includeVerse = el('member-note-include-verse')?.checked;
      const scriptureRaw = (el('member-note-scripture')?.value || '').trim();
      const editId = ref?.dataset.editId ? parseInt(ref.dataset.editId, 10) : undefined;
      const data = await apiPost(urls.note || `${base}/note`, {
        id: editId || undefined,
        scope,
        translation: annotationKey || translation(),
        book: currentBook,
        chapter: scope === 'book' ? 0 : currentChapter,
        verse_start: scope === 'verse' ? parseInt(ref?.dataset.vStart || '0', 10) : 0,
        verse_end: scope === 'verse' ? parseInt(ref?.dataset.vEnd || '0', 10) : 0,
        title: (el('member-note-title')?.value || '').trim(),
        scripture_text: includeVerse ? scriptureRaw : '',
        tags: (el('member-note-tags')?.value || '').trim(),
        body,
      });
      if (!data.ok) throw new Error(data.error || 'Failed');
      toast(editId ? 'Note updated' : 'Note saved');
      closeNoteModal();
      setNotesPanelOpen(true, { flash: true });
      loadChapter(currentChapter);
    } catch (e) {
      toast(e.message || 'Could not save note');
    }
  }

  function noteIsOnCurrentPassage(n) {
    if (!n) return false;
    const scope = (n.scope || 'verse').toLowerCase();
    const book = (n.book || '').toString();
    if (book && book !== currentBook) return false;
    if (scope === 'book') return true;
    if (scope === 'chapter') return Number(n.chapter) === Number(currentChapter);
    return Number(n.chapter) === Number(currentChapter);
  }

  function goToNotePassage(n, opts = {}) {
    if (!n) return;
    const book = n.book || currentBook;
    const ch = Number(n.chapter) || 1;
    const v = Number(n.verse_start) || 1;
    const scope = (n.scope || 'verse').toLowerCase();
    closeFlyouts();
    const after = () => {
      if (opts.openEdit && n.id) {
        // small delay so chapter notes are loaded for modal prefill
        setTimeout(() => openNoteModalForEdit(n.id), 120);
      }
    };
    if (book === currentBook && Number(ch) === Number(currentChapter) && scope !== 'book') {
      if (scope === 'verse' && v) scrollToVerse(v);
      if (opts.openEdit) focusNotesPanel();
      else setNotesPanelOpen(false);
      after();
      return;
    }
    currentBook = book;
    prepareBook(book, {
      chapter: scope === 'book' ? 1 : ch,
      scrollToVerse: scope === 'verse' ? v : 1,
    }).then(() => {
      after();
      if (!opts.openEdit) setNotesPanelOpen(false);
      if (notesPanelTab === 'all') {
        setNotesPanelTab('all');
      } else {
        setNotesPanelTab('passage');
      }
    }).catch(() => {
      toast('Could not open that passage');
    });
  }

  function truncateText(s, n) {
    const t = String(s || '').trim();
    if (t.length <= n) return t;
    return `${t.slice(0, n - 1).trimEnd()}…`;
  }

  function updateNotesCount() {
    const badge = el('member-notes-count');
    if (!badge) return;
    const n = (currentNotes || []).length;
    if (n > 0) {
      badge.hidden = false;
      badge.textContent = String(n);
    } else {
      badge.hidden = true;
      badge.textContent = '';
    }
  }

  function setNotesPanelOpen(open, opts = {}) {
    notesPanelOpen = !!open;
    const panel = el('member-notes-panel');
    const body = el('member-notes-body');
    const toggle = el('member-notes-toggle');
    if (!panel) return;
    panel.classList.toggle('is-collapsed', !notesPanelOpen);
    if (body) body.hidden = !notesPanelOpen;
    if (toggle) toggle.setAttribute('aria-expanded', notesPanelOpen ? 'true' : 'false');
    if (notesPanelOpen) {
      panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      if (opts.flash) {
        panel.classList.add('member-notes-panel-flash');
        setTimeout(() => panel.classList.remove('member-notes-panel-flash'), 1600);
      }
    }
  }

  function focusNotesPanel(flash) {
    setNotesPanelOpen(true, { flash: !!flash });
  }

  function setNotesPanelTab(tab) {
    notesPanelTab = tab === 'all' ? 'all' : 'passage';
    document.querySelectorAll('[data-notes-tab]').forEach((btn) => {
      const on = btn.dataset.notesTab === notesPanelTab;
      btn.classList.toggle('active', on);
      btn.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    const hint = el('member-notes-hint');
    if (hint) {
      hint.innerHTML = notesPanelTab === 'all'
        ? 'All notes across books. Click a note (or <strong>Go</strong>) to jump to that chapter/verse.'
        : 'Notes for this chapter. Verses with notes show a <span class="member-note-dot-demo" title="Note marker">📝</span> marker in the reader — tap it to open.';
    }
    if (notesPanelTab === 'all') {
      loadAllNotesPanel();
    } else {
      renderNotesPanel(currentNotes, { mode: 'passage' });
    }
  }

  function renderNoteCards(listEl, notes, mode) {
    listEl.innerHTML = notes.map((n) => {
      const scopeBadge = n.scope && n.scope !== 'verse'
        ? `<span class="member-scope-badge">${escapeHtml(n.scope)}</span>`
        : '<span class="member-scope-badge verse">verse</span>';
      const here = noteIsOnCurrentPassage(n);
      const elsewhere = mode === 'all' && !here;
      const hereBadge = here && mode === 'all'
        ? '<span class="member-note-here-badge">Here</span>'
        : '';
      const title = n.display_title || n.title || n.reference || 'Note';
      const metaBits = [];
      if (n.reference && n.reference !== title) metaBits.push(n.reference);
      if (n.translation) metaBits.push('noted in ' + String(n.translation).replace(/^online:/, ''));
      if (n.tags) metaBits.push(n.tags);
      const meta = metaBits.join(' · ');
      const scripture = (mode === 'all' && n.scripture_text)
        ? `<blockquote class="member-note-scripture">${escapeHtml(truncateText(n.scripture_text, 140))}</blockquote>`
        : '';
      return `<article class="member-note-card is-clickable${elsewhere ? ' is-elsewhere' : ''}" data-note-id="${n.id}" data-goto-note-id="${n.id}">
        <header class="member-note-card-head">
          <h4 class="member-note-card-title">${escapeHtml(title)}</h4>
          ${scopeBadge}${hereBadge}
        </header>
        ${meta ? `<div class="member-note-card-meta">${escapeHtml(meta)}</div>` : ''}
        ${scripture}
        <div class="member-note-body">${escapeHtml(n.body || '')}</div>
        <footer class="member-note-card-actions">
          <button type="button" class="btn btn-sm btn-secondary" data-goto-note-id="${n.id}">Go to verse</button>
          <button type="button" class="btn btn-sm btn-primary" data-edit-note="${n.id}">Edit / add</button>
          <a class="btn btn-sm btn-secondary" href="${base}/note/${n.id}/download">Download</a>
          <button type="button" class="btn btn-sm btn-secondary" data-del-note="${n.id}">Delete</button>
        </footer>
      </article>`;
    }).join('');

    const findNote = (id) => {
      const nid = Number(id);
      return (notes || []).find((x) => Number(x.id) === nid)
        || (currentNotes || []).find((x) => Number(x.id) === nid)
        || (allNotesCache || []).find((x) => Number(x.id) === nid);
    };

    listEl.querySelectorAll('[data-goto-note-id]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const n = findNote(btn.dataset.gotoNoteId);
        if (n) goToNotePassage(n);
      });
    });
    listEl.querySelectorAll('.member-note-card[data-goto-note-id]').forEach((card) => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('button, a')) return;
        const n = findNote(card.dataset.gotoNoteId);
        // Card body → jump to passage; Edit button opens the note
        if (n) goToNotePassage(n);
      });
    });
    listEl.querySelectorAll('[data-edit-note]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const n = findNote(btn.dataset.editNote);
        if (n && !noteIsOnCurrentPassage(n)) {
          goToNotePassage(n, { openEdit: true });
        } else {
          openNoteModalForEdit(parseInt(btn.dataset.editNote, 10));
        }
      });
    });
    listEl.querySelectorAll('[data-del-note]').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (!confirm('Delete this note?')) return;
        try {
          const resp = await fetch(`${base}/note/${btn.dataset.delNote}`, {
            method: 'DELETE',
            headers: apiHeaders(false),
            credentials: 'same-origin',
          });
          const data = await resp.json().catch(() => ({}));
          if (data.ok) {
            toast('Note deleted');
            loadChapter(currentChapter);
            if (notesPanelTab === 'all') loadAllNotesPanel();
          } else toast(data.error || 'Could not delete');
        } catch (err) {
          toast('Could not delete note');
        }
      });
    });
  }

  function renderNotesPanel(notes, opts = {}) {
    const list = el('member-notes-list');
    if (!list) return;
    if (opts.mode !== 'all') {
      currentNotes = notes || [];
    }
    updateNotesCount();
    if (!isLoggedIn) {
      list.innerHTML = `<p class="member-notes-empty">Notes are for members.
        <a href="${escapeAttr(loginUrl)}">Log in</a> to save verse, chapter, and book notes.</p>`;
      return;
    }
    const mode = opts.mode || notesPanelTab || 'passage';
    if (!notes?.length) {
      list.innerHTML = mode === 'all'
        ? '<p class="member-notes-empty">No notes yet. Tap a verse → <strong>Note</strong> to start.</p>'
        : '<p class="member-notes-empty">No notes on this passage yet. Tap a verse → <strong>Note</strong>.</p>';
      return;
    }
    renderNoteCards(list, notes, mode);
  }

  async function loadAllNotesPanel() {
    const list = el('member-notes-list');
    if (!list) return;
    if (!isLoggedIn) {
      list.innerHTML = `<p class="member-notes-empty"><a href="${escapeAttr(loginUrl)}">Log in</a> to see all notes.</p>`;
      return;
    }
    list.innerHTML = '<p class="small text-muted mb-0">Loading all notes…</p>';
    try {
      const resp = await fetch((urls.notes || `${base}/notes`) + '?limit=100', {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      });
      const data = await resp.json().catch(() => ({}));
      allNotesCache = data.notes || [];
      renderNotesPanel(allNotesCache, { mode: 'all' });
    } catch (e) {
      list.innerHTML = '<p class="small text-warning">Could not load notes.</p>';
    }
  }

  async function loadNotesLibrary() {
    const box = el('member-notes-lib');
    if (!box) return;
    if (!isLoggedIn) {
      box.innerHTML = `<p class="small text-muted"><a href="${escapeAttr(loginUrl)}">Log in</a> to search and download your notes.</p>`;
      return;
    }
    const q = el('member-notes-q')?.value || '';
    const scope = el('member-notes-scope')?.value || '';
    box.innerHTML = '<p class="small text-muted">Loading…</p>';
    try {
      const params = new URLSearchParams({ q, limit: '50' });
      if (scope) params.set('scope', scope);
      const resp = await fetch((urls.notes || `${base}/notes`) + '?' + params.toString());
      const data = await resp.json();
      const rows = data.notes || [];
      allNotesCache = rows;
      if (!rows.length) {
        box.innerHTML = '<p class="small text-muted">No notes found.</p>';
        return;
      }
      box.innerHTML = rows.map((n) => `
        <div class="member-lib-item" data-lib-note-id="${n.id}" title="Go to ${escapeAttr(n.reference || '')}">
          <div class="small fw-semibold">${escapeHtml(n.display_title || n.title)}</div>
          <div class="small text-muted">${escapeHtml(n.reference || '')}${n.scope && n.scope !== 'verse' ? ' · ' + n.scope : ''}</div>
          <div class="small" style="max-height:2.8em;overflow:hidden;">${escapeHtml((n.body || '').slice(0, 140))}</div>
          <button type="button" class="btn btn-sm btn-primary mt-1" data-goto-note-id="${n.id}">Go to verse</button>
          <button type="button" class="btn btn-sm btn-secondary mt-1" data-edit-note="${n.id}">Edit</button>
          <a class="btn btn-sm btn-secondary mt-1" href="${base}/note/${n.id}/download">Download</a>
        </div>
      `).join('');
      const findNote = (id) => rows.find((x) => Number(x.id) === Number(id));
      box.querySelectorAll('[data-goto-note-id]').forEach((btn) => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const n = findNote(btn.dataset.gotoNoteId);
          if (n) goToNotePassage(n);
        });
      });
      box.querySelectorAll('[data-edit-note]').forEach((btn) => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const n = findNote(btn.dataset.editNote);
          if (n) goToNotePassage(n, { openEdit: true });
        });
      });
      box.querySelectorAll('.member-lib-item[data-lib-note-id]').forEach((item) => {
        item.addEventListener('click', (e) => {
          if (e.target.closest('button, a')) return;
          const n = findNote(item.dataset.libNoteId);
          if (n) goToNotePassage(n);
        });
      });
    } catch (e) {
      box.innerHTML = '<p class="small text-warning">Could not load notes.</p>';
    }
  }

  async function loadFavoritesLibrary() {
    const box = el('member-favs-lib');
    if (!box) return;
    if (!isLoggedIn) {
      box.innerHTML = `<p class="small text-muted"><a href="${escapeAttr(loginUrl)}">Log in</a> to save and browse favorites.</p>`;
      return;
    }
    const scope = el('member-favs-scope')?.value || '';
    box.innerHTML = '<p class="small text-muted">Loading…</p>';
    try {
      const params = new URLSearchParams({ limit: '80' });
      if (scope) params.set('scope', scope);
      const resp = await fetch((urls.favorites || `${base}/favorites`) + '?' + params.toString());
      const data = await resp.json();
      const rows = data.favorites || [];
      if (!rows.length) {
        box.innerHTML = '<p class="small text-muted">No favorites yet. Heart a verse, chapter, or book.</p>';
        return;
      }
      box.innerHTML = rows.map((f) => `
        <div class="member-lib-item">
          <div class="small fw-semibold">♥ ${escapeHtml(f.label || '')}</div>
          <div class="small text-muted">${escapeHtml(f.scope || 'verse')}${f.scripture_text ? ' — ' + escapeHtml(f.scripture_text.slice(0, 80)) : ''}</div>
          <button type="button" class="btn btn-sm btn-secondary mt-1" data-goto-fav="${escapeAttr(f.book)}|${f.chapter || 1}|${f.verse || 1}">Open</button>
        </div>
      `).join('');
      box.querySelectorAll('[data-goto-fav]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const [book, ch, v] = btn.dataset.gotoFav.split('|');
          currentBook = book;
          closeFlyouts();
          prepareBook(book, {
            chapter: parseInt(ch, 10) || 1,
            scrollToVerse: parseInt(v, 10) || 1,
          });
        });
      });
    } catch (e) {
      box.innerHTML = '<p class="small text-warning">Could not load favorites.</p>';
    }
  }

  function ensureStrongsPopup() {
    let root = el('member-strongs-popup');
    if (root) return root;
    root = document.createElement('div');
    root.id = 'member-strongs-popup';
    root.className = 'bible-strongs-popup';
    root.setAttribute('aria-hidden', 'true');
    root.innerHTML = `
      <div class="bible-strongs-card" role="dialog" aria-modal="true" aria-labelledby="member-strongs-title">
        <button type="button" class="bible-strongs-close" data-strongs-close aria-label="Close">&times;</button>
        <p class="bible-strongs-kicker">Strong’s</p>
        <h3 id="member-strongs-title" class="bible-strongs-title">—</h3>
        <p class="bible-strongs-meta" data-strongs-meta></p>
        <ol class="bible-strongs-senses" data-strongs-senses></ol>
        <p class="bible-strongs-full small text-muted" data-strongs-full></p>
        <ul class="bible-strongs-occ small" data-strongs-occ></ul>
      </div>`;
    document.body.appendChild(root);
    root.addEventListener('click', (e) => {
      if (e.target === root || e.target.closest('[data-strongs-close]')) {
        root.classList.remove('open');
        root.setAttribute('aria-hidden', 'true');
      }
    });
    return root;
  }

  async function showStrongs(number) {
    if (!number) return;
    const root = ensureStrongsPopup();
    root.classList.add('open');
    root.setAttribute('aria-hidden', 'false');
    root.querySelector('#member-strongs-title').textContent = number;
    root.querySelector('[data-strongs-meta]').textContent = 'Loading…';
    root.querySelector('[data-strongs-senses]').innerHTML = '';
    root.querySelector('[data-strongs-full]').textContent = '';
    root.querySelector('[data-strongs-occ]').innerHTML = '';
    try {
      const resp = await fetch(`${base}/strongs/${encodeURIComponent(number)}`);
      if (!resp.ok) throw new Error('missing');
      const data = await resp.json();
      root.querySelector('#member-strongs-title').textContent =
        `${data.number || number}  ·  ${data.transliteration || data.lemma || ''}`;
      root.querySelector('[data-strongs-meta]').textContent =
        [data.lemma, data.language].filter(Boolean).join(' · ');
      const senses = (data.senses && data.senses.length)
        ? data.senses
        : (data.definition ? [data.definition] : ['No gloss on file.']);
      root.querySelector('[data-strongs-senses]').innerHTML = senses
        .map((s) => `<li>${escapeHtml(s)}</li>`).join('');
      if (data.definition && senses.length > 1) {
        root.querySelector('[data-strongs-full]').textContent = data.definition;
      }
      const occ = data.occurrences || [];
      if (occ.length) {
        root.querySelector('[data-strongs-occ]').innerHTML = occ.slice(0, 12).map((o) =>
          `<li><a href="#" data-goto="${escapeAttr(o.book)}|${o.chapter}|${o.verse}">${escapeHtml(o.book)} ${o.chapter}:${o.verse}</a>${o.surface_word ? ' · ' + escapeHtml(o.surface_word) : ''}</li>`
        ).join('');
        root.querySelectorAll('[data-goto]').forEach((a) => {
          a.addEventListener('click', (ev) => {
            ev.preventDefault();
            const [book, ch, v] = a.dataset.goto.split('|');
            root.classList.remove('open');
            currentBook = book;
            loadChapter(parseInt(ch, 10)).then(() => scrollToVerse(parseInt(v, 10)));
          });
        });
      }
    } catch (e) {
      root.querySelector('[data-strongs-meta]').textContent = 'Strong’s entry not found.';
    }
  }

  /* ---- Linked-verse popup (cross-refs) ---- */
  let xrefPopupState = null;
  let xrefLoadId = 0;

  function xrefItemFromBtn(btn) {
    return {
      book: btn.dataset.book || btn.dataset.xrefBook || '',
      chapter: parseInt(btn.dataset.chapter || btn.dataset.xrefChapter, 10),
      verse: parseInt(btn.dataset.verse || btn.dataset.xrefVerse, 10) || 1,
      end_verse: parseInt(btn.dataset.endVerse || btn.dataset.xrefEnd, 10) || 0,
      reference: (btn.textContent || '').trim(),
      label: btn.getAttribute('title') || '',
    };
  }

  function expandXrefQueue(items) {
    const out = [];
    (items || []).forEach((r) => {
      const start = parseInt(r.verse, 10) || 1;
      const end = Math.max(parseInt(r.end_verse, 10) || 0, start);
      for (let v = start; v <= end; v += 1) {
        out.push({
          book: r.book,
          chapter: r.chapter,
          verse: v,
          reference: `${r.book} ${r.chapter}:${v}`,
          label: r.label || '',
        });
      }
    });
    return out;
  }

  function openXrefFromButton(btn) {
    const row = btn.closest('.member-xrefs') || btn.closest('#member-study-focus-body') || btn.parentElement;
    const btns = row ? Array.from(row.querySelectorAll('.member-xref-link')) : [btn];
    const raw = (btns.length ? btns : [btn]).map(xrefItemFromBtn).filter((r) => r.book && r.chapter);
    const queue = expandXrefQueue(raw.length ? raw : [xrefItemFromBtn(btn)]);
    const clicked = xrefItemFromBtn(btn);
    let idx = queue.findIndex((q) => (
      q.book === clicked.book && Number(q.chapter) === Number(clicked.chapter) && Number(q.verse) === Number(clicked.verse)
    ));
    if (idx < 0) idx = 0;
    openXrefPopup({ ...queue[idx], queue, index: idx });
  }

  function updateXrefNav(root) {
    const nav = root.querySelector('[data-xref-nav]');
    const queue = xrefPopupState?.queue || [];
    const n = queue.length;
    const show = n > 1;
    if (nav) nav.hidden = !show;
    root.querySelectorAll('.bible-xref-nav-side').forEach((btn) => { btn.hidden = !show; });
    const count = root.querySelector('[data-xref-count]');
    if (count && show) count.textContent = `${(xrefPopupState.index || 0) + 1} of ${n}`;
  }

  function stepXref(delta) {
    const queue = xrefPopupState?.queue;
    if (!queue || queue.length < 2) return;
    const n = queue.length;
    const next = (xrefPopupState.index + delta + n) % n;
    openXrefPopup({ ...queue[next], queue, index: next });
  }

  function ensureXrefPopup() {
    let root = el('member-xref-popup');
    if (root) return root;
    root = document.createElement('div');
    root.id = 'member-xref-popup';
    root.className = 'bible-xref-popup';
    root.setAttribute('aria-hidden', 'true');
    root.innerHTML = `
      <button type="button" class="bible-xref-nav-btn bible-xref-nav-side" data-xref-prev aria-label="Previous linked verse">‹</button>
      <div class="bible-xref-popup-card" role="dialog" aria-modal="true" aria-labelledby="member-xref-popup-title">
        <button type="button" class="bible-xref-popup-close" data-xref-close aria-label="Close">&times;</button>
        <div class="bible-xref-popup-meta">
          <span class="bible-xref-popup-kicker">Linked verse</span>
          <h3 id="member-xref-popup-title" class="bible-xref-popup-title">—</h3>
          <div class="bible-xref-popup-bcv">
            <span data-xref-book></span>
            <span class="bible-xref-popup-dot">·</span>
            <span>Chapter <strong data-xref-chapter></strong></span>
            <span class="bible-xref-popup-dot">·</span>
            <span>Verse <strong data-xref-verse></strong></span>
          </div>
          <div class="bible-xref-popup-nav" data-xref-nav hidden>
            <button type="button" class="bible-xref-nav-btn" data-xref-prev aria-label="Previous linked verse">‹</button>
            <span class="bible-xref-nav-count" data-xref-count></span>
            <button type="button" class="bible-xref-nav-btn" data-xref-next aria-label="Next linked verse">›</button>
          </div>
          <p class="bible-xref-popup-label small text-muted" data-xref-label style="display:none;"></p>
        </div>
        <blockquote class="bible-xref-popup-text" data-xref-text>Loading…</blockquote>
        <div class="bible-xref-popup-actions">
          <button type="button" class="btn btn-secondary btn-sm" data-xref-copy>Copy</button>
          <button type="button" class="btn btn-warning btn-sm" data-xref-highlight>Highlight</button>
          <button type="button" class="btn btn-primary btn-sm" data-xref-goto>Go to passage</button>
        </div>
      </div>
      <button type="button" class="bible-xref-nav-btn bible-xref-nav-side" data-xref-next aria-label="Next linked verse">›</button>`;
    document.body.appendChild(root);
    root.addEventListener('click', (e) => {
      if (e.target === root || e.target.closest('[data-xref-close]')) closeXrefPopup();
    });
    root.querySelectorAll('[data-xref-prev]').forEach((btn) => {
      btn.addEventListener('click', (e) => { e.stopPropagation(); stepXref(-1); });
    });
    root.querySelectorAll('[data-xref-next]').forEach((btn) => {
      btn.addEventListener('click', (e) => { e.stopPropagation(); stepXref(1); });
    });
    document.addEventListener('keydown', (e) => {
      if (!root.classList.contains('is-open')) return;
      if (e.key === 'ArrowLeft') { e.preventDefault(); stepXref(-1); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); stepXref(1); }
      else if (e.key === 'Escape') closeXrefPopup();
    });
    root.querySelector('[data-xref-copy]')?.addEventListener('click', () => {
      if (!xrefPopupState) return;
      const blob = `${xrefPopupState.reference}\n${xrefPopupState.text || ''}`.trim();
      const doCopy = () => toast('Copied');
      if (navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(blob).then(doCopy).catch(() => {
          // fallback
          const ta = document.createElement('textarea');
          ta.value = blob;
          document.body.appendChild(ta);
          ta.select();
          try { document.execCommand('copy'); doCopy(); } catch (err) { toast('Could not copy'); }
          ta.remove();
        });
      } else {
        toast('Copy not available');
      }
    });
    root.querySelector('[data-xref-highlight]')?.addEventListener('click', async () => {
      if (!xrefPopupState) return;
      if (!requireLogin('highlights')) return;
      const color = el('member-hl-color')?.value || 'yellow';
      try {
        if (!csrfToken()) throw new Error('Security token missing — refresh the page');
        const data = await apiPost(urls.highlight || `${base}/highlight`, {
          translation: annotationKey || translation(),
          book: xrefPopupState.book,
          chapter: xrefPopupState.chapter,
          verse_start: xrefPopupState.verse,
          verse_end: xrefPopupState.verse,
          color,
        });
        if (!data.ok) throw new Error(data.error || 'Failed');
        toast(`Highlighted ${xrefPopupState.reference}`);
      } catch (err) {
        toast(err.message || 'Could not highlight');
      }
    });
    root.querySelector('[data-xref-goto]')?.addEventListener('click', () => {
      if (!xrefPopupState) return;
      const { book, chapter, verse } = xrefPopupState;
      closeXrefPopup();
      closeFlyouts();
      currentBook = book;
      prepareBook(book, { chapter, scrollToVerse: verse || 1 });
    });
    return root;
  }

  function closeXrefPopup() {
    const root = el('member-xref-popup');
    if (!root) return;
    root.classList.remove('is-open');
    root.setAttribute('aria-hidden', 'true');
    xrefPopupState = null;
  }

  async function openXrefPopup(opts) {
    const book = (opts.book || '').trim();
    const chapter = parseInt(opts.chapter, 10);
    const verse = parseInt(opts.verse, 10) || 1;
    if (!book || !chapter) return;
    const reference = opts.reference || `${book} ${chapter}:${verse}`;
    const queue = (opts.queue && opts.queue.length) ? opts.queue : [{ book, chapter, verse, reference, label: opts.label || '' }];
    let index = Number.isInteger(opts.index) ? opts.index : queue.findIndex((q) => (
      q.book === book && Number(q.chapter) === chapter && Number(q.verse) === verse
    ));
    if (index < 0) index = 0;
    xrefPopupState = { book, chapter, verse, reference, text: '', label: opts.label || '', queue, index };
    const root = ensureXrefPopup();
    updateXrefNav(root);
    root.querySelector('#member-xref-popup-title').textContent = reference;
    root.querySelector('[data-xref-book]').textContent = book;
    root.querySelector('[data-xref-chapter]').textContent = String(chapter);
    root.querySelector('[data-xref-verse]').textContent = String(verse);
    const labelEl = root.querySelector('[data-xref-label]');
    if (opts.label && opts.label !== reference) {
      labelEl.style.display = '';
      labelEl.textContent = opts.label;
    } else {
      labelEl.style.display = 'none';
      labelEl.textContent = '';
    }
    const textEl = root.querySelector('[data-xref-text]');
    textEl.textContent = 'Loading verse…';
    root.classList.add('is-open');
    root.setAttribute('aria-hidden', 'false');
    const loadId = ++xrefLoadId;

    try {
      const tr = translation();
      let url = `${base}/verse/${encodeURIComponent(book)}/${chapter}/${verse}`;
      if (tr) url += `?translation=${encodeURIComponent(tr)}`;
      const resp = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (!resp.ok) throw new Error('not found');
      const data = await resp.json();
      if (loadId !== xrefLoadId) return;
      const text = (data.text || '').trim();
      xrefPopupState.text = text;
      xrefPopupState.reference = data.reference || reference;
      root.querySelector('#member-xref-popup-title').textContent = xrefPopupState.reference;
      if (data.book) root.querySelector('[data-xref-book]').textContent = data.book;
      textEl.textContent = text || 'Verse text unavailable in this version.';
    } catch (err) {
      if (loadId !== xrefLoadId) return;
      textEl.textContent = 'Could not load this verse in the current version. You can still go to the passage.';
    }
  }

  async function searchBible() {
    const q = (el('member-bible-search-q')?.value || '').trim();
    if (!q) return;
    const refMatch = q.match(/^\s*((?:\d\s*)?[A-Za-z]+(?:\s+[A-Za-z]+)?)\s+(\d+)\s*:\s*(\d+)/i);
    if (refMatch) {
      currentBook = refMatch[1].replace(/\s+/g, ' ').trim();
      closeFlyouts();
      await prepareBook(currentBook, {
        chapter: parseInt(refMatch[2], 10),
        scrollToVerse: parseInt(refMatch[3], 10),
      });
      return;
    }
    const tr = translation();
    if (tr && (tr.startsWith('online:') || tr.startsWith('api:'))) {
      toast('Word search needs an installed translation. Try a reference like John 3:16.');
      return;
    }
    const content = main();
    content.innerHTML = '<p class="small text-muted">Searching…</p>';
    closeFlyouts();
    setMainView('search');
    const url = (urls.search || `${base}/search`) + `?q=${encodeURIComponent(q)}&limit=25` +
      (tr ? `&translation=${encodeURIComponent(tr)}` : '');
    const resp = await fetch(url);
    const data = await resp.json();
    if (!data.verses?.length) {
      content.innerHTML = '<p class="text-muted">No results.</p>';
      return;
    }
    content.innerHTML = data.verses.map((v) => `
      <div class="member-search-hit" data-book="${escapeAttr(v.book)}" data-chapter="${v.chapter}" data-verse="${v.verse}">
        <strong>${escapeHtml(v.reference)}</strong>
        <div class="small">${escapeHtml(v.text || '')}</div>
      </div>
    `).join('');
    content.querySelectorAll('.member-search-hit').forEach((item) => {
      item.addEventListener('click', () => {
        currentBook = item.dataset.book;
        prepareBook(currentBook, {
          chapter: parseInt(item.dataset.chapter, 10),
          scrollToVerse: parseInt(item.dataset.verse, 10),
        });
      });
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    renderBooks('NT');
    document.querySelectorAll('.member-bible-tabs button').forEach((tab) => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.member-bible-tabs button').forEach((t) => t.classList.remove('active'));
        tab.classList.add('active');
        renderBooks(tab.dataset.testament);
      });
    });

    el('member-open-canon')?.addEventListener('click', () => openFlyout('canon'));
    el('member-open-tools')?.addEventListener('click', () => {
      openFlyout('tools');
      if (isLoggedIn) {
        loadNotesLibrary();
        loadFavoritesLibrary();
      }
      fillStudyFocus();
    });
    el('member-mode-read')?.addEventListener('click', () => applyStudyMode(false));
    el('member-mode-study')?.addEventListener('click', () => applyStudyMode(true));
    el('member-woj-toggle')?.addEventListener('change', () => {
      const on = !!el('member-woj-toggle').checked;
      el('member-bible-stage')?.classList.toggle('hide-woj', !on);
      try { localStorage.setItem('member_bible_woj', on ? '1' : '0'); } catch (e) { /* ignore */ }
    });
    try {
      if (localStorage.getItem('member_bible_woj') === '0' && el('member-woj-toggle')) {
        el('member-woj-toggle').checked = false;
        el('member-bible-stage')?.classList.add('hide-woj');
      }
    } catch (e) { /* ignore */ }
    el('member-compare-translation')?.addEventListener('change', () => {
      try { localStorage.setItem('member_bible_compare', el('member-compare-translation').value || ''); } catch (e) { /* ignore */ }
      loadCompareChapter();
    });
    window.addEventListener('resize', () => applyStudyMode(studyModeWanted));
    el('member-bible-backdrop')?.addEventListener('click', closeFlyouts);
    document.querySelectorAll('.bible-flyout-close').forEach((b) => b.addEventListener('click', closeFlyouts));
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeXrefPopup();
        el('member-strongs-popup')?.classList.remove('open');
        closeFlyouts();
        closeNoteModal();
        setNotesPanelOpen(false);
      }
    });
    document.addEventListener('click', (e) => {
      if (!notesPanelOpen) return;
      const panel = el('member-notes-panel');
      if (panel && !panel.contains(e.target) && !e.target.closest('.member-note-modal')) {
        setNotesPanelOpen(false);
      }
    });

    el('member-nav-mode-chapter')?.addEventListener('click', () => setPickerMode('chapter'));
    el('member-nav-mode-verse')?.addEventListener('click', () => setPickerMode('verse'));
    el('member-bible-chapter')?.addEventListener('change', () => {
      const ch = parseInt(el('member-bible-chapter').value, 10);
      if (ch) loadChapter(ch, { scrollToVerse: 1 });
    });
    el('member-bible-prev')?.addEventListener('click', () => {
      closeFlyouts();
      loadChapter(currentChapter - 1, { scrollToVerse: 1 });
    });
    el('member-bible-next')?.addEventListener('click', () => {
      closeFlyouts();
      loadChapter(currentChapter + 1, { scrollToVerse: 1 });
    });
    el('member-bible-back')?.addEventListener('click', restoreChapter);
    el('member-bible-translation')?.addEventListener('change', (e) => switchTranslationSeamless(e.target));
    el('member-translation-toolbar')?.addEventListener('change', (e) => switchTranslationSeamless(e.target));

    el('member-bible-search-btn')?.addEventListener('click', searchBible);
    el('member-bible-search-q')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') searchBible(); });
    el('member-strongs-btn')?.addEventListener('click', () => {
      const q = el('member-strongs-q')?.value?.trim();
      if (q) showStrongs(q.toUpperCase());
    });

    el('member-hl-btn')?.addEventListener('click', applyHighlight);
    el('member-hl-clear')?.addEventListener('click', clearHighlight);
    el('member-fav-verse')?.addEventListener('click', () => {
      const v = Array.from(selectedVerses)[0];
      if (!v) return toast('Select a verse first');
      const line = main()?.querySelector(`.member-bible-verse[data-verse="${v}"]`);
      toggleFavorite('verse', { verse: v, text: line?.dataset.text || '' });
    });
    el('member-fav-chapter')?.addEventListener('click', () => toggleFavorite('chapter'));
    el('member-fav-book')?.addEventListener('click', () => toggleFavorite('book'));
    el('member-note-btn')?.addEventListener('click', () => openNoteModal({ scope: 'verse' }));
    el('member-note-chapter')?.addEventListener('click', () => openNoteModal({ scope: 'chapter' }));
    el('member-note-book')?.addEventListener('click', () => openNoteModal({ scope: 'book' }));
    el('member-note-cancel')?.addEventListener('click', closeNoteModal);
    el('member-note-save')?.addEventListener('click', saveNoteFromModal);
    el('member-note-new')?.addEventListener('click', startNewNoteFromModal);
    el('member-note-include-verse')?.addEventListener('change', syncNoteScriptureVisibility);
    el('member-note-modal')?.addEventListener('click', (e) => {
      if (e.target === el('member-note-modal')) closeNoteModal();
    });
    el('member-note-scope')?.addEventListener('change', () => {
      const scope = el('member-note-scope')?.value;
      const ref = el('member-note-ref');
      const include = el('member-note-include-verse');
      if (!ref) return;
      if (scope === 'book') {
        ref.textContent = `${currentBook} (whole book)`;
        if (include) include.checked = false;
      } else if (scope === 'chapter') {
        ref.textContent = `${currentBook} ${currentChapter}`;
        if (include) include.checked = false;
      } else {
        const bundle = selectedScripture();
        if (bundle) {
          ref.textContent = bundle.reference;
          ref.dataset.vStart = String(bundle.verse_start);
          ref.dataset.vEnd = String(bundle.verse_end);
          if (el('member-note-scripture') && !el('member-note-scripture').value) {
            el('member-note-scripture').value = bundle.scripture_text || '';
          }
          if (include) include.checked = !!bundle.scripture_text;
        }
      }
      syncNoteScriptureVisibility();
    });
    // Remember default highlight color in this browser
    el('member-hl-color')?.addEventListener('change', () => {
      try {
        localStorage.setItem('member_bible_hl_color', el('member-hl-color').value);
      } catch (e) { /* ignore */ }
    });
    try {
      const savedColor = localStorage.getItem('member_bible_hl_color');
      if (savedColor && el('member-hl-color')) el('member-hl-color').value = savedColor;
    } catch (e) { /* ignore */ }

    el('member-notes-toggle')?.addEventListener('click', (e) => {
      e.stopPropagation();
      setNotesPanelOpen(!notesPanelOpen);
    });
    el('member-open-notes-lib')?.addEventListener('click', () => {
      setNotesPanelOpen(false);
      openFlyout('tools');
      loadNotesLibrary();
    });
    el('member-open-favs-lib')?.addEventListener('click', () => {
      setNotesPanelOpen(false);
      openFlyout('tools');
      loadFavoritesLibrary();
    });
    document.querySelectorAll('[data-notes-tab]').forEach((btn) => {
      btn.addEventListener('click', () => {
        setNotesPanelOpen(true);
        setNotesPanelTab(btn.dataset.notesTab);
      });
    });
    el('member-notes-search-btn')?.addEventListener('click', loadNotesLibrary);
    el('member-notes-q')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') loadNotesLibrary(); });
    el('member-notes-scope')?.addEventListener('change', loadNotesLibrary);
    el('member-favs-scope')?.addEventListener('change', loadFavoritesLibrary);
    el('member-notes-download')?.addEventListener('click', () => {
      const q = el('member-notes-q')?.value || '';
      const scope = el('member-notes-scope')?.value || '';
      const params = new URLSearchParams();
      if (q) params.set('q', q);
      if (scope) params.set('scope', scope);
      window.location.href = (urls.notesDownload || `${base}/notes/download`) + '?' + params.toString();
    });

    // Logged-in: server place wins, then local. Guests: this browser's last chapter.
    let want = cfg.selectedTranslation || cfg.userPreferred || null;
    let resumeBook = cfg.lastBook || null;
    let resumeChapter = cfg.lastChapter || null;
    let resumeVerse = cfg.lastVerse || null;
    try {
      want = want || localStorage.getItem('member_bible_translation');
      const raw = localStorage.getItem('member_bible_place');
      if (raw) {
        const p = JSON.parse(raw);
        if (!want && p.translation) want = p.translation;
        if (!isLoggedIn || !resumeBook) {
          if (p.book) resumeBook = p.book;
          if (p.chapter) resumeChapter = p.chapter;
          if (p.verse) resumeVerse = p.verse;
        }
      }
      const savedCompare = localStorage.getItem('member_bible_compare') || '';
      if (savedCompare && el('member-compare-translation')) {
        el('member-compare-translation').value = savedCompare;
        compareTranslation = savedCompare;
      }
    } catch (e) { /* ignore */ }
    if (!isLoggedIn && !resumeBook) {
      resumeBook = cfg.lastBook || 'John';
      resumeChapter = cfg.lastChapter || 1;
      resumeVerse = cfg.lastVerse || 1;
    }
    if (want) {
      const candidates = [want, `online:${want}`, String(want).replace(/^online:/, '')];
      const pick = candidates.find((c) =>
        Array.from(el('member-bible-translation')?.options || []).some((o) => o.value === c)
        || Array.from(el('member-translation-toolbar')?.options || []).some((o) => o.value === c)
      );
      if (pick) setTranslationValue(pick);
      else setTranslationValue(want);
      if (isLoggedIn) updateDefaultBadge(pick || want);
    }

    el('member-save-my-bible')?.addEventListener('click', async () => {
      if (!requireLogin('a saved Bible version')) return;
      const val = translation();
      if (!val) return toast('Pick a Bible version first');
      const data = await savePreferredTranslation(val);
      if (data && data.ok) toast(data.message || 'Saved as your study Bible');
    });

    // Open notes/favs libraries: login required
    const openNotesLib = el('member-open-notes-lib');
    if (openNotesLib && !isLoggedIn) {
      openNotesLib.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopImmediatePropagation();
        requireLogin('your notes library');
      }, true);
    }
    const openFavsLib = el('member-open-favs-lib');
    if (openFavsLib && !isLoggedIn) {
      openFavsLib.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopImmediatePropagation();
        requireLogin('favorites');
      }, true);
    }

    let wantStudy = true;
    try {
      const savedMode = localStorage.getItem('member_bible_mode');
      if (savedMode === 'read') wantStudy = false;
    } catch (e) { /* ignore */ }
    applyStudyMode(wantStudy);

    // Resume last place (version already applied above)
    if (books.length) {
      const startBook = resumeBook || currentBook || 'John';
      const startCh = parseInt(resumeChapter, 10) || 1;
      const startV = parseInt(resumeVerse, 10) || 1;
      currentBook = startBook;
      prepareBook(startBook, { chapter: startCh, scrollToVerse: startV });
    }
  });
})();
