# app/routes/attendance/views.py
# Full path: MyVineChurch/app/routes/attendance/views.py
# File name: views.py
# Brief, detailed purpose: Clean, thin route handlers for the Attendance blueprint.
# • All DB work moved to queries.py
# • All form validation moved to forms.py
# • All constants/helpers moved to utils.py
# • 100% original behavior preserved – now super easy to maintain and grow.

from flask import render_template, request, redirect, url_for, flash, session, jsonify
from datetime import date, datetime

from . import attendance_bp
from .queries import (
    get_today_attendance_count, get_recent_days, get_day_count_and_attendees,
    create_kiosk_session, close_kiosk_session, validate_kiosk_session,
    search_members, get_member_for_checkin, record_attendance,
    get_user_for_self_checkin, get_existing_attendance
)
from .forms import validate_kiosk_checkin_form, validate_self_checkin_form
from .utils import generate_kiosk_token, get_kiosk_expiration

from app.utils.decorators import login_required, permission_required
from werkzeug.security import check_password_hash
from app.models.log import log_change
from app.utils.time_utils import utc_now, format_church


# ----------------------------------------------------------------------
# Attendance Dashboard
# ----------------------------------------------------------------------
@attendance_bp.route('/')
@attendance_bp.route('/dashboard')
@permission_required('manage_attendance')
def attendance_dashboard():
    today_count = get_today_attendance_count()
    recent_days = get_recent_days()

    return render_template(
        'attendance/attendance_dashboard.html',
        today_date=date.today().strftime('%Y-%m-%d'),
        today_count=today_count,
        recent_days=recent_days
    )


# ----------------------------------------------------------------------
# Day Detail View
# ----------------------------------------------------------------------
@attendance_bp.route('/day/<date>')
@permission_required('manage_attendance')
def day_detail(date):
    try:
        service_date = datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'error')
        return redirect(url_for('attendance.attendance_dashboard'))

    nice_date = service_date.strftime('%A, %B %d, %Y')
    count, attendees = get_day_count_and_attendees(date)

    for a in attendees:
        a['check_in_time'] = format_church(a['check_in'], '%I:%M %p') if a['check_in'] else 'N/A'

    return render_template(
        'attendance/day_detail.html',
        date=date,
        nice_date=nice_date,
        count=count,
        attendees=attendees
    )


# ----------------------------------------------------------------------
# Open Kiosk
# ----------------------------------------------------------------------
@attendance_bp.route('/open_kiosk')
@permission_required('manage_attendance')
def open_kiosk():
    user_id = session['user_id']
    token = generate_kiosk_token()
    expires_at = get_kiosk_expiration()

    try:
        create_kiosk_session(user_id, token, expires_at)
        log_change(user_id, 'create', change_details=f'Opened attendance kiosk (token: {token})')
        flash('Kiosk opened – launch below or share URL.', 'success')
        kiosk_url = url_for('attendance.kiosk', token=token, _external=True)
    except Exception as e:
        flash('Failed to open kiosk.', 'error')
        print(f"Open kiosk error: {e}")
        kiosk_url = None

    return render_template('attendance/open_kiosk.html', kiosk_url=kiosk_url)


# ----------------------------------------------------------------------
# Close Kiosk
# ----------------------------------------------------------------------
@attendance_bp.route('/close/<token>', methods=['POST'])
@permission_required('manage_attendance')
def close_kiosk(token):
    user_id = session['user_id']
    try:
        if close_kiosk_session(token):
            log_change(user_id, 'update', change_details=f'Closed attendance kiosk (token: {token})')
            flash('Kiosk closed successfully.', 'success')
        else:
            flash('Invalid or already closed token.', 'error')
    except Exception as e:
        flash('Failed to close kiosk.', 'error')
        print(f"Close kiosk error: {e}")

    return redirect(url_for('attendance.attendance_dashboard'))


# ----------------------------------------------------------------------
# AJAX Live Search for Kiosk
# ----------------------------------------------------------------------
@attendance_bp.route('/kiosk_search')
def kiosk_search():
    token = request.args.get('token')
    session_row = validate_kiosk_session(token) if token else None
    if not session_row or not session_row['active'] or datetime.now() > session_row['expires_at']:
        return jsonify({'error': 'invalid_token'}), 403

    search_term = request.args.get('search', '').strip()
    members = search_members(search_term)

    return jsonify([
        {'id': m['id'], 'name': f"{m['first_name']} {m['last_name']}".strip() or m['username'] or 'Unknown'}
        for m in members
    ])


# ----------------------------------------------------------------------
# Public Kiosk Page
# ----------------------------------------------------------------------
@attendance_bp.route('/kiosk', methods=['GET', 'POST'])
def kiosk():
    token = request.args.get('token') or request.form.get('token')
    session_row = validate_kiosk_session(token) if token else None
    if not session_row or not session_row['active'] or datetime.now() > session_row['expires_at']:
        return render_template('attendance/kiosk_closed.html'), 403

    if request.method == 'POST':
        result = validate_kiosk_checkin_form(request.form)
        if not result:
            return redirect(url_for('attendance.kiosk', token=token))

        member_id, pin = result
        member = get_member_for_checkin(member_id)

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
        check_in_utc = utc_now()

        try:
            record_attendance(member_id, today, check_in_utc)
            log_change(None, 'checkin', target_id=member_id,
                       change_details=f"Kiosk check-in: {member['first_name']} {member['last_name']}")
            flash(f"{member['first_name']} {member['last_name']} checked in!", 'success')
        except Exception as e:
            flash('Check-in failed.', 'error')
            print(f"Kiosk check-in error: {e}")

        return redirect(url_for('attendance.kiosk', token=token))

    return render_template('attendance/kiosk.html')


# ----------------------------------------------------------------------
# Self Check-In – Logged-in members only (My Portal)
# ----------------------------------------------------------------------
@attendance_bp.route('/self_checkin', methods=['GET', 'POST'])
@login_required
def self_checkin():
    """Self check-in for logged-in users only – accessed via My Portal dropdown."""
    user_id = session['user_id']
    user = get_user_for_self_checkin(user_id)
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('dashboard.dashboard'))

    today_str = date.today().strftime('%Y-%m-%d')
    nice_date = date.today().strftime('%A, %B %d, %Y')

    existing = get_existing_attendance(user_id, today_str)
    checked_in = existing is not None
    check_in_raw = existing['check_in'] if existing else None

    if request.method == 'POST' and not checked_in:
        client_iso = validate_self_checkin_form(request.form)
        check_in_utc = utc_now()

        if client_iso:
            try:
                dt = datetime.fromisoformat(client_iso.replace('Z', '+00:00'))
                check_in_utc = dt
            except (ValueError, TypeError):
                pass  # fallback to server time

        try:
            record_attendance(user_id, today_str, check_in_utc)
            log_change(user_id, 'checkin', target_id=user_id,
                       change_details='Self check-in via /attendance/self_checkin')
            flash('Thank you for checking in today!', 'success')
            checked_in = True
            check_in_raw = check_in_utc
        except Exception as e:
            flash('Check-in failed. Please try again.', 'error')
            print(f"Self check-in error: {e}")

    return render_template(
        'attendance/user_signin.html',
        user=user,
        nice_date=nice_date,
        checked_in=checked_in,
        check_in_raw=check_in_raw
    )