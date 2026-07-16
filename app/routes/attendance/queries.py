# app/routes/attendance/queries.py
# Attendance data-access layer (MariaDB / PyMySQL).

import pymysql
from app.models.db import get_db
from app.utils.time_utils import now_church


def church_today_str():
    """Church-local calendar date as YYYY-MM-DD."""
    return now_church().date().strftime('%Y-%m-%d')


def _campus_frag(alias_col='campus_id'):
    try:
        from app.models.campuses import campus_scope_sql
        return campus_scope_sql(alias_col)
    except Exception:
        return '', []


def get_today_attendance_count():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    today_str = church_today_str()
    frag, params = _campus_frag()
    cur.execute(f"""
        SELECT COUNT(*) AS count
        FROM attendance
        WHERE DATE(service_date) = %s{frag}
    """, [today_str, *params])
    result = cur.fetchone()
    return result['count'] if result else 0


def get_recent_days(limit=10):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    frag, params = _campus_frag()
    cur.execute(f"""
        SELECT DATE(service_date) AS date, COUNT(*) AS count
        FROM attendance
        WHERE 1=1{frag}
        GROUP BY DATE(service_date)
        ORDER BY DATE(service_date) DESC
        LIMIT %s
    """, [*params, limit])
    return cur.fetchall()


def get_day_count_and_attendees(service_date):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    frag, params = _campus_frag('a.campus_id')

    cur.execute(f"""
        SELECT COUNT(*) AS count
        FROM attendance a
        WHERE DATE(a.service_date) = %s{frag}
    """, [service_date, *params])
    count = cur.fetchone()['count']

    cur.execute(f"""
        SELECT u.id, u.first_name, u.last_name, u.username, a.check_in, a.checked_in_by
        FROM attendance a
        JOIN users u ON a.user_id = u.id
        WHERE DATE(a.service_date) = %s{frag}
        ORDER BY a.check_in DESC
    """, [service_date, *params])
    attendees = cur.fetchall()

    return count, attendees


def create_kiosk_session(user_id, token, expires_at):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO kiosk_sessions (token, created_by, expires_at, active)
            VALUES (%s, %s, %s, 1)
        """, (token, user_id, expires_at))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def close_kiosk_session(token):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("UPDATE kiosk_sessions SET active = 0 WHERE token = %s AND active = 1", (token,))
        db.commit()
        return cur.rowcount > 0
    except Exception:
        db.rollback()
        raise


def list_kiosk_sessions(active_only=True, limit=20):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    sql = """
        SELECT k.id, k.token, k.created_at, k.expires_at, k.active,
               u.username AS created_by_name
        FROM kiosk_sessions k
        LEFT JOIN users u ON k.created_by = u.id
    """
    if active_only:
        sql += " WHERE k.active = 1 "
    sql += " ORDER BY k.created_at DESC LIMIT %s"
    cur.execute(sql, (limit,))
    return cur.fetchall()


def validate_kiosk_session(token):
    if not token:
        return None
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "SELECT active, expires_at, created_by FROM kiosk_sessions WHERE token = %s",
        (token,),
    )
    return cur.fetchone()


def search_members(search_term):
    """Kiosk search: approved, not shadow-banned members only."""
    if not search_term:
        return []
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    like_param = f'%{search_term}%'
    cur.execute("""
        SELECT id, first_name, last_name, username
        FROM users
        WHERE (COALESCE(needs_approval, 0) = 0)
          AND (COALESCE(is_shadow_banned, 0) = 0)
          AND (
               LOWER(CONCAT(COALESCE(first_name,''), ' ', COALESCE(last_name,''))) LIKE LOWER(%s)
            OR LOWER(COALESCE(first_name,'')) LIKE LOWER(%s)
            OR LOWER(COALESCE(last_name,'')) LIKE LOWER(%s)
            OR LOWER(COALESCE(username,'')) LIKE LOWER(%s)
          )
        ORDER BY last_name, first_name
        LIMIT 50
    """, (like_param, like_param, like_param, like_param))
    return cur.fetchall()


def get_member_for_checkin(member_id):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT id, first_name, last_name, allow_proxy_checkin, checkin_pin,
               needs_approval, is_shadow_banned
        FROM users WHERE id = %s
    """, (member_id,))
    return cur.fetchone()


def record_attendance(user_id, service_date, check_in_utc, checked_in_by=None):
    """Insert or update attendance; preserve first check_in on re-hit."""
    db = get_db()
    cur = db.cursor()
    try:
        campus_id = None
        try:
            from app.models.campuses import resolve_campus_id_for_write
            campus_id = resolve_campus_id_for_write()
        except Exception:
            campus_id = None
        if campus_id is not None:
            try:
                cur.execute("""
                    INSERT INTO attendance (user_id, service_date, check_in, checked_in_by, campus_id)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        checked_in_by = COALESCE(VALUES(checked_in_by), checked_in_by)
                """, (user_id, service_date, check_in_utc, checked_in_by, campus_id))
                db.commit()
                return True
            except Exception:
                db.rollback()
        # Standard path / pre-campus schema
        cur.execute("""
            INSERT INTO attendance (user_id, service_date, check_in, checked_in_by)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                checked_in_by = COALESCE(VALUES(checked_in_by), checked_in_by)
        """, (user_id, service_date, check_in_utc, checked_in_by))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def get_user_for_self_checkin(user_id):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT first_name, last_name, username
        FROM users WHERE id = %s
    """, (user_id,))
    return cur.fetchone()


def get_existing_attendance(user_id, service_date):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT check_in
        FROM attendance
        WHERE user_id = %s AND DATE(service_date) = %s
    """, (user_id, service_date))
    return cur.fetchone()


# ---------------------------------------------------------------------------
# Full-scale attendance reporting
# ---------------------------------------------------------------------------

from datetime import date, datetime, timedelta


RANGE_PRESETS = (
    ('today', 'Today'),
    ('yesterday', 'Yesterday'),
    ('week', 'This week'),
    ('last_week', 'Last week'),
    ('month', 'This month'),
    ('last_month', 'Last month'),
    ('quarter', 'This quarter'),
    ('year', 'This year'),
    ('ytd', 'Year to date'),
    ('last_year', 'Last year'),
    ('2y', 'Last 2 years'),
    ('5y', 'Last 5 years'),
    ('all', 'All time'),
    ('custom', 'Custom range'),
)

GRAIN_OPTIONS = (
    ('auto', 'Auto'),
    ('day', 'By day'),
    ('week', 'By week'),
    ('month', 'By month'),
    ('year', 'By year'),
)


def _parse_ymd(value):
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def resolve_report_range(range_key='month', start=None, end=None):
    """
    Resolve a named range (or custom dates) into inclusive start/end dates
    and a human label. Dates are church-local calendar days.
    """
    today = now_church().date()
    key = (range_key or 'month').strip().lower()
    start_d = _parse_ymd(start)
    end_d = _parse_ymd(end)

    if key == 'custom' and start_d and end_d:
        if start_d > end_d:
            start_d, end_d = end_d, start_d
        return {
            'range_key': 'custom',
            'start': start_d,
            'end': end_d,
            'label': f"{start_d.strftime('%b %d, %Y')} – {end_d.strftime('%b %d, %Y')}",
        }

    if key == 'today':
        start_d = end_d = today
        label = 'Today'
    elif key == 'yesterday':
        start_d = end_d = today - timedelta(days=1)
        label = 'Yesterday'
    elif key == 'week':
        # Monday-start week (ISO)
        start_d = today - timedelta(days=today.weekday())
        end_d = today
        label = 'This week'
    elif key == 'last_week':
        this_monday = today - timedelta(days=today.weekday())
        start_d = this_monday - timedelta(days=7)
        end_d = this_monday - timedelta(days=1)
        label = 'Last week'
    elif key == 'month':
        start_d = today.replace(day=1)
        end_d = today
        label = today.strftime('%B %Y')
    elif key == 'last_month':
        first_this = today.replace(day=1)
        end_d = first_this - timedelta(days=1)
        start_d = end_d.replace(day=1)
        label = start_d.strftime('%B %Y')
    elif key == 'quarter':
        q = (today.month - 1) // 3
        start_d = date(today.year, q * 3 + 1, 1)
        end_d = today
        label = f"Q{q + 1} {today.year}"
    elif key in ('year', 'ytd'):
        start_d = date(today.year, 1, 1)
        end_d = today
        label = f"Year to date {today.year}" if key == 'ytd' else str(today.year)
    elif key == 'last_year':
        start_d = date(today.year - 1, 1, 1)
        end_d = date(today.year - 1, 12, 31)
        label = str(today.year - 1)
    elif key == '2y':
        start_d = today - timedelta(days=730)
        end_d = today
        label = 'Last 2 years'
    elif key == '5y':
        start_d = today - timedelta(days=365 * 5)
        end_d = today
        label = 'Last 5 years'
    elif key == 'all':
        # Earliest record or 10 years back as soft floor
        start_d = _earliest_attendance_date() or (today - timedelta(days=365 * 10))
        end_d = today
        label = 'All time'
    else:
        # Default: this month
        start_d = today.replace(day=1)
        end_d = today
        key = 'month'
        label = today.strftime('%B %Y')

    return {
        'range_key': key,
        'start': start_d,
        'end': end_d,
        'label': label,
    }


def _earliest_attendance_date():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    frag, params = _campus_frag()
    try:
        cur.execute(f"SELECT MIN(DATE(service_date)) AS d FROM attendance WHERE 1=1{frag}", params)
        row = cur.fetchone()
        d = row.get('d') if row else None
        return _parse_ymd(d)
    except Exception:
        return None


def pick_grain(start_d, end_d, grain='auto'):
    """Choose chart/table grain from span length."""
    g = (grain or 'auto').strip().lower()
    if g in ('day', 'week', 'month', 'year'):
        return g
    days = max((end_d - start_d).days + 1, 1)
    if days <= 21:
        return 'day'
    if days <= 120:
        return 'week'
    if days <= 900:
        return 'month'
    return 'year'


def _date_where(alias=''):
    """SQL fragment: DATE(col) BETWEEN %s AND %s + campus."""
    col = f"{alias}service_date" if alias else 'service_date'
    campus_col = f"{alias}campus_id" if alias else 'campus_id'
    frag, params = _campus_frag(campus_col)
    return f" AND DATE({col}) BETWEEN %s AND %s{frag}", params


def get_period_summary(start_d, end_d):
    """KPIs for an inclusive date range."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    where, campus_params = _date_where()
    params = [start_d.isoformat(), end_d.isoformat(), *campus_params]

    cur.execute(f"""
        SELECT
            COUNT(*) AS total_checkins,
            COUNT(DISTINCT user_id) AS unique_people,
            COUNT(DISTINCT DATE(service_date)) AS days_with_attendance,
            MIN(DATE(service_date)) AS first_day,
            MAX(DATE(service_date)) AS last_day
        FROM attendance
        WHERE 1=1{where}
    """, params)
    row = cur.fetchone() or {}

    # Peak day
    cur.execute(f"""
        SELECT DATE(service_date) AS d, COUNT(*) AS c
        FROM attendance
        WHERE 1=1{where}
        GROUP BY DATE(service_date)
        ORDER BY c DESC, d DESC
        LIMIT 1
    """, params)
    peak = cur.fetchone() or {}

    span_days = max((end_d - start_d).days + 1, 1)
    total = int(row.get('total_checkins') or 0)
    unique = int(row.get('unique_people') or 0)
    days_active = int(row.get('days_with_attendance') or 0)

    return {
        'total_checkins': total,
        'unique_people': unique,
        'days_with_attendance': days_active,
        'span_days': span_days,
        'avg_per_calendar_day': round(total / span_days, 1) if span_days else 0,
        'avg_per_active_day': round(total / days_active, 1) if days_active else 0,
        'peak_date': peak.get('d'),
        'peak_count': int(peak.get('c') or 0),
        'first_day': row.get('first_day'),
        'last_day': row.get('last_day'),
    }


def get_series(start_d, end_d, grain='day'):
    """
    Time series of check-in counts.
    Returns list of {period_key, label, checkins, unique_people}.
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    where, campus_params = _date_where()
    params = [start_d.isoformat(), end_d.isoformat(), *campus_params]
    grain = (grain or 'day').lower()

    if grain == 'week':
        # ISO week (mode 3: Monday first, week 1 has Jan 4)
        group_expr = "YEARWEEK(service_date, 3)"
        select_key = "YEARWEEK(service_date, 3) AS period_key"
        order = "period_key ASC"
    elif grain == 'month':
        # Escape % for PyMySQL mogrify (%% → literal %)
        group_expr = "DATE_FORMAT(service_date, '%%Y-%%m')"
        select_key = "DATE_FORMAT(service_date, '%%Y-%%m') AS period_key"
        order = "period_key ASC"
    elif grain == 'year':
        group_expr = "YEAR(service_date)"
        select_key = "YEAR(service_date) AS period_key"
        order = "period_key ASC"
    else:
        grain = 'day'
        group_expr = "DATE(service_date)"
        select_key = "DATE(service_date) AS period_key"
        order = "period_key ASC"

    cur.execute(f"""
        SELECT
            {select_key},
            COUNT(*) AS checkins,
            COUNT(DISTINCT user_id) AS unique_people
        FROM attendance
        WHERE 1=1{where}
        GROUP BY {group_expr}
        ORDER BY {order}
    """, params)
    rows = cur.fetchall() or []

    series = []
    for r in rows:
        key = r.get('period_key')
        series.append({
            'period_key': str(key) if key is not None else '',
            'label': _format_period_label(key, grain),
            'checkins': int(r.get('checkins') or 0),
            'unique_people': int(r.get('unique_people') or 0),
            'grain': grain,
        })

    # Fill gaps for day grain so charts look continuous (cap to avoid huge series)
    if grain == 'day' and series and (end_d - start_d).days <= 120:
        by_key = {s['period_key']: s for s in series}
        filled = []
        d = start_d
        while d <= end_d:
            k = d.isoformat()
            if k in by_key:
                filled.append(by_key[k])
            else:
                filled.append({
                    'period_key': k,
                    'label': d.strftime('%b %d'),
                    'checkins': 0,
                    'unique_people': 0,
                    'grain': 'day',
                })
            d += timedelta(days=1)
        series = filled

    max_c = max((s['checkins'] for s in series), default=0) or 1
    for s in series:
        s['pct'] = round(100.0 * s['checkins'] / max_c, 1)
    return series


def _format_period_label(key, grain):
    if key is None:
        return '—'
    if grain == 'day':
        d = _parse_ymd(key)
        if d:
            return d.strftime('%a %b %d, %Y') if False else d.strftime('%b %d')
        return str(key)
    if grain == 'week':
        # YEARWEEK returns e.g. 202612 — year*100 + week
        try:
            n = int(key)
            year, week = divmod(n, 100)
            return f"{year} W{week:02d}"
        except (TypeError, ValueError):
            return str(key)
    if grain == 'month':
        try:
            d = datetime.strptime(str(key), '%Y-%m')
            return d.strftime('%b %Y')
        except ValueError:
            return str(key)
    if grain == 'year':
        return str(key)
    return str(key)


def get_day_of_week_breakdown(start_d, end_d):
    """Sunday–Saturday totals for the range."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    where, campus_params = _date_where()
    params = [start_d.isoformat(), end_d.isoformat(), *campus_params]
    # MySQL DAYOFWEEK: 1=Sunday … 7=Saturday
    cur.execute(f"""
        SELECT DAYOFWEEK(service_date) AS dow, COUNT(*) AS checkins,
               COUNT(DISTINCT user_id) AS unique_people
        FROM attendance
        WHERE 1=1{where}
        GROUP BY DAYOFWEEK(service_date)
        ORDER BY dow
    """, params)
    by_dow = {int(r['dow']): r for r in (cur.fetchall() or []) if r.get('dow') is not None}
    names = {1: 'Sunday', 2: 'Monday', 3: 'Tuesday', 4: 'Wednesday',
             5: 'Thursday', 6: 'Friday', 7: 'Saturday'}
    out = []
    max_c = max((int(by_dow[d]['checkins']) for d in by_dow), default=0) or 1
    for i in range(1, 8):
        r = by_dow.get(i) or {}
        c = int(r.get('checkins') or 0)
        out.append({
            'dow': i,
            'name': names[i],
            'checkins': c,
            'unique_people': int(r.get('unique_people') or 0),
            'pct': round(100.0 * c / max_c, 1),
        })
    return out


def get_top_attendees(start_d, end_d, limit=25):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    where, campus_params = _date_where('a.')
    params = [start_d.isoformat(), end_d.isoformat(), *campus_params, int(limit)]
    cur.execute(f"""
        SELECT u.id, u.first_name, u.last_name, u.username,
               COUNT(*) AS visits,
               MIN(DATE(a.service_date)) AS first_in_range,
               MAX(DATE(a.service_date)) AS last_in_range
        FROM attendance a
        JOIN users u ON u.id = a.user_id
        WHERE 1=1{where}
        GROUP BY u.id, u.first_name, u.last_name, u.username
        ORDER BY visits DESC, u.last_name, u.first_name
        LIMIT %s
    """, params)
    rows = cur.fetchall() or []
    for r in rows:
        r['visits'] = int(r.get('visits') or 0)
    return rows


def get_first_time_in_range(start_d, end_d, limit=40):
    """People whose first-ever check-in falls inside the range."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    frag, campus_params = _campus_frag('a.campus_id')
    params = [*campus_params, start_d.isoformat(), end_d.isoformat(), int(limit)]
    cur.execute(f"""
        SELECT u.id, u.first_name, u.last_name, u.username,
               t.first_visit
        FROM (
            SELECT user_id, MIN(DATE(service_date)) AS first_visit
            FROM attendance a
            WHERE 1=1{frag}
            GROUP BY user_id
        ) t
        JOIN users u ON u.id = t.user_id
        WHERE t.first_visit BETWEEN %s AND %s
        ORDER BY t.first_visit DESC, u.last_name
        LIMIT %s
    """, params)
    return cur.fetchall() or []


def get_comparison_summary(start_d, end_d):
    """Same-length previous period KPIs + percent change."""
    span = (end_d - start_d).days + 1
    prev_end = start_d - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span - 1)
    current = get_period_summary(start_d, end_d)
    previous = get_period_summary(prev_start, prev_end)

    def delta(cur_v, prev_v):
        cur_v = float(cur_v or 0)
        prev_v = float(prev_v or 0)
        if prev_v == 0:
            return None if cur_v == 0 else 100.0
        return round(100.0 * (cur_v - prev_v) / prev_v, 1)

    return {
        'previous_start': prev_start,
        'previous_end': prev_end,
        'current': current,
        'previous': previous,
        'delta_checkins': delta(current['total_checkins'], previous['total_checkins']),
        'delta_unique': delta(current['unique_people'], previous['unique_people']),
        'delta_avg_active': delta(current['avg_per_active_day'], previous['avg_per_active_day']),
    }


def get_year_over_year_months(years=5):
    """
    Last N calendar years of monthly totals for multi-year heat view.
    Returns {years: [2022,...], rows: [{month:1, label:'Jan', y2022: n, ...}]}.
    """
    today = now_church().date()
    years = max(1, min(int(years or 5), 10))
    year_list = list(range(today.year - years + 1, today.year + 1))
    start_d = date(year_list[0], 1, 1)
    end_d = today

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    where, campus_params = _date_where()
    params = [start_d.isoformat(), end_d.isoformat(), *campus_params]
    cur.execute(f"""
        SELECT YEAR(service_date) AS y, MONTH(service_date) AS m, COUNT(*) AS c
        FROM attendance
        WHERE 1=1{where}
        GROUP BY YEAR(service_date), MONTH(service_date)
    """, params)
    grid = {}
    for r in cur.fetchall() or []:
        grid[(int(r['y']), int(r['m']))] = int(r['c'] or 0)

    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    rows = []
    for m in range(1, 13):
        row = {'month': m, 'label': month_names[m - 1]}
        for y in year_list:
            row[f'y{y}'] = grid.get((y, m), 0)
        rows.append(row)
    return {'years': year_list, 'rows': rows}


def iter_export_rows(start_d, end_d):
    """Flat attendance rows for CSV export."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    where, campus_params = _date_where('a.')
    params = [start_d.isoformat(), end_d.isoformat(), *campus_params]
    cur.execute(f"""
        SELECT DATE(a.service_date) AS service_date,
               a.check_in,
               u.id AS user_id,
               u.first_name, u.last_name, u.username, u.email
        FROM attendance a
        JOIN users u ON u.id = a.user_id
        WHERE 1=1{where}
        ORDER BY a.service_date DESC, a.check_in DESC
        LIMIT 50000
    """, params)
    return cur.fetchall() or []


def get_dashboard_quick_stats():
    """Compact stats for the attendance dashboard header."""
    today = now_church().date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    year_start = date(today.year, 1, 1)
    return {
        'today': get_period_summary(today, today),
        'week': get_period_summary(week_start, today),
        'month': get_period_summary(month_start, today),
        'year': get_period_summary(year_start, today),
        'recent_days': get_recent_days(14),
    }
