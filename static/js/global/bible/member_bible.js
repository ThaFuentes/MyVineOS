// Member Bible Study — online reading, multi-color highlights, favorites
// (verse / chapter / book), notes with scopes, searchable libraries.
(function () {
  const cfg = window.MEMBER_BIBLE || {};
  const books = cfg.books || [];
  const urls = cfg.urls || {};

  let currentBook = 'John';
  let currentChapter = 1;
  let maxChapter = 0;
  let mainView = 'chapter';
  let lastChapterHtml = '';
  let annotationKey = null;
  let chapterData = null;
  let selectedVerses = new Set();
  let favoriteVerses = new Set();
  let favChapter = false;
  let favBook = false;

  const el = (id) => document.getElementById(id);
  const base = '/bible';
  const main = () => el('member-bible-content');

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
    }
    backdrop?.classList.add('open');
    backdrop?.setAttribute('aria-hidden', 'false');
  }

  function closeFlyouts() {
    el('member-canon-flyout')?.classList.remove('open');
    el('member-tools-flyout')?.classList.remove('open');
    el('member-bible-backdrop')?.classList.remove('open');
    el('member-open-canon')?.classList.remove('active');
    el('member-open-tools')?.classList.remove('active');
    el('member-canon-flyout')?.setAttribute('aria-hidden', 'true');
    el('member-tools-flyout')?.setAttribute('aria-hidden', 'true');
    el('member-bible-backdrop')?.setAttribute('aria-hidden', 'true');
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
        scrollToChapterSection();
        prepareBook(currentBook);
      });
      list.appendChild(btn);
    });
  }

  function populateChapters(max) {
    const sel = el('member-bible-chapter');
    if (!sel) return;
    sel.innerHTML = '';
    for (let i = 1; i <= Math.max(1, max); i++) {
      const o = document.createElement('option');
      o.value = String(i);
      o.textContent = String(i);
      sel.appendChild(o);
    }
  }

  function renderVersePicker(verses) {
    const picker = el('member-bible-verse-picker');
    if (!picker) return;
    picker.innerHTML = '';
    (verses || []).forEach((v) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = String(v.verse);
      b.addEventListener('click', () => {
        if (mainView !== 'chapter') restoreChapter();
        scrollToVerse(v.verse);
        closeFlyouts();
      });
      picker.appendChild(b);
    });
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

  async function switchTranslationSeamless(fromControl) {
    const val = fromControl?.value || translation();
    setTranslationValue(val);
    const anchor = getVisibleVerseAnchor();
    await prepareBook(currentBook, {
      chapter: currentChapter || 1,
      scrollToVerse: anchor,
    });
    toast(anchor
      ? `Switched · stayed at ${currentBook} ${currentChapter}:${anchor}`
      : `Switched · stayed at ${currentBook} ${currentChapter}`);
  }

  async function loadChapter(chapter, opts = {}) {
    const tr = translation();
    if (maxChapter > 0) chapter = Math.max(1, Math.min(chapter, maxChapter));
    currentChapter = chapter;
    selectedVerses = new Set();
    updateSelectionBar();
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
      renderVersePicker(data.verses);
      renderChapter(data);
      renderNotesPanel(data.notes || []);
      updateNav();
      if (opts.scrollToVerse) {
        requestAnimationFrame(() => scrollToVerse(opts.scrollToVerse));
      }
    } catch (e) {
      if (main()) main().innerHTML = '<p class="text-muted">Chapter not found.</p>';
      renderVersePicker([]);
      renderNotesPanel([]);
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
        html += `<button type="button" class="member-xref-link messianic" data-book="${escapeAttr(r.book)}" data-chapter="${r.chapter}" data-verse="${r.verse}" title="${escapeAttr(r.label || r.reference)}">${escapeHtml(r.reference)}</button> `;
      });
      html += '</div>';
    }
    if (related.length) {
      html += '<div class="member-xref-row"><span class="member-xref-label">See also</span> ';
      related.forEach((r) => {
        html += `<button type="button" class="member-xref-link" data-book="${escapeAttr(r.book)}" data-chapter="${r.chapter}" data-verse="${r.verse}">${escapeHtml(r.reference)}</button> `;
      });
      html += '</div>';
    }
    html += '</div>';
    return html;
  }

  function renderChapter(data) {
    const content = main();
    if (!content) return;
    const highlights = data.highlights || [];
    const crossRefs = data.cross_refs || {};
    let html = '';
    (data.verses || []).forEach((v) => {
      const ref = `${data.book} ${data.chapter}:${v.verse}`;
      const strongs = (data.strongs && data.strongs[v.verse]) || [];
      const hl = highlightClass(v.verse, highlights);
      const isFav = favoriteVerses.has(v.verse);
      html += `<div class="member-bible-verse${hl}${isFav ? ' is-favorite' : ''}" data-verse="${v.verse}" data-text="${escapeAttr(v.text)}">`;
      html += `<span class="member-bible-verse-num">${v.verse}</span>`;
      html += `<button type="button" class="member-verse-heart${isFav ? ' on' : ''}" data-heart-verse="${v.verse}" title="Favorite verse" aria-label="Favorite">${isFav ? '♥' : '♡'}</button>`;
      html += `<span class="member-bible-verse-text">${linkStrongs(v.text, strongs)}</span>`;
      html += xrefHtml(v.verse, crossRefs);
      // One Highlight button uses the default color from the top toolbar
      html += `<div class="member-verse-actions">
        <button type="button" class="btn btn-warning btn-sm" data-hl-verse="${v.verse}" title="Highlight with your default color">Highlight</button>
        <button type="button" class="btn btn-secondary btn-sm" data-hl-clear-verse="${v.verse}" title="Clear highlight">Clear</button>
        <button type="button" class="btn btn-secondary btn-sm" data-copy="${escapeAttr(ref)}" data-copy-text="${escapeAttr(v.text)}">Copy</button>
        <button type="button" class="btn btn-secondary btn-sm" data-note-verse="${v.verse}">Note</button>
      </div>`;
      html += '</div>';
    });
    content.innerHTML = html || '<p class="text-muted">Empty chapter.</p>';
    lastChapterHtml = content.innerHTML;
    setMainView('chapter');
    bindMainChapterEvents();
  }

  function linkStrongs(text, strongsList) {
    if (!strongsList?.length) return escapeHtml(text);
    let result = escapeHtml(text);
    strongsList.forEach((s) => {
      if (!s.surface_word) return;
      const re = new RegExp(`\\b(${escapeRegex(s.surface_word)})\\b`, 'i');
      result = result.replace(re, (m) =>
        `<span class="member-bible-strongs-word" data-strongs="${s.strongs_number}" title="${s.strongs_number}">${m}</span>`
      );
    });
    return result;
  }

  function updateSelectionBar() {
    const bar = el('member-selection-bar');
    const label = el('member-selection-label');
    if (!bar) return;
    if (!selectedVerses.size) {
      bar.style.display = 'none';
      return;
    }
    bar.style.display = '';
    const nums = Array.from(selectedVerses).sort((a, b) => a - b);
    if (label) {
      label.textContent = nums.length === 1
        ? `${currentBook} ${currentChapter}:${nums[0]}`
        : `${currentBook} ${currentChapter}:${nums[0]}–${nums[nums.length - 1]} (${nums.length} verses)`;
    }
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
    content.querySelectorAll('.member-bible-strongs-word').forEach((node) => {
      node.addEventListener('click', (e) => {
        e.stopPropagation();
        showStrongs(node.dataset.strongs);
      });
    });
    content.querySelectorAll('.member-xref-link').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        currentBook = btn.dataset.book;
        prepareBook(currentBook, {
          chapter: parseInt(btn.dataset.chapter, 10),
          scrollToVerse: parseInt(btn.dataset.verse, 10) || 1,
        });
        closeFlyouts();
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
        openNoteModal({ scope: 'verse' });
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
          || e.target.closest('.member-hl-swatches')
          || e.target.closest('.member-xrefs')
          || e.target.closest('.member-bible-strongs-word')) return;
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
          if (selectedVerses.size === 1 && selectedVerses.has(v)) selectedVerses.clear();
          else {
            selectedVerses.clear();
            selectedVerses.add(v);
          }
        }
        content.querySelectorAll('.member-bible-verse').forEach((l) => {
          l.classList.toggle('verse-selected', selectedVerses.has(parseInt(l.dataset.verse, 10)));
        });
        updateSelectionBar();
      });
    });
  }

  function scrollToVerse(n) {
    el('member-bible-verse-picker')?.querySelectorAll('button').forEach((b) => {
      b.classList.toggle('active', parseInt(b.textContent, 10) === n);
    });
    main()?.querySelectorAll('.member-bible-verse').forEach((l) => l.classList.remove('highlight'));
    const line = main()?.querySelector(`.member-bible-verse[data-verse="${n}"]`);
    if (line) {
      line.classList.add('highlight');
      line.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
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

  function openNoteModal(opts = {}) {
    const scope = opts.scope || 'verse';
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

    if (scopeSel) scopeSel.value = scope;
    if (ref) {
      ref.textContent = bundle.reference;
      ref.dataset.vStart = String(bundle.verse_start || 0);
      ref.dataset.vEnd = String(bundle.verse_end || 0);
      ref.dataset.editId = opts.editId ? String(opts.editId) : '';
      ref.dataset.scripture = bundle.scripture_text || '';
    }
    if (title) title.value = opts.title || bundle.reference || '';
    if (scripture) scripture.value = opts.scripture_text || bundle.scripture_text || '';
    if (body) body.value = opts.body || '';
    if (tags) tags.value = opts.tags || '';
    // Include verse text by default when we have scripture for a verse note
    if (include) {
      include.checked = scope === 'verse'
        ? !!(opts.scripture_text || bundle.scripture_text)
        : false;
    }
    syncNoteScriptureVisibility();

    if (modal) {
      modal.style.display = 'flex';
      modal.setAttribute('aria-hidden', 'false');
    }
    body?.focus();
  }

  function closeNoteModal() {
    const modal = el('member-note-modal');
    if (modal) {
      modal.style.display = 'none';
      modal.setAttribute('aria-hidden', 'true');
    }
  }

  async function saveNoteFromModal() {
    const ref = el('member-note-ref');
    const scope = el('member-note-scope')?.value || 'verse';
    const body = (el('member-note-body')?.value || '').trim();
    if (!body) return toast('Write a note first');
    try {
      if (!csrfToken()) throw new Error('Security token missing — refresh the page');
      const includeVerse = el('member-note-include-verse')?.checked;
      const scriptureRaw = (el('member-note-scripture')?.value || '').trim();
      const data = await apiPost(urls.note || `${base}/note`, {
        id: ref?.dataset.editId ? parseInt(ref.dataset.editId, 10) : undefined,
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
      toast('Note saved');
      closeNoteModal();
      loadChapter(currentChapter);
    } catch (e) {
      toast(e.message || 'Could not save note');
    }
  }

  function renderNotesPanel(notes) {
    const list = el('member-notes-list');
    if (!list) return;
    if (!notes?.length) {
      list.innerHTML = '<p class="member-notes-empty">No notes yet. Tap a verse → <strong>Note</strong>, or use <strong>Note chapter</strong> / <strong>Note book</strong>.</p>';
      return;
    }
    list.innerHTML = notes.map((n) => {
      const scopeBadge = n.scope && n.scope !== 'verse'
        ? `<span class="member-scope-badge">${escapeHtml(n.scope)}</span>`
        : '<span class="member-scope-badge verse">verse</span>';
      return `<article class="member-note-card">
        <header class="member-note-card-head">
          <h4 class="member-note-card-title">${escapeHtml(n.display_title || n.title || n.reference)}</h4>
          ${scopeBadge}
        </header>
        <div class="member-note-card-meta">${escapeHtml(n.reference || '')}${n.tags ? ' · ' + escapeHtml(n.tags) : ''}</div>
        ${n.scripture_text ? `<blockquote class="member-note-scripture">${escapeHtml(n.scripture_text)}</blockquote>` : ''}
        <div class="member-note-body">${escapeHtml(n.body || '')}</div>
        <footer class="member-note-card-actions">
          <a class="btn btn-sm btn-secondary" href="${base}/note/${n.id}/download">Download</a>
          <button type="button" class="btn btn-sm btn-secondary" data-del-note="${n.id}">Delete</button>
        </footer>
      </article>`;
    }).join('');
    list.querySelectorAll('[data-del-note]').forEach((btn) => {
      btn.addEventListener('click', async () => {
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
          } else toast(data.error || 'Could not delete');
        } catch (e) {
          toast('Could not delete note');
        }
      });
    });
  }

  async function loadNotesLibrary() {
    const box = el('member-notes-lib');
    if (!box) return;
    const q = el('member-notes-q')?.value || '';
    const scope = el('member-notes-scope')?.value || '';
    box.innerHTML = '<p class="small text-muted">Loading…</p>';
    try {
      const params = new URLSearchParams({ q, limit: '50' });
      if (scope) params.set('scope', scope);
      const resp = await fetch((urls.notes || `${base}/notes`) + '?' + params.toString());
      const data = await resp.json();
      const rows = data.notes || [];
      if (!rows.length) {
        box.innerHTML = '<p class="small text-muted">No notes found.</p>';
        return;
      }
      box.innerHTML = rows.map((n) => `
        <div class="member-lib-item">
          <div class="small fw-semibold">${escapeHtml(n.display_title || n.title)}</div>
          <div class="small text-muted">${escapeHtml(n.reference || '')}${n.scope && n.scope !== 'verse' ? ' · ' + n.scope : ''}</div>
          <div class="small" style="max-height:2.8em;overflow:hidden;">${escapeHtml((n.body || '').slice(0, 140))}</div>
          <button type="button" class="btn btn-sm btn-secondary mt-1" data-goto-note="${escapeAttr(n.book)}|${n.chapter || 1}|${n.verse_start || 1}">Open</button>
          <a class="btn btn-sm btn-secondary mt-1" href="${base}/note/${n.id}/download">Download</a>
        </div>
      `).join('');
      box.querySelectorAll('[data-goto-note]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const [book, ch, v] = btn.dataset.gotoNote.split('|');
          currentBook = book;
          closeFlyouts();
          prepareBook(book, { chapter: parseInt(ch, 10) || 1, scrollToVerse: parseInt(v, 10) || 1 });
        });
      });
    } catch (e) {
      box.innerHTML = '<p class="small text-warning">Could not load notes.</p>';
    }
  }

  async function loadFavoritesLibrary() {
    const box = el('member-favs-lib');
    if (!box) return;
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

  async function showStrongs(number) {
    const content = main();
    if (!content) return;
    content.innerHTML = '<p class="small text-muted">Loading Strong\'s…</p>';
    closeFlyouts();
    setMainView('strongs');
    if (el('member-bible-title')) el('member-bible-title').textContent = `Strong's ${number}`;
    try {
      const resp = await fetch(`${base}/strongs/${encodeURIComponent(number)}`);
      if (!resp.ok) throw new Error('missing');
      const data = await resp.json();
      let html = `<h3>${escapeHtml(data.number)}</h3>`;
      html += `<p><em>${escapeHtml(data.transliteration || '')}</em> (${escapeHtml(data.language || '')})</p>`;
      html += `<p>${escapeHtml(data.definition || '')}</p>`;
      content.innerHTML = html;
    } catch (e) {
      content.innerHTML = '<p class="text-muted">Strong\'s entry not found.</p>';
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
      loadNotesLibrary();
      loadFavoritesLibrary();
    });
    el('member-bible-backdrop')?.addEventListener('click', closeFlyouts);
    document.querySelectorAll('.bible-flyout-close').forEach((b) => b.addEventListener('click', closeFlyouts));
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeFlyouts();
        closeNoteModal();
      }
    });

    el('member-bible-chapter')?.addEventListener('change', () => {
      const ch = parseInt(el('member-bible-chapter').value, 10);
      if (ch) loadChapter(ch);
    });
    el('member-bible-prev')?.addEventListener('click', () => { closeFlyouts(); loadChapter(currentChapter - 1); });
    el('member-bible-next')?.addEventListener('click', () => { closeFlyouts(); loadChapter(currentChapter + 1); });
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

    el('member-open-notes-lib')?.addEventListener('click', () => {
      openFlyout('tools');
      loadNotesLibrary();
    });
    el('member-open-favs-lib')?.addEventListener('click', () => {
      openFlyout('tools');
      loadFavoritesLibrary();
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

    if (cfg.selectedTranslation) {
      const want = cfg.selectedTranslation;
      const candidates = [want, `online:${want}`];
      const pick = candidates.find((c) =>
        Array.from(el('member-bible-translation')?.options || []).some((o) => o.value === c)
        || Array.from(el('member-translation-toolbar')?.options || []).some((o) => o.value === c)
      );
      if (pick) setTranslationValue(pick);
    }

    if (books.length) prepareBook(currentBook);
  });
})();
