# myvinechurchonline/app/routes/settings/ticket_managers.py
# Full path: myvinechurchonline/app/routes/settings/ticket_managers.py
# File name: ticket_managers.py
# Brief, detailed purpose: Manage dedicated ticket_managers group (Admin/Owner only).
# Add/remove users from the group. All actions audit-logged with full 5-argument log_change.
# Uses DictCursor for safe row access.

from flask import render_template, request, redirect, url_for, flash, session
from app.utils.decorators import login_required, role_required
from app.models.db import get_db
from app.models.log import log_change
from . import settings_bp
import pymysql  # Required for DictCursor

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
            # Fetch username for better logging
            cur.execute("SELECT username FROM users WHERE id = %s", (target_user_id,))
            user_row = cur.fetchone()
            username = user_row['username'] if user_row else f'User ID {target_user_id}'

            if action == 'add':
                cur.execute("INSERT OR IGNORE INTO ticket_managers (user_id, added_by) VALUES (%s, %s)",
                            (target_user_id, user_id))
                db.commit()
                log_change(user_id, 'update', target_user_id, username, f'Added {username} to ticket managers group')
                flash(f'{username} added to ticket managers.', 'success')

            elif action == 'remove':
                cur.execute("DELETE FROM ticket_managers WHERE user_id = %s", (target_user_id,))
                db.commit()
                log_change(user_id, 'update', target_user_id, username, f'Removed {username} from ticket managers group')
                flash(f'{username} removed from ticket managers.', 'success')

    # Load all users
    cur.execute("SELECT id, username, first_name, last_name, role FROM users ORDER BY username")
    all_users = cur.fetchall()

    # Load current managers
    cur.execute("SELECT user_id FROM ticket_managers")
    manager_ids = {row['user_id'] for row in cur.fetchall()}

    return render_template('settings/ticket_manager.html',
                           all_users=all_users,
                           manager_ids=manager_ids)