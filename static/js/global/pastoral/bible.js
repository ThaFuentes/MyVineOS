// app/static/js/global/pastoral/bible.js
// Full path: WebChurchMan/app/static/js/global/pastoral/bible.js
// File name: bible.js
// Brief, detailed purpose:
//   Bible sidebar functionality in the Sermon Editor.
//   - Search: Input + button → POST JSON to /bible/search → display results list
//   - Click result → load full chapter via GET /bible/chapter/<book>/<chapter>?translation=...
//   - Insert selected verse(s) into active Quill editor (via SermonEditor.getActiveQuill)
//   - Optional translation selector (defaults to server default)
//   - Results show reference + snippet; chapter view shows numbered verses
//   - Insert formats as blockquote with reference

document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('bible-search');
    const searchBtn = document.getElementById('bible-search-btn');
    const resultsDiv = document.getElementById('bible-results');
    const chapterDiv = document.getElementById('bible-chapter-view');
    const insertBibleBtn = document.getElementById('insert-bible-btn'); // Toolbar button

    let currentTranslation = null; // Could add selector later

    if (!searchInput || !searchBtn || !resultsDiv || !chapterDiv) return;

    // Search handler
    async function performSearch() {
        const query = searchInput.value.trim();
        if (!query) {
            resultsDiv.innerHTML = '<p class="text-muted small">Enter search terms...</p>';
            chapterDiv.innerHTML = '';
            return;
        }

        resultsDiv.innerHTML = '<p class="text-muted small">Searching...</p>';

        try {
            const params = new URLSearchParams({ q: query, limit: '30' });
            if (currentTranslation) params.set('translation', currentTranslation);
            const resp = await fetch('/pastoral/bible/search?' + params.toString());

            if (!resp.ok) throw new Error('Search failed');

            const data = await resp.json();
            displaySearchResults(data.verses);
        } catch (err) {
            resultsDiv.innerHTML = '<p class="text-danger small">Search error – try again.</p>';
        }
    }

    function displaySearchResults(verses) {
        if (!verses || verses.length === 0) {
            resultsDiv.innerHTML = '<p class="text-muted small">No results found.</p>';
            chapterDiv.innerHTML = '';
            return;
        }

        let html = '<ul class="list-unstyled small">';
        verses.forEach(v => {
            html += `
                <li class="mb-2 verse-result" data-book="${v.book}" data-chapter="${v.chapter}" data-verse="${v.verse}">
                    <strong>${v.reference}</strong><br>
                    <span class="text-muted">${v.text.substring(0, 200)}${v.text.length > 200 ? '...' : ''}</span>
                </li>
            `;
        });
        html += '</ul>';
        resultsDiv.innerHTML = html;

        // Click to load chapter
        document.querySelectorAll('.verse-result').forEach(el => {
            el.addEventListener('click', () => loadChapter(el.dataset.book, el.dataset.chapter));
        });
    }

    async function loadChapter(book, chapter) {
        chapterDiv.innerHTML = '<p class="text-muted small">Loading chapter...</p>';

        try {
            const slug = String(book || '').trim().toLowerCase().replace(/[_\s]+/g, '-').replace(/[^a-z0-9-]/g, '') || 'john';
            let url = `/pastoral/bible/chapter/${encodeURIComponent(slug)}/${chapter}?book=${encodeURIComponent(book)}`;
            if (currentTranslation) url += `&translation=${encodeURIComponent(currentTranslation)}`;
            const resp = await fetch(url);
            if (!resp.ok) throw new Error('Chapter load failed');

            const data = await resp.json();
            displayChapter(data);
        } catch (err) {
            chapterDiv.innerHTML = '<p class="text-danger small">Failed to load chapter.</p>';
        }
    }

    function displayChapter(data) {
        let html = `<h6 class="text-cyan">${data.book} ${data.chapter}</h6>`;
        html += '<ol class="verse-list small">';
        data.verses.forEach(v => {
            html += `<li value="${v.verse}" class="verse-item mb-2" data-verse="${v.verse}">
                <span class="verse-text">${v.text}</span>
            </li>`;
        });
        html += '</ol>';

        // Insert button per verse or whole chapter
        html += '<div class="mt-3 text-center">';
        html += '<button class="btn btn-sm btn-cyan insert-chapter-btn">Insert Entire Chapter</button>';
        html += '</div>';

        chapterDiv.innerHTML = html;

        // Verse selection for insert
        document.querySelectorAll('.verse-item').forEach(item => {
            item.addEventListener('click', () => {
                item.classList.toggle('selected');
            });
        });

        // Insert chapter
        document.querySelector('.insert-chapter-btn')?.addEventListener('click', () => insertSelectedVerses(data.book, data.chapter, data.verses));
    }

    function insertSelectedVerses(book, chapter, allVerses) {
        const selected = document.querySelectorAll('.verse-item.selected');
        let verses = selected.length > 0
            ? Array.from(selected).map(el => ({
                verse: el.dataset.verse,
                text: el.querySelector('.verse-text').textContent.trim()
            }))
            : allVerses;

        if (verses.length === 0) return;

        const quill = window.SermonEditor?.getActiveQuill();
        if (!quill) return;

        let html = '<blockquote class="bible-insertion">';
        html += `<p><strong>${book} ${chapter}</strong></p>`;
        verses.forEach(v => {
            html += `<p><sup>${v.verse}</sup> ${v.text}</p>`;
        });
        html += '</blockquote>';

        const range = quill.getSelection() || { index: quill.getLength() };
        quill.clipboard.dangerouslyPasteHTML(range.index, html);
        quill.setSelection(range.index + html.length);
    }

    // Bind search
    searchBtn.addEventListener('click', performSearch);
    searchInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') {
            e.preventDefault();
            performSearch();
        }
    });

    // Toolbar button opens sidebar or focuses search
    if (insertBibleBtn) {
        insertBibleBtn.addEventListener('click', () => {
            searchInput.focus();
        });
    }
});