import json
import secrets
import pymysql
from datetime import datetime, time, timedelta

from app.models.db import get_db
from app.models.worship.sections import resolve_display_sections

WEEKDAY_NAMES = [
    'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
]


def _norm_time(v):
    if v is None:
        return None
    if isinstance(v, time):
        return v
    if isinstance(v, timedelta):
        s = v.seconds
        return time(s // 3600, (s % 3600) // 60)
    return v


def _token():
    return secrets.token_urlsafe(18)


def list_templates():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM worship_weekly_templates ORDER BY FIELD(weekday, 6, 0, 1, 2, 3, 4, 5)")
    rows = cur.fetchall()
    for r in rows:
        r['weekday_name'] = WEEKDAY_NAMES[r['weekday']] if r['weekday'] is not None else ''
        r['service_time'] = _norm_time(r.get('service_time'))
        r['rehearsal_time'] = _norm_time(r.get('rehearsal_time'))
    return rows


def get_template_for_weekday(weekday: int):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM worship_weekly_templates WHERE weekday = %s LIMIT 1", (weekday,))
    row = cur.fetchone()
    if not row:
        return None
    row['service_time'] = _norm_time(row.get('service_time'))
    row['rehearsal_time'] = _norm_time(row.get('rehearsal_time'))
    row['assignments'] = get_template_assignments(row['id'])
    row['songs'] = get_template_songs(row['id'])
    row['weekday_name'] = WEEKDAY_NAMES[weekday]
    return row


def get_template(template_id: int):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM worship_weekly_templates WHERE id = %s", (template_id,))
    row = cur.fetchone()
    if not row:
        return None
    row['service_time'] = _norm_time(row.get('service_time'))
    row['rehearsal_time'] = _norm_time(row.get('rehearsal_time'))
    row['assignments'] = get_template_assignments(template_id)
    row['songs'] = get_template_songs(template_id)
    row['weekday_name'] = WEEKDAY_NAMES[row['weekday']]
    return row


def get_template_assignments(template_id: int):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT a.*, CONCAT(u.first_name,' ',u.last_name) AS user_full_name,
               u.username, u.email, ug.role_in_group
        FROM worship_weekly_template_assignments a
        JOIN users u ON u.id = a.user_id
        LEFT JOIN user_groups ug ON ug.user_id = u.id
        LEFT JOIN groups g ON g.id = ug.group_id AND (g.system_key = 'worship_team' OR g.name = 'Worship Team Group')
        WHERE a.template_id = %s ORDER BY a.role_name
    """, (template_id,))
    return cur.fetchall()


def save_template_assignments(template_id: int, rows: list):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM worship_weekly_template_assignments WHERE template_id = %s", (template_id,))
    for row in rows:
        role = (row.get('role_name') or '').strip()
        uid = row.get('user_id')
        if role and uid:
            cur.execute("""
                INSERT INTO worship_weekly_template_assignments (template_id, role_name, user_id)
                VALUES (%s, %s, %s)
            """, (template_id, role, uid))
    db.commit()


def get_template_songs(template_id: int):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT ts.*, s.title, s.artist, s.ccli_song_number, s.copyright_line,
               s.publisher, s.copyright_year, s.sections_json, s.play_order_json,
               s.lyrics_raw, s.notes_permanent
        FROM worship_weekly_template_songs ts
        JOIN worship_songs s ON s.id = ts.song_id
        WHERE ts.template_id = %s ORDER BY ts.sort_order, ts.id
    """, (template_id,))
    rows = cur.fetchall()
    for r in rows:
        try:
            r['arrangement'] = json.loads(r.get('arrangement_json') or '[]')
        except json.JSONDecodeError:
            r['arrangement'] = []
        r['display_sections'] = resolve_display_sections(r, r['arrangement'])
    return rows


def ensure_template(weekday: int, user_id: int, title: str = None):
    existing = get_template_for_weekday(weekday)
    if existing:
        return existing['id']
    db = get_db()
    cur = db.cursor()
    label = title or f"{WEEKDAY_NAMES[weekday]} Worship"
    cur.execute("""
        INSERT INTO worship_weekly_templates (weekday, title, public_token, created_by, updated_by)
        VALUES (%s, %s, %s, %s, %s)
    """, (weekday, label, _token(), user_id, user_id))
    db.commit()
    return cur.lastrowid


def update_template(template_id: int, data: dict, user_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        UPDATE worship_weekly_templates
        SET title=%s, service_time=%s, rehearsal_time=%s, rehearsal_location=%s,
            notes=%s, updated_by=%s
        WHERE id=%s
    """, (
        data['title'], data.get('service_time'), data.get('rehearsal_time'),
        data.get('rehearsal_location'), data.get('notes'), user_id, template_id,
    ))
    db.commit()


def add_song_to_template(template_id: int, song_id: int, sort_order: int = 99):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    from app.models.worship.sections import (
        default_play_order_from_sections,
        parse_play_order,
    )

    cur.execute(
        "SELECT sections_json, play_order_json FROM worship_songs WHERE id = %s",
        (song_id,),
    )
    song = cur.fetchone()
    arrangement = []
    if song:
        arrangement = parse_play_order(song.get('play_order_json'))
        if not arrangement:
            try:
                secs = json.loads(song.get('sections_json') or '[]')
            except json.JSONDecodeError:
                secs = []
            arrangement = default_play_order_from_sections(secs)
    cur.execute("""
        INSERT INTO worship_weekly_template_songs (template_id, song_id, sort_order, arrangement_json)
        VALUES (%s, %s, %s, %s)
    """, (template_id, song_id, sort_order, json.dumps(arrangement)))
    db.commit()


def remove_template_song(item_id: int, template_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM worship_weekly_template_songs WHERE id = %s AND template_id = %s", (item_id, template_id))
    db.commit()


def get_by_public_token(token: str):
    if not token:
        return None
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM worship_setlists WHERE public_token = %s LIMIT 1", (token,))
    row = cur.fetchone()
    if row:
        from app.models.worship import setlists as sl
        return sl.get_setlist(row['id'])
    cur.execute("SELECT * FROM worship_weekly_templates WHERE public_token = %s LIMIT 1", (token,))
    trow = cur.fetchone()
    if trow:
        return _template_as_setlist(get_template(trow['id']))
    return None


def ensure_public_token_setlist(setlist_id: int):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT public_token FROM worship_setlists WHERE id = %s", (setlist_id,))
    row = cur.fetchone()
    if row and row.get('public_token'):
        return row['public_token']
    token = _token()
    cur.execute("UPDATE worship_setlists SET public_token = %s WHERE id = %s", (token, setlist_id))
    db.commit()
    return token


def ensure_public_token_template(template_id: int):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT public_token FROM worship_weekly_templates WHERE id = %s", (template_id,))
    row = cur.fetchone()
    if row and row.get('public_token'):
        return row['public_token']
    token = _token()
    cur.execute("UPDATE worship_weekly_templates SET public_token = %s WHERE id = %s", (token, template_id))
    db.commit()
    return token


def _template_as_setlist(template: dict) -> dict:
    if not template:
        return None
    out = dict(template)
    out['source'] = 'template'
    out['template_id'] = template['id']
    out['is_published'] = 1
    for s in out.get('songs') or []:
        s['display_sections'] = resolve_display_sections(s, s.get('arrangement'))
    return out


def get_setlist_for_date(date_str: str):
    """Dated override first, else weekday permanent template (like pastoral planning)."""
    from app.models.worship import setlists as sl
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT id FROM worship_setlists WHERE service_date = %s ORDER BY id DESC LIMIT 1", (date_str,))
    row = cur.fetchone()
    if row:
        plan = sl.get_setlist(row['id'])
        if plan:
            plan['source'] = 'override'
            for s in plan.get('songs') or []:
                s['display_sections'] = resolve_display_sections(s, s.get('arrangement'))
        return plan

    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    template = get_template_for_weekday(date_obj.weekday())
    if template:
        plan = _template_as_setlist(template)
        plan['service_date'] = date_obj
        return plan
    return None


def create_override_from_template(date_str: str, user_id: int):
    plan = get_setlist_for_date(date_str)
    if plan and plan.get('source') == 'override':
        return plan['id']
    if not plan:
        return None

    from app.models.worship import setlists as sl
    data = {
        'title': plan.get('title') or 'Service',
        'service_date': date_str,
        'service_time': plan.get('service_time'),
        'rehearsal_time': plan.get('rehearsal_time'),
        'rehearsal_location': plan.get('rehearsal_location'),
        'notes': plan.get('notes'),
        'is_published': True,
    }
    setlist_id = sl.create_setlist(data, user_id)
    sl.ensure_public_token(setlist_id)
    rows = [{'role_name': a['role_name'], 'user_id': a['user_id']} for a in (plan.get('assignments') or [])]
    if rows:
        sl.save_assignments(setlist_id, rows)
    sl.copy_template_songs_to_setlist(setlist_id, plan.get('songs') or [])
    return setlist_id