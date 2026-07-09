# app/routes/attendance.py
# Full path: WebChurchMan/app/routes/attendance.py
# File name: attendance.py
# Brief, detailed purpose: Attendance module blueprint – complete, MySQL/pymysql-compatible version.
# Features:
#   • Staff/Admin/Owner dashboard_tgp: today's count + recent days list + clickable day details
#   • Staff+ secure token-based kiosk open/close (8-hour expiry)
#   • Public token-protected kiosk: live AJAX search (name + username), PIN/proxy support
#   • Private self-check-in (/self_checkin): mobile-friendly, logged-in members only
#   • Timestamps stored in UTC in DB (using time_utils.utc_now() or to_utc())
#   • Displayed times converted to church local time via time_utils.format_church()
#   • Client local time captured when possible (self_checkin) → converted to UTC on save
#   • Robust ISO parsing with fallback to server UTC now
#   • All significant actions audit-logged
#   • Uses base_attendance.html for admin views
#   • FULL REBUILD: Integrated timezone-aware UTC storage + church local display
#     All existing functionality preserved exactly – only time handling updated.

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from app.utils.decorators import login_required, role_required
from werkzeug.security import check_password_hash
from app.models.db import get_db
from app.models.log import log_change
from app.utils.time_utils import utc_now, to_utc, format_church
from datetime import date, datetime, timedelta
import secrets
import pymysql

attendance_bp = Blueprint('attendance', __name__, url_prefix='/attendance')

REQUIRED_ROLES = ['Staff', 'Admin', 'Owner']


# ----------------------------------------------------------------------
# Attendance Dashboard – Staff/Admin/Owner only
# ----------------------------------------------------------------------
@attendance_bp.route('/')
@attendance_bp.route('/dashboard_tgp')
@login_required
@role_required(REQUIRED_ROLES)
def attendance_dashboard():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    today_str = date.today().strftime('%Y-%m-%d')

    try:
        cur.execute("""
            SELECT COUNT(*) AS count
            FROM attendance
            WHERE DATE(service_date) = %s
        """, (today_str,))
        today_count = cur.fetchone()['count']

        cur.execute("""
            SELECT DATE(service_date) AS date, COUNT(*) AS count
            FROM attendance
            GROUP BY DATE(service_date)
            ORDER BY DATE(service_date) DESC
            LIMIT 10
        """)
        recent_days = cur.fetchall()

    except Exception as e:
        flash('Failed to load attendance data.', 'error')
        print(f"Attendance dashboard_tgp error: {e}")
        today_count = 0
        recent_days = []

    return render_template(
        'attendance/attendance_dashboard.html',
        today_date=today_str,
        today_count=today_count,
        recent_days=recent_days
    )


# ----------------------------------------------------------------------
# Day Detail View – Staff/Admin/Owner only
# ----------------------------------------------------------------------
@attendance_bp.route('/day/<date>')
@login_required
@role_required(REQUIRED_ROLES)
def day_detail(date):
    try:
        service_date = datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'error')
        return redirect(url_for('attendance.attendance_dashboard'))

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    # Use church local time for nice date display
    nice_date = service_date.strftime('%A, %B %d, %Y')

    cur.execute("""
        SELECT COUNT(*) AS count
        FROM attendance
        WHERE DATE(service_date) = %s
    """, (date,))
    count = cur.fetchone()['count']

    cur.execute("""
        SELECT u.id, u.first_name, u.last_name, u.username, a.check_in
        FROM attendance a
        JOIN users u ON a.user_id = u.id
        WHERE DATE(a.service_date) = %s
        ORDER BY a.check_in DESC
    """, (date,))
    attendees = cur.fetchall()

    # Convert UTC check_in to church local time for display
    for a in attendees:
        if a['check_in']:
            # Format in church local time (e.g., 04:28 PM)
            a['check_in_time'] = format_church(a['check_in'], '%I:%M %p')
        else:
            a['check_in_time'] = 'N/A'

    return render_template(
        'attendance/day_detail.html',
        date=date,
        nice_date=nice_date,
        count=count,
        attendees=attendees
    )


# ----------------------------------------------------------------------
# Open Kiosk – Staff/Admin/Owner only
# ----------------------------------------------------------------------
@attendance_bp.route('/open_kiosk')
@login_required
@role_required(REQUIRED_ROLES)
def open_kiosk():
    user_id = session['user_id']
    db = get_db()
    cur = db.cursor()

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(hours=8)

    try:
        cur.execute("""
            INSERT INTO kiosk_sessions (token, created_by, expires_at, active)
            VALUES (%s, %s, %s, 1)
        """, (token, user_id, expires_at))
        db.commit()

        log_change(user_id, 'create', change_details=f'Opened attendance kiosk (token: {token})')
        flash('Kiosk opened – launch below or share URL with kiosk device.', 'success')
        kiosk_url = url_for('attendance.kiosk', token=token, _external=True)
    except Exception as e:
        db.rollback()
        flash('Failed to open kiosk.', 'error')
        print(f"Open kiosk error: {e}")
        kiosk_url = None

    return render_template('attendance/open_kiosk.html', kiosk_url=kiosk_url)


# ----------------------------------------------------------------------
# Close Kiosk – Staff/Admin/Owner only (POST)
# ----------------------------------------------------------------------
@attendance_bp.route('/close/<token>', methods=['POST'])
@login_required
@role_required(REQUIRED_ROLES)
def close_kiosk(token):
    user_id = session['user_id']
    db = get_db()
    cur = db.cursor()

    try:
        cur.execute("UPDATE kiosk_sessions SET active = 0 WHERE token = %s", (token,))
        if cur.rowcount:
            db.commit()
            log_change(user_id, 'update', change_details=f'Closed attendance kiosk (token: {token})')
            flash('Kiosk closed successfully.', 'success')
        else:
            flash('Invalid or already closed token.', 'error')
    except Exception as e:
        db.rollback()
        flash('Failed to close kiosk.', 'error')
        print(f"Close kiosk error: {e}")

    return redirect(url_for('attendance.attendance_dashboard'))


# ----------------------------------------------------------------------
# AJAX Live Search for Kiosk – token protected (name + username)
# ----------------------------------------------------------------------
@attendance_bp.route('/kiosk_search')
def kiosk_search():
    token = request.args.get('token')
    if not token:
        return jsonify({'error': 'missing_token'}), 403

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    try:
        cur.execute("SELECT active, expires_at FROM kiosk_sessions WHERE token = %s", (token,))
        session_row = cur.fetchone()
        if not session_row or not session_row['active'] or datetime.now() > session_row['expires_at']:
            return jsonify({'error': 'invalid_token'}), 403
    except Exception:
        return jsonify({'error': 'invalid_token'}), 403

    search_term = request.args.get('search', '').strip()
    members = []

    if search_term:
        like_param = f'%{search_term}%'
        cur.execute("""
            SELECT id, first_name, last_name, username
            FROM users
            WHERE LOWER(CONCAT(first_name, ' ', last_name)) LIKE LOWER(%s)
               OR LOWER(first_name) LIKE LOWER(%s)
               OR LOWER(last_name) LIKE LOWER(%s)
               OR LOWER(username) LIKE LOWER(%s)
            ORDER BY last_name, first_name
            LIMIT 200
        """, (like_param, like_param, like_param, like_param))
        members = cur.fetchall()

    return jsonify([
        {'id': m['id'], 'name': f"{m['first_name']} {m['last_name']}".strip() or m['username'] or 'Unknown'}
        for m in members
    ])


# ----------------------------------------------------------------------
# Public Kiosk Page – token protected (GET + POST check-in)
# ----------------------------------------------------------------------
@attendance_bp.route('/kiosk', methods=['GET', 'POST'])
def kiosk():
    token = request.args.get('token') or request.form.get('token')
    if not token:
        return render_template('attendance/kiosk_closed.html'), 403

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    try:
        cur.execute("SELECT active, expires_at FROM kiosk_sessions WHERE token = %s", (token,))
        session_row = cur.fetchone()
        if not session_row or not session_row['active'] or datetime.now() > session_row['expires_at']:
            return render_template('attendance/kiosk_closed.html'), 403
    except Exception:
        return render_template('attendance/kiosk_closed.html'), 403

    if request.method == 'POST':
        member_id = request.form.get('member_id')
        pin = request.form.get('pin', '').strip()

        if not member_id:
            flash('No member selected.', 'error')
            return redirect(url_for('attendance.kiosk', token=token))

        try:
            cur.execute("""
                SELECT id, first_name, last_name, allow_proxy_checkin, checkin_pin
                FROM users WHERE id = %s
            """, (member_id,))
            member = cur.fetchone()
            if not member:
                flash('Member not found.', 'error')
                return redirect(url_for('attendance.kiosk', token=token))

            if not member['allow_proxy_checkin'] and member['checkin_pin']:
                if not pin or not check_password_hash(member['checkin_pin'], pin):
                    flash('Invalid PIN.', 'error')
                    return redirect(url_for('attendance.kiosk', token=token))
            elif not member['allow_proxy_checkin'] and not member['checkin_pin']:
                flash('This member requires staff assistance.', 'error')
                return redirect(url_for('attendance.kiosk', token=token))

            today = date.today().strftime('%Y-%m-%d')

            # Store check_in as UTC now (server-generated)
            check_in_utc = utc_now()

            cur.execute("""
                INSERT INTO attendance (user_id, service_date, check_in)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE check_in = %s
            """, (member_id, today, check_in_utc, check_in_utc))
            db.commit()

            log_change(None, 'checkin', target_id=member_id,
                       change_details=f"Kiosk check-in: {member['first_name']} {member['last_name']}")
            flash(f"{member['first_name']} {member['last_name']} checked in!", 'success')

        except Exception as e:
            db.rollback()
            flash('Check-in failed.', 'error')
            print(f"Kiosk check-in error: {e}")

        return redirect(url_for('attendance.kiosk', token=token))

    return render_template('attendance/kiosk.html')


# ----------------------------------------------------------------------
# Self Check-In – Logged-in members only (mobile-friendly, private)
# ----------------------------------------------------------------------
@attendance_bp.route('/self_checkin', methods=['GET', 'POST'])
@login_required
def self_checkin():
    user_id = session['user_id']
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT first_name, last_name, username
        FROM users
        WHERE id = %s
    """, (user_id,))
    user = cur.fetchone()
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('dashboard_tgp.dashboard_tgp'))

    today_str = date.today().strftime('%Y-%m-%d')
    nice_date = date.today().strftime('%A, %B %d, %Y')

    # Load existing check-in for display
    cur.execute("""
        SELECT check_in
        FROM attendance
        WHERE user_id = %s AND DATE(service_date) = %s
    """, (user_id, today_str))
    existing = cur.fetchone()

    checked_in = existing is not None
    check_in_raw = existing['check_in'] if existing and existing['check_in'] else None

    if request.method == 'POST':
        client_iso = request.form.get('client_checkin')  # e.g. "2026-01-16T16:28:58.352Z" (UTC)

        check_in_utc = utc_now()  # fallback server UTC

        if client_iso:
            try:
                # Client sends UTC ISO string – parse directly (it's already UTC)
                dt = datetime.fromisoformat(client_iso.replace('Z', '+00:00'))
                check_in_utc = dt  # already UTC aware
            except (ValueError, TypeError) as parse_err:
                print(f"Invalid client check-in time: {client_iso} → {parse_err}")
                # fallback to server UTC

        try:
            cur.execute("""
                INSERT INTO attendance (user_id, service_date, check_in)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE check_in = %s
            """, (user_id, today_str, check_in_utc, check_in_utc))
            db.commit()

            log_change(user_id, 'checkin', target_id=user_id,
                       change_details='Self check-in via /attendance/self_checkin')

            flash('Thank you for checking in today!', 'success')
            checked_in = True
            check_in_raw = check_in_utc  # for display (will be formatted in template)

        except Exception as e:
            db.rollback()
            flash('Check-in failed. Please try again.', 'error')
            print(f"Self check-in database error: {e}")

    return render_template(
        'attendance/user_signin.html',
        user=user,
        nice_date=nice_date,
        checked_in=checked_in,
        check_in_raw=check_in_raw  # Pass raw UTC datetime – template uses format_church()
    )