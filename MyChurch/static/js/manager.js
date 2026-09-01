/* Gathering Place Manager — shared UI helpers */

function mgrOpenEdit(commentId, body, contentType, parentId) {
    var overlay = document.getElementById('mgr-edit-overlay');
    if (!overlay) return;
    document.getElementById('mgr-edit-comment-id').value = commentId;
    document.getElementById('mgr-edit-content-type').value = contentType || '';
    document.getElementById('mgr-edit-parent-id').value = parentId || '';
    document.getElementById('mgr-edit-text').value = body || '';
    overlay.style.display = 'flex';
    document.getElementById('mgr-edit-text').focus();
}

function mgrCloseEdit(evt) {
    if (evt && evt.target && !evt.target.classList.contains('mgr-edit-overlay')) return;
    var overlay = document.getElementById('mgr-edit-overlay');
    if (overlay) overlay.style.display = 'none';
}

document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
        mgrCloseEdit();
        mgrHidePreview();
    }
});

/* ---- Smart hover previews (fixed position, flips above near bottom) ---- */
(function () {
    var floatEl = null;
    var activeWrap = null;

    function getFloat() {
        if (!floatEl) {
            floatEl = document.createElement('div');
            floatEl.id = 'mgr-preview-float';
            floatEl.className = 'mgr-preview-popup';
            floatEl.setAttribute('role', 'tooltip');
            document.body.appendChild(floatEl);
        }
        return floatEl;
    }

    function mgrHidePreview() {
        if (floatEl) {
            floatEl.classList.remove('mgr-preview-visible');
            floatEl.style.visibility = '';
        }
        activeWrap = null;
    }

    function mgrShowPreview(wrap) {
        var trigger = wrap.querySelector('.mgr-preview-trigger');
        var source = wrap.querySelector('.mgr-preview-popup');
        if (!trigger || !source || !source.textContent.trim()) return;

        var float = getFloat();
        float.textContent = source.textContent;
        float.classList.add('mgr-preview-visible');
        float.style.visibility = 'hidden';
        float.style.top = '0';
        float.style.left = '0';

        var rect = trigger.getBoundingClientRect();
        var fh = float.offsetHeight;
        var fw = float.offsetWidth;
        var gap = 6;
        var margin = 10;
        var viewH = window.innerHeight;
        var viewW = window.innerWidth;

        var top = rect.bottom + gap;
        if (top + fh > viewH - margin) {
            top = rect.top - fh - gap;
        }
        if (top < margin) {
            top = margin;
        }
        if (top + fh > viewH - margin) {
            float.style.maxHeight = (viewH - top - margin) + 'px';
        } else {
            float.style.maxHeight = '';
        }

        var left = rect.left;
        if (left + fw > viewW - margin) {
            left = viewW - fw - margin;
        }
        if (left < margin) {
            left = margin;
        }

        float.style.top = top + 'px';
        float.style.left = left + 'px';
        float.style.visibility = 'visible';
        activeWrap = wrap;
    }

    function bindPreviews(root) {
        (root || document).querySelectorAll('.mgr-preview-wrap').forEach(function (wrap) {
            if (wrap.dataset.mgrPreviewBound) return;
            wrap.dataset.mgrPreviewBound = '1';
            wrap.addEventListener('mouseenter', function () {
                mgrShowPreview(wrap);
            });
            wrap.addEventListener('mouseleave', function () {
                mgrHidePreview();
            });
            wrap.addEventListener('focusin', function () {
                mgrShowPreview(wrap);
            });
            wrap.addEventListener('focusout', function () {
                mgrHidePreview();
            });
        });
    }

    window.mgrHidePreview = mgrHidePreview;

    document.addEventListener('DOMContentLoaded', function () {
        bindPreviews();
    });
    window.addEventListener('scroll', mgrHidePreview, true);
    window.addEventListener('resize', mgrHidePreview);
})();