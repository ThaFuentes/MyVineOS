// app/static/js/pastoral/sermon_editor.js
// Full path: WebChurchMan/app/static/js/pastoral/sermon_editor.js
// File name: sermon_editor.js
// Brief, detailed purpose:
//   Client-side logic for the Sermon Editor – FINAL PRODUCTION VERSION (NO HARDCODED HTML).
//   • Clones the hidden server-rendered template → new sections are 100% identical to existing ones (all fields, buttons, vault tags, source, Save to Vault button).
//   • Save explicitly excludes the template → ZERO extra blank sections ever.
//   • Delegated remove, reorder (move-up/down), header updates.
//   • Per-section "Save to Vault" fully working (pre-fill + AJAX).
//   • Insert from Vault fully working (global button appends to end).
//   • Collaborators fully functional (add/remove + hidden inputs on save).
//   • Quill initialized safely on existing + new sections.
//   • No content loss or clearing bugs.

document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('sections-container');
    if (!container) {
        console.error('[SERMON EDITOR] #sections-container not found');
        return;
    }

    let currentCard = null;

    // Initialise Quill on all visible editors (skip hidden template)
    document.querySelectorAll('.quill-editor').forEach(el => {
        const card = el.closest('.section-card');
        if (card && card.hasAttribute('data-template')) return;
        if (!el.classList.contains('ql-container')) {
            new Quill(el, {
                theme: 'snow',
                modules: { toolbar: [['bold', 'italic', 'underline'], [{'list': 'ordered'}, {'list': 'bullet'}], ['link'], ['clean']] }
            });
        }
    });

    // Vault modal Quill
    const vaultQuill = new Quill('#vault-quill-editor', {
        theme: 'snow',
        modules: { toolbar: [['bold', 'italic', 'underline'], [{'list': 'ordered'}, {'list': 'bullet'}], ['link'], ['clean']] }
    });

    const saveVaultModal = document.getElementById('saveToVaultModal');

    // Reset modal on close – prevents stale data or wrong insertion position
    saveVaultModal.addEventListener('hidden.bs.modal', () => {
        currentCard = null;
        document.querySelectorAll('#vault-save-form input, #vault-save-form textarea').forEach(el => el.value = '');
        document.getElementById('vault-visibility').value = 'private';
        vaultQuill.root.innerHTML = '';
    });

    function updateAllHeaders() {
        document.querySelectorAll('.section-card:not([data-template])').forEach((card, i) => {
            const title = card.querySelector('.section-title').value.trim() || 'Untitled';
            const header = card.querySelector('.section-header-title');
            if (header) header.textContent = `Section ${i + 1}: ${title}`;
        });
    }
    updateAllHeaders();

    // Add new section – clone hidden template
    document.getElementById('add-section-btn').addEventListener('click', () => {
        const template = document.querySelector('.section-card[data-template]');
        if (!template) {
            console.error('[SERMON EDITOR] Hidden template not found – check template HTML');
            alert('Error: Section template missing. Check browser console.');
            return;
        }

        const newCard = template.cloneNode(true);
        newCard.removeAttribute('data-template');
        newCard.style.display = '';

        // Clear all fields for blank new section
        newCard.querySelectorAll('input, textarea').forEach(el => el.value = '');
        const quillEl = newCard.querySelector('.quill-editor');
        if (quillEl) quillEl.innerHTML = '';

        container.appendChild(newCard);

        // Initialise Quill on the new editor
        new Quill(quillEl, {
            theme: 'snow',
            modules: { toolbar: [['bold', 'italic', 'underline'], [{'list': 'ordered'}, {'list': 'bullet'}], ['link'], ['clean']] }
        });

        updateAllHeaders();
    });

    // Delegated: remove + reorder
    container.addEventListener('click', e => {
        const card = e.target.closest('.section-card');
        if (!card || card.hasAttribute('data-template')) return;

        if (e.target.closest('.remove-section')) {
            if (confirm('Permanently delete this section?')) {
                card.remove();
                updateAllHeaders();
            }
        } else if (e.target.closest('.move-up')) {
            const prev = card.previousElementSibling;
            if (prev && !prev.hasAttribute('data-template')) {
                container.insertBefore(card, prev);
                updateAllHeaders();
            }
        } else if (e.target.closest('.move-down')) {
            const next = card.nextElementSibling;
            if (next && !next.hasAttribute('data-template')) {
                container.insertBefore(next, card);
                updateAllHeaders();
            }
        }
    });

    container.addEventListener('input', e => {
        if (e.target.matches('.section-title')) updateAllHeaders();
    });

    // Save to Vault pre-fill (triggered by per-section button)
    saveVaultModal.addEventListener('show.bs.modal', event => {
        const button = event.relatedTarget;
        currentCard = button ? button.closest('.section-card') : null;

        if (currentCard) {
            const type = currentCard.querySelector('.section-type').value;
            const sectTitle = currentCard.querySelector('.section-title').value.trim() || 'Untitled';

            document.getElementById('vault-title').value = `${type.charAt(0).toUpperCase() + type.slice(1)}: ${sectTitle}`;
            document.getElementById('vault-section-type').value = type;
            document.getElementById('vault-scripture').value = currentCard.querySelector('.section-scripture').value.trim();
            document.getElementById('vault-source').value = currentCard.querySelector('.section-source').value.trim();
            document.getElementById('vault-notes').value = currentCard.querySelector('.section-notes').value.trim();
            const tagsEl = currentCard.querySelector('.section-vault-tags');
            document.getElementById('vault-tags').value = tagsEl ? tagsEl.value.trim() : '';
            document.getElementById('vault-visibility').value = 'private';

            const sectionQuill = Quill.find(currentCard.querySelector('.quill-editor'));
            vaultQuill.root.innerHTML = sectionQuill ? sectionQuill.root.innerHTML : '';
        }
    });

    // Save to Vault AJAX (full stable code)
    document.getElementById('vault-save-btn').addEventListener('click', () => {
        if (!currentCard) return;

        const data = {
            title: document.getElementById('vault-title').value.trim() || 'Untitled Section',
            section_type: document.getElementById('vault-section-type').value,
            scripture_reference: document.getElementById('vault-scripture').value.trim(),
            source_url: document.getElementById('vault-source').value.trim(),
            content: vaultQuill.root.innerHTML,
            notes: document.getElementById('vault-notes').value.trim(),
            tags: document.getElementById('vault-tags').value.trim(),
            visibility: document.getElementById('vault-visibility').value
        };

        fetch('{{ url_for("pastoral.vault.save_section_ajax") }}', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        })
        .then(res => res.json().catch(() => ({ status: 'error', message: 'Invalid response' })))
        .then(result => {
            const toastEl = document.getElementById('vault-toast');
            const toastBody = toastEl.querySelector('.toast-body');
            const toast = bootstrap.Toast.getOrCreateInstance(toastEl);

            if (result.status === 'success') {
                toastBody.textContent = 'Section saved to Vault!';
                toastEl.classList.remove('bg-danger');
                toastEl.classList.add('bg-success');
            } else {
                toastBody.textContent = result.message || 'Error saving to Vault';
                toastEl.classList.remove('bg-success');
                toastEl.classList.add('bg-danger');
            }
            toast.show();

            if (result.status === 'success') {
                bootstrap.Modal.getInstance(saveVaultModal).hide();
            }
        })
        .catch(err => {
            console.error(err);
            const toastEl = document.getElementById('vault-toast');
            const toastBody = toastEl.querySelector('.toast-body');
            toastBody.textContent = 'Save failed';
            toastEl.classList.add('bg-danger');
            bootstrap.Toast.getOrCreateInstance(toastEl).show();
        });
    });

    // Insert from Vault (full stable code)
    const insertVaultModal = document.getElementById('insertFromVaultModal');
    const searchInput = document.getElementById('vault-search-input');
    const resultsDiv = document.getElementById('vault-search-results');

    let searchTimeout;
    searchInput.addEventListener('input', () => {
        clearTimeout(searchTimeout);
        const q = searchInput.value.trim();
        searchTimeout = setTimeout(() => {
            if (q.length < 2) {
                resultsDiv.innerHTML = '<div class="col-12 text-center text-muted">Start typing to search...</div>';
                return;
            }

            fetch(`{{ url_for('pastoral.vault.search_ajax') }}?q=${encodeURIComponent(q)}`)
            .then(res => res.json())
            .then(data => {
                if (!data.items || data.items.length === 0) {
                    resultsDiv.innerHTML = '<div class="col-12 text-center text-muted">No results found</div>';
                    return;
                }

                resultsDiv.innerHTML = data.items.map(item => `
                    <div class="col-md-6">
                        <div class="card glass-card h-100 cursor-pointer" data-item='${JSON.stringify(item).replace(/'/g, "&#39;")}'>
                            <div class="card-body d-flex flex-column">
                                <h6 class="text-cyan">${escapeHtml(item.title || 'Untitled')}</h6>
                                ${item.scripture_reference ? `<p class="small text-muted mb-2">${escapeHtml(item.scripture_reference)}</p>` : ''}
                                ${item.source_url ? `<p class="small text-muted mb-2">Source: ${escapeHtml(item.source_url)}</p>` : ''}
                                <div class="flex-grow-1 overflow-hidden" style="max-height: 100px;">${item.content || ''}</div>
                                ${item.tags && item.tags.length ? `<div class="mt-2">${item.tags.map(t => `<span class="badge bg-secondary me-1">${escapeHtml(t)}</span>`).join('')}</div>` : ''}
                                <button class="btn btn-sm btn-outline-cyan mt-3 insert-vault-item">Insert</button>
                            </div>
                        </div>
                    </div>
                `).join('');
            })
            .catch(err => console.error(err));
        }, 300);
    });

    resultsDiv.addEventListener('click', e => {
        if (e.target.classList.contains('insert-vault-item')) {
            const card = e.target.closest('.card');
            const item = JSON.parse(card.dataset.item);

            const template = document.querySelector('.section-card[data-template]');
            const newCard = template.cloneNode(true);
            newCard.removeAttribute('data-template');
            newCard.style.display = '';

            newCard.querySelector('.section-type').value = item.section_type || 'point';
            newCard.querySelector('.section-title').value = item.title || '';
            newCard.querySelector('.section-scripture').value = item.scripture_reference || '';
            newCard.querySelector('.section-source').value = item.source_url || '';
            newCard.querySelector('.section-notes').value = item.notes || '';
            const tagsEl = newCard.querySelector('.section-vault-tags');
            if (tagsEl && item.tags) tagsEl.value = item.tags.join(', ');

            const quillEl = newCard.querySelector('.quill-editor');
            quillEl.innerHTML = item.content || '';

            new Quill(quillEl, {
                theme: 'snow',
                modules: { toolbar: [['bold', 'italic', 'underline'], [{'list': 'ordered'}, {'list': 'bullet'}], ['link'], ['clean']] }
            });

            container.appendChild(newCard);
            updateAllHeaders();
            bootstrap.Modal.getInstance(insertVaultModal).hide();
        }
    });

    // Collaborators
    const collaboratorIds = new Set();
    document.querySelectorAll('#collaborators-list .remove-collab').forEach(link => collaboratorIds.add(link.dataset.id));

    document.getElementById('add-collaborator-btn')?.addEventListener('click', () => {
        const select = document.getElementById('collaborator-select');
        const userId = select.value;
        if (!userId || collaboratorIds.has(userId)) {
            select.value = '';
            return;
        }
        const userName = select.options[select.selectedIndex].text;
        collaboratorIds.add(userId);

        const badge = document.createElement('span');
        badge.className = 'badge bg-info text-dark';
        badge.innerHTML = `${escapeHtml(userName)} <a href="#" class="text-dark ms-1 remove-collab" data-id="${userId}">x</a>`;
        document.getElementById('collaborators-list').appendChild(badge);
        select.value = '';
    });

    document.getElementById('collaborators-list')?.addEventListener('click', e => {
        const link = e.target.closest('.remove-collab');
        if (link) {
            e.preventDefault();
            collaboratorIds.delete(link.dataset.id);
            link.closest('.badge').remove();
        }
    });

    // Main save – excludes template, includes collaborators
    document.getElementById('save-btn').addEventListener('click', () => {
        const sections = [];
        document.querySelectorAll('.section-card:not([data-template])').forEach((card, i) => {
            const quill = Quill.find(card.querySelector('.quill-editor'));
            sections.push({
                sort_order: i + 1,
                section_type: card.querySelector('.section-type').value,
                title: card.querySelector('.section-title').value.trim(),
                scripture_reference: card.querySelector('.section-scripture').value.trim(),
                source: card.querySelector('.section-source').value.trim(),
                content: quill ? quill.root.innerHTML : '',
                notes: card.querySelector('.section-notes').value.trim()
            });
        });
        document.getElementById('sections-json').value = JSON.stringify(sections);

        const form = document.getElementById('sermon-form');
        form.querySelectorAll('input[name="collaborator_ids"]').forEach(el => el.remove());
        collaboratorIds.forEach(id => {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'collaborator_ids';
            input.value = id;
            form.appendChild(input);
        });

        form.submit();
    });
});