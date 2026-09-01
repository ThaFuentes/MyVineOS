// Standalone podium teleprompter — viewport-fixed bar is in the HTML/CSS.
// This script only handles play, speed, font, double-space, and line marks.

document.addEventListener('DOMContentLoaded', () => {
  const scrollEl = document.getElementById('podium-scroll');
  const content = document.getElementById('podium-content');
  const playPauseBtn = document.getElementById('play-pause-btn');
  const playPauseMini = document.getElementById('play-pause-mini');
  const speedSlider = document.getElementById('speed-slider');
  const speedDisplay = document.getElementById('speed-display');
  const fontSlider = document.getElementById('font-size-slider');
  const timerEl = document.getElementById('timer');
  const resetBtn = document.getElementById('reset-btn');
  const fsBtn = document.getElementById('exit-fullscreen-btn');
  const doubleToggle = document.getElementById('double-space-toggle');
  const doubleLabel = document.getElementById('double-space-label');
  const bar = document.getElementById('podium-bar');

  if (!scrollEl || !content) return;

  let scrolling = false;
  let speed = 1.0;
  let startTime = null;
  let animationFrame = null;
  let currentLine = null;
  let prevLine = null;

  // Pad under fixed top bar
  function padForBar() {
    if (!bar) return;
    const h = Math.ceil(bar.getBoundingClientRect().height || 100);
    scrollEl.style.paddingTop = (h + 16) + 'px';
  }
  padForBar();
  window.addEventListener('resize', padForBar);

  // Font size
  const savedSize = localStorage.getItem('podiumFontSize');
  if (savedSize && fontSlider) {
    fontSlider.value = savedSize;
    content.style.fontSize = savedSize + 'px';
  }
  fontSlider?.addEventListener('input', (e) => {
    content.style.fontSize = e.target.value + 'px';
    localStorage.setItem('podiumFontSize', e.target.value);
    // Debounce re-wrap so line breaks match new size
    clearTimeout(fontSlider._wrapTimer);
    fontSlider._wrapTimer = setTimeout(() => {
      if (typeof rebuildLines === 'function') rebuildLines();
    }, 180);
  });

  // Double space
  function applyDouble(on) {
    content.classList.toggle('double', on);
    if (doubleToggle) doubleToggle.checked = on;
    doubleLabel?.classList.toggle('on', on);
    localStorage.setItem('podiumDoubleSpace', on ? '1' : '0');
    padForBar();
    // Line wraps change with line-height
    clearTimeout(applyDouble._t);
    applyDouble._t = setTimeout(() => {
      if (typeof rebuildLines === 'function') rebuildLines();
    }, 120);
  }
  // Apply double-space class only first; full wrap happens in initLines
  content.classList.toggle('double', localStorage.getItem('podiumDoubleSpace') === '1');
  if (doubleToggle) doubleToggle.checked = localStorage.getItem('podiumDoubleSpace') === '1';
  doubleLabel?.classList.toggle('on', localStorage.getItem('podiumDoubleSpace') === '1');
  doubleToggle?.addEventListener('change', () => applyDouble(!!doubleToggle.checked));

  // ── Real visual LINES (not whole paragraphs/sections) ───────
  // Uses Range.getClientRects so wraps match what you see on screen.

  function makeLineEl(text) {
    const div = document.createElement('div');
    div.className = 'podium-line';
    div.textContent = text;
    div.tabIndex = 0;
    div.setAttribute('role', 'button');
    div.setAttribute('aria-label', 'Mark this line');
    return div;
  }

  /** Split plain text into visual screen lines inside a measuring box. */
  function visualLinesFromText(text, measureBox) {
    const raw = (text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    if (!raw.trim()) return [];

    // Keep soft paragraph breaks as separate blank lines
    const paragraphs = raw.split('\n');
    const out = [];

    paragraphs.forEach((para, pIdx) => {
      if (!para.trim()) {
        if (pIdx > 0) out.push(''); // blank line gap
        return;
      }

      // Measure wrap of this paragraph in the same width/font as content
      measureBox.textContent = '';
      const tn = document.createTextNode(para);
      measureBox.appendChild(tn);

      const range = document.createRange();
      let lineStart = 0;
      let lastTop = null;

      for (let i = 0; i < para.length; i++) {
        range.setStart(tn, i);
        range.setEnd(tn, Math.min(i + 1, para.length));
        const rects = range.getClientRects();
        if (!rects.length) continue;
        const top = Math.round(rects[0].top);
        if (lastTop === null) {
          lastTop = top;
          continue;
        }
        if (top > lastTop + 1) {
          // New visual line starts at i
          const slice = para.slice(lineStart, i).replace(/\s+$/, '');
          if (slice.trim()) out.push(slice);
          // skip leading spaces on next line
          let ns = i;
          while (ns < para.length && para[ns] === ' ') ns++;
          lineStart = ns;
          lastTop = top;
          i = ns - 1;
        }
      }
      const tail = para.slice(lineStart).replace(/\s+$/, '');
      if (tail.trim()) out.push(tail);
    });

    measureBox.textContent = '';
    return out;
  }

  /** Pull plain text chunks from HTML, honoring <br> and block tags as breaks. */
  function htmlToSoftParagraphs(el) {
    const chunks = [];
    let buf = '';

    function flush() {
      if (buf.length) {
        chunks.push(buf);
        buf = '';
      }
    }

    function walk(node) {
      if (node.nodeType === Node.TEXT_NODE) {
        buf += node.textContent || '';
        return;
      }
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      const tag = node.tagName;
      if (tag === 'BR') {
        buf += '\n';
        return;
      }
      if (tag === 'SCRIPT' || tag === 'STYLE') return;
      const block = /^(P|DIV|LI|H1|H2|H3|H4|H5|H6|BLOCKQUOTE|TR|SECTION|ARTICLE)$/.test(tag);
      if (block) {
        flush();
        Array.from(node.childNodes).forEach(walk);
        flush();
        chunks.push('\n'); // paragraph gap
        return;
      }
      Array.from(node.childNodes).forEach(walk);
    }

    Array.from(el.childNodes).forEach(walk);
    flush();
    // Join soft chunks: \n markers already inside
    return chunks.join('').replace(/\n{3,}/g, '\n\n');
  }

  function explodeElementToLines(el, { keepHeadingStyle = false } = {}) {
    if (!el || el.dataset.linesReady === '1') return;
    const soft = htmlToSoftParagraphs(el);
    if (!soft.trim()) return;

    // Measuring box: same width & font as the element
    const measure = document.createElement('div');
    const cs = window.getComputedStyle(el);
    measure.style.cssText = [
      'position:absolute',
      'visibility:hidden',
      'pointer-events:none',
      'left:0',
      'top:0',
      'height:auto',
      'white-space:normal',
      'word-wrap:break-word',
      'overflow-wrap:anywhere',
      `width:${el.clientWidth || content.clientWidth || 700}px`,
      `font-size:${cs.fontSize}`,
      `font-family:${cs.fontFamily}`,
      `font-weight:${cs.fontWeight}`,
      `font-style:${cs.fontStyle}`,
      `line-height:${cs.lineHeight}`,
      `letter-spacing:${cs.letterSpacing}`,
      `padding:0`,
      'margin:0',
      'border:0',
    ].join(';');
    document.body.appendChild(measure);

    const lines = visualLinesFromText(soft, measure);
    document.body.removeChild(measure);

    el.textContent = '';
    el.dataset.linesReady = '1';
    lines.forEach((lineText) => {
      if (lineText === '') {
        const gap = document.createElement('div');
        gap.className = 'podium-line-gap';
        gap.setAttribute('aria-hidden', 'true');
        gap.innerHTML = '&nbsp;';
        el.appendChild(gap);
        return;
      }
      const lineEl = makeLineEl(lineText);
      if (keepHeadingStyle) lineEl.classList.add('podium-line-heading');
      el.appendChild(lineEl);
    });
  }

  function wrapLines() {
    // Headings / short labels → still explode (usually 1 visual line)
    content.querySelectorAll(
      '.podium-title, .podium-passage, .podium-section-title, .podium-scripture'
    ).forEach((el) => explodeElementToLines(el, { keepHeadingStyle: true }));

    // Body text: real line-by-line
    content.querySelectorAll('.podium-body, .podium-notes-body').forEach((el) => {
      explodeElementToLines(el);
    });
  }

  // Wait a frame so font-size / layout width is final before measuring wraps
  function initLines() {
    padForBar();
    wrapLines();
  }
  requestAnimationFrame(() => requestAnimationFrame(initLines));

  // Re-split when font size / double-space changes (wraps change)
  function rebuildLines() {
    currentLine = null;
    prevLine = null;
    content.querySelectorAll('[data-original-html]').forEach((el) => {
      el.innerHTML = el.getAttribute('data-original-html') || '';
      delete el.dataset.linesReady;
    });
    wrapLines();
  }

  // Snapshot originals before first explode
  content.querySelectorAll(
    '.podium-body, .podium-notes-body, .podium-title, .podium-passage, .podium-section-title, .podium-scripture'
  ).forEach((el) => {
    if (!el.hasAttribute('data-original-html')) {
      el.setAttribute('data-original-html', el.innerHTML);
    }
  });

  function setCurrentLine(el) {
    if (!el || !el.classList.contains('podium-line') || el === currentLine) return;
    if (prevLine && prevLine !== currentLine) prevLine.classList.remove('is-prev');
    if (currentLine) {
      currentLine.classList.remove('is-current');
      currentLine.classList.add('is-prev');
      prevLine = currentLine;
    }
    el.classList.remove('is-prev');
    el.classList.add('is-current');
    currentLine = el;
    try {
      const rect = el.getBoundingClientRect();
      if (rect.top < (bar?.offsetHeight || 80) + 20 || rect.bottom > window.innerHeight - 90) {
        el.scrollIntoView({ block: 'center', behavior: 'smooth' });
      }
    } catch (e) { /* ignore */ }
  }

  content.addEventListener('click', (e) => {
    const line = e.target.closest('.podium-line');
    if (line && content.contains(line)) {
      e.preventDefault();
      setCurrentLine(line);
    }
  });

  // Play / scroll
  function setPlayUi(on) {
    const html = on
      ? '<i class="fas fa-pause" aria-hidden="true"></i> Pause'
      : '<i class="fas fa-play" aria-hidden="true"></i> Play';
    const mini = on
      ? '<i class="fas fa-pause" aria-hidden="true"></i>'
      : '<i class="fas fa-play" aria-hidden="true"></i>';
    if (playPauseBtn) playPauseBtn.innerHTML = html;
    if (playPauseMini) playPauseMini.innerHTML = mini;
  }

  function updateTimer() {
    if (!startTime || !timerEl) return;
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const mins = String(Math.floor(elapsed / 60)).padStart(2, '0');
    const secs = String(elapsed % 60).padStart(2, '0');
    timerEl.textContent = `${mins}:${secs}`;
  }

  function scrollLoop() {
    if (!scrolling) return;
    scrollEl.scrollTop += speed * 0.85;
    updateTimer();
    animationFrame = requestAnimationFrame(scrollLoop);
  }

  function togglePlay() {
    scrolling = !scrolling;
    setPlayUi(scrolling);
    if (scrolling) {
      if (!startTime) startTime = Date.now();
      scrollLoop();
    } else {
      cancelAnimationFrame(animationFrame);
    }
  }

  playPauseBtn?.addEventListener('click', togglePlay);
  playPauseMini?.addEventListener('click', togglePlay);

  speedSlider?.addEventListener('input', (e) => {
    speed = parseFloat(e.target.value) || 1;
    if (speedDisplay) speedDisplay.textContent = `${speed.toFixed(1)}x`;
  });

  resetBtn?.addEventListener('click', () => {
    scrollEl.scrollTop = 0;
    scrolling = false;
    setPlayUi(false);
    cancelAnimationFrame(animationFrame);
    startTime = null;
    if (timerEl) timerEl.textContent = '00:00';
  });

  document.addEventListener('keydown', (e) => {
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
    if (e.code === 'Space' && !e.target.classList?.contains('podium-line')) {
      e.preventDefault();
      togglePlay();
    } else if (e.code === 'ArrowLeft' && speedSlider) {
      speedSlider.value = String(Math.max(0.3, (parseFloat(speedSlider.value) || 1) - 0.1));
      speedSlider.dispatchEvent(new Event('input'));
    } else if (e.code === 'ArrowRight' && speedSlider) {
      speedSlider.value = String(Math.min(3, (parseFloat(speedSlider.value) || 1) + 0.1));
      speedSlider.dispatchEvent(new Event('input'));
    } else if (e.code === 'KeyR' && !e.ctrlKey && !e.metaKey) {
      resetBtn?.click();
    } else if (e.code === 'KeyD') {
      if (doubleToggle) {
        doubleToggle.checked = !doubleToggle.checked;
        doubleToggle.dispatchEvent(new Event('change'));
      }
    } else if (e.code === 'ArrowDown' || e.code === 'KeyJ') {
      const lines = Array.from(content.querySelectorAll('.podium-line'));
      if (!lines.length) return;
      e.preventDefault();
      const idx = currentLine ? lines.indexOf(currentLine) : -1;
      setCurrentLine(lines[Math.min(lines.length - 1, idx + 1)]);
    } else if (e.code === 'ArrowUp' || e.code === 'KeyK') {
      const lines = Array.from(content.querySelectorAll('.podium-line'));
      if (!lines.length) return;
      e.preventDefault();
      const idx = currentLine ? lines.indexOf(currentLine) : lines.length;
      setCurrentLine(lines[Math.max(0, idx - 1)]);
    }
  });

  fsBtn?.addEventListener('click', () => {
    if (document.fullscreenElement) {
      document.exitFullscreen?.();
    } else {
      document.documentElement.requestFullscreen?.().catch(() => {});
    }
  });

  document.addEventListener('fullscreenchange', () => {
    if (!fsBtn) return;
    fsBtn.innerHTML = document.fullscreenElement
      ? '<i class="fas fa-compress" aria-hidden="true"></i> Exit FS'
      : '<i class="fas fa-expand" aria-hidden="true"></i> Fullscreen';
    padForBar();
  });
});
