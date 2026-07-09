// app/static/js/global/pastoral/illustrations.js
// Full path: WebChurchMan/app/static/js/global/pastoral/illustrations.js
// File name: illustrations.js
// Brief, detailed purpose:
//   Illustrations sidebar functionality in the Sermon Editor.
//   • EXTREME DEBUG MODE: Immediate alert on ANY button click + detailed console logs
//   • If you see the alert → click registered, problem is in fetch/insert
//   • If no alert → script not running or element ID wrong
//   • Hardcoded loading, search, insert – maximum feedback
//   • Exact style/pattern from sermon_editor.js debug version

document.addEventListener('DOMContentLoaded', function () {
    console.log('%c[ILLUSTRATIONS SIDEBAR] Script fully loaded and DOM ready', 'color: lime; font-size: 20px; font-weight: bold');

    const searchInput = document.getElementById('illus-search');
    const illusList = document.getElementById('illus-list');
    const insertIllustrationBtn = document.getElementById('insert-illustration-btn'); // Toolbar button

    const sermonId = document.body.dataset.sermonId || null;

    if (!illusList) {
        console.error('[ILLUSTRATIONS SIDEBAR] FATAL: #illus-list missing');
        alert('FATAL ERROR: illustrations list container not found – template broken');
        return;
    }

    if (!sermonId) {
        console.error('[ILLUSTRATIONS SIDEBAR] FATAL: sermonId missing from body dataset');
        alert('FATAL ERROR: No sermon ID – cannot insert illustrations');
        return;
    }

    console.log('%c[ILLUSTRATIONS SIDEBAR] All required elements found – proceeding', 'color: lime; font-size: 18px');

    // Load recent illustrations on init
    async function loadIllustrations(query = '') {
        console.log('[ILLUSTRATIONS SIDEBAR] loadIllustrations called with query:', query);
        illusList.innerHTML = '<p class="text-muted small">Loading illustrations...</p>';

        try {
            const url = `/pastoral/illustrations/library_data?sermon_id=${sermonId}${query ? '&search=' + encodeURIComponent(query) : ''}`;
            console.log('[ILLUSTRATIONS SIDEBAR] Fetching from:', url);
            const resp = await fetch(url);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

            const data = await resp.json();
            console.log('[ILLUSTRATIONS SIDEBAR] Data received:', data);
            displayIllustrations(data.illustrations || []);
        } catch (err) {
            console.error('[ILLUSTRATIONS SIDEBAR] Load failed:', err);
            illusList.innerHTML = '<p class="text-danger small">Failed to load illustrations – check console/network.</p>';
        }
    }

    function displayIllustrations(illustrations) {
        console.log('[ILLUSTRATIONS SIDEBAR] displayIllustrations called with', illustrations.length, 'items');

        if (illustrations.length === 0) {
            illusList.innerHTML = '<p class="text-muted small">No illustrations found.</p>';
            return;
        }

        let html = '';
        illustrations.forEach(illus => {
            html += `
                <div class="illustration-card mb-3 p-3 border rounded glass-card">
                    <strong class="d-block mb-1">${illus.title}</strong>
                    <p class="small text-muted mb-2">${illus.content.substring(0, 150)}${illus.content.length > 150 ? '...' : ''}</p>
                    ${illus.source ? `<em class="small text-muted d-block mb-2">Source: ${illus.source}</em>` : ''}
                    <button class="btn btn-sm btn-cyan insert-illus-btn w-100" data-id="${illus.id}">
                        Insert into Sermon
                    </button>
                </div>
            `;
        });
        illusList.innerHTML = html;

        // MAXIMUM FEEDBACK: Bind with alert + logs
        document.querySelectorAll('.insert-illus-btn').forEach(btn => {
            btn.addEventListener('click', function () {
                alert('INSERT BUTTON CLICKED! ID: ' + btn.dataset.id + ' – Check console for logs.');
                console.log('%c[INSERT CLICK] REGISTERED for illustration ID:', 'color: yellow; background: black; font-size: 20px', btn.dataset.id);
                insertIllustration(btn.dataset.id);
            });
        });

        console.log('[ILLUSTRATIONS SIDEBAR] All insert buttons bound with debug alerts');
    }

    async function insertIllustration(illusId) {
        console.log('[ILLUSTRATIONS SIDEBAR] insertIllustration called for ID:', illusId);
        const btn = document.querySelector(`.insert-illus-btn[data-id="${illusId}"]`);
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = 'Inserting...';
        }

        try {
            const resp = await fetch(`/pastoral/illustrations/insert/${sermonId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ illustration_id: parseInt(illusId) })
            });

            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

            const data = await resp.json();
            console.log('[ILLUSTRATIONS SIDEBAR] Insert response:', data);

            const quill = window.SermonEditor?.getActiveQuill();
            if (!quill) throw new Error('No active Quill editor found');
            if (!data.html) throw new Error('No HTML returned from server');

            const range = quill.getSelection() || { index: quill.getLength() };
            quill.clipboard.dangerouslyPasteHTML(range.index, data.html);
            quill.setSelection(range.index + data.html.length);

            console.log('[ILLUSTRATIONS SIDEBAR] Successfully inserted HTML into sermon');
            alert('Illustration inserted successfully!');
        } catch (err) {
            console.error('[ILLUSTRATIONS SIDEBAR] Insert failed:', err);
            alert('Failed to insert illustration – check console/network tab.');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = 'Insert into Sermon';
            }
        }
    }

    // Search handler with debug
    if (searchInput) {
        console.log('%c[ILLUSTRATIONS SIDEBAR] Search input FOUND', 'color: lime; font-size: 18px');
        let searchTimeout;
        searchInput.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                console.log('[ILLUSTRATIONS SIDEBAR] Search triggered for:', searchInput.value.trim());
                loadIllustrations(searchInput.value.trim());
            }, 500);
        });
    } else {
        console.error('[ILLUSTRATIONS SIDEBAR] Search input #illus-search NOT FOUND');
        alert('ERROR: Search input missing – check template ID');
    }

    // Toolbar button focuses search
    if (insertIllustrationBtn) {
        console.log('%c[ILLUSTRATIONS SIDEBAR] Toolbar button FOUND', 'color: lime; font-size: 18px');
        insertIllustrationBtn.addEventListener('click', () => {
            alert('TOOLBAR BUTTON CLICKED! Focusing search...');
            searchInput?.focus();
        });
    } else {
        console.error('[ILLUSTRATIONS SIDEBAR] Toolbar button #insert-illustration-btn NOT FOUND');
    }

    // Initial load with debug
    console.log('[ILLUSTRATIONS SIDEBAR] Performing initial load');
    loadIllustrations();
});