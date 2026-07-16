# myvinechurchonline/app/routes/settings/general.py
# General church info settings (name, address, contact, paths) + pastoral care toggle.

from flask import render_template, request, redirect, url_for, flash, session
from app.models.db import get_db
from app.models.log import log_change
from . import settings_bp, has_section_permission, load_settings
from app.utils.helpers import contains_censored_word


def _ensure_settings_row(cur):
    cur.execute("SELECT id FROM settings WHERE id = 1")
    if not cur.fetchone():
        cur.execute("INSERT INTO settings (id) VALUES (1)")


@settings_bp.route('/general', methods=['GET', 'POST'])
def general():
    if request.method == 'POST' and not has_section_permission('general'):
        flash('Insufficient permission to edit General settings.', 'error')
        return redirect(url_for('settings.general'))

    db = get_db()
    user_id = session['user_id']
    action = request.form.get('action', 'update_general')

    if request.method == 'POST':
        if action == 'update_comments':
            enabled = 1 if request.form.get('public_comments_enabled') else 0
            cur = db.cursor()
            _ensure_settings_row(cur)
            try:
                cur.execute(
                    "UPDATE settings SET public_comments_enabled = %s WHERE id = 1",
                    (enabled,),
                )
                db.commit()
                log_change(user_id, 'update', None, None,
                           f"Public comments {'enabled' if enabled else 'disabled'}")
                flash('Comment settings saved.', 'success')
            except Exception:
                db.rollback()
                flash('Comment settings could not be saved (column may need migration).', 'error')
            return redirect(url_for('settings.general'))

        if action == 'update_pastoral_care':
            enabled = 1 if request.form.get('pastoral_care_public_submission_enabled') else 0
            cur = db.cursor()
            _ensure_settings_row(cur)
            try:
                cur.execute(
                    "UPDATE settings SET pastoral_care_public_submission_enabled = %s WHERE id = 1",
                    (enabled,),
                )
                db.commit()
                log_change(user_id, 'update', None, None, 'Updated pastoral care settings')
                flash('Pastoral care settings saved.', 'success')
            except Exception:
                db.rollback()
                flash('Pastoral care settings could not be saved (column may need migration).', 'error')
            return redirect(url_for('settings.general'))

        visible_text = ' '.join([
            request.form.get('church_name', ''),
            request.form.get('pastor', ''),
            request.form.get('address', ''),
            request.form.get('phone_number', ''),
        ])
        if contains_censored_word(visible_text):
            flash('General settings contain a prohibited word or phrase.', 'error')
            return redirect(url_for('settings.general'))

        if action == 'update_display_default':
            from app.utils.ui_prefs import save_church_default_theme, THEME_LABELS
            theme = request.form.get('default_ui_theme') or 'cyan-glow'
            try:
                saved = save_church_default_theme(theme)
                # So this browser immediately reflects the new church default
                session['church_default_theme'] = saved
                if not session.get('user_id') or not session.get('ui_use_personal_theme'):
                    session['user_theme'] = saved
                session.modified = True
                log_change(
                    user_id, 'update', None, None,
                    f"Church default display theme → {THEME_LABELS.get(saved, saved)}",
                )
                flash(
                    f'Default church theme set to {THEME_LABELS.get(saved, saved)}. '
                    'Visitors and members who follow church default will see this. '
                    'Anyone can still change Display for themselves.',
                    'success',
                )
            except Exception as e:
                flash(str(e), 'error')
            return redirect(url_for('settings.general'))

        updates = {
            'church_name': request.form.get('church_name', '').strip() or None,
            'tax_status': request.form.get('tax_status', '').strip() or None,
            'address': request.form.get('address', '').strip() or None,
            'phone_number': request.form.get('phone_number', '').strip() or None,
            'pastor': request.form.get('pastor', '').strip() or None,
            'icon_path': request.form.get('icon_path', '').strip() or None,
            'export_location': request.form.get('export_location', '').strip() or None,
            'sermon_folder_location': request.form.get('sermon_folder_location', '').strip() or None,
        }

        cur = db.cursor()
        _ensure_settings_row(cur)
        set_parts = []
        values = []
        for key, value in updates.items():
            set_parts.append(f"{key} = %s")
            values.append(value)
        cur.execute(f"UPDATE settings SET {', '.join(set_parts)} WHERE id = 1", values)
        db.commit()
        log_change(user_id, 'update', None, None, 'Updated church & general settings')
        flash('Church & general settings saved.', 'success')
        return redirect(url_for('settings.general'))

    from app.utils.ui_prefs import ALLOWED_THEMES, THEME_LABELS, get_church_default_theme
    settings = load_settings()
    return render_template(
        'settings/general.html',
        settings=settings,
        theme_choices=ALLOWED_THEMES,
        theme_labels=THEME_LABELS,
        church_default_theme=get_church_default_theme(settings),
    )