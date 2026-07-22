(function () {
  const cfg = window.BIBLE_STUDY || {};
  const books = cfg.books || [];
  const urls = cfg.urls || {};

  let currentBook = 'John';
  let currentChapter = 1;
  let currentTranslation = null;
  let maxChapter = 0;
  let mainView = 'chapter';
  let lastChapterHtml = '';
  let activeSermonId = cfg.sermonId || null;
  let annotationKey = null;
  let chapterData = null;
  let currentNotes = [];
  let allNotesCache = [];
  let notesPanelTab = 'passage'; // 'passage' | 'all'
  let selectedVerses = new Set();
  let lastSource = null;
  let chapterPage = 0;
  const CHAPTERS_PER_PAGE = 20;

  const el = (id) => document.getElementById(id);
  const main = () => el('bible-reader-content');
  const api = '/pastoral/bible';

  function csrfToken() {
    if (cfg.csrf) return cfg.csrf;
    const m = document.querySelector('meta[name="csrf-token"]');
    if (m && m.content) return m.content;
    const i = document.querySelector('input[name="csrf_token"]');
    return i ? i.value : '';
  }

  function getTranslation() {
    return el('bible-translation-toolbar')?.value
      || el('bible-translation')?.value
      || cfg.selectedTranslation
      || null;
  }

  function setTranslationValue(val) {
    if (!val) return;
    const a = el('bible-translation');
    const b = el('bible-translation-toolbar');
    if (a) {
      if (!Array.from(a.options).some((o) => o.value === val)) {
        const opt = document.createElement('option');
        opt.value = val;
        opt.textContent = val.replace(/^online:/, '') + ' · online';
        a.appendChild(opt);
      }
      a.value = val;
    }
    if (b) {
      if (!Array.from(b.options).some((o) => o.value === val)) {
        const opt = document.createElement('option');
        opt.value = val;
        opt.textContent = (val.split(':').pop() || val);
        b.appendChild(opt);
      }
      b.value = val;
    }
  }

  function isOnlineTranslation(val) {
    const v = val || getTranslation() || '';
    return String(v).startsWith('online:') || String(v).startsWith('api:');
  }

  function getActiveSermonId() {
    const v = el('bible-sermon-select')?.value;
    return v ? parseInt(v, 10) : null;
  }

  function sermonEditUrl(sermonId) {
    const sid = sermonId || getActiveSermonId();
    if (!sid) return '#';
    const template = urls.sermonEdit || '/pastoral/sermons/edit/0';
    // Support both …/edit/0 and …/0/edit templates
    if (template.includes('/0')) return template.replace('/0', `/${sid}`);
    return template.replace(/\/\d+(\/?)$/, `/${sid}$1`);
  }

  function updateSermonBar() {
    activeSermonId = getActiveSermonId();
    const openBtn = el('bible-open-sermon-btn');
    const openTabBtn = el('bible-open-sermon-tab-btn');
    const url = sermonEditUrl(activeSermonId);
    [openBtn, openTabBtn].forEach((btn) => {
      if (!btn) return;
      if (activeSermonId) {
        btn.href = url;
        btn.classList.remove('disabled');
        btn.removeAttribute('aria-disabled');
      } else {
        btn.href = '#';
        btn.classList.add('disabled');
        btn.setAttribute('aria-disabled', 'true');
      }
    });
    if (activeSermonId) sessionStorage.setItem('bible_active_sermon', String(activeSermonId));
  }

  function toast(msg) {
    const t = el('bible-toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => t.classList.remove('show'), 2200);
  }

  function setMainView(view) {
    mainView = view;
    const back = el('bible-back-chapter');
    if (back) back.style.display = view === 'chapter' ? 'none' : 'inline-block';
  }

  function openFlyout(which) {
    const canon = el('bible-canon-flyout');
    const tools = el('bible-tools-flyout');
    const backdrop = el('bible-flyout-backdrop');
    if (which === 'canon') {
      tools?.classList.remove('open');
      el('bible-open-tools')?.classList.remove('active');
      canon?.classList.add('open');
      el('bible-open-canon')?.classList.add('active');
    } else {
      canon?.classList.remove('open');
      el('bible-open-canon')?.classList.remove('active');
      tools?.classList.add('open');
      el('bible-open-tools')?.classList.add('active');
      loadNotesLibrary(el('bible-notes-lib-q')?.value || '');
    }
    backdrop?.classList.add('open');
  }

  function scrollToChapterSection() {
    const section = el('bible-chapter-section');
    if (!section) return;
    requestAnimationFrame(() => {
      section.scrollIntoView({ behavior: 'smooth', block: 'start' });
      section.classList.remove('bible-anchor-flash');
      void section.offsetWidth;
      section.classList.add('bible-anchor-flash');
      setTimeout(() => section.classList.remove('bible-anchor-flash'), 900);
    });
  }

  function closeFlyouts() {
    el('bible-canon-flyout')?.classList.remove('open');
    el('bible-tools-flyout')?.classList.remove('open');
    el('bible-flyout-backdrop')?.classList.remove('open');
    el('bible-open-canon')?.classList.remove('active');
    el('bible-open-tools')?.classList.remove('active');
  }

  function activeSermonTitle() {
    const sel = el('bible-sermon-select');
    if (!sel || !sel.value) return null;
    const opt = sel.options[sel.selectedIndex];
    return (opt && opt.textContent) ? opt.textContent.trim() : `Sermon #${sel.value}`;
  }

  function actionButtonsHtml(opts) {
    const ref = escapeAttr(opts.reference || '');
    const text = escapeAttr(opts.text || '');
    const book = escapeAttr(opts.book || '');
    const noteLabel = opts.hasNote ? 'Edit note' : 'Note';
    return `
      <div class="content-actions">
        <button type="button" class="btn btn-outline-secondary btn-sm" data-act="copy"
          data-ref="${ref}" data-text="${text}"
          title="Copy this verse reference and text to the clipboard">Copy</button>
        <button type="button" class="btn btn-outline-cyan btn-sm" data-act="note"
          data-ref="${ref}" data-text="${text}" data-book="${book}"
          data-chapter="${opts.chapter || ''}" data-verse="${opts.verse || ''}"
          title="Open a study note with this verse filled in">${noteLabel}</button>
        <button type="button" class="btn btn-cyan btn-sm" data-act="sermon"
          data-ref="${ref}" data-text="${text}" data-book="${book}"
          data-chapter="${opts.chapter || ''}" data-verse="${opts.verse || ''}"
          title="Insert this verse into the sermon selected in the bar above">+ Sermon</button>
        <button type="button" class="btn btn-outline-cyan btn-sm" data-act="illustration"
          data-ref="${ref}" data-text="${text}" data-book="${book}"
          data-chapter="${opts.chapter || ''}" data-verse="${opts.verse || ''}"
          data-strongs="${escapeAttr(opts.strongs || '')}"
          title="Save this verse to your Illustration Library (reusable in any sermon)">+ Library</button>
      </div>`;
  }

  function bindActionButtons(root) {
    if (!root) return;
    root.querySelectorAll('[data-act="copy"]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const payload = btn.dataset.ref && btn.dataset.text
          ? `${btn.dataset.ref}\n${btn.dataset.text}` : (btn.dataset.text || btn.dataset.ref || '');
        navigator.clipboard.writeText(payload).then(() => toast('Copied verse to clipboard'));
      });
    });
    root.querySelectorAll('[data-act="note"]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        // Select this verse so the note modal has range metadata
        const v = parseInt(btn.dataset.verse, 10);
        if (v) {
          selectedVerses.clear();
          selectedVerses.add(v);
          main()?.querySelectorAll('.bible-verse-line').forEach((l) => {
            l.classList.toggle('verse-selected', selectedVerses.has(parseInt(l.dataset.verse, 10)));
          });
          updateSelectionBar();
        }
        // Loads previous note for this verse when one exists (edit / add to it)
        openNoteModal({
          verse_start: v || 1,
          verse_end: v || 1,
          reference: btn.dataset.ref || '',
          scripture_text: btn.dataset.text || '',
          title: btn.dataset.ref || '',
        });
      });
    });
    root.querySelectorAll('[data-open-note-verse]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const v = parseInt(btn.dataset.openNoteVerse, 10);
        if (v) {
          selectedVerses.clear();
          selectedVerses.add(v);
          main()?.querySelectorAll('.bible-verse-line').forEach((l) => {
            l.classList.toggle('verse-selected', selectedVerses.has(parseInt(l.dataset.verse, 10)));
          });
          updateSelectionBar();
        }
        openNoteModal({
          verse_start: v || 1,
          verse_end: v || 1,
          reference: `${currentBook} ${currentChapter}:${v}`,
          scripture_text: btn.closest('.bible-verse-line')?.dataset.text || '',
          title: `${currentBook} ${currentChapter}:${v}`,
        });
      });
    });
    root.querySelectorAll('[data-act="sermon"]').forEach((btn) => {
      btn.addEventListener('click', (e) => { e.stopPropagation(); insertToSermon(btn); });
    });
    root.querySelectorAll('[data-act="illustration"]').forEach((btn) => {
      btn.addEventListener('click', (e) => { e.stopPropagation(); saveIllustration(btn); });
    });
  }

  function setSermonHint(message, isSuccess) {
    const hint = el('bible-sermon-hint');
    if (!hint) return;
    hint.innerHTML = message;
    hint.classList.toggle('bible-sermon-hint-ok', !!isSuccess);
    if (isSuccess) {
      clearTimeout(setSermonHint._t);
      setSermonHint._t = setTimeout(() => {
        const title = activeSermonTitle();
        const sid = getActiveSermonId();
        hint.classList.remove('bible-sermon-hint-ok');
        if (sid && title) {
          hint.innerHTML = `Active sermon: <strong>${escapeHtml(title)}</strong>. Use <strong>+ Sermon</strong> on a verse or selection to insert.`;
        }
      }, 6000);
    }
  }

  async function insertToSermon(btn) {
    let sermonId = getActiveSermonId();
    if (!sermonId) {
      toast('Pick a sermon in the bar above first (or create one).');
      el('bible-sermon-select')?.focus();
      setSermonHint('No sermon selected — choose one above, then try again.', false);
      sermonId = await quickCreateSermon(btn.dataset.ref || 'Scripture');
      if (!sermonId) return;
    }
    const title = activeSermonTitle() || `Sermon #${sermonId}`;
    const label = btn.dataset.ref || 'verse';
    const prevLabel = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Adding…';
    try {
      const resp = await fetch(`${api}/insert/${sermonId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken(),
          Accept: 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'same-origin',
        body: JSON.stringify({
          reference: btn.dataset.ref,
          text: btn.dataset.text,
          book: btn.dataset.book,
          chapter: btn.dataset.chapter ? parseInt(btn.dataset.chapter, 10) : undefined,
          verse: btn.dataset.verse ? parseInt(btn.dataset.verse, 10) : undefined,
          translation: getTranslation(),
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (resp.ok && (data.status === 'success' || data.ok)) {
        const editUrl = data.edit_url || sermonEditUrl(sermonId);
        const sermonName = data.sermon_title || title;
        btn.textContent = 'Added ✓';
        toast(`Added ${label} → “${sermonName}”`);
        setSermonHint(
          `✓ Added <strong>${escapeHtml(label)}</strong> into <strong>${escapeHtml(sermonName)}</strong> `
          + `(section <em>Bible Study inserts</em>). `
          + `<a href="${editUrl}" id="bible-hint-open-same">Open sermon</a> · `
          + `<a href="${editUrl}" target="_blank" rel="noopener">New tab</a>`,
          true,
        );
        // Allow adding more verses from the same button after a short beat
        setTimeout(() => {
          btn.disabled = false;
          btn.textContent = prevLabel || '+ Sermon';
        }, 1200);
      } else {
        btn.disabled = false;
        btn.textContent = prevLabel || '+ Sermon';
        const msg = data.message || data.error || `Insert failed (${resp.status})`;
        toast(msg);
        setSermonHint(escapeHtml(msg), false);
      }
    } catch (err) {
      btn.disabled = false;
      btn.textContent = prevLabel || '+ Sermon';
      toast(err.message || 'Network error adding to sermon');
    }
  }

  async function saveIllustration(btn) {
    const resp = await fetch(urls.saveIllustration, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken(),
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({
        title: btn.dataset.ref || btn.dataset.strongs || 'Bible note',
        content: btn.dataset.text || '',
        source: getTranslation() || '',
        book: btn.dataset.book,
        chapter: btn.dataset.chapter ? parseInt(btn.dataset.chapter, 10) : undefined,
        verse: btn.dataset.verse ? parseInt(btn.dataset.verse, 10) : undefined,
        translation: getTranslation(),
        tags: btn.dataset.strongs ? 'bible,strongs' : 'bible,scripture',
      }),
    });
    const data = await resp.json().catch(() => ({}));
    if (data.status === 'success' || data.ok) {
      btn.textContent = 'In library ✓';
      btn.disabled = true;
      toast('Saved to Illustration Library (not a sermon)');
    } else toast(data.message || data.error || 'Could not save to library');
  }

  async function insertSelectionToSermon() {
    const bundle = selectedScriptureBundle() || chapterScriptureBundle();
    if (!bundle) return toast('Select one or more verses first (or use Copy chapter)');
    let sermonId = getActiveSermonId();
    if (!sermonId) {
      toast('Pick a sermon above first.');
      el('bible-sermon-select')?.focus();
      sermonId = await quickCreateSermon(bundle.reference || 'Scripture');
      if (!sermonId) return;
    }
    const title = activeSermonTitle() || `Sermon #${sermonId}`;
    try {
      const resp = await fetch(`${api}/insert/${sermonId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken(),
          Accept: 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'same-origin',
        body: JSON.stringify({
          reference: bundle.reference,
          text: bundle.scripture_text,
          book: currentBook,
          chapter: currentChapter,
          verse: bundle.verse_start,
          translation: getTranslation(),
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (resp.ok && (data.status === 'success' || data.ok)) {
        const editUrl = data.edit_url || sermonEditUrl(sermonId);
        const sermonName = data.sermon_title || title;
        toast(`Added ${bundle.reference} → “${sermonName}”`);
        setSermonHint(
          `✓ Added <strong>${escapeHtml(bundle.reference)}</strong> into <strong>${escapeHtml(sermonName)}</strong>. `
          + `<a href="${editUrl}">Open sermon</a> · `
          + `<a href="${editUrl}" target="_blank" rel="noopener">New tab</a>`,
          true,
        );
      } else toast(data.message || data.error || `Could not insert selection (${resp.status})`);
    } catch (err) {
      toast(err.message || 'Network error');
    }
  }

  function chapterScriptureBundle() {
    const lines = main()?.querySelectorAll('.bible-verse-line');
    if (!lines || !lines.length) return null;
    const texts = [];
    let first = null;
    let last = null;
    lines.forEach((line) => {
      const v = parseInt(line.dataset.verse, 10);
      if (!v) return;
      if (first == null) first = v;
      last = v;
      const t = line.dataset.text || line.querySelector('.bible-verse-text')?.textContent || '';
      if (t) texts.push(`${v} ${t.trim()}`);
    });
    if (first == null) return null;
    return {
      verse_start: first,
      verse_end: last,
      reference: first === last
        ? `${currentBook} ${currentChapter}:${first}`
        : `${currentBook} ${currentChapter}:${first}-${last}`,
      scripture_text: texts.join('\n'),
    };
  }

  function copyBundle(bundle, label) {
    if (!bundle) return toast('Nothing to copy');
    const payload = `${bundle.reference}\n${bundle.scripture_text || ''}`.trim();
    navigator.clipboard.writeText(payload).then(() => toast(label || 'Copied'));
  }

  async function quickCreateSermon(reference) {
    const title = reference ? `Sermon — ${reference}` : 'New Sermon from Bible Study';
    if (!confirm(`Create "${title}" and use it?`)) return null;
    const resp = await fetch(urls.quickSermon, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, reference }),
    });
    const data = await resp.json();
    if (data.status === 'success') {
      const sel = el('bible-sermon-select');
      if (sel) {
        const opt = document.createElement('option');
        opt.value = data.sermon_id;
        opt.textContent = data.title;
        opt.selected = true;
        sel.appendChild(opt);
      }
      updateSermonBar();
      toast('New sermon created');
      return data.sermon_id;
    }
    return null;
  }

  function renderBooks(testament) {
    const list = el('bible-book-list');
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

  function populateChapterSelect(max) {
    maxChapter = Math.max(0, max || 0);
    const sel = el('bible-chapter-select');
    if (sel) {
      sel.innerHTML = '';
      if (!maxChapter) {
        sel.appendChild(new Option('—', ''));
      } else {
        for (let i = 1; i <= maxChapter; i++) sel.appendChild(new Option(String(i), String(i)));
        sel.value = String(Math.min(currentChapter, maxChapter) || 1);
      }
    }
    if (maxChapter > 0) {
      chapterPage = Math.floor((Math.min(currentChapter || 1, maxChapter) - 1) / CHAPTERS_PER_PAGE);
    } else {
      chapterPage = 0;
    }
    renderChapterGrid();
  }

  function renderChapterGrid() {
    const grid = el('bible-chapter-grid');
    const label = el('bible-chapter-page-label');
    const prev = el('bible-chapter-page-prev');
    const next = el('bible-chapter-page-next');
    const hint = el('bible-chapter-scroll-hint');
    const pager = el('bible-chapter-pager');
    if (!grid) return;

    const total = Math.max(0, maxChapter || 0);
    if (!total) {
      grid.innerHTML = '';
      if (label) label.textContent = 'No chapters yet';
      if (prev) prev.hidden = true;
      if (next) next.hidden = true;
      if (hint) hint.style.display = 'none';
      return;
    }

    const maxPage = Math.max(0, Math.ceil(total / CHAPTERS_PER_PAGE) - 1);
    if (chapterPage > maxPage) chapterPage = maxPage;
    if (chapterPage < 0) chapterPage = 0;

    const start = chapterPage * CHAPTERS_PER_PAGE + 1;
    const end = Math.min(total, start + CHAPTERS_PER_PAGE - 1);
    const multi = total > CHAPTERS_PER_PAGE;

    if (label) {
      label.textContent = multi
        ? `Chapters ${start}–${end} of ${total}`
        : (total === 1 ? '1 chapter' : `${total} chapters`);
    }
    if (pager) pager.classList.toggle('is-multi', multi);
    if (prev) {
      prev.disabled = chapterPage <= 0;
      prev.hidden = !multi;
    }
    if (next) {
      next.disabled = end >= total;
      next.hidden = !multi;
    }
    if (hint) {
      if (!multi) {
        hint.style.display = 'none';
        hint.textContent = '';
      } else {
        hint.style.display = '';
        if (end < total) {
          hint.innerHTML = '👉 Tap <strong>More →</strong> for chapters ' +
            `${end + 1}–${Math.min(total, end + CHAPTERS_PER_PAGE)}.`;
        } else if (start > 1) {
          hint.innerHTML = '👉 Tap <strong>← Earlier</strong> to go back toward chapter 1.';
        } else {
          hint.style.display = 'none';
        }
      }
    }

    grid.innerHTML = '';
    for (let i = start; i <= end; i++) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'bible-chapter-num' + (i === currentChapter ? ' active' : '');
      b.textContent = String(i);
      b.setAttribute('aria-label', `Chapter ${i}`);
      b.addEventListener('click', () => {
        const sel = el('bible-chapter-select');
        if (sel) sel.value = String(i);
        loadChapter(i);
        grid.querySelectorAll('button').forEach((x) => x.classList.remove('active'));
        b.classList.add('active');
      });
      grid.appendChild(b);
    }
  }

  function renderVersePicker(verses) {
    const picker = el('bible-verse-picker');
    const meta = el('bible-chapter-meta');
    if (!picker) return;
    const nums = (verses || []).map((v) => v.verse);
    picker.innerHTML = '';
    if (!nums.length) {
      if (meta) meta.textContent = 'No verses in this chapter.';
      return;
    }
    if (meta) meta.textContent = `${currentBook} ${currentChapter}: ${nums.length} verse${nums.length === 1 ? '' : 's'}`;
    nums.forEach((num) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = String(num);
      btn.addEventListener('click', () => {
        if (mainView !== 'chapter') restoreChapter();
        scrollToVerse(num);
        closeFlyouts();
      });
      picker.appendChild(btn);
    });
    if (el('bible-canon-flyout')?.classList.contains('open') && nums.length) {
      scrollToChapterSection();
    }
  }

  function scrollToVerse(verseNum) {
    el('bible-verse-picker')?.querySelectorAll('button').forEach((b) => {
      b.classList.toggle('active', parseInt(b.textContent, 10) === verseNum);
    });
    main()?.querySelectorAll('.bible-verse-line').forEach((l) => l.classList.remove('verse-highlight'));
    const line = main()?.querySelector(`.bible-verse-line[data-verse="${verseNum}"]`);
    if (line) {
      line.classList.add('verse-highlight');
      line.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  function restoreChapter() {
    if (lastChapterHtml) {
      main().innerHTML = lastChapterHtml;
      bindChapterEvents();
      setMainView('chapter');
    } else loadChapter(currentChapter);
  }

  function getVisibleVerseAnchor() {
    /** First verse line that is substantially in view (for seamless version switch). */
    const lines = Array.from(main()?.querySelectorAll('.bible-verse-line') || []);
    if (!lines.length) return null;
    const offset = 140; // toolbar / selection bar
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
    currentTranslation = getTranslation();
    const startChapter = opts.chapter || 1;
    const scrollToVerse = opts.scrollToVerse || null;
    try {
      const url = `${api}/chapter/${encodeURIComponent(book)}/${startChapter}` +
        (currentTranslation ? `?translation=${encodeURIComponent(currentTranslation)}` : '');
      const resp = await fetch(url);
      if (!resp.ok) throw new Error('no book');
      const data = await resp.json();
      maxChapter = data.max_chapter || startChapter || 1;
      populateChapterSelect(maxChapter);
      await loadChapter(startChapter, { scrollToVerse, keepSelection: !!opts.keepSelection });
    } catch (e) {
      maxChapter = 0;
      populateChapterSelect(0);
      main().innerHTML = '<p class="text-muted">No verses for this book.</p>';
    }
  }

  function updateDefaultBadge(val) {
    const badge = el('bible-my-version-badge');
    if (!badge) return;
    const label = String(val || '').replace(/^online:/, '') || '—';
    badge.textContent = `My Bible: ${label}`;
    badge.style.display = val ? '' : 'none';
  }

  async function savePreferredTranslation(val) {
    if (!val || !csrfToken()) return null;
    try {
      const resp = await fetch(urls.preferred || `${api}/preferred`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken(),
          'X-Requested-With': 'XMLHttpRequest',
          Accept: 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify({
          translation: val,
          book: currentBook,
          chapter: currentChapter || 1,
          verse: getVisibleVerseAnchor() || 1,
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (data && data.ok) updateDefaultBadge(val);
      return data;
    } catch (e) {
      console.warn('Could not save preferred translation', e);
      return null;
    }
  }

  async function saveReadingPlace(extra = {}) {
    if (!csrfToken()) return;
    const body = {
      translation: getTranslation(),
      book: currentBook,
      chapter: currentChapter || 1,
      verse: getVisibleVerseAnchor() || extra.verse || 1,
      ...extra,
    };
    try {
      localStorage.setItem('pastoral_bible_place', JSON.stringify(body));
      localStorage.setItem('pastoral_bible_translation', body.translation || '');
    } catch (e) { /* ignore */ }
    try {
      await fetch(urls.place || `${api}/place`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken(),
          'X-Requested-With': 'XMLHttpRequest',
          Accept: 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify(body),
      });
    } catch (e) { /* quiet */ }
  }

  async function switchTranslationSeamless(fromControl) {
    // Keep both version dropdowns in sync (toolbar + flyout)
    const val = fromControl?.value || getTranslation();
    setTranslationValue(val);
    // Personal study version overrides church default next visit / any device after login
    const saved = await savePreferredTranslation(val);
    try {
      localStorage.setItem('pastoral_bible_translation', val);
    } catch (e) { /* ignore */ }
    const book = currentBook;
    const chapter = currentChapter || 1;
    const anchorVerse = getVisibleVerseAnchor();
    // Keep place: same book + chapter, restore scroll to the verse that was on screen
    await prepareBook(book, {
      chapter,
      scrollToVerse: anchorVerse,
      keepSelection: false,
    });
    if (saved && saved.ok) {
      toast(saved.message || `Saved as your study Bible: ${String(val).replace(/^online:/, '')}`);
    } else {
      toast(anchorVerse
        ? `Switched · stayed at ${book} ${chapter}:${anchorVerse}`
        : `Switched · stayed at ${book} ${chapter}`);
    }
  }

  async function loadChapter(chapter, opts = {}) {
    currentTranslation = getTranslation();
    if (maxChapter > 0) chapter = Math.max(1, Math.min(chapter, maxChapter));
    currentChapter = chapter;
    if (!opts.keepSelection) {
      selectedVerses = new Set();
      updateSelectionBar();
    }
    const chSel = el('bible-chapter-select');
    if (chSel?.options.length) chSel.value = String(chapter);

    // Soft loading: keep old text until new arrives when switching versions
    if (!opts.soft) {
      main().innerHTML = '<p class="text-muted small">Loading...</p>';
    }
    const title = el('bible-reader-title');

    try {
      const url = `${api}/chapter/${encodeURIComponent(currentBook)}/${chapter}` +
        (currentTranslation ? `?translation=${encodeURIComponent(currentTranslation)}` : '');
      const resp = await fetch(url);
      if (!resp.ok) throw new Error('not found');
      const data = await resp.json();
      chapterData = data;
      annotationKey = data.annotation_key || data.translation || currentTranslation;
      lastSource = data.source || (isOnlineTranslation(currentTranslation) ? 'online' : 'local');
      maxChapter = data.max_chapter || chapter;
      populateChapterSelect(maxChapter);
      if (chSel) chSel.value = String(chapter);
      const badge = el('bible-source-badge');
      if (badge) {
        badge.style.display = '';
        badge.textContent = lastSource === 'online' ? 'Online' : 'Installed';
        badge.className = 'badge ' + (lastSource === 'online' ? 'bg-info' : 'bg-success');
      }
      if (title) {
        const trLabel = data.translation || data.name || '';
        title.textContent = `${data.book} ${data.chapter}${trLabel ? ' · ' + trLabel : ''}`;
      }
      renderVersePicker(data.verses);
      currentNotes = data.notes || [];
      renderChapter(data);
      if (notesPanelTab === 'all') loadAllNotesPanel();
      else renderNotesPanel(currentNotes, { mode: 'passage' });
      updateNavButtons();
      if (opts.scrollToVerse) {
        // Wait a tick for layout so scrollIntoView hits the right place
        requestAnimationFrame(() => {
          scrollToVerse(opts.scrollToVerse);
        });
      }
      // Remember version + book + chapter so reopening Bible continues here
      saveReadingPlace({ verse: opts.scrollToVerse || getVisibleVerseAnchor() || 1 });
    } catch (e) {
      main().innerHTML = '<p class="text-muted">Could not load this chapter. Try another version or book.</p>';
      if (title) title.textContent = `${currentBook} ${chapter}`;
      renderVersePicker([]);
      currentNotes = [];
      renderNotesPanel([], { mode: 'passage' });
      updateNavButtons();
    }
  }

  function highlightClassForVerse(verseNum, highlights) {
    const hits = (highlights || []).filter((h) => verseNum >= h.verse_start && verseNum <= h.verse_end);
    if (!hits.length) return '';
    return ' hl-' + (hits[hits.length - 1].color || 'yellow');
  }

  function xrefHtmlForVerse(verseNum, crossRefs) {
    const key = String(verseNum);
    const refs = (crossRefs && (crossRefs[key] || crossRefs[verseNum])) || [];
    if (!refs.length) return '';
    const messianic = refs.filter((r) => r.kind === 'messianic');
    const related = refs.filter((r) => r.kind !== 'messianic').slice(0, 5);
    const show = [...messianic, ...related].slice(0, 6);
    let html = '<div class="bible-xrefs">';
    if (messianic.length) {
      html += '<div class="bible-xref-row bible-xref-messianic">';
      html += '<span class="bible-xref-label" title="Widely taught as fulfilled in Christ / NT">✝ Related to Jesus</span> ';
      messianic.slice(0, 4).forEach((r) => {
        const tip = r.label || r.reference;
        html += `<button type="button" class="bible-xref-link messianic" data-xref-book="${escapeAttr(r.book)}" data-xref-chapter="${r.chapter}" data-xref-verse="${r.verse}" title="${escapeAttr(tip)}">${escapeHtml(r.reference)}</button> `;
      });
      html += '</div>';
    }
    if (related.length) {
      html += '<div class="bible-xref-row">';
      html += '<span class="bible-xref-label">See also</span> ';
      related.forEach((r) => {
        html += `<button type="button" class="bible-xref-link" data-xref-book="${escapeAttr(r.book)}" data-xref-chapter="${r.chapter}" data-xref-verse="${r.verse}" title="Cross-reference (score ${r.score || ''})">${escapeHtml(r.reference)}</button> `;
      });
      html += '</div>';
    }
    // Labels under messianic for teaching clarity
    messianic.filter((r) => r.label).slice(0, 2).forEach((r) => {
      html += `<div class="bible-xref-note small text-muted">${escapeHtml(r.label)}</div>`;
    });
    html += '</div>';
    return html;
  }

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

  function renderChapter(data) {
    const reader = main();
    const highlights = data.highlights || [];
    const crossRefs = data.cross_refs || {};
    const notesForMarkers = (currentNotes && currentNotes.length)
      ? currentNotes
      : (data.notes || []);
    const noted = noteVerseSet(notesForMarkers);
    let html = '';
    (data.verses || []).forEach((v) => {
      const ref = `${data.book} ${data.chapter}:${v.verse}`;
      const strongs = (data.strongs && data.strongs[v.verse]) || [];
      const hl = highlightClassForVerse(v.verse, highlights);
      const hasNote = noted.has(v.verse);
      html += `<div class="bible-verse-line${hl}${hasNote ? ' has-note' : ''}" data-verse="${v.verse}" data-text="${escapeAttr(v.text)}">`;
      html += `<span class="bible-verse-num">${v.verse}</span>`;
      if (hasNote) {
        html += `<button type="button" class="bible-note-marker" data-open-note-verse="${v.verse}" title="Open your note on this verse" aria-label="Open note">📝</button>`;
      }
      html += `<span class="bible-verse-text">${linkStrongsInVerse(v.text, strongs)}</span>`;
      html += xrefHtmlForVerse(v.verse, crossRefs);
      html += actionButtonsHtml({
        reference: ref,
        text: v.text,
        book: data.book,
        chapter: data.chapter,
        verse: v.verse,
        hasNote,
      });
      html += '</div>';
    });
    reader.innerHTML = html || '<p class="text-muted">Empty chapter.</p>';
    lastChapterHtml = reader.innerHTML;
    setMainView('chapter');
    bindChapterEvents();
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
        setTimeout(() => openNoteModalForEdit(n.id), 150);
      }
    };
    if (book === currentBook && Number(ch) === Number(currentChapter) && scope !== 'book') {
      if (scope === 'verse' && v) scrollToVerse(v);
      focusNotesPanel(false);
      after();
      return;
    }
    currentBook = book;
    prepareBook(book, {
      chapter: scope === 'book' ? 1 : ch,
      scrollToVerse: scope === 'verse' ? v : 1,
    })
      .then(() => {
        after();
        setNotesPanelTab(notesPanelTab === 'all' ? 'all' : 'passage');
      })
      .catch(() => toast('Could not open that passage'));
  }

  function setNotesPanelTab(tab) {
    notesPanelTab = tab === 'all' ? 'all' : 'passage';
    document.querySelectorAll('[data-notes-tab]').forEach((btn) => {
      const on = btn.dataset.notesTab === notesPanelTab;
      btn.classList.toggle('active', on);
      btn.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    const hint = el('bible-notes-hint');
    if (hint) {
      hint.innerHTML = notesPanelTab === 'all'
        ? 'All notes across books. Click a note (or <strong>Go to verse</strong>) to jump there.'
        : 'Notes for this chapter. Verses with notes show a <span class="bible-note-dot-demo">📝</span> marker — click it to open.';
    }
    if (notesPanelTab === 'all') loadAllNotesPanel();
    else renderNotesPanel(currentNotes, { mode: 'passage' });
  }

  function renderNotesPanel(notes, opts = {}) {
    const list = el('bible-notes-list');
    if (!list) return;
    if (opts.mode !== 'all') currentNotes = notes || [];
    const mode = opts.mode || notesPanelTab || 'passage';
    if (!notes || !notes.length) {
      list.innerHTML = mode === 'all'
        ? '<p class="small text-muted mb-0">No notes yet. Select verses → <strong>Add note</strong>.</p>'
        : '<p class="small text-muted mb-0">No notes on this chapter yet. Select verses → <strong>Add note</strong>, or open <strong>All my notes</strong>.</p>';
      return;
    }
    list.innerHTML = notes.map((n) => {
      const title = n.display_title || n.title || n.reference || 'Note';
      const range = n.reference || (
        n.verse_start === n.verse_end
          ? `v${n.verse_start}`
          : `v${n.verse_start}–${n.verse_end}`
      );
      const here = noteIsOnCurrentPassage(n);
      const elsewhere = mode === 'all' && !here;
      const hereBadge = here && mode === 'all'
        ? '<span class="bible-note-here-badge">Here</span>'
        : '';
      return `<div class="bible-note-item is-clickable${elsewhere ? ' is-elsewhere' : ''}" data-id="${n.id}" data-goto-note-id="${n.id}">
        <div class="d-flex justify-content-between gap-2 flex-wrap">
          <div class="small text-cyan mb-1"><strong>${escapeHtml(title)}</strong> · ${escapeHtml(range)}${hereBadge}</div>
        </div>
        ${n.scripture_text ? `<blockquote class="bible-note-scripture small">${escapeHtml(n.scripture_text)}</blockquote>` : ''}
        <div class="bible-note-body">${escapeHtml(n.body || '')}</div>
        <div class="bible-note-actions mt-1 d-flex flex-wrap gap-1">
          <button type="button" class="btn btn-sm btn-outline-secondary" data-goto-note-id="${n.id}">Go to verse</button>
          <button type="button" class="btn btn-sm btn-outline-cyan" data-edit-note="${n.id}">Edit / add</button>
          <button type="button" class="btn btn-sm btn-outline-cyan" data-illus-note="${n.id}">To illustrations</button>
          <a class="btn btn-sm btn-outline-secondary" href="${api}/note/${n.id}/download">Download</a>
          <button type="button" class="btn btn-sm btn-outline-danger" data-del-note="${n.id}">Delete</button>
        </div>
      </div>`;
    }).join('');

    const findNote = (id) => {
      const nid = Number(id);
      return (notes || []).find((x) => Number(x.id) === nid)
        || (currentNotes || []).find((x) => Number(x.id) === nid)
        || (allNotesCache || []).find((x) => Number(x.id) === nid);
    };

    list.querySelectorAll('[data-goto-note-id]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const n = findNote(btn.dataset.gotoNoteId);
        if (n) goToNotePassage(n);
      });
    });
    list.querySelectorAll('.bible-note-item[data-goto-note-id]').forEach((card) => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('button, a')) return;
        const n = findNote(card.dataset.gotoNoteId);
        if (n) goToNotePassage(n);
      });
    });
    list.querySelectorAll('[data-del-note]').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (!confirm('Delete this note?')) return;
        const resp = await fetch(`${api}/note/${btn.dataset.delNote}`, {
          method: 'DELETE',
          headers: { 'X-CSRF-Token': csrfToken(), 'X-Requested-With': 'XMLHttpRequest' },
        });
        const data = await resp.json().catch(() => ({}));
        if (data.ok) {
          toast('Note deleted');
          loadChapter(currentChapter);
          if (notesPanelTab === 'all') loadAllNotesPanel();
        } else toast('Could not delete note');
      });
    });
    list.querySelectorAll('[data-illus-note]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        sendNoteToIllustration(parseInt(btn.dataset.illusNote, 10));
      });
    });
    list.querySelectorAll('[data-edit-note]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const n = findNote(btn.dataset.editNote);
        if (n && !noteIsOnCurrentPassage(n)) goToNotePassage(n, { openEdit: true });
        else openNoteModalForEdit(parseInt(btn.dataset.editNote, 10));
      });
    });
  }

  async function loadAllNotesPanel() {
    const list = el('bible-notes-list');
    if (!list) return;
    list.innerHTML = '<p class="small text-muted mb-0">Loading all notes…</p>';
    try {
      const url = (urls.notesList || `${api}/notes`) + '?limit=100';
      const resp = await fetch(url, { headers: { Accept: 'application/json' } });
      const data = await resp.json().catch(() => ({}));
      allNotesCache = data.notes || [];
      renderNotesPanel(allNotesCache, { mode: 'all' });
    } catch (e) {
      list.innerHTML = '<p class="small text-warning">Could not load notes.</p>';
    }
  }

  function selectedScriptureBundle() {
    const nums = Array.from(selectedVerses).sort((a, b) => a - b);
    if (!nums.length) return null;
    const texts = [];
    nums.forEach((v) => {
      const line = main()?.querySelector(`.bible-verse-line[data-verse="${v}"]`);
      const t = line?.dataset.text || line?.querySelector('.bible-verse-text')?.textContent || '';
      if (t) texts.push(`${v} ${t.trim()}`);
    });
    const ref = nums.length === 1
      ? `${currentBook} ${currentChapter}:${nums[0]}`
      : `${currentBook} ${currentChapter}:${nums[0]}-${nums[nums.length - 1]}`;
    return {
      verse_start: nums[0],
      verse_end: nums[nums.length - 1],
      reference: ref,
      scripture_text: texts.join('\n'),
    };
  }

  async function sendNoteToIllustration(noteId) {
    const resp = await fetch(`${api}/note/${noteId}/to_illustration`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken(),
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({ visibility: 'private' }),
    });
    const data = await resp.json().catch(() => ({}));
    if (data.ok) {
      toast(data.message || 'Also copied to Illustration Library');
      // Do not auto-navigate away from Study notes
    } else toast(data.error || 'Could not save to illustrations');
  }

  async function selectionToIllustration() {
    const bundle = selectedScriptureBundle();
    if (!bundle) return toast('Select a verse first');
    const resp = await fetch(urls.selectionToIllustration || `${api}/selection/to_illustration`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken(),
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({
        reference: bundle.reference,
        text: bundle.scripture_text,
        translation: annotationKey || getTranslation(),
      }),
    });
    const data = await resp.json().catch(() => ({}));
    if (data.ok) {
      toast(data.message || 'Saved to illustrations');
      if (data.library_url && confirm('Open Illustration Library?')) {
        window.open(data.library_url, '_blank');
      }
    } else toast(data.error || 'Could not save');
  }

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
        return a <= ve && b >= vs;
      });
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

  function setNoteModalEditingState(isEditing) {
    const heading = el('bible-note-heading');
    const status = el('bible-note-status');
    const saveBtn = el('bible-note-save');
    const newBtn = el('bible-note-new');
    if (heading) heading.textContent = isEditing ? 'Edit study note' : 'Study note';
    if (saveBtn) saveBtn.textContent = isEditing ? 'Update study note' : 'Save to Study notes';
    if (newBtn) newBtn.style.display = isEditing ? '' : 'none';
    if (status) {
      if (isEditing) {
        status.style.display = '';
        status.className = 'small mb-2 text-cyan';
        status.textContent = 'Previous note loaded — edit the text or add more at the end, then Update.';
      } else {
        status.style.display = 'none';
        status.textContent = '';
      }
    }
  }

  function focusNoteBodyAtEnd() {
    const body = el('bible-note-body');
    if (!body) return;
    body.focus();
    try {
      const len = body.value.length;
      body.setSelectionRange(len, len);
    } catch (e) { /* ignore */ }
  }

  async function openNoteModalForEdit(noteId) {
    try {
      let n = (currentNotes || []).find((x) => Number(x.id) === Number(noteId));
      if (!n) {
        const resp = await fetch(`${api}/note/${noteId}`, {
          headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        });
        const data = await resp.json();
        if (!data.ok || !data.note) throw new Error(data.error || 'Not found');
        n = data.note;
      }
      openNoteModal({
        editId: n.id,
        verse_start: n.verse_start,
        verse_end: n.verse_end,
        reference: n.reference,
        title: n.title || n.display_title || '',
        scripture_text: n.scripture_text || '',
        body: n.body || '',
        tags: n.tags || '',
      });
    } catch (e) {
      toast(e.message || 'Could not load note');
    }
  }

  function startNewNoteFromModal() {
    const ref = el('bible-note-ref');
    if (ref) ref.dataset.editId = '';
    const body = el('bible-note-body');
    const tags = el('bible-note-tags');
    if (body) body.value = '';
    if (tags) tags.value = 'bible,study-note';
    setNoteModalEditingState(false);
    const status = el('bible-note-status');
    if (status) {
      status.style.display = '';
      status.className = 'small mb-2 text-muted';
      status.textContent = 'Writing a new note (previous note is kept).';
    }
    focusNoteBodyAtEnd();
  }

  async function loadNotesLibrary(q) {
    const box = el('bible-notes-lib-results');
    if (!box) return;
    box.innerHTML = '<p class="small text-muted">Loading…</p>';
    try {
      const url = (urls.notesList || `${api}/notes`) + `?q=${encodeURIComponent(q || '')}&limit=40`;
      const resp = await fetch(url);
      const data = await resp.json();
      const rows = data.notes || [];
      allNotesCache = rows;
      if (!rows.length) {
        box.innerHTML = '<p class="small text-muted">No notes found.</p>';
        return;
      }
      box.innerHTML = rows.map((n) => `
        <div class="bible-lib-note mb-2 p-2 border rounded" data-lib-note-id="${n.id}" title="Go to ${escapeAttr(n.reference || '')}">
          <div class="small fw-semibold">${escapeHtml(n.display_title || n.title || n.reference)}</div>
          <div class="small text-muted">${escapeHtml(n.reference || '')}</div>
          <div class="small" style="max-height:3.2em;overflow:hidden;">${escapeHtml((n.body || '').slice(0, 160))}</div>
          <div class="d-flex flex-wrap gap-1 mt-1">
            <button type="button" class="btn btn-sm btn-outline-cyan" data-goto-note-id="${n.id}">Go to verse</button>
            <button type="button" class="btn btn-sm btn-outline-cyan" data-edit-note="${n.id}">Edit</button>
            <button type="button" class="btn btn-sm btn-outline-cyan" data-lib-illus="${n.id}">To illustrations</button>
            <a class="btn btn-sm btn-outline-secondary" href="${api}/note/${n.id}/download">Download</a>
          </div>
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
      box.querySelectorAll('.bible-lib-note[data-lib-note-id]').forEach((item) => {
        item.addEventListener('click', (e) => {
          if (e.target.closest('button, a')) return;
          const n = findNote(item.dataset.libNoteId);
          if (n) goToNotePassage(n);
        });
      });
      box.querySelectorAll('[data-lib-illus]').forEach((btn) => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          sendNoteToIllustration(parseInt(btn.dataset.libIllus, 10));
        });
      });
    } catch (e) {
      box.innerHTML = '<p class="small text-warning">Could not load notes library.</p>';
    }
  }

  function updateSelectionBar() {
    const bar = el('bible-selection-bar');
    const label = el('bible-selection-label');
    if (!bar) return;
    if (!selectedVerses.size) {
      bar.style.display = 'none';
      return;
    }
    bar.style.display = '';
    const nums = Array.from(selectedVerses).sort((a, b) => a - b);
    if (label) {
      const range = nums.length === 1
        ? `${currentBook} ${currentChapter}:${nums[0]}`
        : `${currentBook} ${currentChapter}:${nums[0]}–${nums[nums.length - 1]}`;
      label.textContent = nums.length === 1
        ? `${range} selected — use buttons to copy, note, or send to sermon`
        : `${range} (${nums.length} verses) selected — multi-verse actions apply to all`;
    }
  }

  function bindChapterEvents() {
    const reader = main();
    reader?.querySelectorAll('.strongs-word').forEach((node) => {
      node.addEventListener('click', (e) => {
        e.stopPropagation();
        showStrongs(node.dataset.strongs);
      });
    });
    reader?.querySelectorAll('.bible-xref-link').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        e.preventDefault();
        const book = btn.dataset.xrefBook;
        const ch = parseInt(btn.dataset.xrefChapter, 10);
        const v = parseInt(btn.dataset.xrefVerse, 10);
        if (!book || !ch) return;
        openXrefPopup({
          book,
          chapter: ch,
          verse: v || 1,
          reference: (btn.textContent || '').trim(),
          label: btn.getAttribute('title') || '',
        });
      });
    });
    reader?.querySelectorAll('.bible-verse-line').forEach((line) => {
      line.addEventListener('click', (e) => {
        if (e.target.closest('.content-actions')
          || e.target.closest('.strongs-word')
          || e.target.closest('.bible-xrefs')
          || e.target.closest('.bible-note-marker')) return;
        const v = parseInt(line.dataset.verse, 10);
        if (!v) return;
        if (e.shiftKey && selectedVerses.size) {
          const existing = Array.from(selectedVerses);
          const anchor = existing[existing.length - 1];
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
        reader.querySelectorAll('.bible-verse-line').forEach((l) => {
          l.classList.toggle('verse-selected', selectedVerses.has(parseInt(l.dataset.verse, 10)));
        });
        updateSelectionBar();
      });
    });
    bindActionButtons(reader);
  }

  async function applyHighlight() {
    if (!selectedVerses.size) return toast('Select a verse first');
    const nums = Array.from(selectedVerses).sort((a, b) => a - b);
    const color = el('bible-hl-color')?.value || 'yellow';
    const resp = await fetch(urls.highlight || `${api}/highlight`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken(),
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({
        translation: annotationKey || getTranslation(),
        book: currentBook,
        chapter: currentChapter,
        verse_start: nums[0],
        verse_end: nums[nums.length - 1],
        color,
      }),
    });
    const data = await resp.json().catch(() => ({}));
    if (data.ok) {
      toast('Highlighted');
      loadChapter(currentChapter);
    } else toast(data.error || 'Could not highlight');
  }

  async function clearHighlight() {
    if (!selectedVerses.size) return toast('Select a verse first');
    const nums = Array.from(selectedVerses);
    for (const v of nums) {
      await fetch(urls.highlightClear || `${api}/highlight/clear`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken(),
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({
          translation: annotationKey || getTranslation(),
          book: currentBook,
          chapter: currentChapter,
          verse: v,
        }),
      });
    }
    toast('Highlight cleared');
    loadChapter(currentChapter);
  }

  function openNoteModal(prefill) {
    const modal = el('bible-note-modal');
    const ref = el('bible-note-ref');
    const title = el('bible-note-title');
    const scripture = el('bible-note-scripture');
    const body = el('bible-note-body');
    const tags = el('bible-note-tags');
    const alsoIllus = el('bible-note-also-illustration');

    let bundle = prefill || null;
    if (!bundle) {
      if (!selectedVerses.size) return toast('Select a verse first');
      bundle = selectedScriptureBundle();
    }
    if (!bundle) return;

    // Auto-load previous note for this passage unless starting fresh
    let existing = null;
    if (!bundle.forceNew) {
      if (bundle.editId) {
        existing = (currentNotes || []).find((n) => Number(n.id) === Number(bundle.editId)) || null;
      } else {
        existing = findExistingNote(
          bundle.scope || 'verse',
          bundle.verse_start,
          bundle.verse_end || bundle.verse_start,
        );
      }
    }

    if (ref) {
      ref.textContent = (existing && existing.reference)
        || bundle.reference
        || `${currentBook} ${currentChapter}`;
      ref.dataset.vStart = String(
        existing ? (existing.verse_start || bundle.verse_start || 1) : (bundle.verse_start || 1)
      );
      ref.dataset.vEnd = String(
        existing
          ? (existing.verse_end || existing.verse_start || bundle.verse_end || 1)
          : (bundle.verse_end || bundle.verse_start || 1)
      );
      ref.dataset.editId = existing
        ? String(existing.id)
        : (bundle.editId ? String(bundle.editId) : '');
    }
    if (title) {
      title.value = bundle.title
        || (existing && (existing.title || existing.display_title))
        || bundle.reference
        || '';
    }
    if (scripture) {
      scripture.value = bundle.scripture_text != null && bundle.scripture_text !== ''
        ? bundle.scripture_text
        : ((existing && existing.scripture_text) || '');
    }
    if (body) {
      // Prefer explicit prefill body (edit), else existing note, else blank
      if (bundle.body != null && (bundle.editId || bundle.forceNew)) {
        body.value = bundle.body || '';
      } else if (existing) {
        body.value = existing.body || '';
      } else {
        body.value = bundle.body || '';
      }
    }
    if (tags) {
      tags.value = bundle.tags != null && (bundle.editId || bundle.forceNew)
        ? (bundle.tags || 'bible,study-note')
        : (existing ? (existing.tags || 'bible,study-note') : (bundle.tags || 'bible,study-note'));
    }
    // Notes stay in Study notes by default — illustrations are opt-in
    if (alsoIllus) alsoIllus.checked = false;

    setNoteModalEditingState(!!(existing || bundle.editId));

    if (modal) {
      modal.style.display = 'flex';
      modal.setAttribute('aria-hidden', 'false');
    }
    requestAnimationFrame(() => focusNoteBodyAtEnd());
  }

  function focusNotesPanel(flash) {
    const panel = el('bible-notes-panel');
    if (!panel) return;
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    if (flash) {
      panel.classList.add('bible-notes-panel-flash');
      setTimeout(() => panel.classList.remove('bible-notes-panel-flash'), 1800);
    }
  }

  function closeNoteModal() {
    const modal = el('bible-note-modal');
    if (modal) {
      modal.style.display = 'none';
      modal.setAttribute('aria-hidden', 'true');
    }
  }

  async function saveNoteFromModal() {
    const ref = el('bible-note-ref');
    const body = (el('bible-note-body')?.value || '').trim();
    const title = (el('bible-note-title')?.value || '').trim();
    const scripture_text = (el('bible-note-scripture')?.value || '').trim();
    const tags = (el('bible-note-tags')?.value || '').trim();
    const editId = ref?.dataset.editId ? parseInt(ref.dataset.editId, 10) : null;
    if (!body) return toast('Write a note first');
    const resp = await fetch(urls.note || `${api}/note`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrfToken(),
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({
        id: editId || undefined,
        translation: annotationKey || getTranslation(),
        book: currentBook,
        chapter: currentChapter,
        verse_start: parseInt(ref?.dataset.vStart || '1', 10),
        verse_end: parseInt(ref?.dataset.vEnd || '1', 10),
        title,
        body,
        scripture_text,
        tags,
      }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!data.ok) {
      toast(data.error || 'Could not save note');
      return;
    }
    const alsoIllus = el('bible-note-also-illustration')?.checked;
    closeNoteModal();
    // Stay on chapter view and refresh the Study notes panel (not illustrations)
    try {
      if (mainView !== 'chapter') setMainView('chapter');
      // Reload notes for this chapter without wiping the reader if possible
      const chData = await (async () => {
        const tr = getTranslation();
        let url = `${api}/chapter/${encodeURIComponent(currentBook)}/${currentChapter}`;
        if (tr) url += `?translation=${encodeURIComponent(tr)}`;
        const r = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
        return r.ok ? r.json() : null;
      })();
      if (chData) {
        annotationKey = chData.annotation_key || annotationKey;
        currentNotes = chData.notes || [];
        renderNotesPanel(currentNotes);
      } else if (data.note) {
        // Merge into local cache
        const idx = currentNotes.findIndex((n) => Number(n.id) === Number(data.note.id));
        if (idx >= 0) currentNotes[idx] = data.note;
        else currentNotes = [data.note, ...currentNotes];
        renderNotesPanel(currentNotes);
      }
    } catch (e) {
      /* still focus panel */
    }
    focusNotesPanel(true);
    if (alsoIllus && data.note?.id) {
      toast(editId ? 'Note updated — also copying to Illustration Library…' : 'Note saved to Study notes — also copying to Illustration Library…');
      await sendNoteToIllustration(data.note.id);
    } else {
      toast(editId ? 'Note updated in Study notes (below)' : 'Note saved in Study notes (below)');
    }
  }

  function downloadChapterNotes() {
    const params = new URLSearchParams({
      book: currentBook,
      chapter: String(currentChapter),
    });
    if (annotationKey) params.set('translation', annotationKey);
    window.location.href = (urls.notesDownload || `${api}/notes/download`) + '?' + params.toString();
  }

  function downloadAllNotes() {
    window.location.href = urls.notesDownload || `${api}/notes/download`;
  }

  async function searchOnlineVersions() {
    const q = (el('bible-online-search')?.value || '').trim();
    const box = el('bible-online-results');
    if (!box) return;
    box.innerHTML = '<p class="small text-muted">Searching catalog…</p>';
    try {
      const url = (urls.onlineTranslations || `${api}/online/translations`) +
        `?q=${encodeURIComponent(q)}&lang=eng`;
      const resp = await fetch(url);
      const data = await resp.json();
      if (!data.ok && data.error) {
        box.innerHTML = `<p class="small text-warning">${escapeHtml(data.error)}</p>`;
        return;
      }
      const rows = data.translations || [];
      if (!rows.length) {
        box.innerHTML = '<p class="small text-muted">No matches.</p>';
        return;
      }
      box.innerHTML = rows.slice(0, 25).map((t) => `
        <button type="button" class="btn btn-sm btn-outline-cyan w-100 text-start mb-1 bible-online-pick"
          data-value="${escapeAttr(t.value)}" data-name="${escapeAttr(t.name)}">
          ${escapeHtml(t.name)} <span class="text-muted">(${escapeHtml(t.code)})</span>
        </button>
      `).join('');
      box.querySelectorAll('.bible-online-pick').forEach((btn) => {
        btn.addEventListener('click', () => {
          const sel = el('bible-translation');
          if (!sel) return;
          let opt = Array.from(sel.options).find((o) => o.value === btn.dataset.value);
          if (!opt) {
            opt = document.createElement('option');
            opt.value = btn.dataset.value;
            opt.textContent = `${btn.dataset.name} · online`;
            sel.appendChild(opt);
          }
          setTranslationValue(btn.dataset.value);
          toast(`Using ${btn.dataset.name}`);
          switchTranslationSeamless(sel);
        });
      });
    } catch (e) {
      box.innerHTML = '<p class="small text-warning">Could not reach Bible catalog.</p>';
    }
  }

  function linkStrongsInVerse(text, strongsList) {
    if (!strongsList.length) return escapeHtml(text);
    let result = escapeHtml(text);
    strongsList.forEach((s) => {
      if (!s.surface_word) return;
      const re = new RegExp(`\\b(${escapeRegex(s.surface_word)})\\b`, 'i');
      result = result.replace(re, (m) =>
        `<span class="strongs-word" data-strongs="${s.strongs_number}" title="${s.strongs_number}">${m}</span>`
      );
    });
    return result;
  }

  /* ---- Linked-verse popup (cross-refs) ---- */
  let xrefPopupState = null;

  function ensureXrefPopup() {
    let root = el('pastoral-xref-popup');
    if (root) return root;
    root = document.createElement('div');
    root.id = 'pastoral-xref-popup';
    root.className = 'bible-xref-popup';
    root.setAttribute('aria-hidden', 'true');
    root.innerHTML = `
      <div class="bible-xref-popup-card" role="dialog" aria-modal="true" aria-labelledby="pastoral-xref-popup-title">
        <button type="button" class="bible-xref-popup-close" data-xref-close aria-label="Close">&times;</button>
        <div class="bible-xref-popup-meta">
          <span class="bible-xref-popup-kicker">Linked verse</span>
          <h3 id="pastoral-xref-popup-title" class="bible-xref-popup-title">—</h3>
          <div class="bible-xref-popup-bcv">
            <span data-xref-book></span>
            <span class="bible-xref-popup-dot">·</span>
            <span>Chapter <strong data-xref-chapter></strong></span>
            <span class="bible-xref-popup-dot">·</span>
            <span>Verse <strong data-xref-verse></strong></span>
          </div>
          <p class="bible-xref-popup-label small text-muted" data-xref-label style="display:none;"></p>
        </div>
        <blockquote class="bible-xref-popup-text" data-xref-text>Loading…</blockquote>
        <div class="bible-xref-popup-actions">
          <button type="button" class="btn btn-outline-secondary btn-sm" data-xref-copy>Copy</button>
          <button type="button" class="btn btn-warning btn-sm" data-xref-highlight>Highlight</button>
          <button type="button" class="btn btn-outline-cyan btn-sm" data-xref-goto>Go to passage</button>
        </div>
      </div>`;
    document.body.appendChild(root);
    root.addEventListener('click', (e) => {
      if (e.target === root || e.target.closest('[data-xref-close]')) closeXrefPopup();
    });
    root.querySelector('[data-xref-copy]')?.addEventListener('click', () => {
      if (!xrefPopupState) return;
      const blob = `${xrefPopupState.reference}\n${xrefPopupState.text || ''}`.trim();
      if (navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(blob).then(() => toast('Copied')).catch(() => toast('Could not copy'));
      } else {
        toast('Copy not available');
      }
    });
    root.querySelector('[data-xref-highlight]')?.addEventListener('click', async () => {
      if (!xrefPopupState) return;
      const color = el('bible-hl-color')?.value || 'yellow';
      try {
        const resp = await fetch(urls.highlight || `${api}/highlight`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrfToken(),
            'X-Requested-With': 'XMLHttpRequest',
          },
          body: JSON.stringify({
            translation: annotationKey || getTranslation(),
            book: xrefPopupState.book,
            chapter: xrefPopupState.chapter,
            verse_start: xrefPopupState.verse,
            verse_end: xrefPopupState.verse,
            color,
          }),
        });
        const data = await resp.json().catch(() => ({}));
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
    const root = el('pastoral-xref-popup');
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
    xrefPopupState = { book, chapter, verse, reference, text: '', label: opts.label || '' };
    const root = ensureXrefPopup();
    root.querySelector('#pastoral-xref-popup-title').textContent = reference;
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

    try {
      const tr = getTranslation();
      let url = `${api}/verse/${encodeURIComponent(book)}/${chapter}/${verse}`;
      if (tr) url += `?translation=${encodeURIComponent(tr)}`;
      const resp = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (!resp.ok) throw new Error('not found');
      const data = await resp.json();
      const text = (data.text || '').trim();
      xrefPopupState.text = text;
      xrefPopupState.reference = data.reference || reference;
      if (data.book) {
        xrefPopupState.book = data.book;
        root.querySelector('[data-xref-book]').textContent = data.book;
      }
      root.querySelector('#pastoral-xref-popup-title').textContent = xrefPopupState.reference;
      textEl.textContent = text || 'Verse text unavailable in this version.';
    } catch (err) {
      textEl.textContent = 'Could not load this verse in the current version. You can still go to the passage.';
    }
  }

  async function showStrongs(number) {
    const reader = main();
    reader.innerHTML = '<p class="text-muted small">Loading...</p>';
    closeFlyouts();
    setMainView('strongs');
    if (el('bible-reader-title')) el('bible-reader-title').textContent = `Strong's ${number}`;

    try {
      const resp = await fetch(`${api}/strongs/${encodeURIComponent(number)}`);
      if (!resp.ok) throw new Error('missing');
      const data = await resp.json();
      const defText = `${data.number} (${data.transliteration || ''}) — ${data.definition || ''}`;
      let html = `<h3 class="bible-main-heading">Strong's ${escapeHtml(data.number)}</h3>`;
      html += `<div class="strongs-entry"><h6>${escapeHtml(data.transliteration || '')}</h6>`;
      html += `<p class="small mb-1"><em>${escapeHtml(data.lemma || '')}</em> (${escapeHtml(data.language || '')})</p>`;
      html += `<p>${escapeHtml(data.definition || '')}</p>`;
      html += actionButtonsHtml({ reference: data.number, text: defText, strongs: data.number });
      if (data.occurrences?.length) {
        html += '<p class="small text-cyan mt-2">Sample occurrences</p><ul class="small">';
        data.occurrences.slice(0, 10).forEach((o) => {
          html += `<li><a href="#" data-goto="${o.book}|${o.chapter}|${o.verse}" class="text-cyan">${o.book} ${o.chapter}:${o.verse}</a></li>`;
        });
        html += '</ul>';
      }
      html += '</div>';
      reader.innerHTML = html;
      bindActionButtons(reader);
      reader.querySelectorAll('[data-goto]').forEach((a) => {
        a.addEventListener('click', (ev) => {
          ev.preventDefault();
          const [book, ch, v] = a.dataset.goto.split('|');
          currentBook = book;
          loadChapter(parseInt(ch, 10)).then(() => scrollToVerse(parseInt(v, 10)));
        });
      });
    } catch (e) {
      reader.innerHTML = '<p class="text-muted">Strong\'s entry not found.</p>';
    }
  }

  async function searchBible() {
    const q = (el('bible-search-input')?.value || '').trim();
    if (!q) return;

    // Reference jump works for online + local (e.g. John 3:16)
    const refMatch = q.match(/^\s*((?:\d\s*)?[A-Za-z]+(?:\s+[A-Za-z]+)?)\s+(\d+)\s*:\s*(\d+)/i);
    if (refMatch) {
      currentBook = refMatch[1].replace(/\s+/g, ' ').trim();
      // normalize common casing via server when chapter loads
      const ch = parseInt(refMatch[2], 10);
      const v = parseInt(refMatch[3], 10);
      closeFlyouts();
      await prepareBook(currentBook, { chapter: ch, scrollToVerse: v });
      return;
    }

    if (isOnlineTranslation()) {
      toast('Full-text search needs an installed translation. Try a reference like John 3:16, or install a copy for offline search.');
      return;
    }

    const reader = main();
    reader.innerHTML = '<p class="text-muted small">Searching...</p>';
    closeFlyouts();
    setMainView('search');
    if (el('bible-reader-title')) el('bible-reader-title').textContent = `Search: ${q}`;

    const tr = getTranslation();
    const url = `${api}/search?q=${encodeURIComponent(q)}&limit=25` +
      (tr ? `&translation=${encodeURIComponent(tr)}` : '');
    const resp = await fetch(url);
    const data = await resp.json();
    if (!data.verses?.length) {
      reader.innerHTML = '<p class="text-muted small">No results.</p>';
      return;
    }
    let html = `<h3 class="bible-main-heading">Search results (${data.verses.length})</h3>`;
    html += data.verses.map((v) => `
      <div class="result-item" data-book="${escapeAttr(v.book)}" data-chapter="${v.chapter}" data-verse="${v.verse}">
        <strong>${escapeHtml(v.reference)}</strong>
        <div class="small" style="margin-top:0.35rem;">${escapeHtml(v.text || '')}</div>
        ${actionButtonsHtml({ reference: v.reference, text: v.text, book: v.book, chapter: v.chapter, verse: v.verse })}
      </div>
    `).join('');
    reader.innerHTML = html;
    reader.querySelectorAll('.result-item').forEach((item) => {
      item.addEventListener('click', (e) => {
        if (e.target.closest('.content-actions')) return;
        currentBook = item.dataset.book;
        loadChapter(parseInt(item.dataset.chapter, 10)).then(() => scrollToVerse(parseInt(item.dataset.verse, 10)));
      });
    });
    bindActionButtons(reader);
  }

  async function searchStrongs() {
    const q = (el('strongs-search-input')?.value || '').trim();
    if (!q) return;
    const reader = main();
    reader.innerHTML = '<p class="text-muted small">Looking up...</p>';
    closeFlyouts();
    setMainView('strongs-list');
    if (el('bible-reader-title')) el('bible-reader-title').textContent = `Strong's: ${q}`;

    const resp = await fetch(`${api}/strongs/search?q=${encodeURIComponent(q)}`);
    const data = await resp.json();
    if (!data.entries?.length) {
      reader.innerHTML = '<p class="text-muted small">No Strong\'s matches.</p>';
      return;
    }
    let html = `<h3 class="bible-main-heading">Strong's matches (${data.entries.length})</h3>`;
    html += data.entries.map((e) => {
      const defText = `${e.number} (${e.transliteration || ''}) — ${e.definition || ''}`;
      return `
      <div class="strongs-hit" data-num="${e.number}">
        <strong>${e.number}</strong> ${escapeHtml(e.transliteration || '')}
        <div class="small text-muted" style="margin-top:0.25rem;">${escapeHtml((e.definition || '').slice(0, 200))}</div>
        ${actionButtonsHtml({ reference: e.number, text: defText, strongs: e.number })}
      </div>`;
    }).join('');
    reader.innerHTML = html;
    reader.querySelectorAll('.strongs-hit').forEach((hit) => {
      hit.addEventListener('click', (e) => {
        if (e.target.closest('.content-actions')) return;
        showStrongs(hit.dataset.num);
      });
    });
    bindActionButtons(reader);
  }

  function updateNavButtons() {
    const prev = el('bible-prev-chapter');
    const next = el('bible-next-chapter');
    if (prev) prev.disabled = currentChapter <= 1;
    if (next) next.disabled = maxChapter > 0 ? currentChapter >= maxChapter : true;
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  function escapeAttr(s) { return escapeHtml(s).replace(/"/g, '&quot;'); }
  function escapeRegex(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  document.addEventListener('DOMContentLoaded', () => {
    const saved = sessionStorage.getItem('bible_active_sermon');
    if (saved && el('bible-sermon-select') && !cfg.sermonId) {
      const opt = el('bible-sermon-select').querySelector(`option[value="${saved}"]`);
      if (opt) el('bible-sermon-select').value = saved;
    }
    updateSermonBar();

    renderBooks('NT');
    document.querySelectorAll('.bible-book-tabs button').forEach((tab) => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.bible-book-tabs button').forEach((t) => t.classList.remove('active'));
        tab.classList.add('active');
        renderBooks(tab.dataset.testament);
      });
    });

    el('bible-open-canon')?.addEventListener('click', () => openFlyout('canon'));
    el('bible-open-tools')?.addEventListener('click', () => openFlyout('tools'));
    el('bible-flyout-backdrop')?.addEventListener('click', closeFlyouts);
    document.querySelectorAll('.bible-flyout-close').forEach((b) => b.addEventListener('click', closeFlyouts));
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeXrefPopup();
        closeFlyouts();
        closeNoteModal();
      }
    });

    el('bible-chapter-select')?.addEventListener('change', () => {
      const ch = parseInt(el('bible-chapter-select').value, 10);
      if (ch) {
        chapterPage = Math.floor((ch - 1) / CHAPTERS_PER_PAGE);
        loadChapter(ch);
      }
    });
    el('bible-chapter-page-prev')?.addEventListener('click', () => {
      if (chapterPage <= 0) return;
      chapterPage -= 1;
      renderChapterGrid();
    });
    el('bible-chapter-page-next')?.addEventListener('click', () => {
      const maxPage = Math.max(0, Math.ceil((maxChapter || 1) / CHAPTERS_PER_PAGE) - 1);
      if (chapterPage >= maxPage) return;
      chapterPage += 1;
      renderChapterGrid();
    });
    el('bible-search-btn')?.addEventListener('click', searchBible);
    el('bible-search-input')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') searchBible(); });
    el('strongs-search-btn')?.addEventListener('click', searchStrongs);
    el('strongs-search-input')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') searchStrongs(); });
    el('bible-prev-chapter')?.addEventListener('click', () => {
      closeFlyouts();
      loadChapter(currentChapter - 1).then(() => {
        chapterPage = Math.floor((currentChapter - 1) / CHAPTERS_PER_PAGE);
        renderChapterGrid();
      });
    });
    el('bible-next-chapter')?.addEventListener('click', () => {
      closeFlyouts();
      loadChapter(currentChapter + 1).then(() => {
        chapterPage = Math.floor((currentChapter - 1) / CHAPTERS_PER_PAGE);
        renderChapterGrid();
      });
    });
    el('bible-back-chapter')?.addEventListener('click', restoreChapter);
    el('bible-translation')?.addEventListener('change', (e) => switchTranslationSeamless(e.target));
    el('bible-translation-toolbar')?.addEventListener('change', (e) => switchTranslationSeamless(e.target));
    el('bible-sermon-select')?.addEventListener('change', updateSermonBar);
    el('bible-new-sermon-btn')?.addEventListener('click', async () => {
      const id = await quickCreateSermon(`${currentBook} ${currentChapter}`);
      if (id) updateSermonBar();
    });

    el('bible-hl-btn')?.addEventListener('click', applyHighlight);
    el('bible-hl-clear-btn')?.addEventListener('click', clearHighlight);
    el('bible-note-btn')?.addEventListener('click', () => openNoteModal());
    el('bible-to-illustration-btn')?.addEventListener('click', selectionToIllustration);
    el('bible-copy-sel-btn')?.addEventListener('click', () => {
      copyBundle(selectedScriptureBundle(), 'Selection copied');
    });
    el('bible-copy-chapter-btn')?.addEventListener('click', () => {
      copyBundle(chapterScriptureBundle(), 'Whole chapter copied');
    });
    el('bible-sel-sermon-btn')?.addEventListener('click', insertSelectionToSermon);
    el('bible-chapter-note-btn')?.addEventListener('click', () => {
      const ch = chapterScriptureBundle();
      if (!ch) return toast('Load a chapter first');
      // Match any prior note covering this chapter range (loads for edit/add)
      openNoteModal({
        verse_start: ch.verse_start,
        verse_end: ch.verse_end,
        reference: ch.reference,
        scripture_text: ch.scripture_text,
        title: ch.reference,
      });
    });
    el('bible-sermon-select')?.addEventListener('change', () => {
      updateSermonBar();
      const title = activeSermonTitle();
      const sid = getActiveSermonId();
      if (sid && title) {
        setSermonHint(
          `Active sermon: <strong>${escapeHtml(title)}</strong>. Use <strong>+ Sermon</strong> on a verse or selection to insert.`,
          false,
        );
      }
    });
    el('bible-note-cancel')?.addEventListener('click', closeNoteModal);
    el('bible-note-save')?.addEventListener('click', saveNoteFromModal);
    el('bible-note-new')?.addEventListener('click', startNewNoteFromModal);
    el('bible-note-modal')?.addEventListener('click', (e) => {
      if (e.target === el('bible-note-modal')) closeNoteModal();
    });
    el('bible-online-search-btn')?.addEventListener('click', searchOnlineVersions);
    el('bible-online-search')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') searchOnlineVersions();
    });
    el('bible-notes-library-btn')?.addEventListener('click', () => {
      openFlyout('tools');
      loadNotesLibrary('');
    });
    el('bible-notes-lib-btn')?.addEventListener('click', () => {
      loadNotesLibrary(el('bible-notes-lib-q')?.value || '');
    });
    el('bible-notes-lib-q')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') loadNotesLibrary(el('bible-notes-lib-q')?.value || '');
    });
    document.querySelectorAll('[data-notes-tab]').forEach((btn) => {
      btn.addEventListener('click', () => setNotesPanelTab(btn.dataset.notesTab));
    });
    el('bible-notes-dl-chapter')?.addEventListener('click', downloadChapterNotes);
    el('bible-notes-dl-all')?.addEventListener('click', downloadAllNotes);

    // Personal preference (server) → localStorage → church default
    let want = cfg.selectedTranslation || cfg.userPreferred || null;
    let resumeBook = cfg.lastBook || null;
    let resumeChapter = cfg.lastChapter || null;
    let resumeVerse = cfg.lastVerse || null;
    try {
      want = want || localStorage.getItem('pastoral_bible_translation');
      const raw = localStorage.getItem('pastoral_bible_place');
      if (raw) {
        const p = JSON.parse(raw);
        if (!want && p.translation) want = p.translation;
        // Prefer server place; fill gaps from browser backup
        if (!resumeBook && p.book) resumeBook = p.book;
        if (!resumeChapter && p.chapter) resumeChapter = p.chapter;
        if (!resumeVerse && p.verse) resumeVerse = p.verse;
      }
    } catch (e) { /* ignore */ }
    if (want) {
      const candidates = [want, `online:${want}`, String(want).replace(/^online:/, '')];
      const pick = candidates.find((c) =>
        Array.from(el('bible-translation')?.options || []).some((o) => o.value === c)
        || Array.from(el('bible-translation-toolbar')?.options || []).some((o) => o.value === c)
      );
      if (pick) setTranslationValue(pick);
      else setTranslationValue(want);
      updateDefaultBadge(pick || want);
    }

    el('bible-save-my-bible')?.addEventListener('click', async () => {
      const val = getTranslation();
      if (!val) return toast('Pick a Bible version first');
      const data = await savePreferredTranslation(val);
      if (data && data.ok) {
        updateDefaultBadge(val);
        toast(data.message || 'Saved as your study Bible');
      } else {
        toast((data && data.error) || 'Could not save — try again');
      }
    });

    // Resume last place (version already applied above)
    const startBook = resumeBook || currentBook || 'John';
    const startCh = parseInt(resumeChapter, 10) || 1;
    const startV = parseInt(resumeVerse, 10) || 1;
    currentBook = startBook;
    prepareBook(startBook, { chapter: startCh, scrollToVerse: startV });
  });
})();