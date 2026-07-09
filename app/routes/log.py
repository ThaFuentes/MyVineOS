# myvinechurchonline/app/routes/log.py
# Full path: myvinechurchonline/app/routes/log.py
# File name: log.py
# Brief, detailed purpose: Blueprint for viewing change audit records.
# Route /log/change_records – TEMPORARILY open to any logged-in user (for debugging).
# Displays all audit entries from the change_records table (table name aligned exactly with your builddb).
# Searchable by username/action/details. Simple pagination.
# Template: log/change_records.html (consistent with folder structure).

from flask import Blueprint, render_template, request, session, flash, redirect, url_for
from app.utils.decorators import login_required  # Only login required for current test
from app.models.db import get_db
import pymysql

log_bp = Blueprint('log', __name__, url_prefix='/log')

@log_bp.route('/')
@login_required
def log_root():
    return redirect(url_for('log.change_records'))

PAGE_SIZE = 100

@log_bp.route('/change_records')
@login_required
def change_records():
    """View all change audit records (temporarily open to any logged-in user for debugging)."""
    user_id = session['user_id']

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    search_term = request.args.get('search', '').strip()
    page = int(request.args.get('page', 1))
    offset = (page - 1) * PAGE_SIZE

    base_sql = """
        SELECT cr.id, cr.user_id, cr.action, cr.target_id, cr.target_username,
               cr.change_details, cr.timestamp,
               u.username AS user_name
        FROM change_records cr
        LEFT JOIN users u ON cr.user_id = u.id
    """
    count_sql = "SELECT COUNT(*) AS total FROM change_records cr"
    params = []
    where_clause = ""

    if search_term:
        like_param = f'%{search_term}%'
        where_clause = """
            WHERE cr.action LIKE %s 
               OR cr.change_details LIKE %s 
               OR cr.target_username LIKE %s
               OR u.username LIKE %s
        """
        params = [like_param, like_param, like_param, like_param]
        count_sql += where_clause

    # Get total count for pagination
    cur.execute(count_sql, params)
    total_records = cur.fetchone()['total']

    sql = base_sql + where_clause + " ORDER BY cr.timestamp DESC LIMIT %s OFFSET %s"
    params.extend([PAGE_SIZE, offset])

    try:
        cur.execute(sql, params)
        logs = cur.fetchall()
    except Exception as e:
        flash('Failed to load change records.', 'error')
        print(f"Change records query error: {e}")
        logs = []
        total_records = 0

    total_pages = (total_records + PAGE_SIZE - 1) // PAGE_SIZE if total_records else 1

    return render_template(
        'log/change_records.html',
        logs=logs,
        search_term=search_term,
        page=page,
        total_pages=total_pages,
        total_records=total_records
    )


@log_bp.route('/delete_record', methods=['GET', 'POST'])
@login_required
def delete_record():
    """Delete single record confirmation / handler (legacy template support)."""
    # In real use, would take id and do delete + log
    if request.method == 'POST':
        flash('Delete record action (stub).', 'info')
        return redirect(url_for('log.change_records'))
    return render_template('log/delete_record.html')


@log_bp.route('/delete_all_records', methods=['GET', 'POST'])
@login_required
def delete_all_records():
    """Delete all records confirmation / handler (legacy template support)."""
    if request.method == 'POST':
        flash('Delete ALL records action (stub).', 'info')
        return redirect(url_for('log.change_records'))
    return render_template('log/delete_all_records.html')