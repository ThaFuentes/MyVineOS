# myvinechurchonline/app/routes/settings/ticket_managers.py
# Manage dedicated ticket_managers table (Admin/Owner only).
# MariaDB-safe INSERT IGNORE + assigned_by column.

from flask import render_template, request, redirect, url_for, flash, session
from app.utils.decorators import login_required, role_required
from app.models.db import get_db
from app.models.log import log_change
from . import settings_bp
import pymysql


@settings_bp.route('/ticket_managers', methods=['GET', 'POST'])
@login_required
@role_required(['Admin', 'Owner'])
def ticket_managers():
    db = get_db()
    user_id = session['user_id']
    cur = db.cursor(pymysql.cursors.DictCursor)

    if request.method == 'POST':
        action = request.form.get('action')
        target_user_id = request.form.get('user_id')

        if action in ('add', 'remove') and target_user_id:
            try:
                target_user_id = int(target_user_id)
            except (TypeError, ValueError):
                flash('Invalid user.', 'error')
                return redirect(url_for('settings.ticket_managers'))

            cur.execute("SELECT username FROM users WHERE id = %s", (target_user_id,))
            user_row = cur.fetchone()
            username = user_row['username'] if user_row else f'User ID {target_user_id}'

            if action == 'add':
                cur.execute(
                    "INSERT IGNORE INTO ticket_managers (user_id, assigned_by) VALUES (%s, %s)",
                    (target_user_id, user_id),
                )
                db.commit()
                log_change(
                    user_id, 'update', target_user_id, username,
                    f'Added {username} to ticket managers',
                )
                flash(f'{username} added to ticket managers.', 'success')

            elif action == 'remove':
                cur.execute("DELETE FROM ticket_managers WHERE user_id = %s", (target_user_id,))
                db.commit()
                log_change(
                    user_id, 'update', target_user_id, username,
                    f'Removed {username} from ticket managers',
                )
                flash(f'{username} removed from ticket managers.', 'success')

        return redirect(url_for('settings.ticket_managers'))

    cur.execute(
        "SELECT id, username, first_name, last_name, role FROM users ORDER BY username"
    )
    all_users = cur.fetchall()

    cur.execute("SELECT user_id FROM ticket_managers")
    manager_ids = {row['user_id'] for row in cur.fetchall()}

    return render_template(
        'settings/ticket_managers.html',
        all_users=all_users,
        manager_ids=manager_ids,
    )
