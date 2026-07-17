/**
 * Worship Music Studio — real layered notation for worship charts.
 * Chords + melody notes sit ABOVE lyrics (playing order).
 * Guitar/bass TAB strings and drum grids for actual musical notes.
 */
(function (global) {
  'use strict';

  const CHORD_ROOTS = ['C', 'C#', 'Db', 'D', 'D#', 'Eb', 'E', 'F', 'F#', 'Gb', 'G', 'G#', 'Ab', 'A', 'A#', 'Bb', 'B'];
  const CHORD_QUAL = ['', 'm', '7', 'm7', 'maj7', 'sus2', 'sus4', 'dim', 'aug', '2', '6', '9', 'add9', '5'];
  const MELODY_NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B', '·'];
  const GUITAR_STRINGS = ['e', 'B', 'G', 'D', 'A', 'E']; // high e first (standard tab)
  const BASS_STRINGS = ['G', 'D', 'A', 'E'];
  const DRUM_VOICES = [
    { id: 'hh', label: 'HH (hi-hat)', char: 'x' },
    { id: 'sn', label: 'SN (snare)', char: 'o' },
    { id: 'kd', label: 'KD (kick)', char: 'O' },
    { id: 'ht', label: 'HT (high tom)', char: 't' },
    { id: 'mt', label: 'MT (mid tom)', char: 'T' },
    { id: 'lt', label: 'LT (floor)', char: 'f' },
    { id: 'cr', label: 'CR (crash)', char: 'X' },
  ];

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function tokenizeLyrics(text) {
    // Split into words + preserving spaces as separate tokens for alignment
    const lines = String(text || '').replace(/\r\n/g, '\n').split('\n');
    return lines.map((line) => {
      if (!line.trim()) return [{ t: ' ', kind: 'space' }];
      // Prefer splitting on spaces; keep punctuation with words
      return line.split(/(\s+)/).filter((p) => p !== '').map((p) =>
        /^\s+$/.test(p) ? { t: p, kind: 'space' } : { t: p, kind: 'word' }
      );
    });
  }

  function parseChordPro(content) {
    /** Extract plain lyrics + chord-at-word map from ChordPro [G]Amazing text */
    const lines = String(content || '').replace(/\r\n/g, '\n').split('\n');
    const lyricLines = [];
    const chordLines = [];
    lines.forEach((line) => {
      let lyrics = '';
      let chords = '';
      let i = 0;
      while (i < line.length) {
        if (line[i] === '[') {
          const end = line.indexOf(']', i);
          if (end > i) {
            const ch = line.slice(i + 1, end);
            // Place chord over next non-space position
            while (chords.length < lyrics.length) chords += ' ';
            chords += ch;
            i = end + 1;
            continue;
          }
        }
        lyrics += line[i];
        if (chords.length < lyrics.length) chords += ' ';
        i += 1;
      }
      lyricLines.push(lyrics);
      chordLines.push(chords.trimEnd());
    });
    return { lyrics: lyricLines.join('\n'), chordOverlay: chordLines.join('\n') };
  }

  function toChordPro(lyrics, chordOverlay) {
    const lLines = String(lyrics || '').replace(/\r\n/g, '\n').split('\n');
    const cLines = String(chordOverlay || '').replace(/\r\n/g, '\n').split('\n');
    return lLines
      .map((ly, li) => {
        const ch = cLines[li] || '';
        let out = '';
        let i = 0;
        while (i < ly.length) {
          // If a chord starts at this column (non-space in chord line)
          if (i < ch.length && ch[i] !== ' ') {
            // Read chord token until space or end
            let j = i;
            while (j < ch.length && ch[j] !== ' ') j++;
            const chord = ch.slice(i, j).trim();
            if (chord) out += '[' + chord + ']';
            // Skip chord columns that don't advance lyrics (already handled)
          }
          out += ly[i];
          i++;
        }
        // Chords past end of lyrics line
        if (ch.length > ly.length) {
          const rest = ch.slice(ly.length).trim();
          if (rest) out += ' [' + rest.split(/\s+/).filter(Boolean).join('] [') + ']';
        }
        return out;
      })
      .join('\n');
  }

  function emptyLayers() {
    return {
      lyrics: '',
      chords: '', // space-aligned overlay lines matching lyrics
      melody: '', // space-aligned note names
      guitar_tab: defaultTab(GUITAR_STRINGS, 16),
      bass_tab: defaultTab(BASS_STRINGS, 16),
      drums: emptyDrums(16),
    };
  }

  function defaultTab(strings, cols) {
    return strings.map((s) => s + '|' + '-'.repeat(cols) + '|').join('\n');
  }

  function emptyDrums(steps) {
    const grid = {};
    DRUM_VOICES.forEach((v) => {
      grid[v.id] = Array(steps).fill(0);
    });
    return { steps: steps, grid: grid, subdivision: '16th' };
  }

  function layersFromSection(sec) {
    let layers = emptyLayers();
    if (sec && sec.layers && typeof sec.layers === 'object') {
      layers = { ...layers, ...sec.layers };
      if (sec.layers.drums && typeof sec.layers.drums === 'object') {
        layers.drums = {
          steps: sec.layers.drums.steps || 16,
          subdivision: sec.layers.drums.subdivision || '16th',
          grid: { ...emptyDrums(16).grid, ...(sec.layers.drums.grid || {}) },
        };
      }
    }
    const content = sec && sec.content ? String(sec.content) : '';
    if (!layers.lyrics && content) {
      const parsed = parseChordPro(content);
      layers.lyrics = parsed.lyrics;
      if (!layers.chords) layers.chords = parsed.chordOverlay;
    }
    if (!layers.lyrics) layers.lyrics = content.replace(/\[[^\]]+\]/g, '');
    return layers;
  }

  function ensureChordLineLength(chords, lyrics) {
    const lLines = String(lyrics || '').split('\n');
    const cLines = String(chords || '').split('\n');
    return lLines
      .map((ly, i) => {
        let c = cLines[i] || '';
        if (c.length < ly.length) c = c + ' '.repeat(ly.length - c.length);
        return c;
      })
      .join('\n');
  }

  function buildStudioHtml(sec, chartFamily) {
    const layers = layersFromSection(sec);
    const fam = (chartFamily || 'full').toLowerCase();
    const showTab = fam === 'guitar' || fam === 'full' || fam === 'lead_guitar' || fam === 'rhythm_guitar';
    const showBass = fam === 'bass' || fam === 'full';
    const showDrums = fam === 'drums' || fam === 'full';
    const showMelody = fam === 'vocals' || fam === 'lyrics' || fam === 'full' || fam === 'keys';

    return `
      <div class="ms-studio" data-sec-id="${escapeHtml(sec.id)}">
        <div class="ms-toolbar">
          <span class="ms-toolbar-label">Music studio</span>
          <button type="button" class="ms-tab-btn is-active" data-ms-tab="stack">Chords + melody over lyrics</button>
          ${showTab ? '<button type="button" class="ms-tab-btn" data-ms-tab="guitar">Guitar TAB</button>' : ''}
          ${showBass ? '<button type="button" class="ms-tab-btn" data-ms-tab="bass">Bass TAB</button>' : ''}
          ${showDrums ? '<button type="button" class="ms-tab-btn" data-ms-tab="drums">Drums</button>' : ''}
          <button type="button" class="ms-tab-btn" data-ms-tab="raw">Raw / ChordPro</button>
        </div>

        <div class="ms-panel is-active" data-ms-panel="stack">
          <p class="ms-help">
            Click a lyric syllable, then pick a <strong>chord</strong> or <strong>melody note</strong>.
            Chords and notes sit <em>above</em> the words — the way you play them.
          </p>
          <div class="ms-stack-wrap">
            <div class="ms-stack-preview" data-role="stack-preview"></div>
          </div>
          <label class="ms-field-label">Lyrics (edit words — chords stay aligned by column)</label>
          <textarea class="ms-lyrics" data-role="lyrics" rows="4" spellcheck="true">${escapeHtml(layers.lyrics)}</textarea>
          <div class="ms-palettes">
            <div class="ms-palette-block">
              <div class="ms-field-label">Chord palette — select a word above, then click a chord</div>
              <div class="ms-chord-roots" data-role="chord-roots">
                ${CHORD_ROOTS.map((r) => `<button type="button" class="ms-chip" data-chord-root="${r}">${r}</button>`).join('')}
              </div>
              <div class="ms-chord-qual" data-role="chord-qual">
                ${CHORD_QUAL.map((q) => `<button type="button" class="ms-chip ms-chip-sm" data-chord-qual="${escapeHtml(q)}">${q || 'maj'}</button>`).join('')}
              </div>
              <button type="button" class="btn btn-secondary btn-small" data-role="clear-chord">Clear chord on selection</button>
            </div>
            ${
              showMelody
                ? `<div class="ms-palette-block">
              <div class="ms-field-label">Melody / vocal pitch notes (above lyrics)</div>
              <div class="ms-melody-notes" data-role="melody-notes">
                ${MELODY_NOTES.map((n) => `<button type="button" class="ms-chip" data-melody="${n}">${n === '·' ? 'rest' : n}</button>`).join('')}
              </div>
              <button type="button" class="btn btn-secondary btn-small" data-role="clear-melody">Clear note on selection</button>
            </div>`
                : ''
            }
          </div>
          <input type="hidden" data-role="chords" value="${escapeHtml(layers.chords)}">
          <input type="hidden" data-role="melody" value="${escapeHtml(layers.melody)}">
        </div>

        ${
          showTab
            ? `<div class="ms-panel" data-ms-panel="guitar">
          <p class="ms-help">Standard 6-string TAB (high <strong>e</strong> on top). Type frets <code>0-24</code>, use <code>-</code> for rest. Click a cell then a fret number.</p>
          <div class="ms-tab-editor" data-role="guitar-tab" data-strings="guitar"></div>
          <div class="ms-fret-bar" data-role="fret-bar-guitar">
            ${[0,1,2,3,4,5,6,7,8,9,10,12,14,15,17,19].map((f) => `<button type="button" class="ms-chip" data-fret="${f}">${f}</button>`).join('')}
            <button type="button" class="ms-chip" data-fret="-">—</button>
          </div>
        </div>`
            : ''
        }

        ${
          showBass
            ? `<div class="ms-panel" data-ms-panel="bass">
          <p class="ms-help">4-string bass TAB (G D A E). Enter frets for walking bass / root patterns.</p>
          <div class="ms-tab-editor" data-role="bass-tab" data-strings="bass"></div>
          <div class="ms-fret-bar" data-role="fret-bar-bass">
            ${[0,1,2,3,4,5,6,7,8,9,10,12].map((f) => `<button type="button" class="ms-chip" data-fret="${f}">${f}</button>`).join('')}
            <button type="button" class="ms-chip" data-fret="-">—</button>
          </div>
        </div>`
            : ''
        }

        ${
          showDrums
            ? `<div class="ms-panel" data-ms-panel="drums">
          <p class="ms-help">One bar of 16th notes. Click cells to toggle hits. Pattern = how the kit plays under this section.</p>
          <div class="ms-drum-grid" data-role="drum-grid"></div>
          <div class="ms-drum-presets">
            <button type="button" class="btn btn-secondary btn-small" data-drum-preset="rock">Rock basic</button>
            <button type="button" class="btn btn-secondary btn-small" data-drum-preset="ballad">Ballad</button>
            <button type="button" class="btn btn-secondary btn-small" data-drum-preset="clear">Clear bar</button>
          </div>
        </div>`
            : ''
        }

        <div class="ms-panel" data-ms-panel="raw">
          <p class="ms-help">ChordPro export for this section (synced from the stack). Advanced users can paste ChordPro here.</p>
          <textarea class="ms-raw sec-content" name="sec_content[]" rows="6">${escapeHtml(
            toChordPro(layers.lyrics, layers.chords) || layers.lyrics || sec.content || ''
          )}</textarea>
          <input type="hidden" name="sec_layers[]" data-role="layers-json" value="">
        </div>
      </div>
    `;
  }

  function parseTab(text, stringNames) {
    const lines = String(text || '').split('\n');
    const rows = stringNames.map((name) => {
      const line = lines.find((l) => l.trim().startsWith(name + '|') || l.trim().startsWith(name + ' |')) || '';
      const m = line.match(/\|([^|]*)\|?/);
      const body = m ? m[1] : '-'.repeat(16);
      return body.split('').map((ch) => (ch === ' ' ? '-' : ch));
    });
    const cols = Math.max(16, ...rows.map((r) => r.length));
    rows.forEach((r) => {
      while (r.length < cols) r.push('-');
    });
    return { strings: stringNames, cells: rows, cols };
  }

  function serializeTab(parsed) {
    return parsed.strings
      .map((name, si) => {
        const body = parsed.cells[si].join('');
        return name + '|' + body + '|';
      })
      .join('\n');
  }

  function renderTabEditor(el, text, stringNames) {
    const parsed = parseTab(text, stringNames);
    el._tabState = parsed;
    el._tabCursor = { s: 0, c: 0 };
    let html = '<div class="ms-tab-grid">';
    parsed.strings.forEach((name, si) => {
      html += `<div class="ms-tab-row"><span class="ms-tab-name">${escapeHtml(name)}</span>`;
      for (let c = 0; c < parsed.cols; c++) {
        const val = parsed.cells[si][c] || '-';
        html += `<button type="button" class="ms-tab-cell" data-s="${si}" data-c="${c}">${escapeHtml(val)}</button>`;
      }
      html += '</div>';
    });
    html += '</div>';
    el.innerHTML = html;
  }

  function renderDrumGrid(el, drums) {
    const steps = drums.steps || 16;
    const grid = drums.grid || emptyDrums(steps).grid;
    let html = '<div class="ms-drum-table"><div class="ms-drum-beat-labels"><span></span>';
    for (let i = 0; i < steps; i++) {
      const beat = Math.floor(i / 4) + 1;
      const sub = ['e', '+', 'a'][i % 4 === 0 ? -1 : (i % 4) - 1] || '';
      html += `<span class="ms-drum-beat">${i % 4 === 0 ? beat : sub}</span>`;
    }
    html += '</div>';
    DRUM_VOICES.forEach((v) => {
      const row = grid[v.id] || Array(steps).fill(0);
      html += `<div class="ms-drum-row"><span class="ms-drum-label">${escapeHtml(v.label)}</span>`;
      for (let i = 0; i < steps; i++) {
        html += `<button type="button" class="ms-drum-cell ${row[i] ? 'is-on' : ''}" data-voice="${v.id}" data-step="${i}">${row[i] ? v.char : '·'}</button>`;
      }
      html += '</div>';
    });
    html += '</div>';
    el.innerHTML = html;
    el._drums = { steps, grid: { ...grid }, subdivision: drums.subdivision || '16th' };
  }

  function renderStackPreview(studio) {
    const preview = studio.querySelector('[data-role="stack-preview"]');
    const lyrics = studio.querySelector('[data-role="lyrics"]').value;
    const chords = ensureChordLineLength(studio.querySelector('[data-role="chords"]').value, lyrics);
    const melody = ensureChordLineLength(studio.querySelector('[data-role="melody"]').value, lyrics);
    studio.querySelector('[data-role="chords"]').value = chords;
    studio.querySelector('[data-role="melody"]').value = melody;

    const lLines = lyrics.split('\n');
    const cLines = chords.split('\n');
    const mLines = melody.split('\n');
    let html = '';
    lLines.forEach((ly, li) => {
      const ch = cLines[li] || '';
      const mel = mLines[li] || '';
      html += '<div class="ms-line-block">';
      // Melody row
      html += '<div class="ms-overlay-line ms-melody-line">';
      for (let i = 0; i < ly.length; i++) {
        const mc = mel[i] && mel[i] !== ' ' ? mel[i] : '';
        // multi-char notes: look ahead
        let note = '';
        if (mel[i] && mel[i] !== ' ') {
          let j = i;
          while (j < mel.length && mel[j] !== ' ') j++;
          note = mel.slice(i, j);
        }
        if (note && (i === 0 || mel[i - 1] === ' ')) {
          html += `<span class="ms-mel-tok">${escapeHtml(note)}</span>`;
          i += note.length - 1;
        } else if (!note) {
          html += `<span class="ms-mel-pad">${ly[i] === ' ' ? '&nbsp;' : '&nbsp;'}</span>`;
        }
      }
      html += '</div>';
      // Chord row
      html += '<div class="ms-overlay-line ms-chord-line">';
      for (let i = 0; i < Math.max(ly.length, ch.length); i++) {
        if (ch[i] && ch[i] !== ' ' && (i === 0 || ch[i - 1] === ' ')) {
          let j = i;
          while (j < ch.length && ch[j] !== ' ') j++;
          const chord = ch.slice(i, j);
          html += `<span class="ms-ch-tok" data-col="${i}">${escapeHtml(chord)}</span>`;
          i = j - 1;
        } else {
          html += '<span class="ms-ch-pad">&nbsp;</span>';
        }
      }
      html += '</div>';
      // Lyrics clickable
      html += '<div class="ms-lyric-line">';
      for (let i = 0; i < ly.length; i++) {
        const ch = ly[i] === ' ' ? '&nbsp;' : escapeHtml(ly[i]);
        html += `<span class="ms-ly-ch ${studio._selCol === i && studio._selLine === li ? 'is-selected' : ''}" data-line="${li}" data-col="${i}">${ch}</span>`;
      }
      if (!ly.length) html += '<span class="ms-ly-empty">(empty line)</span>';
      html += '</div></div>';
    });
    preview.innerHTML = html || '<p class="ms-help">Type lyrics below, then click letters to attach chords / notes.</p>';
  }

  function setOverlayAt(overlay, line, col, token) {
    const lines = String(overlay || '').split('\n');
    while (lines.length <= line) lines.push('');
    let row = lines[line];
    // Clear existing token starting at col
    if (row.length < col) row = row + ' '.repeat(col - row.length);
    // Wipe old token under this region
    let end = col;
    while (end < row.length && row[end] !== ' ') end++;
    const wipeLen = Math.max(token.length, end - col, 1);
    row = row.substring(0, col) + ' '.repeat(wipeLen) + row.substring(col + wipeLen);
    if (token) {
      row = row.substring(0, col) + token + row.substring(col + token.length);
    }
    lines[line] = row;
    return lines.join('\n');
  }

  function collectLayers(studio) {
    const lyrics = studio.querySelector('[data-role="lyrics"]')?.value || '';
    const chords = studio.querySelector('[data-role="chords"]')?.value || '';
    const melody = studio.querySelector('[data-role="melody"]')?.value || '';
    const gEl = studio.querySelector('[data-role="guitar-tab"]');
    const bEl = studio.querySelector('[data-role="bass-tab"]');
    const dEl = studio.querySelector('[data-role="drum-grid"]');
    const guitar_tab = gEl && gEl._tabState ? serializeTab(gEl._tabState) : defaultTab(GUITAR_STRINGS, 16);
    const bass_tab = bEl && bEl._tabState ? serializeTab(bEl._tabState) : defaultTab(BASS_STRINGS, 16);
    const drums = dEl && dEl._drums ? dEl._drums : emptyDrums(16);
    return { lyrics, chords, melody, guitar_tab, bass_tab, drums };
  }

  function syncRaw(studio) {
    const layers = collectLayers(studio);
    const raw = studio.querySelector('textarea.ms-raw');
    if (raw) raw.value = toChordPro(layers.lyrics, layers.chords) || layers.lyrics;
    const hid = studio.querySelector('[data-role="layers-json"]');
    if (hid) hid.value = JSON.stringify(layers);
  }

  function bindStudio(studio, chartFamily) {
    const fam = (chartFamily || 'full').toLowerCase();
    studio._selLine = 0;
    studio._selCol = 0;
    studio._chordRoot = 'G';
    studio._chordQual = '';

    // Init guitar/bass/drums
    const gEl = studio.querySelector('[data-role="guitar-tab"]');
    const bEl = studio.querySelector('[data-role="bass-tab"]');
    const dEl = studio.querySelector('[data-role="drum-grid"]');
    const layers0 = {
      guitar_tab: studio.dataset.guitarTab || defaultTab(GUITAR_STRINGS, 16),
      bass_tab: studio.dataset.bassTab || defaultTab(BASS_STRINGS, 16),
      drums: emptyDrums(16),
    };
    try {
      const parsed = JSON.parse(studio.querySelector('[data-role="layers-json"]')?.value || '{}');
      if (parsed.guitar_tab) layers0.guitar_tab = parsed.guitar_tab;
      if (parsed.bass_tab) layers0.bass_tab = parsed.bass_tab;
      if (parsed.drums) layers0.drums = parsed.drums;
    } catch (e) {}

    if (gEl) renderTabEditor(gEl, layers0.guitar_tab, GUITAR_STRINGS);
    if (bEl) renderTabEditor(bEl, layers0.bass_tab, BASS_STRINGS);
    if (dEl) renderDrumGrid(dEl, layers0.drums);

    renderStackPreview(studio);
    syncRaw(studio);

    studio.addEventListener('click', (e) => {
      const tabBtn = e.target.closest('[data-ms-tab]');
      if (tabBtn) {
        studio.querySelectorAll('.ms-tab-btn').forEach((b) => b.classList.remove('is-active'));
        studio.querySelectorAll('.ms-panel').forEach((p) => p.classList.remove('is-active'));
        tabBtn.classList.add('is-active');
        const panel = studio.querySelector(`[data-ms-panel="${tabBtn.dataset.msTab}"]`);
        if (panel) panel.classList.add('is-active');
        return;
      }

      const ly = e.target.closest('.ms-ly-ch');
      if (ly) {
        studio._selLine = parseInt(ly.dataset.line, 10) || 0;
        studio._selCol = parseInt(ly.dataset.col, 10) || 0;
        renderStackPreview(studio);
        return;
      }

      const root = e.target.closest('[data-chord-root]');
      if (root) {
        studio._chordRoot = root.dataset.chordRoot;
        studio.querySelectorAll('[data-chord-root]').forEach((b) => b.classList.toggle('is-on', b === root));
        applyChord(studio);
        return;
      }
      const qual = e.target.closest('[data-chord-qual]');
      if (qual) {
        studio._chordQual = qual.dataset.chordQual || '';
        studio.querySelectorAll('[data-chord-qual]').forEach((b) => b.classList.toggle('is-on', b === qual));
        applyChord(studio);
        return;
      }
      if (e.target.closest('[data-role="clear-chord"]')) {
        const chEl = studio.querySelector('[data-role="chords"]');
        chEl.value = setOverlayAt(chEl.value, studio._selLine, studio._selCol, '');
        renderStackPreview(studio);
        syncRaw(studio);
        return;
      }
      const mel = e.target.closest('[data-melody]');
      if (mel) {
        const note = mel.dataset.melody === '·' ? '' : mel.dataset.melody;
        const mEl = studio.querySelector('[data-role="melody"]');
        mEl.value = setOverlayAt(mEl.value, studio._selLine, studio._selCol, note);
        renderStackPreview(studio);
        syncRaw(studio);
        return;
      }
      if (e.target.closest('[data-role="clear-melody"]')) {
        const mEl = studio.querySelector('[data-role="melody"]');
        mEl.value = setOverlayAt(mEl.value, studio._selLine, studio._selCol, '');
        renderStackPreview(studio);
        syncRaw(studio);
        return;
      }

      // Tab cells
      const cell = e.target.closest('.ms-tab-cell');
      if (cell) {
        const editor = cell.closest('.ms-tab-editor');
        editor._tabCursor = { s: +cell.dataset.s, c: +cell.dataset.c };
        editor.querySelectorAll('.ms-tab-cell').forEach((c) => c.classList.remove('is-selected'));
        cell.classList.add('is-selected');
        return;
      }
      const fretBtn = e.target.closest('[data-fret]');
      if (fretBtn) {
        const bar = fretBtn.closest('.ms-fret-bar');
        const editor =
          bar && bar.dataset.role === 'fret-bar-bass'
            ? studio.querySelector('[data-role="bass-tab"]')
            : studio.querySelector('[data-role="guitar-tab"]');
        if (editor && editor._tabState && editor._tabCursor) {
          const { s, c } = editor._tabCursor;
          const val = fretBtn.dataset.fret === '-' ? '-' : String(fretBtn.dataset.fret);
          // frets 10+ need two cells — simple: store first digit only for now in one cell as hex-like
          editor._tabState.cells[s][c] = val.length === 1 ? val : val.slice(-1);
          if (val.length > 1) {
            // mark multi-digit as letter map 10=a style for display
            const n = parseInt(val, 10);
            editor._tabState.cells[s][c] = n >= 10 ? String.fromCharCode(87 + n) : val; // 10->a
          }
          const names = editor.dataset.strings === 'bass' ? BASS_STRINGS : GUITAR_STRINGS;
          renderTabEditor(editor, serializeTab(editor._tabState), names);
          editor._tabCursor = { s, c: Math.min(c + 1, editor._tabState.cols - 1) };
          const next = editor.querySelector(`.ms-tab-cell[data-s="${editor._tabCursor.s}"][data-c="${editor._tabCursor.c}"]`);
          if (next) next.classList.add('is-selected');
          syncRaw(studio);
        }
        return;
      }

      // Drums
      const dcell = e.target.closest('.ms-drum-cell');
      if (dcell) {
        const grid = studio.querySelector('[data-role="drum-grid"]');
        const voice = dcell.dataset.voice;
        const step = +dcell.dataset.step;
        if (grid._drums) {
          const row = grid._drums.grid[voice] || [];
          row[step] = row[step] ? 0 : 1;
          grid._drums.grid[voice] = row;
          renderDrumGrid(grid, grid._drums);
          syncRaw(studio);
        }
        return;
      }
      const preset = e.target.closest('[data-drum-preset]');
      if (preset) {
        const grid = studio.querySelector('[data-role="drum-grid"]');
        if (!grid) return;
        const d = emptyDrums(16);
        if (preset.dataset.drumPreset === 'rock') {
          // kick 1 & 3, snare 2 & 4, hh 8ths
          for (let i = 0; i < 16; i++) {
            if (i % 2 === 0) d.grid.hh[i] = 1;
            if (i === 0 || i === 8) d.grid.kd[i] = 1;
            if (i === 4 || i === 12) d.grid.sn[i] = 1;
          }
        } else if (preset.dataset.drumPreset === 'ballad') {
          for (let i = 0; i < 16; i++) {
            if (i % 4 === 0) d.grid.hh[i] = 1;
            if (i === 0 || i === 8) d.grid.kd[i] = 1;
            if (i === 8) d.grid.sn[i] = 1;
          }
        }
        renderDrumGrid(grid, d);
        syncRaw(studio);
      }
    });

    studio.querySelector('[data-role="lyrics"]')?.addEventListener('input', () => {
      renderStackPreview(studio);
      syncRaw(studio);
    });
  }

  function applyChord(studio) {
    const chord = (studio._chordRoot || 'G') + (studio._chordQual || '');
    const chEl = studio.querySelector('[data-role="chords"]');
    chEl.value = setOverlayAt(chEl.value, studio._selLine, studio._selCol, chord);
    renderStackPreview(studio);
    syncRaw(studio);
  }

  function enhanceSectionCard(card, sec, chartFamily) {
    const existing = card.querySelector('.ms-studio');
    if (existing) return;
    const ta = card.querySelector('textarea.sec-content, textarea[name="sec_content[]"]');
    if (!ta) return;
    // Replace plain textarea with studio
    const wrap = document.createElement('div');
    wrap.innerHTML = buildStudioHtml(
      {
        id: sec.id,
        content: sec.content || ta.value,
        layers: sec.layers,
      },
      chartFamily
    );
    const studio = wrap.firstElementChild;
    // seed layers json
    const layers = layersFromSection({ content: sec.content || ta.value, layers: sec.layers });
    ta.replaceWith(studio);
    const hid = studio.querySelector('[data-role="layers-json"]');
    if (hid) hid.value = JSON.stringify(layers);
    studio.querySelector('[data-role="lyrics"]').value = layers.lyrics || '';
    studio.querySelector('[data-role="chords"]').value = layers.chords || '';
    studio.querySelector('[data-role="melody"]').value = layers.melody || '';
    studio.dataset.guitarTab = layers.guitar_tab || '';
    studio.dataset.bassTab = layers.bass_tab || '';
    bindStudio(studio, chartFamily);
  }

  function readAllStudios(listEl) {
    const cards = listEl.querySelectorAll('.song-section-card');
    const out = [];
    cards.forEach((card, i) => {
      const id = card.querySelector('[name="sec_id[]"]')?.value;
      const type = card.querySelector('[name="sec_type[]"]')?.value || 'verse';
      const label = card.querySelector('[name="sec_label[]"]')?.value || type;
      const studio = card.querySelector('.ms-studio');
      let content = '';
      let layers = emptyLayers();
      if (studio) {
        layers = collectLayers(studio);
        content = toChordPro(layers.lyrics, layers.chords) || layers.lyrics;
        const raw = studio.querySelector('textarea.ms-raw');
        if (raw && raw.value.trim()) {
          // Prefer raw if user edited ChordPro panel last
          const activeRaw = studio.querySelector('[data-ms-panel="raw"].is-active');
          if (activeRaw) {
            content = raw.value;
            const parsed = parseChordPro(content);
            layers.lyrics = parsed.lyrics;
            layers.chords = parsed.chordOverlay;
          } else {
            raw.value = content;
          }
        }
        const hid = studio.querySelector('[data-role="layers-json"]');
        if (hid) hid.value = JSON.stringify(layers);
      } else {
        content = card.querySelector('[name="sec_content[]"]')?.value || '';
      }
      out.push({ id, type, label, content, layers, sort: i + 1, repeat: 1 });
    });
    return out;
  }

  global.WorshipMusicStudio = {
    enhanceSectionCard,
    readAllStudios,
    layersFromSection,
    toChordPro,
    parseChordPro,
    emptyLayers,
  };
})(window);
