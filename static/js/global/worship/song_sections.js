/**
 * Worship song section builder + play order (arrangement).
 * Sections = unique content blocks; play order may repeat ids (e.g. chorus twice).
 */
(function () {
  const cfg = window.SONG_EDITOR || {};
  let sections = Array.isArray(cfg.sections) ? cfg.sections.map((s) => ({ ...s })) : [];
  let playOrder = Array.isArray(cfg.playOrder) ? cfg.playOrder.slice() : [];

  const listEl = document.getElementById('song-sections-list');
  const orderEl = document.getElementById('play-order-list');
  const orderHidden = document.getElementById('play-order-hidden');
  const pickEl = document.getElementById('play-order-pick');
  if (!listEl || !orderEl) return;

  const TYPE_LABELS = {
    intro: 'Intro',
    verse: 'Verse',
    prechorus: 'Pre-Chorus',
    chorus: 'Chorus',
    bridge: 'Bridge',
    tag: 'Tag',
    outro: 'Outro',
  };

  function uid() {
    return 's' + Math.random().toString(36).slice(2, 10);
  }

  function nextVerseLabel() {
    let max = 0;
    sections.forEach((s) => {
      if ((s.type || '') === 'verse') {
        const m = String(s.label || '').match(/(\d+)/);
        if (m) max = Math.max(max, parseInt(m[1], 10));
      }
    });
    return 'Verse ' + (max + 1);
  }

  function defaultLabel(type) {
    if (type === 'verse') return nextVerseLabel();
    if (type === 'prechorus') return 'Pre-Chorus';
    return TYPE_LABELS[type] || type;
  }

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function readCardsIntoState() {
    const cards = listEl.querySelectorAll('.song-section-card');
    const next = [];
    cards.forEach((card, i) => {
      const id = card.querySelector('[name="sec_id[]"]')?.value || uid();
      const type = card.querySelector('[name="sec_type[]"]')?.value || 'verse';
      const label = card.querySelector('[name="sec_label[]"]')?.value || TYPE_LABELS[type] || 'Section';
      const content = card.querySelector('[name="sec_content[]"]')?.value || '';
      next.push({ id, type, label, content, sort: i + 1, repeat: 1 });
    });
    sections = next;
    // Drop play order entries for removed sections
    const ids = new Set(sections.map((s) => s.id));
    playOrder = playOrder.filter((id) => ids.has(id));
  }

  function renderSections() {
    listEl.innerHTML = '';
    if (!sections.length) {
      listEl.innerHTML =
        '<p class="hint" style="margin:0;">No sections yet. Add Intro / Verse / Chorus, or paste lyrics.</p>';
      renderPlayOrder();
      return;
    }
    sections.forEach((sec, index) => {
      const card = document.createElement('div');
      card.className = 'song-section-card';
      card.dataset.type = sec.type || 'verse';
      card.dataset.id = sec.id;
      card.innerHTML = `
        <div class="sec-head">
          <input type="hidden" name="sec_id[]" value="${escapeHtml(sec.id)}">
          <label>Type
            <select name="sec_type[]" class="sec-type">
              ${Object.keys(TYPE_LABELS)
                .map(
                  (t) =>
                    `<option value="${t}" ${t === (sec.type || 'verse') ? 'selected' : ''}>${TYPE_LABELS[t]}</option>`
                )
                .join('')}
            </select>
          </label>
          <label style="flex:1; min-width:120px;">Label
            <input type="text" name="sec_label[]" class="sec-label" value="${escapeHtml(sec.label || '')}">
          </label>
          <div class="sec-actions">
            <button type="button" class="sec-up" title="Move up" ${index === 0 ? 'disabled' : ''}>↑</button>
            <button type="button" class="sec-down" title="Move down" ${index === sections.length - 1 ? 'disabled' : ''}>↓</button>
            <button type="button" class="sec-remove" title="Remove">×</button>
          </div>
        </div>
        <textarea name="sec_content[]" class="sec-content" placeholder="Lyrics for this section…">${escapeHtml(sec.content || '')}</textarea>
      `;
      listEl.appendChild(card);
    });
    renderPlayOrder();
  }

  function sectionById(id) {
    return sections.find((s) => s.id === id);
  }

  function renderPlayOrder() {
    orderEl.innerHTML = '';
    orderHidden.innerHTML = '';
    if (pickEl) {
      pickEl.innerHTML = '<option value="">Add section to order…</option>';
      sections.forEach((s) => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = `${s.label || s.type} (${s.type})`;
        pickEl.appendChild(opt);
      });
    }

    if (!playOrder.length) {
      orderEl.innerHTML =
        '<li style="opacity:0.65; border-style:dashed;">No play order yet — add sections above, then build the order (Chorus can appear more than once).</li>';
      return;
    }

    playOrder.forEach((id, index) => {
      const sec = sectionById(id) || { label: id, type: '?' };
      const li = document.createElement('li');
      li.dataset.id = id;
      li.innerHTML = `
        <span class="po-index">${index + 1}.</span>
        <span class="po-label">${escapeHtml(sec.label || id)}</span>
        <span class="po-type">${escapeHtml(sec.type || '')}</span>
        <div class="play-order-actions">
          <button type="button" class="po-up" title="Move up" ${index === 0 ? 'disabled' : ''}>↑</button>
          <button type="button" class="po-down" title="Move down" ${index === playOrder.length - 1 ? 'disabled' : ''}>↓</button>
          <button type="button" class="po-remove" title="Remove from order">×</button>
        </div>
      `;
      orderEl.appendChild(li);

      const hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = 'play_order[]';
      hidden.value = id;
      orderHidden.appendChild(hidden);
    });
  }

  function addSection(type) {
    readCardsIntoState();
    const id = uid();
    const label = defaultLabel(type);
    sections.push({
      id,
      type,
      label,
      content: '',
      sort: sections.length + 1,
      repeat: 1,
    });
    // Auto-append new section to play order once
    playOrder.push(id);
    renderSections();
    const ta = listEl.querySelector(`.song-section-card[data-id="${id}"] textarea`);
    if (ta) ta.focus();
  }

  function parseLyricsLocal(text) {
    const lines = String(text || '').replace(/\r\n/g, '\n').split('\n');
    const marker = /^\s*[\[\{\(]?\s*(verse\s*\d*|v\s*\d*|chorus|ch|bridge|br|pre-?chorus|prechorus|tag|intro|outro|ending|interlude)\s*[\]\}\)]?\s*:?\s*$/i;
    const out = [];
    let label = 'Lyrics';
    let type = 'verse';
    let buf = [];

    function flush() {
      const content = buf.join('\n').trim();
      if (!content) return;
      out.push({
        id: uid(),
        type,
        label,
        content,
        sort: out.length + 1,
        repeat: 1,
      });
    }

    lines.forEach((line) => {
      const stripped = line.trim();
      if (marker.test(stripped)) {
        flush();
        buf = [];
        label = stripped.replace(/^[\[\{\(]|[\]\}\)]$/g, '').replace(/:$/, '').trim();
        const low = label.toLowerCase();
        if (low.includes('pre') && low.includes('chorus')) type = 'prechorus';
        else if (low.includes('chorus') || low === 'ch' || low === 'refrain') type = 'chorus';
        else if (low.includes('bridge') || low === 'br') type = 'bridge';
        else if (low.includes('tag')) type = 'tag';
        else if (low.includes('intro')) type = 'intro';
        else if (low.includes('outro') || low.includes('ending')) type = 'outro';
        else if (low.includes('interlude') || low.includes('instrumental')) type = 'interlude';
        else type = 'verse';
        label = label.replace(/\b\w/g, (c) => c.toUpperCase());
        return;
      }
      buf.push(line);
    });
    flush();
    return out;
  }

  function getParseMode() {
    const el = document.querySelector('input[name="client_parse_mode"]:checked');
    return el ? el.value : 'auto';
  }

  function applyParsedSong(song) {
    if (!song) return;
    const secs = Array.isArray(song.sections) ? song.sections : [];
    sections = secs.map((s, i) => ({
      id: s.id || uid(),
      type: s.type || 'verse',
      label: s.label || defaultLabel(s.type || 'verse'),
      content: s.content || '',
      sort: s.sort || i + 1,
      repeat: s.repeat || 1,
    }));
    if (Array.isArray(song.play_order) && song.play_order.length) {
      const ids = new Set(sections.map((s) => s.id));
      playOrder = song.play_order.filter((id) => ids.has(id));
    } else {
      playOrder = sections.map((s) => s.id);
    }
    // Optional metadata fill if empty
    const titleEl = document.querySelector('input[name="title"]');
    const artistEl = document.querySelector('input[name="artist"]');
    const ccliEl = document.querySelector('input[name="ccli_song_number"]');
    const copyEl = document.querySelector('input[name="copyright_line"]');
    if (titleEl && !titleEl.value && song.title) titleEl.value = song.title;
    if (artistEl && !artistEl.value && song.artist) artistEl.value = song.artist;
    if (ccliEl && !ccliEl.value && song.ccli_song_number) ccliEl.value = song.ccli_song_number;
    if (copyEl && !copyEl.value && song.copyright_line) copyEl.value = song.copyright_line;
    renderSections();
  }

  function parseLyricsViaServer(text, mode) {
    const status = document.getElementById('lyrics-parse-status');
    const url = cfg.parseUrl;
    const finishLocal = (msg) => {
      const local = parseLyricsLocal(text);
      if (!local.length) {
        if (status) status.textContent = msg || 'No sections found.';
        else alert(msg || 'No sections found. Use markers like [Verse 1] or (Chorus).');
        return;
      }
      applyParsedSong({ sections: local });
      if (status) status.textContent = msg || 'Local rules · ' + local.length + ' sections';
      document.getElementById('lyrics-paste-box')?.classList.remove('is-open');
    };
    if (!url) {
      finishLocal();
      return;
    }
    if (status) status.textContent = mode === 'rules' ? 'Parsing…' : 'Parsing (may use AI)…';
    const body = new FormData();
    body.append('chart_text', text);
    body.append('parse_mode', mode || 'auto');
    body.append('title', document.querySelector('input[name="title"]')?.value || '');
    body.append('artist', document.querySelector('input[name="artist"]')?.value || '');
    if (cfg.csrf) body.append('csrf_token', cfg.csrf);
    fetch(url, {
      method: 'POST',
      body,
      credentials: 'same-origin',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        ...(cfg.csrf ? { 'X-CSRF-Token': cfg.csrf } : {}),
      },
    })
      .then((r) => r.json())
      .then((data) => {
        if (!data || !data.ok) {
          finishLocal((data && data.error) || 'Parse failed — using local rules');
          return;
        }
        applyParsedSong(data.song);
        if (status) {
          const s = data.song || {};
          status.textContent =
            'OK · ' +
            (s.parse_mode || mode) +
            (s.ai_used ? ' · AI' : '') +
            ' · ' +
            (s.sections || []).length +
            ' sections';
        }
        document.getElementById('lyrics-paste-box')?.classList.remove('is-open');
      })
      .catch(() => {
        finishLocal('Network error — local rules used');
      });
  }

  // Events
  document.getElementById('section-type-bar')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-add-type]');
    if (btn) {
      e.preventDefault();
      addSection(btn.getAttribute('data-add-type'));
    }
  });

  document.getElementById('toggle-paste')?.addEventListener('click', () => {
    document.getElementById('lyrics-paste-box')?.classList.toggle('is-open');
  });
  document.getElementById('lyrics-paste-cancel')?.addEventListener('click', () => {
    document.getElementById('lyrics-paste-box')?.classList.remove('is-open');
  });
  document.getElementById('lyrics-parse-btn')?.addEventListener('click', () => {
    const text = (document.getElementById('lyrics-paste-input')?.value || '').trim();
    if (!text) {
      alert('Paste a chord chart or lyrics first (ChordPro, chord-over-lyrics, or [Verse]/[Chorus] markers).');
      return;
    }
    parseLyricsViaServer(text, getParseMode());
  });

  listEl.addEventListener('click', (e) => {
    const card = e.target.closest('.song-section-card');
    if (!card) return;
    const cards = [...listEl.querySelectorAll('.song-section-card')];
    const idx = cards.indexOf(card);
    if (e.target.closest('.sec-up') && idx > 0) {
      readCardsIntoState();
      [sections[idx - 1], sections[idx]] = [sections[idx], sections[idx - 1]];
      renderSections();
    } else if (e.target.closest('.sec-down') && idx < cards.length - 1) {
      readCardsIntoState();
      [sections[idx + 1], sections[idx]] = [sections[idx], sections[idx + 1]];
      renderSections();
    } else if (e.target.closest('.sec-remove')) {
      readCardsIntoState();
      const id = sections[idx]?.id;
      sections.splice(idx, 1);
      playOrder = playOrder.filter((x) => x !== id);
      renderSections();
    }
  });

  listEl.addEventListener('change', (e) => {
    if (e.target.classList.contains('sec-type')) {
      readCardsIntoState();
      const card = e.target.closest('.song-section-card');
      const id = card?.dataset.id;
      const sec = sections.find((s) => s.id === id);
      if (sec) {
        sec.type = e.target.value;
        // refresh accent via re-render if label empty
        renderSections();
      }
    }
  });

  listEl.addEventListener('input', () => {
    // keep state soft-synced for pick dropdown labels
    // (full read on order actions)
  });

  document.getElementById('play-order-add-btn')?.addEventListener('click', () => {
    readCardsIntoState();
    const id = pickEl?.value;
    if (!id) return;
    playOrder.push(id);
    renderPlayOrder();
  });

  document.getElementById('play-order-rebuild-btn')?.addEventListener('click', () => {
    readCardsIntoState();
    playOrder = sections.map((s) => s.id);
    renderPlayOrder();
  });

  orderEl.addEventListener('click', (e) => {
    const li = e.target.closest('li[data-id]');
    if (!li) return;
    const items = [...orderEl.querySelectorAll('li[data-id]')];
    const idx = items.indexOf(li);
    if (e.target.closest('.po-up') && idx > 0) {
      [playOrder[idx - 1], playOrder[idx]] = [playOrder[idx], playOrder[idx - 1]];
      renderPlayOrder();
    } else if (e.target.closest('.po-down') && idx < playOrder.length - 1) {
      [playOrder[idx + 1], playOrder[idx]] = [playOrder[idx], playOrder[idx + 1]];
      renderPlayOrder();
    } else if (e.target.closest('.po-remove')) {
      playOrder.splice(idx, 1);
      renderPlayOrder();
    }
  });

  document.getElementById('song-edit-form')?.addEventListener('submit', () => {
    readCardsIntoState();
    // ensure hidden play_order fields current
    renderPlayOrder();
  });

  // Init: if empty play order but have sections, default one-pass
  if (sections.length && !playOrder.length) {
    playOrder = sections.map((s) => s.id);
  }
  // ensure ids
  sections = sections.map((s, i) => ({
    id: s.id || uid(),
    type: (s.type || 'verse').toLowerCase(),
    label: s.label || defaultLabel((s.type || 'verse').toLowerCase()),
    content: s.content || '',
    sort: s.sort || i + 1,
    repeat: s.repeat || 1,
  }));

  renderSections();
})();
