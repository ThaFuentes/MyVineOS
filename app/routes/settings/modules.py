# Owner/Admin: enable or disable optional church modules (apps-style).

from flask import flash, redirect, render_template, request, session, url_for

import app.models.module_toggles as mt
from app.models.log import log_change

from . import has_section_permission, settings_bp


def _ensure_toggles_column():
    """Create settings.module_toggles_json if missing (older DBs)."""
    try:
        from app.models.db import get_db
        db = get_db()
        cur = db.cursor()
        cur.execute("""
            SELECT COUNT(*) AS c FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'settings'
              AND COLUMN_NAME = 'module_toggles_json'
        """)
        row = cur.fetchone()
        n = row[0] if isinstance(row, (list, tuple)) else (row or {}).get('c', 0)
        if not n:
            cur.execute("ALTER TABLE settings ADD COLUMN module_toggles_json MEDIUMTEXT NULL")
            db.commit()
    except Exception as e:
        print(f'module_toggles column ensure: {e}')



@settings_bp.route('/modules', methods=['GET', 'POST'])
def modules():
    """Toggle which optional modules appear in nav / are available."""
    _ensure_toggles_column()
    if session.get('user_role') not in ('Owner', 'Admin') and not has_section_permission('general'):
        flash('Only Owner or Admin can change module availability.', 'error')
        return redirect(url_for('settings.general'))

    if request.method == 'POST':
        if session.get('user_role') not in ('Owner', 'Admin'):
            flash('Only Owner or Admin can change module availability.', 'error')
            return redirect(url_for('settings.modules'))

        # Checkboxes: only enabled keys are submitted
        enabled = set(request.form.getlist('modules'))
        # Validate against catalog
        valid = {m['key'] for m in mt.OPTIONAL_MODULES}
        enabled = {k for k in enabled if k in valid}
        mt.save_module_toggles(enabled)
        log_change(
            session.get('user_id'),
            'update',
            change_details=f"Updated module toggles ({len(enabled)} enabled of {len(valid)})",
        )
        flash('Module availability saved. Navigation updates immediately.', 'success')
        return redirect(url_for('settings.modules'))

    toggles = mt.get_module_toggles()
    return render_template(
        'settings/modules.html',
        categories=mt.modules_by_category(),
        toggles=toggles,
        core_always_on=mt.CORE_ALWAYS_ON,
    )
