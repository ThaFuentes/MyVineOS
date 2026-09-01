# app/routes/attendance/views.py

from flask import render_template, request, redirect, url_for, flash, session, jsonify, Response
from datetime import datetime, timedelta
from calendar import monthrange
import csv
import io

from . import attendance_bp
from .queries import (
    get_today_attendance_count, get_recent_days, get_day_count_and_attendees,
    create_kiosk_session, close_kiosk_session, validate_kiosk_session,
    list_kiosk_sessions, search_members, get_member_for_checkin, record_attendance,
    get_user_for_self_checkin, get_existing_attendance, church_today_str,
    resolve_report_range, pick_grain, get_period_summary, get_series,
    get_day_of_week_breakdown, get_top_attendees, get_first_time_in_range,
    get_comparison_summary, get_year_over_year_months, iter_export_rows,
    get_dashboard_quick_stats, RANGE_PRESETS, GRAIN_OPTIONS,
)
from .forms import validate_kiosk_checkin_form
from .utils import generate_kiosk_token, get_kiosk_expiration

from app.utils.decorators import login_required, permission_required
from werkzeug.security import check_password_hash
from app.models.log import log_change
from app.utils.time_utils import utc_now, format_church, now_church


def _kiosk_still_valid(session_row):
    if not session_row or not session_row.get('active'):
        return False
    expires = session_row.get('expires_at')
    if not expires:
        return False
    # Compare as naive/aware-safe strings via timestamp if possible
    now = utc_now()
    if getattr(expires, 'tzinfo', None) is None:
        # DB often returns naive UTC
        from datetime import timezone
        expires = expires.replace(tzinfo=timezone.utc)
    return now < expires


@attendance_bp.route('/')
@attendance_bp.route('/dashboard')
@permission_required('manage_attendance')
def attendance_dashboard():
    today = now_church().date()
    try:
        stats = get_dashboard_quick_stats()
        recent_days = stats.get('recent_days') or get_recent_days(14)
        today_count = stats['today']['total_checkins']
    except Exception as e:
        print(f"Attendance dashboard stats error: {e}")
        stats = None
        recent_days = get_recent_days(14)
        today_count = get_today_attendance_count()

    return render_template(
        'attendance/attendance_dashboard.html',
        today_date=today.strftime('%Y-%m-%d'),
        today_count=today_count,
        recent_days=recent_days,
        stats=stats,
        range_presets=RANGE_PRESETS,
    )


@attendance_bp.route('/reports')
@permission_required('manage_attendance')
def attendance_reports():
    range_key = (request.args.get('range') or 'month').strip().lower()
    grain_req = (request.args.get('grain') or 'auto').strip().lower()
    start_arg = request.args.get('start')
    end_arg = request.args.get('end')

    period = resolve_report_range(range_key, start_arg, end_arg)
    start_d, end_d = period['start'], period['end']
    grain = pick_grain(start_d, end_d, grain_req)

    summary = get_period_summary(start_d, end_d)
    series = get_series(start_d, end_d, grain)
    dow = get_day_of_week_breakdown(start_d, end_d)
    top = get_top_attendees(start_d, end_d, limit=25)
    first_timers = get_first_time_in_range(start_d, end_d, limit=30)
    comparison = get_comparison_summary(start_d, end_d)
    yoy = get_year_over_year_months(5)
    yoy_max = 1
    for row in yoy.get('rows') or []:
        for y in yoy.get('years') or []:
            yoy_max = max(yoy_max, int(row.get(f'y{y}') or 0))

    # Chart bar heights in px (CSS % needs a fixed parent height)
    chart_max_px = 140
    for s in series:
        s['bar_px'] = max(3, int(round(chart_max_px * (s.get('pct') or 0) / 100.0))) if s.get('checkins') else 2

    # Daily table only when grain is day or range is short enough
    daily_rows = []
    if grain == 'day' or (end_d - start_d).days <= 45:
        daily_rows = get_series(start_d, end_d, 'day')
        if (end_d - start_d).days > 21:
            daily_rows = [r for r in daily_rows if r['checkins'] > 0]

    return render_template(
        'attendance/reports.html',
        period=period,
        grain=grain,
        grain_req=grain_req,
        summary=summary,
        series=series,
        dow=dow,
        top_attendees=top,
        first_timers=first_timers,
        comparison=comparison,
        yoy=yoy,
        yoy_max=yoy_max,
        daily_rows=daily_rows,
        range_presets=RANGE_PRESETS,
        grain_options=GRAIN_OPTIONS,
        start_str=start_d.isoformat(),
        end_str=end_d.isoformat(),
    )


@attendance_bp.route('/reports/export.csv')
@permission_required('manage_attendance')
def attendance_export_csv():
    range_key = (request.args.get('range') or 'month').strip().lower()
    period = resolve_report_range(
        range_key,
        request.args.get('start'),
        request.args.get('end'),
    )
    start_d, end_d = period['start'], period['end']
    rows = iter_export_rows(start_d, end_d)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        'service_date', 'check_in_utc', 'user_id',
        'first_name', 'last_name', 'username', 'email',
    ])
    for r in rows:
        writer.writerow([
            r.get('service_date'),
            r.get('check_in'),
            r.get('user_id'),
            r.get('first_name') or '',
            r.get('last_name') or '',
            r.get('username') or '',
            r.get('email') or '',
        ])

    filename = f"attendance_{start_d.isoformat()}_to_{end_d.isoformat()}.csv"
    return Response(
        buf.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


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

    # Context: week / month totals for this date
    week_start = service_date - timedelta(days=service_date.weekday())
    week_end = week_start + timedelta(days=6)
    month_start = service_date.replace(day=1)
    month_end = service_date.replace(day=monthrange(service_date.year, service_date.month)[1])
    week_summary = get_period_summary(week_start, week_end)
    month_summary = get_period_summary(month_start, month_end)

    return render_template(
        'attendance/day_detail.html',
        date=date,
        nice_date=nice_date,
        count=count,
        attendees=attendees,
        week_summary=week_summary,
        month_summary=month_summary,
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat(),
        month_start=month_start.isoformat(),
        month_end=month_end.isoformat(),
    )


@attendance_bp.route('/sessions')
@permission_required('manage_attendance')
def kiosk_sessions():
    sessions = list_kiosk_sessions(active_only=False, limit=30)
    for s in sessions:
        if s.get('created_at'):
            s['formatted_created'] = format_church(s['created_at'], '%b %d, %Y %I:%M %p')
        if s.get('expires_at'):
            s['formatted_expires'] = format_church(s['expires_at'], '%b %d, %Y %I:%M %p')
        s['is_live'] = _kiosk_still_valid(s)
    return render_template('attendance/sessions.html', sessions=sessions)


@attendance_bp.route('/open_kiosk')
@permission_required('manage_attendance')
def open_kiosk():
    user_id = session['user_id']
    token = generate_kiosk_token()
    expires_at = get_kiosk_expiration()

    try:
        create_kiosk_session(user_id, token, expires_at)
        log_change(user_id, 'create', change_details=f'Opened attendance kiosk (token: {token[:8]}…)')
        flash('Kiosk opened - launch below or share URL.', 'success')
        kiosk_url = url_for('attendance.kiosk', token=token, _external=True)
    except Exception as e:
        flash('Failed to open kiosk.', 'error')
        print(f"Open kiosk error: {e}")
        kiosk_url = None

    return render_template('attendance/open_kiosk.html', kiosk_url=kiosk_url, token=token)


@attendance_bp.route('/close/<token>', methods=['POST'])
@permission_required('manage_attendance')
def close_kiosk(token):
    user_id = session['user_id']
    try:
        if close_kiosk_session(token):
            log_change(user_id, 'update', change_details=f'Closed attendance kiosk (token: {token[:8]}…)')
            flash('Kiosk closed successfully.', 'success')
        else:
            flash('Invalid or already closed token.', 'error')
    except Exception as e:
        flash('Failed to close kiosk.', 'error')
        print(f"Close kiosk error: {e}")

    next_url = request.form.get('next') or url_for('attendance.kiosk_sessions')
    return redirect(next_url)


@attendance_bp.route('/kiosk_search')
def kiosk_search():
    token = request.args.get('token')
    session_row = validate_kiosk_session(token) if token else None
    if not _kiosk_still_valid(session_row):
        return jsonify({'error': 'invalid_token'}), 403

    search_term = request.args.get('search', '').strip()
    members = search_members(search_term)

    return jsonify([
        {
            'id': m['id'],
            'name': f"{m['first_name'] or ''} {m['last_name'] or ''}".strip() or m['username'] or 'Unknown',
        }
        for m in members
    ])


@attendance_bp.route('/kiosk', methods=['GET', 'POST'])
def kiosk():
    token = request.args.get('token') or request.form.get('token')
    session_row = validate_kiosk_session(token) if token else None
    if not _kiosk_still_valid(session_row):
        return render_template('attendance/kiosk_closed.html'), 403

    if request.method == 'POST':
        result = validate_kiosk_checkin_form(request.form)
        if not result:
            return redirect(url_for('attendance.kiosk', token=token))

        member_id, pin = result
        try:
            member_id = int(member_id)
        except (TypeError, ValueError):
            flash('Invalid member.', 'error')
            return redirect(url_for('attendance.kiosk', token=token))

        member = get_member_for_checkin(member_id)

        if not member:
            flash('Member not found.', 'error')
            return redirect(url_for('attendance.kiosk', token=token))

        if member.get('needs_approval') or member.get('is_shadow_banned'):
            flash('This member cannot check in here.', 'error')
            return redirect(url_for('attendance.kiosk', token=token))

        if not member['allow_proxy_checkin'] and member['checkin_pin']:
            if not pin or not check_password_hash(member['checkin_pin'], pin):
                flash('Invalid PIN.', 'error')
                return redirect(url_for('attendance.kiosk', token=token))
        elif not member['allow_proxy_checkin'] and not member['checkin_pin']:
            flash('This member requires staff assistance.', 'error')
            return redirect(url_for('attendance.kiosk', token=token))

        today = church_today_str()
        check_in_utc = utc_now()
        actor = session_row.get('created_by')

        try:
            record_attendance(member_id, today, check_in_utc, checked_in_by=actor)
            log_change(
                actor, 'checkin', target_id=member_id,
                change_details=f"Kiosk check-in: {member['first_name']} {member['last_name']}",
            )
            flash(f"{member['first_name']} {member['last_name']} checked in!", 'success')
        except Exception as e:
            flash('Check-in failed.', 'error')
            print(f"Kiosk check-in error: {e}")

        return redirect(url_for('attendance.kiosk', token=token))

    return render_template('attendance/kiosk.html')


@attendance_bp.route('/self_checkin', methods=['GET', 'POST'])
@login_required
def self_checkin():
    user_id = session['user_id']
    user = get_user_for_self_checkin(user_id)
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('dashboard.dashboard'))

    today = now_church().date()
    today_str = today.strftime('%Y-%m-%d')
    nice_date = today.strftime('%A, %B %d, %Y')

    existing = get_existing_attendance(user_id, today_str)
    checked_in = existing is not None
    check_in_raw = existing['check_in'] if existing else None

    if request.method == 'POST' and not checked_in:
        # Always use server UTC — ignore client-supplied timestamps for integrity
        check_in_utc = utc_now()
        try:
            record_attendance(user_id, today_str, check_in_utc, checked_in_by=user_id)
            log_change(
                user_id, 'checkin', target_id=user_id,
                change_details='Self check-in via /attendance/self_checkin',
            )
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
        check_in_raw=check_in_raw,
    )
