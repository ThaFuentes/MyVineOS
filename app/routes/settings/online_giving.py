# myvinechurchonline/app/routes/settings/online_giving.py
# Full path: myvinechurchonline/app/routes/settings/online_giving.py
# File name: online_giving.py
# Brief, detailed purpose: Online giving page config + option management.
# Handles global settings toggle/text and full CRUD/reordering for donation options (with image upload/removal).
# Censored word checks on option names. All actions audit-logged with full 5-argument log_change.
# Uses DictCursor consistently for safe row access.
# CONFIRMED CORRECT: Package-relative imports + pymysql.

from flask import render_template, request, redirect, url_for, flash, session
from app.models.db import get_db
from app.models.log import log_change
from werkzeug.utils import secure_filename
from . import settings_bp, allowed_file, DONATIONS_FOLDER, has_section_permission, load_settings, load_online_options
from app.utils.helpers import contains_censored_word
import os
import pymysql

@settings_bp.route('/online-giving', methods=['GET', 'POST'])
def online_giving():
    if request.method == 'POST' and not has_section_permission('online_giving'):
        flash('Insufficient permission to edit Online Giving settings.', 'error')
        return redirect(url_for('settings.online_giving'))

    os.makedirs(DONATIONS_FOLDER, exist_ok=True)

    db = get_db()
    user_id = session['user_id']

    settings = load_settings()

    if request.method == 'POST':
        cur = db.cursor(pymysql.cursors.DictCursor)
        action = request.form.get('action')

        if action == 'update_online_global':
            updates = {
                'online_donations_enabled': 1 if 'online_donations_enabled' in request.form else 0,
                'donations_page_title': request.form.get('donations_page_title', '').strip() or None,
                'donations_welcome_text': request.form.get('donations_welcome_text', '').strip() or None,
                'donations_thank_you_text': request.form.get('donations_thank_you_text', '').strip() or None,
                'donations_extra_text': request.form.get('donations_extra_text', '').strip() or None,
            }
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            values = list(updates.values())
            cur.execute(f"UPDATE settings SET {set_clause} WHERE id = 1", values)
            db.commit()
            log_change(user_id, 'update', None, None, 'Updated online giving global settings')
            flash('Online giving page settings saved.', 'success')

        elif action == 'add_option':
            name = request.form.get('option_name', '').strip()
            if not name:
                flash('Option name is required.', 'error')
            else:
                if contains_censored_word(name):
                    flash('Option name contains a prohibited word or phrase.', 'error')
                else:
                    image_path = None
                    file = request.files.get('option_image')
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        file.save(os.path.join(DONATIONS_FOLDER, filename))
                        image_path = filename

                    cur.execute("""
                        INSERT INTO online_donation_options 
                        (name, option_type, url, embed_code, image_path, enabled, sort_order)
                        VALUES (%s, %s, %s, %s, %s, %s, 
                         COALESCE((SELECT MAX(sort_order) FROM online_donation_options), 0) + 1)
                    """, (
                        name,
                        request.form.get('option_type', '').strip() or None,
                        request.form.get('option_url') or None,
                        request.form.get('option_embed') or None,
                        image_path,
                        1 if 'option_enabled' in request.form else 0
                    ))
                    new_id = cur.lastrowid
                    db.commit()
                    log_change(user_id, 'create', new_id, name, f'Added giving option: {name}')
                    flash('New giving option added.', 'success')

        elif action in ('move_up', 'move_down'):
            option_id = request.form.get('option_id')
            if option_id:
                cur.execute("SELECT sort_order, name FROM online_donation_options WHERE id = %s", (option_id,))
                current = cur.fetchone()
                if current:
                    delta = -1 if action == 'move_up' else 1
                    target = current['sort_order'] + delta
                    cur.execute("""
                        UPDATE online_donation_options o1
                        JOIN online_donation_options o2 ON o2.sort_order = %s
                        SET o1.sort_order = o2.sort_order, o2.sort_order = o1.sort_order
                        WHERE o1.id = %s
                    """, (target, option_id))
                    db.commit()
                    log_change(user_id, 'update', option_id, current['name'], f'Reordered giving option: {current["name"]}')
                    flash('Option reordered.', 'success')

        elif action == 'update_option':
            option_id = request.form.get('option_id')
            name = request.form.get('option_name', '').strip()
            if not option_id or not name:
                flash('Invalid data.', 'error')
            else:
                if contains_censored_word(name):
                    flash('Option name contains a prohibited word or phrase.', 'error')
                else:
                    updates = {
                        'name': name,
                        'option_type': request.form.get('option_type', '').strip() or None,
                        'url': request.form.get('option_url') or None,
                        'embed_code': request.form.get('option_embed') or None,
                        'enabled': 1 if 'option_enabled' in request.form else 0
                    }
                    file = request.files.get('option_image')
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        file.save(os.path.join(DONATIONS_FOLDER, filename))
                        updates['image_path'] = filename
                    if 'remove_image' in request.form:
                        cur.execute("SELECT image_path FROM online_donation_options WHERE id = %s", (option_id,))
                        old = cur.fetchone()
                        if old and old['image_path']:
                            try:
                                os.remove(os.path.join(DONATIONS_FOLDER, old['image_path']))
                            except OSError:
                                pass
                        updates['image_path'] = None

                    set_clause = ", ".join(f"{k} = %s" for k in updates)
                    values = list(updates.values()) + [option_id]
                    cur.execute(f"UPDATE online_donation_options SET {set_clause} WHERE id = %s", values)
                    db.commit()
                    log_change(user_id, 'update', option_id, name, f'Updated giving option: {name}')
                    flash('Giving option updated.', 'success')

        elif action == 'delete_option':
            option_id = request.form.get('option_id')
            if option_id:
                cur.execute("SELECT name, image_path FROM online_donation_options WHERE id = %s", (option_id,))
                row = cur.fetchone()
                if not row:
                    flash('Option not found.', 'error')
                else:
                    name = row['name']
                    if row['image_path']:
                        try:
                            os.remove(os.path.join(DONATIONS_FOLDER, row['image_path']))
                        except OSError:
                            pass
                    cur.execute("DELETE FROM online_donation_options WHERE id = %s", (option_id,))
                    db.commit()
                    log_change(user_id, 'delete', option_id, name, f'Deleted giving option: {name}')
                    flash('Giving option deleted.', 'success')

    # Always load fresh data for template (ensures changes reflect immediately)
    online_options = load_online_options()

    return render_template('settings/online_giving.html', settings=settings, online_options=online_options)