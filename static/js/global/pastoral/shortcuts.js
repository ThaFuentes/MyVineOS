// app/static/js/global/pastoral/shortcuts.js
// Full path: WebChurchMan/app/static/js/global/pastoral/shortcuts.js
// File name: shortcuts.js
// Brief, detailed purpose:
//   Shared keyboard shortcut handler for the entire Pastoral Area.
//   - Alt + Space: Toggle hidden editor toolbar visibility (#editor-toolbar)
//   - ? (Shift + /): Open shortcut help overlay (discoverability)
//   - Help overlay lists all current and future shortcuts
//   - Non-conflicting (Alt-based only, no overrides of common browser shortcuts)
//   - Works across all pastoral pages (graceful degradation if elements missing)
//   - Loaded in base_pastoral.html

document.addEventListener('DOMContentLoaded', () => {
    const toolbar = document.getElementById('editor-toolbar');
    const gripper = document.getElementById('toolbar-gripper');
    const helpBtn = document.getElementById('shortcut-help-btn'); // Bottom status bar ? button

    let helpOverlay = null;

    // Helper: Create help overlay modal (only once)
    function createHelpOverlay() {
        if (helpOverlay) return helpOverlay;

        helpOverlay = document.createElement('div');
        helpOverlay.className = 'shortcut-help-overlay';
        helpOverlay.innerHTML = `
            <div class="shortcut-help-modal glass-card">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h4 class="mb-0">Keyboard Shortcuts</h4>
                    <button class="btn btn-sm btn-outline-cyan close-help">&times;</button>
                </div>
                <ul class="list-unstyled">
                    <li><kbd>Alt + Space</kbd> – Show/hide top toolbar (Sermon Editor)</li>
                    <li><kbd>?</kbd> – Open this help overlay</li>
                    <li><kbd>Space</kbd> – Play/Pause auto-scroll (Podium Mode)</li>
                    <li><kbd>← →</kbd> – Decrease/Increase scroll speed (Podium Mode)</li>
                    <li><kbd>R</kbd> – Reset scroll & timer (Podium Mode)</li>
                </ul>
                <small class="text-muted d-block mt-3">More shortcuts coming as features grow.</small>
            </div>
        `;

        // Close handlers
        helpOverlay.querySelector('.close-help').addEventListener('click', () => {
            helpOverlay.classList.remove('visible');
        });
        helpOverlay.addEventListener('click', (e) => {
            if (e.target === helpOverlay) {
                helpOverlay.classList.remove('visible');
            }
        });

        document.body.appendChild(helpOverlay);
        return helpOverlay;
    }

    // Alt + Space – toggle toolbar (only if toolbar exists)
    if (toolbar) {
        document.addEventListener('keydown', (e) => {
            if (e.altKey && e.code === 'Space') {
                e.preventDefault();
                toolbar.classList.toggle('visible');
            }
        });

        // Optional: Gripper click also toggles
        if (gripper) {
            gripper.addEventListener('click', () => {
                toolbar.classList.toggle('visible');
            });
        }

        // Hover reveal (fallback UX)
        const toolbarWrapper = toolbar.parentElement || toolbar;
        toolbarWrapper.addEventListener('mouseenter', () => {
            toolbar.classList.add('visible');
        });
        toolbarWrapper.addEventListener('mouseleave', () => {
            if (!document.activeElement.closest('#editor-toolbar')) {
                toolbar.classList.remove('visible');
            }
        });
    }

    // ? key – open help overlay
    document.addEventListener('keydown', (e) => {
        if (e.key === '?' && !e.ctrlKey && !e.altKey && !e.metaKey) {
            e.preventDefault();
            const overlay = createHelpOverlay();
            overlay.classList.add('visible');
        }
    });

    // Bottom status bar ? button
    if (helpBtn) {
        helpBtn.addEventListener('click', () => {
            const overlay = createHelpOverlay();
            overlay.classList.add('visible');
        });
    }
});