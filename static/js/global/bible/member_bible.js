(function () {
  const cfg = window.MEMBER_BIBLE || {};
  const books = cfg.books || [];

  let currentBook = 'John';
  let currentChapter = 1;
  let maxChapter = 0;
  let mainView = 'chapter';
  let lastChapterHtml = '';

  const el = (id) => document.getElementById(id);
  const base = '/bible';
  const main = () => el('member-bible-content');

  function translation() {
    return el('member-bible-translation')?.value || null;
  }

  function toast(msg) {
    const t = el('member-bible-toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(toast._t);
    toast._t = setTimeout(() => t.classList.remove('show'), 2000);
  }

  function langLabel(language) {
    const l = (language || '').toLowerCase();
    if (l.includes('hebrew')) return 'Hebrew';
    if (l.includes('greek')) return 'Greek';
    if (l.includes('aram')) return 'Aramaic';
    return language || 'Original language';
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      toast('Copied to clipboard');
    } catch (e) {
      toast('Copy failed — check browser permissions');
    }
  }

  function copyBtn(ref, text, trCode) {
    const label = trCode ? `${ref} (${trCode})` : ref;
    return `<button type="button" class="btn btn-secondary btn-sm member-bible-copy-btn"
      data-copy-ref="${escapeAttr(label)}" data-copy-text="${escapeAttr(text)}">Copy</button>`;
  }

  function bindCopyButtons(root) {
    root?.querySelectorAll('.member-bible-copy-btn').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const ref = btn.dataset.copyRef || '';
        const text = btn.dataset.copyText || '';
        copyText(ref && text ? `${ref} — ${text}` : text || ref);
        btn.textContent = 'Copied ✓';
        setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
      });
    });
  }

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

  function scrollToChapterSection() {
    const section = el('member-bible-chapter-section');
    const body = section?.closest('.bible-flyout-body');
    if (!section || !body) return;
    requestAnimationFrame(() => {
      section.scrollIntoView({ behavior: 'smooth', block: 'start' });
      section.classList.remove('bible-anchor-flash');
      void section.offsetWidth;
      section.classList.add('bible-anchor-flash');
      setTimeout(() => section.classList.remove('bible-anchor-flash'), 900);
    });
  }

  function closeFlyouts() {
    el('member-canon-flyout')?.classList.remove('open');
    el('member-tools-flyout')?.classList.remove('open');
    el('member-bible-backdrop')?.classList.remove('open');
    el('member-canon-flyout')?.setAttribute('aria-hidden', 'true');
    el('member-tools-flyout')?.setAttribute('aria-hidden', 'true');
    el('member-bible-backdrop')?.setAttribute('aria-hidden', 'true');
    el('member-open-canon')?.classList.remove('active');
    el('member-open-tools')?.classList.remove('active');
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
    if (!max) {
      sel.appendChild(new Option('—', ''));
      return;
    }
    for (let i = 1; i <= max; i++) sel.appendChild(new Option(String(i), String(i)));
    sel.value = String(Math.min(currentChapter, max) || 1);
  }

  function renderVersePicker(verses) {
    const picker = el('member-bible-verse-picker');
    const meta = el('member-bible-chapter-meta');
    if (!picker) return;
    picker.innerHTML = '';
    const nums = (verses || []).map((v) => v.verse);
    if (!nums.length) {
      if (meta) meta.textContent = 'No verses in this chapter.';
      return;
    }
    if (meta) {
      meta.textContent = `${currentBook} ${currentChapter}: ${nums.length} verse${nums.length === 1 ? '' : 's'}`;
    }
    nums.forEach((n) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = String(n);
      btn.addEventListener('click', () => {
        if (mainView !== 'chapter') restoreChapter();
        scrollToVerse(n);
        closeFlyouts();
      });
      picker.appendChild(btn);
    });
    if (el('member-canon-flyout')?.classList.contains('open') && nums.length) {
      scrollToChapterSection();
    }
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
    } else {
      loadChapter(currentChapter);
    }
  }

  async function prepareBook(book) {
    const tr = translation();
    try {
      const url = `${base}/chapter/${encodeURIComponent(book)}/1` +
        (tr ? `?translation=${encodeURIComponent(tr)}` : '');
      const resp = await fetch(url);
      if (!resp.ok) throw new Error('empty');
      const data = await resp.json();
      maxChapter = data.max_chapter || 1;
      populateChapters(maxChapter);
      loadChapter(1);
    } catch (e) {
      maxChapter = 0;
      populateChapters(0);
      main().innerHTML = '<p class="text-muted">No text for this book in the selected translation.</p>';
    }
  }

  async function loadChapter(chapter) {
    const tr = translation();
    const trCode = tr || '';
    if (maxChapter > 0) chapter = Math.max(1, Math.min(chapter, maxChapter));
    currentChapter = chapter;
    const chSel = el('member-bible-chapter');
    if (chSel?.options.length) chSel.value = String(chapter);

    const content = main();
    const title = el('member-bible-title');
    if (content) content.innerHTML = '<p class="small text-muted">Loading…</p>';

    try {
      const url = `${base}/chapter/${encodeURIComponent(currentBook)}/${chapter}` +
        (tr ? `?translation=${encodeURIComponent(tr)}` : '');
      const resp = await fetch(url);
      if (!resp.ok) throw new Error('404');
      const data = await resp.json();
      maxChapter = data.max_chapter || chapter;
      populateChapters(maxChapter);
      if (chSel) chSel.value = String(chapter);
      if (title) title.textContent = `${data.book} ${data.chapter}`;
      renderVersePicker(data.verses);
      renderChapter(data, trCode);
      updateNav();
    } catch (e) {
      if (content) content.innerHTML = '<p class="text-muted">Chapter not found.</p>';
      renderVersePicker([]);
      if (title) title.textContent = `${currentBook} ${chapter}`;
      updateNav();
    }
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

  function renderChapter(data, trCode) {
    const content = main();
    if (!content) return;
    let html = '';
    (data.verses || []).forEach((v) => {
      const ref = `${data.book} ${data.chapter}:${v.verse}`;
      const strongs = (data.strongs && data.strongs[v.verse]) || [];
      html += `<div class="member-bible-verse" data-verse="${v.verse}">`;
      html += `<span class="member-bible-verse-num">${v.verse}</span>`;
      html += `<span>${linkStrongs(v.text, strongs)}</span>`;
      html += copyBtn(ref, v.text, trCode);
      html += '</div>';
    });
    content.innerHTML = html || '<p class="text-muted">Empty chapter.</p>';
    lastChapterHtml = content.innerHTML;
    setMainView('chapter');
    bindMainChapterEvents();
  }

  function bindMainChapterEvents() {
    const content = main();
    if (!content) return;
    content.querySelectorAll('.member-bible-strongs-word').forEach((node) => {
      node.addEventListener('click', () => showStrongs(node.dataset.strongs));
    });
    bindCopyButtons(content);
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
      const lang = langLabel(data.language);
      const copyLine = `${data.number} (${lang}) ${data.transliteration || ''} — ${data.definition || ''}`;
      let html = `<h3 class="bible-main-heading">Strong's ${escapeHtml(data.number)}</h3>`;
      html += `<div class="member-strongs-entry">`;
      html += `<span class="member-strongs-lang">${escapeHtml(lang)}</span>`;
      html += `<h4>${escapeHtml(data.transliteration || '')}</h4>`;
      if (data.lemma) html += `<p class="small"><em>${escapeHtml(data.lemma)}</em></p>`;
      html += `<p>${escapeHtml(data.definition || '')}</p>`;
      html += copyBtn(data.number, copyLine, '');
      if (data.occurrences?.length) {
        html += '<p class="small text-cyan mt-2">Found in scripture:</p><ul class="small">';
        data.occurrences.slice(0, 12).forEach((o) => {
          html += `<li><a href="#" class="text-cyan" data-goto="${escapeAttr(o.book)}|${o.chapter}|${o.verse}">${o.book} ${o.chapter}:${o.verse}</a></li>`;
        });
        html += '</ul>';
      }
      html += '</div>';
      content.innerHTML = html;
      bindCopyButtons(content);
      content.querySelectorAll('[data-goto]').forEach((a) => {
        a.addEventListener('click', (ev) => {
          ev.preventDefault();
          const [book, ch, v] = a.dataset.goto.split('|');
          currentBook = book;
          closeFlyouts();
          loadChapter(parseInt(ch, 10)).then(() => scrollToVerse(parseInt(v, 10)));
        });
      });
    } catch (e) {
      content.innerHTML = '<p class="text-muted">Entry not found.</p>';
    }
  }

  async function searchBible() {
    const q = (el('member-bible-search-q')?.value || '').trim();
    if (!q) return;
    const content = main();
    content.innerHTML = '<p class="small text-muted">Searching…</p>';
    closeFlyouts();
    setMainView('search');
    if (el('member-bible-title')) el('member-bible-title').textContent = `Search: ${q}`;

    const tr = translation();
    const url = `${base}/search?q=${encodeURIComponent(q)}&limit=25` +
      (tr ? `&translation=${encodeURIComponent(tr)}` : '');
    const resp = await fetch(url);
    const data = await resp.json();
    if (!data.verses?.length) {
      content.innerHTML = '<p class="text-muted">No results. Try another word or reference.</p>';
      return;
    }
    let html = `<h3 class="bible-main-heading">Search results (${data.verses.length})</h3>`;
    html += data.verses.map((v) => {
      const ref = v.reference || `${v.book} ${v.chapter}:${v.verse}`;
      return `<div class="member-bible-hit" data-book="${escapeAttr(v.book)}" data-ch="${v.chapter}" data-v="${v.verse}">
        <strong>${escapeHtml(ref)}</strong>
        <div class="small" style="margin-top:0.35rem;">${escapeHtml(v.text || '')}</div>
        ${copyBtn(ref, v.text, v.translation || tr)}
      </div>`;
    }).join('');
    content.innerHTML = html;
    content.querySelectorAll('.member-bible-hit').forEach((item) => {
      item.addEventListener('click', (e) => {
        if (e.target.closest('.member-bible-copy-btn')) return;
        currentBook = item.dataset.book;
        loadChapter(parseInt(item.dataset.ch, 10)).then(() => scrollToVerse(parseInt(item.dataset.v, 10)));
      });
    });
    bindCopyButtons(content);
  }

  async function searchStrongs() {
    const q = (el('member-strongs-q')?.value || '').trim();
    if (!q) return;
    const content = main();
    content.innerHTML = '<p class="small text-muted">Looking up…</p>';
    closeFlyouts();
    setMainView('strongs-list');
    if (el('member-bible-title')) el('member-bible-title').textContent = `Strong's: ${q}`;

    const resp = await fetch(`${base}/strongs/search?q=${encodeURIComponent(q)}`);
    const data = await resp.json();
    if (!data.entries?.length) {
      content.innerHTML = '<p class="text-muted">No Strong\'s matches.</p>';
      return;
    }
    let html = `<h3 class="bible-main-heading">Strong's matches (${data.entries.length})</h3>`;
    html += data.entries.map((e) => {
      const lang = langLabel(e.language);
      const line = `${e.number} (${lang}) — ${e.definition || ''}`;
      return `<div class="member-strongs-hit" data-num="${e.number}">
        <span class="member-strongs-lang">${escapeHtml(lang)}</span>
        <strong>${escapeHtml(e.number)}</strong> ${escapeHtml(e.transliteration || '')}
        <div class="small text-muted" style="margin-top:0.25rem;">${escapeHtml((e.definition || '').slice(0, 200))}</div>
        ${copyBtn(e.number, line, '')}
      </div>`;
    }).join('');
    content.innerHTML = html;
    content.querySelectorAll('.member-strongs-hit').forEach((hit) => {
      hit.addEventListener('click', (e) => {
        if (e.target.closest('.member-bible-copy-btn')) return;
        showStrongs(hit.dataset.num);
      });
    });
    bindCopyButtons(content);
  }

  function updateNav() {
    const prev = el('member-bible-prev');
    const next = el('member-bible-next');
    if (prev) prev.disabled = currentChapter <= 1;
    if (next) next.disabled = maxChapter > 0 ? currentChapter >= maxChapter : true;
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  function escapeAttr(s) { return escapeHtml(s).replace(/"/g, '&quot;'); }
  function escapeRegex(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

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
    el('member-open-tools')?.addEventListener('click', () => openFlyout('tools'));
    el('member-bible-backdrop')?.addEventListener('click', closeFlyouts);
    document.querySelectorAll('[data-close-flyout]').forEach((btn) => {
      btn.addEventListener('click', closeFlyouts);
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeFlyouts();
    });

    el('member-bible-chapter')?.addEventListener('change', () => {
      const ch = parseInt(el('member-bible-chapter').value, 10);
      if (ch) loadChapter(ch);
    });
    el('member-bible-search-btn')?.addEventListener('click', searchBible);
    el('member-bible-search-q')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') searchBible();
    });
    el('member-strongs-btn')?.addEventListener('click', searchStrongs);
    el('member-strongs-q')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') searchStrongs();
    });
    el('member-bible-prev')?.addEventListener('click', () => {
      closeFlyouts();
      loadChapter(currentChapter - 1);
    });
    el('member-bible-next')?.addEventListener('click', () => {
      closeFlyouts();
      loadChapter(currentChapter + 1);
    });
    el('member-bible-back')?.addEventListener('click', restoreChapter);
    el('member-bible-translation')?.addEventListener('change', () => prepareBook(currentBook));

    if (books.length) prepareBook(currentBook);
  });
})();