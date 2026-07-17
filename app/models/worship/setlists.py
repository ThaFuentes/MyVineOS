import json
import secrets
import pymysql
from datetime import datetime, time, timedelta, date
from app.models.db import get_db
from app.models.worship.sections import resolve_display_sections


def _norm_time(v):
    if v is None:
        return None
    if isinstance(v, time):
        return v
    if isinstance(v, timedelta):
        s = v.seconds
        return time(s // 3600, (s % 3600) // 60)
    return v


def list_setlists(limit=50):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT * FROM worship_setlists ORDER BY service_date DESC, id DESC LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    for r in rows:
        r['service_time'] = _norm_time(r.get('service_time'))
        r['rehearsal_time'] = _norm_time(r.get('rehearsal_time'))
    return rows


def get_setlist(setlist_id: int):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM worship_setlists WHERE id = %s", (setlist_id,))
    row = cur.fetchone()
    if not row:
        return None
    row['service_time'] = _norm_time(row.get('service_time'))
    row['rehearsal_time'] = _norm_time(row.get('rehearsal_time'))
    row['assignments'] = get_assignments(setlist_id)
    row['songs'] = get_setlist_songs(setlist_id)
    return row


def get_assignments(setlist_id: int):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT a.*, CONCAT(u.first_name,' ',u.last_name) AS user_full_name, u.username, u.email
        FROM worship_setlist_assignments a
        JOIN users u ON u.id = a.user_id
        WHERE a.setlist_id = %s ORDER BY a.role_name
    """, (setlist_id,))
    return cur.fetchall()


def save_assignments(setlist_id: int, rows: list):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM worship_setlist_assignments WHERE setlist_id = %s", (setlist_id,))
    for row in rows:
        role = (row.get('role_name') or '').strip()
        uid = row.get('user_id')
        if role and uid:
            cur.execute("""
                INSERT INTO worship_setlist_assignments (setlist_id, role_name, user_id)
                VALUES (%s, %s, %s)
            """, (setlist_id, role, uid))
    db.commit()


def get_setlist_songs(setlist_id: int):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT ss.*, s.title, s.artist, s.ccli_song_number, s.copyright_line, s.publisher,
               s.copyright_year, s.sections_json, s.play_order_json, s.lyrics_raw, s.notes_permanent
        FROM worship_setlist_songs ss
        JOIN worship_songs s ON s.id = ss.song_id
        WHERE ss.setlist_id = %s ORDER BY ss.sort_order, ss.id
    """, (setlist_id,))
    rows = cur.fetchall()
    for r in rows:
        try:
            r['sections'] = json.loads(r.get('sections_json') or '[]')
        except json.JSONDecodeError:
            r['sections'] = []
        try:
            r['arrangement'] = json.loads(r.get('arrangement_json') or '[]')
        except json.JSONDecodeError:
            r['arrangement'] = []
        r['display_sections'] = resolve_display_sections(r, r['arrangement'])
    return rows


def ensure_public_token(setlist_id: int):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT public_token FROM worship_setlists WHERE id = %s", (setlist_id,))
    row = cur.fetchone()
    if row and row.get('public_token'):
        return row['public_token']
    token = secrets.token_urlsafe(18)
    cur.execute("UPDATE worship_setlists SET public_token = %s WHERE id = %s", (token, setlist_id))
    db.commit()
    return token


def copy_template_songs_to_setlist(setlist_id: int, template_songs: list):
    db = get_db()
    cur = db.cursor()
    for s in template_songs or []:
        cur.execute("""
            INSERT INTO worship_setlist_songs (setlist_id, song_id, sort_order, arrangement_json, song_key)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            setlist_id, s['song_id'], s.get('sort_order', 0),
            s.get('arrangement_json') or '[]', s.get('song_key'),
        ))
    db.commit()


def create_setlist(data: dict, user_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO worship_setlists (service_date, title, service_time, rehearsal_time,
            rehearsal_location, notes, is_published, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        data.get('service_date') or None, data['title'],
        data.get('service_time'), data.get('rehearsal_time'),
        data.get('rehearsal_location'), data.get('notes'),
        1 if data.get('is_published') else 0, user_id, user_id,
    ))
    db.commit()
    return cur.lastrowid


def update_setlist(setlist_id: int, data: dict, user_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        UPDATE worship_setlists SET service_date=%s, title=%s, service_time=%s, rehearsal_time=%s,
            rehearsal_location=%s, notes=%s, is_published=%s, updated_by=%s
        WHERE id=%s
    """, (
        data.get('service_date') or None, data['title'],
        data.get('service_time'), data.get('rehearsal_time'),
        data.get('rehearsal_location'), data.get('notes'),
        1 if data.get('is_published') else 0, user_id, setlist_id,
    ))
    db.commit()


def add_song_to_setlist(setlist_id: int, song_id: int, sort_order: int = 99):
    from app.models.worship.sections import (
        default_play_order_from_sections,
        parse_play_order,
    )

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
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
        INSERT INTO worship_setlist_songs (setlist_id, song_id, sort_order, arrangement_json)
        VALUES (%s, %s, %s, %s)
    """, (setlist_id, song_id, sort_order, json.dumps(arrangement)))
    db.commit()
    return cur.lastrowid


def remove_setlist_song(item_id: int, setlist_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM worship_setlist_songs WHERE id = %s AND setlist_id = %s", (item_id, setlist_id))
    db.commit()


def get_default_assignments():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT d.*, CONCAT(u.first_name,' ',u.last_name) AS user_full_name
        FROM worship_default_assignments d JOIN users u ON u.id = d.user_id
    """)
    return cur.fetchall()


def save_default_assignments(rows: list):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM worship_default_assignments")
    for row in rows:
        role = (row.get('role_name') or '').strip()
        uid = row.get('user_id')
        if role and uid:
            cur.execute("INSERT INTO worship_default_assignments (role_name, user_id) VALUES (%s, %s)", (role, uid))
    db.commit()


def apply_defaults_to_setlist(setlist_id: int):
    for d in get_default_assignments():
        db = get_db()
        cur = db.cursor()
        try:
            cur.execute("""
                INSERT INTO worship_setlist_assignments (setlist_id, role_name, user_id)
                VALUES (%s, %s, %s)
            """, (setlist_id, d['role_name'], d['user_id']))
            db.commit()
        except Exception:
            db.rollback()


def delete_setlist(setlist_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM worship_setlist_songs WHERE setlist_id = %s", (setlist_id,))
    cur.execute("DELETE FROM worship_setlist_assignments WHERE setlist_id = %s", (setlist_id,))
    cur.execute("DELETE FROM worship_setlists WHERE id = %s", (setlist_id,))
    db.commit()
    return cur.rowcount > 0


def plan_is_active_schedule(plan) -> bool:
    """
    True only when worship leadership has set something up:
    at least one song and/or one role assignment.
    Empty weekly defaults must not invent a "next service" every weekday.
    """
    if not plan:
        return False
    songs = plan.get('songs') or []
    assignments = plan.get('assignments') or []
    return bool(songs) or bool(assignments)


def get_upcoming_setlist():
    """
    Next service that is actually scheduled (songs or people assigned).
    Does not advertise blank weekly defaults for every matching weekday.
    """
    from app.models.worship import templates as tmpl
    today = date.today()
    for offset in range(0, 60):
        check = today + timedelta(days=offset)
        plan = tmpl.get_setlist_for_date(check.strftime('%Y-%m-%d'))
        if plan_is_active_schedule(plan):
            return plan
    return None