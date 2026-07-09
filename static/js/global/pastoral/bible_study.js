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

  const el = (id) => document.getElementById(id);
  const main = () => el('bible-reader-content');
  const api = '/pastoral/bible';

  function getTranslation() {
    return el('bible-translation')?.value || null;
  }

  function getActiveSermonId() {
    const v = el('bible-sermon-select')?.value;
    return v ? parseInt(v, 10) : null;
  }

  function updateSermonBar() {
    activeSermonId = getActiveSermonId();
    const openBtn = el('bible-open-sermon-btn');
    if (openBtn) {
      if (activeSermonId) {
        openBtn.href = urls.sermonEdit.replace('/0', `/${activeSermonId}`);
        openBtn.classList.remove('disabled');
      } else {
        openBtn.href = '#';
        openBtn.classList.add('disabled');
      }
    }
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

  function actionButtonsHtml(opts) {
    const ref = escapeAttr(opts.reference || '');
    const text = escapeAttr(opts.text || '');
    const book = escapeAttr(opts.book || '');
    return `
      <div class="content-actions">
        <button type="button" class="btn btn-outline-secondary btn-sm" data-act="copy"
          data-ref="${ref}" data-text="${text}">Copy</button>
        <button type="button" class="btn btn-cyan btn-sm" data-act="sermon"
          data-ref="${ref}" data-text="${text}" data-book="${book}"
          data-chapter="${opts.chapter || ''}" data-verse="${opts.verse || ''}">Sermon</button>
        <button type="button" class="btn btn-outline-cyan btn-sm" data-act="illustration"
          data-ref="${ref}" data-text="${text}" data-book="${book}"
          data-chapter="${opts.chapter || ''}" data-verse="${opts.verse || ''}"
          data-strongs="${escapeAttr(opts.strongs || '')}">Save</button>
      </div>`;
  }

  function bindActionButtons(root) {
    if (!root) return;
    root.querySelectorAll('[data-act="copy"]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const payload = btn.dataset.ref && btn.dataset.text
          ? `${btn.dataset.ref} — ${btn.dataset.text}` : btn.dataset.text || btn.dataset.ref;
        navigator.clipboard.writeText(payload).then(() => toast('Copied to clipboard'));
      });
    });
    root.querySelectorAll('[data-act="sermon"]').forEach((btn) => {
      btn.addEventListener('click', (e) => { e.stopPropagation(); insertToSermon(btn); });
    });
    root.querySelectorAll('[data-act="illustration"]').forEach((btn) => {
      btn.addEventListener('click', (e) => { e.stopPropagation(); saveIllustration(btn); });
    });
  }

  async function insertToSermon(btn) {
    let sermonId = getActiveSermonId();
    if (!sermonId) {
      sermonId = await quickCreateSermon(btn.dataset.ref || 'Scripture');
      if (!sermonId) return;
    }
    const resp = await fetch(`${api}/insert/${sermonId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        reference: btn.dataset.ref,
        text: btn.dataset.text,
        book: btn.dataset.book,
        chapter: btn.dataset.chapter ? parseInt(btn.dataset.chapter, 10) : undefined,
        verse: btn.dataset.verse ? parseInt(btn.dataset.verse, 10) : undefined,
        translation: getTranslation(),
      }),
    });
    const data = await resp.json();
    if (data.status === 'success') {
      btn.textContent = 'Inserted ✓';
      btn.disabled = true;
      toast('Inserted into sermon');
    } else toast(data.message || 'Insert failed');
  }

  async function saveIllustration(btn) {
    const resp = await fetch(urls.saveIllustration, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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
    const data = await resp.json();
    if (data.status === 'success') {
      btn.textContent = 'Saved ✓';
      btn.disabled = true;
      toast('Saved to illustrations');
    } else toast(data.message || 'Save failed');
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
    const sel = el('bible-chapter-select');
    if (!sel) return;
    sel.innerHTML = '';
    if (!max) { sel.appendChild(new Option('—', '')); return; }
    for (let i = 1; i <= max; i++) sel.appendChild(new Option(String(i), String(i)));
    sel.value = String(Math.min(currentChapter, max) || 1);
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

  async function prepareBook(book) {
    currentTranslation = getTranslation();
    try {
      const url = `${api}/chapter/${encodeURIComponent(book)}/1` +
        (currentTranslation ? `?translation=${encodeURIComponent(currentTranslation)}` : '');
      const resp = await fetch(url);
      if (!resp.ok) throw new Error('no book');
      const data = await resp.json();
      maxChapter = data.max_chapter || 1;
      populateChapterSelect(maxChapter);
      loadChapter(1);
    } catch (e) {
      maxChapter = 0;
      populateChapterSelect(0);
      main().innerHTML = '<p class="text-muted">No verses for this book.</p>';
    }
  }

  async function loadChapter(chapter) {
    currentTranslation = getTranslation();
    if (maxChapter > 0) chapter = Math.max(1, Math.min(chapter, maxChapter));
    currentChapter = chapter;
    const chSel = el('bible-chapter-select');
    if (chSel?.options.length) chSel.value = String(chapter);

    main().innerHTML = '<p class="text-muted small">Loading...</p>';
    const title = el('bible-reader-title');

    try {
      const url = `${api}/chapter/${encodeURIComponent(currentBook)}/${chapter}` +
        (currentTranslation ? `?translation=${encodeURIComponent(currentTranslation)}` : '');
      const resp = await fetch(url);
      if (!resp.ok) throw new Error('not found');
      const data = await resp.json();
      maxChapter = data.max_chapter || chapter;
      populateChapterSelect(maxChapter);
      if (chSel) chSel.value = String(chapter);
      if (title) title.textContent = `${data.book} ${data.chapter}`;
      renderVersePicker(data.verses);
      renderChapter(data);
      updateNavButtons();
    } catch (e) {
      main().innerHTML = '<p class="text-muted">No verses for this chapter.</p>';
      if (title) title.textContent = `${currentBook} ${chapter}`;
      renderVersePicker([]);
      updateNavButtons();
    }
  }

  function renderChapter(data) {
    const reader = main();
    let html = '';
    (data.verses || []).forEach((v) => {
      const ref = `${data.book} ${data.chapter}:${v.verse}`;
      const strongs = (data.strongs && data.strongs[v.verse]) || [];
      html += `<div class="bible-verse-line" data-verse="${v.verse}">`;
      html += `<span class="bible-verse-num">${v.verse}</span>`;
      html += `<span class="bible-verse-text">${linkStrongsInVerse(v.text, strongs)}</span>`;
      html += actionButtonsHtml({ reference: ref, text: v.text, book: data.book, chapter: data.chapter, verse: v.verse });
      html += '</div>';
    });
    reader.innerHTML = html || '<p class="text-muted">Empty chapter.</p>';
    lastChapterHtml = reader.innerHTML;
    setMainView('chapter');
    bindChapterEvents();
  }

  function bindChapterEvents() {
    const reader = main();
    reader?.querySelectorAll('.strongs-word').forEach((node) => {
      node.addEventListener('click', () => showStrongs(node.dataset.strongs));
    });
    bindActionButtons(reader);
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
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeFlyouts(); });

    el('bible-chapter-select')?.addEventListener('change', () => {
      const ch = parseInt(el('bible-chapter-select').value, 10);
      if (ch) loadChapter(ch);
    });
    el('bible-search-btn')?.addEventListener('click', searchBible);
    el('bible-search-input')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') searchBible(); });
    el('strongs-search-btn')?.addEventListener('click', searchStrongs);
    el('strongs-search-input')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') searchStrongs(); });
    el('bible-prev-chapter')?.addEventListener('click', () => { closeFlyouts(); loadChapter(currentChapter - 1); });
    el('bible-next-chapter')?.addEventListener('click', () => { closeFlyouts(); loadChapter(currentChapter + 1); });
    el('bible-back-chapter')?.addEventListener('click', restoreChapter);
    el('bible-translation')?.addEventListener('change', () => prepareBook(currentBook));
    el('bible-sermon-select')?.addEventListener('change', updateSermonBar);
    el('bible-new-sermon-btn')?.addEventListener('click', async () => {
      const id = await quickCreateSermon(`${currentBook} ${currentChapter}`);
      if (id) updateSermonBar();
    });

    prepareBook(currentBook);
  });
})();