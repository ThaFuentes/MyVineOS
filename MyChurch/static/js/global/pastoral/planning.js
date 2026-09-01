// app/static/js/global/pastoral/planning.js
// Full path: WebChurchMan/app/static/js/global/pastoral/planning.js
// File name: planning.js
// Brief, detailed purpose:
//   Client-side logic for the Service Plan editor (planning_edit.html).
//   - Initializes Quill rich text editor for notes/order of service (light toolbar)
//   - Serializes Quill content to hidden field on form submit
//   - Dynamic role assignment rows: Add new row, remove row (keep at least one)
//   - Clean, reusable – no dependencies beyond Quill (already loaded)

document.addEventListener('DOMContentLoaded', () => {
    // Quill for notes (light toolbar – matches template toolbar config)
    const quill = new Quill('#notes-editor', {
        theme: 'snow',
        modules: {
            toolbar: [
                [{'header': [1, 2, false]}],
                ['bold', 'italic', 'underline'],
                [{'list': 'ordered'}, {'list': 'bullet'}],
                ['link'],
                ['clean']
            ]
        }
    });

    // Serialize notes to hidden field on submit
    const form = document.getElementById('planning-form');
    if (form) {
        form.onsubmit = () => {
            const hiddenNotes = document.getElementById('notes-hidden');
            if (hiddenNotes) {
                hiddenNotes.value = quill.root.innerHTML;
            }
        };
    }

    // Add Role button – clone last row and clear values
    const addRoleBtn = document.getElementById('add-role-btn');
    const assignmentsContainer = document.getElementById('assignments-container');

    if (addRoleBtn && assignmentsContainer) {
        addRoleBtn.addEventListener('click', () => {
            const rows = assignmentsContainer.querySelectorAll('.assignment-row');
            const template = rows[rows.length - 1].cloneNode(true);

            // Clear inputs/selects in cloned row
            template.querySelectorAll('input, select').forEach(el => {
                if (el.name === 'role_name') el.value = '';
                else if (el.tagName === 'SELECT') el.selectedIndex = 0;
            });

            assignmentsContainer.appendChild(template);
        });

        // Remove Role – delegated event (works on existing + future rows)
        assignmentsContainer.addEventListener('click', (e) => {
            const removeBtn = e.target.closest('.remove-role-btn');
            if (!removeBtn) return;

            const row = removeBtn.closest('.assignment-row');
            const allRows = assignmentsContainer.querySelectorAll('.assignment-row');

            if (allRows.length > 1) {
                row.remove();
            } else {
                // If only one row left, just clear it instead of removing
                row.querySelector('input[name="role_name"]').value = '';
                row.querySelector('select[name="assigned_user_id"]').selectedIndex = 0;
            }
        });
    }
});