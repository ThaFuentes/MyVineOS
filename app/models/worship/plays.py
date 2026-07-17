import csv
import io
import pymysql
from datetime import date, datetime, timedelta
from app.models.db import get_db


def log_service_plays(setlist_id: int, service_date: str, song_ids: list, user_id: int):
    if not song_ids or not service_date:
        return 0
    db = get_db()
    cur = db.cursor()
    count = 0
    for sid in song_ids:
        cur.execute("""
            INSERT INTO worship_song_plays (song_id, setlist_id, service_date, recorded_by)
            VALUES (%s, %s, %s, %s)
        """, (sid, setlist_id, service_date, user_id))
        count += 1
    cur.execute(
        "UPDATE worship_setlists SET service_confirmed_at = NOW() WHERE id = %s",
        (setlist_id,),
    )
    db.commit()
    return count


def get_play_history(limit=100):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT p.*, s.title, s.artist, s.ccli_song_number
        FROM worship_song_plays p
        JOIN worship_songs s ON s.id = p.song_id
        ORDER BY p.service_date DESC, p.played_at DESC
        LIMIT %s
    """, (limit,))
    return cur.fetchall()


def _parse_ymd(s: str) -> date | None:
    try:
        return datetime.strptime((s or '').strip()[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


def resolve_ccli_report_range(period: str, start: str = '', end: str = '', on_date: str = '') -> tuple[date, date, str]:
    """
    Returns (start_date, end_date, label).
    period: day | week | month | year | custom
    """
    today = date.today()
    period = (period or 'week').strip().lower()
    if period == 'day':
        d = _parse_ymd(on_date) or today
        return d, d, f'Day {d.isoformat()}'
    if period == 'week':
        # Monday–Sunday containing on_date (or today)
        d = _parse_ymd(on_date) or today
        start_d = d - timedelta(days=d.weekday())
        end_d = start_d + timedelta(days=6)
        return start_d, end_d, f'Week {start_d.isoformat()} → {end_d.isoformat()}'
    if period == 'month':
        d = _parse_ymd(on_date) or today
        start_d = d.replace(day=1)
        if d.month == 12:
            end_d = d.replace(year=d.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_d = d.replace(month=d.month + 1, day=1) - timedelta(days=1)
        return start_d, end_d, f'Month {start_d.strftime("%Y-%m")}'
    if period == 'year':
        d = _parse_ymd(on_date) or today
        start_d = date(d.year, 1, 1)
        end_d = date(d.year, 12, 31)
        return start_d, end_d, f'Year {d.year}'
    # custom
    start_d = _parse_ymd(start) or today.replace(day=1)
    end_d = _parse_ymd(end) or today
    if end_d < start_d:
        start_d, end_d = end_d, start_d
    return start_d, end_d, f'{start_d.isoformat()} → {end_d.isoformat()}'


def get_ccli_usage_report(
    start_date: date | str,
    end_date: date | str,
    *,
    include_planned: bool = False,
) -> dict:
    """
    Songs (with CCLI #) used in the date range.
    Primary source: confirmed service plays (worship_song_plays).
    Optional: dated setlists with songs in range (planned, even if not confirmed).
    """
    if isinstance(start_date, str):
        start_date = _parse_ymd(start_date) or date.today()
    if isinstance(end_date, str):
        end_date = _parse_ymd(end_date) or date.today()
    start_s = start_date.isoformat()
    end_s = end_date.isoformat()

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    # Confirmed plays
    cur.execute(
        """
        SELECT
            s.id AS song_id,
            s.title,
            s.artist,
            s.ccli_song_number,
            s.copyright_line,
            s.publisher,
            p.service_date,
            p.setlist_id,
            sl.title AS setlist_title,
            'played' AS usage_kind
        FROM worship_song_plays p
        JOIN worship_songs s ON s.id = p.song_id
        LEFT JOIN worship_setlists sl ON sl.id = p.setlist_id
        WHERE p.service_date >= %s AND p.service_date <= %s
        ORDER BY p.service_date ASC, s.title ASC
        """,
        (start_s, end_s),
    )
    play_rows = list(cur.fetchall() or [])

    plan_rows = []
    if include_planned:
        cur.execute(
            """
            SELECT
                s.id AS song_id,
                s.title,
                s.artist,
                s.ccli_song_number,
                s.copyright_line,
                s.publisher,
                sl.service_date,
                sl.id AS setlist_id,
                sl.title AS setlist_title,
                'planned' AS usage_kind
            FROM worship_setlist_songs ss
            JOIN worship_setlists sl ON sl.id = ss.setlist_id
            JOIN worship_songs s ON s.id = ss.song_id
            WHERE sl.service_date IS NOT NULL
              AND sl.service_date >= %s AND sl.service_date <= %s
            ORDER BY sl.service_date ASC, s.title ASC
            """,
            (start_s, end_s),
        )
        plan_rows = list(cur.fetchall() or [])

    # Prefer played; add planned only if that song+date wasn't already logged as played
    played_keys = {
        (str(r.get('service_date')), int(r['song_id']))
        for r in play_rows
        if r.get('song_id')
    }
    rows = list(play_rows)
    for r in plan_rows:
        key = (str(r.get('service_date')), int(r['song_id']))
        if key not in played_keys:
            rows.append(r)

    rows.sort(key=lambda r: (str(r.get('service_date') or ''), (r.get('title') or '').lower()))

    # Unique CCLI summary (for reporting paste into CCLI tools)
    by_ccli: dict[str, dict] = {}
    missing_ccli = []
    for r in rows:
        ccli = (r.get('ccli_song_number') or '').strip()
        title = (r.get('title') or 'Untitled').strip()
        if not ccli:
            missing_ccli.append(r)
            continue
        if ccli not in by_ccli:
            by_ccli[ccli] = {
                'ccli_song_number': ccli,
                'title': title,
                'artist': (r.get('artist') or '').strip(),
                'copyright_line': (r.get('copyright_line') or '').strip(),
                'times_used': 0,
                'dates': set(),
            }
        by_ccli[ccli]['times_used'] += 1
        if r.get('service_date'):
            by_ccli[ccli]['dates'].add(str(r['service_date'])[:10])

    unique_list = []
    for item in sorted(by_ccli.values(), key=lambda x: (x['title'] or '').lower()):
        dates = sorted(item['dates'])
        unique_list.append({
            'ccli_song_number': item['ccli_song_number'],
            'title': item['title'],
            'artist': item['artist'],
            'copyright_line': item['copyright_line'],
            'times_used': item['times_used'],
            'dates': dates,
            'dates_text': ', '.join(dates),
        })

    church_license = ''
    church_name = ''
    try:
        from app.models.worship.charts import get_ccli_settings
        settings = get_ccli_settings()
        church_license = settings.get('ccli_license_number') or ''
        church_name = settings.get('organization_name') or ''
    except Exception:
        pass

    return {
        'start_date': start_s,
        'end_date': end_s,
        'include_planned': include_planned,
        'rows': rows,
        'unique_ccli': unique_list,
        'missing_ccli': missing_ccli,
        'play_count': len(play_rows),
        'planned_only_count': max(0, len(rows) - len(play_rows)),
        'unique_count': len(unique_list),
        'missing_count': len(missing_ccli),
        'church_license': church_license,
        'church_name': church_name,
    }


def format_ccli_report_text(report: dict, period_label: str = '') -> str:
    """Plain-text body for email or print."""
    lines = [
        'CCLI song usage report',
        period_label or f"{report.get('start_date')} to {report.get('end_date')}",
        '',
    ]
    if report.get('church_name'):
        lines.append(f"Church: {report['church_name']}")
    if report.get('church_license'):
        lines.append(f"CCLI church license #: {report['church_license']}")
    lines.append(
        f"Songs with CCLI #: {report.get('unique_count', 0)} unique · "
        f"{len(report.get('rows') or [])} usage rows · "
        f"Missing CCLI #: {report.get('missing_count', 0)}"
    )
    if report.get('include_planned'):
        lines.append('(Includes planned setlist songs not yet confirmed as played.)')
    lines.append('')
    lines.append('=== UNIQUE CCLI NUMBERS (summary) ===')
    lines.append('CCLI # | Title | Artist | Times used | Dates')
    for u in report.get('unique_ccli') or []:
        lines.append(
            f"{u.get('ccli_song_number') or '—'} | {u.get('title') or '—'} | "
            f"{u.get('artist') or '—'} | {u.get('times_used') or 0} | {u.get('dates_text') or '—'}"
        )
    if not report.get('unique_ccli'):
        lines.append('(none — no songs with a CCLI number in this range)')
    lines.append('')
    lines.append('=== DETAIL (each service use) ===')
    lines.append('Date | CCLI # | Title | Artist | Kind')
    for r in report.get('rows') or []:
        lines.append(
            f"{str(r.get('service_date') or '—')[:10]} | "
            f"{(r.get('ccli_song_number') or 'MISSING').strip()} | "
            f"{r.get('title') or '—'} | {r.get('artist') or '—'} | "
            f"{r.get('usage_kind') or '—'}"
        )
    if report.get('missing_ccli'):
        lines.append('')
        lines.append('=== SONGS USED WITHOUT CCLI # (add numbers on the song for next time) ===')
        for r in report['missing_ccli']:
            lines.append(
                f"{str(r.get('service_date') or '—')[:10]} | {r.get('title') or '—'} | {r.get('artist') or '—'}"
            )
    lines.append('')
    lines.append(
        'This list is for your church CCLI reporting records. '
        'Submit usage through your official CCLI account as required by your license.'
    )
    return '\n'.join(lines)


def format_ccli_report_csv(report: dict) -> str:
    """CSV download: unique summary + detail sheets as two blocks."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['CCLI Usage Report', report.get('start_date'), 'to', report.get('end_date')])
    if report.get('church_license'):
        w.writerow(['Church CCLI license #', report['church_license']])
    if report.get('church_name'):
        w.writerow(['Church name', report['church_name']])
    w.writerow([])
    w.writerow(['UNIQUE SUMMARY'])
    w.writerow(['CCLI Song Number', 'Title', 'Artist', 'Times Used', 'Dates Used', 'Copyright'])
    for u in report.get('unique_ccli') or []:
        w.writerow([
            u.get('ccli_song_number') or '',
            u.get('title') or '',
            u.get('artist') or '',
            u.get('times_used') or 0,
            u.get('dates_text') or '',
            u.get('copyright_line') or '',
        ])
    w.writerow([])
    w.writerow(['DETAIL BY SERVICE'])
    w.writerow(['Service Date', 'CCLI Song Number', 'Title', 'Artist', 'Kind', 'Setlist', 'Copyright'])
    for r in report.get('rows') or []:
        w.writerow([
            str(r.get('service_date') or '')[:10],
            (r.get('ccli_song_number') or '').strip(),
            r.get('title') or '',
            r.get('artist') or '',
            r.get('usage_kind') or '',
            r.get('setlist_title') or '',
            r.get('copyright_line') or '',
        ])
    if report.get('missing_ccli'):
        w.writerow([])
        w.writerow(['MISSING CCLI NUMBER'])
        w.writerow(['Service Date', 'Title', 'Artist'])
        for r in report['missing_ccli']:
            w.writerow([
                str(r.get('service_date') or '')[:10],
                r.get('title') or '',
                r.get('artist') or '',
            ])
    return buf.getvalue()


def get_song_play_counts():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT s.id, s.title, s.artist, COUNT(p.id) AS play_count,
               MAX(p.service_date) AS last_played
        FROM worship_songs s
        LEFT JOIN worship_song_plays p ON p.song_id = s.id
        GROUP BY s.id
        ORDER BY play_count DESC, s.title
    """)
    return cur.fetchall()


def user_accepts_worship_email(user_id: int) -> bool:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "SELECT accepts_emails, accepts_worship_emails FROM users WHERE id = %s",
        (user_id,),
    )
    row = cur.fetchone()
    if not row:
        return False
    return bool(row.get('accepts_emails', 1)) and bool(row.get('accepts_worship_emails', 1))