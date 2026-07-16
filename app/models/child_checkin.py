# Child Check-In data layer — profiles, rooms, secure codes, attendance.

from __future__ import annotations

import random
import secrets
import string
from datetime import date, datetime
from typing import Any, Optional

import pymysql

from app.models.db import get_db
from app.utils.time_utils import now_church, utc_now


def _cur():
    return get_db().cursor(pymysql.cursors.DictCursor)


def church_today() -> date:
    return now_church().date()


def church_today_str() -> str:
    return church_today().strftime('%Y-%m-%d')


# ── Settings ────────────────────────────────────────────────────────────────

def get_checkin_settings() -> dict:
    cur = _cur()
    try:
        cur.execute(
            """
            SELECT child_checkin_enabled, child_checkin_require_code,
                   child_checkin_notify_default, child_checkin_label_footer,
                   church_name
            FROM settings WHERE id = 1
            """
        )
        row = cur.fetchone() or {}
    except Exception:
        row = {}
    return {
        'enabled': bool(row.get('child_checkin_enabled', 1)),
        'require_code': bool(row.get('child_checkin_require_code', 1)),
        'notify_default': bool(row.get('child_checkin_notify_default', 1)),
        'label_footer': row.get('child_checkin_label_footer') or 'Match code at pickup',
        'church_name': row.get('church_name') or 'Church',
    }


# ── Classrooms ──────────────────────────────────────────────────────────────

def list_classrooms(active_only: bool = True) -> list[dict]:
    cur = _cur()
    sql = "SELECT * FROM child_classrooms"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY sort_order ASC, name ASC"
    cur.execute(sql)
    return list(cur.fetchall() or [])


def get_classroom(room_id: int) -> Optional[dict]:
    cur = _cur()
    cur.execute("SELECT * FROM child_classrooms WHERE id = %s", (room_id,))
    return cur.fetchone()


def save_classroom(data: dict, room_id: int | None = None) -> int:
    db = get_db()
    cur = db.cursor()
    fields = (
        (data.get('name') or 'Room').strip()[:120],
        (data.get('short_code') or '').strip()[:16] or None,
        (data.get('description') or '').strip()[:500] or None,
        (data.get('location') or '').strip()[:120] or None,
        (data.get('age_label') or '').strip()[:80] or None,
        int(data['age_min_months']) if data.get('age_min_months') not in (None, '') else None,
        int(data['age_max_months']) if data.get('age_max_months') not in (None, '') else None,
        int(data['capacity']) if data.get('capacity') not in (None, '') else None,
        (data.get('color') or '#22d3ee')[:24],
        int(data.get('sort_order') or 0),
        1 if data.get('active', True) else 0,
    )
    if room_id:
        cur.execute(
            """
            UPDATE child_classrooms SET
                name=%s, short_code=%s, description=%s, location=%s, age_label=%s,
                age_min_months=%s, age_max_months=%s, capacity=%s, color=%s,
                sort_order=%s, active=%s
            WHERE id=%s
            """,
            (*fields, room_id),
        )
        db.commit()
        return room_id
    cur.execute(
        """
        INSERT INTO child_classrooms
            (name, short_code, description, location, age_label,
             age_min_months, age_max_months, capacity, color, sort_order, active)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        fields,
    )
    db.commit()
    return cur.lastrowid


def room_live_counts(service_date: str | None = None) -> dict[int, int]:
    d = service_date or church_today_str()
    cur = _cur()
    cur.execute(
        """
        SELECT classroom_id, COUNT(*) AS n
        FROM child_checkins
        WHERE service_date = %s AND status = 'checked_in' AND classroom_id IS NOT NULL
        GROUP BY classroom_id
        """,
        (d,),
    )
    return {int(r['classroom_id']): int(r['n']) for r in (cur.fetchall() or []) if r.get('classroom_id')}


# ── Children ────────────────────────────────────────────────────────────────

def list_children(
    *,
    search: str | None = None,
    active_only: bool = True,
    limit: int = 200,
) -> list[dict]:
    cur = _cur()
    sql = """
        SELECT c.*,
               r.name AS default_classroom_name,
               (SELECT COUNT(*) FROM child_guardians g WHERE g.child_id = c.id) AS guardian_count
        FROM child_profiles c
        LEFT JOIN child_classrooms r ON r.id = c.default_classroom_id
        WHERE 1=1
    """
    params: list[Any] = []
    if active_only:
        sql += " AND c.active = 1"
    if search:
        like = f"%{search.strip()}%"
        sql += """
            AND (
                c.first_name LIKE %s OR c.last_name LIKE %s OR c.nickname LIKE %s
                OR c.pin_code = %s
                OR CONCAT(c.first_name,' ',c.last_name) LIKE %s
            )
        """
        pin = search.strip()
        params.extend([like, like, like, pin, like])
    sql += " ORDER BY c.last_name, c.first_name LIMIT %s"
    params.append(int(limit))
    cur.execute(sql, params)
    rows = list(cur.fetchall() or [])
    for r in rows:
        r['display_name'] = child_display_name(r)
        r['age_label'] = age_label(r.get('birthdate'))
    return rows


def get_child(child_id: int) -> Optional[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT c.*, r.name AS default_classroom_name
        FROM child_profiles c
        LEFT JOIN child_classrooms r ON r.id = c.default_classroom_id
        WHERE c.id = %s
        """,
        (child_id,),
    )
    row = cur.fetchone()
    if row:
        row['display_name'] = child_display_name(row)
        row['age_label'] = age_label(row.get('birthdate'))
    return row


def child_display_name(child: dict) -> str:
    first = (child.get('first_name') or '').strip()
    last = (child.get('last_name') or '').strip()
    nick = (child.get('nickname') or '').strip()
    base = f'{first} {last}'.strip() or 'Child'
    return f'{base} (“{nick}”)' if nick else base


def age_label(birthdate) -> str:
    if not birthdate:
        return ''
    if isinstance(birthdate, str):
        try:
            birthdate = datetime.strptime(birthdate[:10], '%Y-%m-%d').date()
        except ValueError:
            return ''
    today = church_today()
    months = (today.year - birthdate.year) * 12 + (today.month - birthdate.month)
    if today.day < birthdate.day:
        months -= 1
    if months < 0:
        return ''
    if months < 24:
        return f'{months} mo'
    years = months // 12
    return f'{years} yr' if years != 1 else '1 yr'


def save_child(data: dict, child_id: int | None = None, created_by: int | None = None) -> int:
    db = get_db()
    cur = db.cursor()
    pin = (data.get('pin_code') or '').strip()
    if pin and not pin.isdigit():
        raise ValueError('Child PIN must be digits only (4–6 recommended).')
    if pin and (len(pin) < 4 or len(pin) > 6):
        raise ValueError('Child PIN should be 4–6 digits.')
    birth = data.get('birthdate') or None
    if birth == '':
        birth = None
    fields = (
        (data.get('first_name') or '').strip()[:100],
        (data.get('last_name') or '').strip()[:100],
        (data.get('nickname') or '').strip()[:80] or None,
        birth,
        (data.get('gender') or '').strip()[:24] or None,
        (data.get('allergies') or '').strip() or None,
        (data.get('medical_notes') or '').strip() or None,
        (data.get('special_needs') or '').strip() or None,
        pin or None,
        int(data['default_classroom_id']) if data.get('default_classroom_id') else None,
        (data.get('notes') or '').strip() or None,
        1 if data.get('active', True) else 0,
    )
    if not fields[0] or not fields[1]:
        raise ValueError('First and last name are required.')
    if child_id:
        cur.execute(
            """
            UPDATE child_profiles SET
                first_name=%s, last_name=%s, nickname=%s, birthdate=%s, gender=%s,
                allergies=%s, medical_notes=%s, special_needs=%s, pin_code=%s,
                default_classroom_id=%s, notes=%s, active=%s
            WHERE id=%s
            """,
            (*fields, child_id),
        )
        db.commit()
        return child_id
    cur.execute(
        """
        INSERT INTO child_profiles
            (first_name, last_name, nickname, birthdate, gender, allergies,
             medical_notes, special_needs, pin_code, default_classroom_id, notes, active, created_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (*fields, created_by),
    )
    db.commit()
    return cur.lastrowid


def delete_child(child_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE child_profiles SET active = 0 WHERE id = %s", (child_id,))
    db.commit()


# ── Guardians ───────────────────────────────────────────────────────────────

def list_guardians(child_id: int) -> list[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT g.*,
               u.first_name AS user_first, u.last_name AS user_last,
               u.email AS user_email, u.username
        FROM child_guardians g
        LEFT JOIN users u ON u.id = g.user_id
        WHERE g.child_id = %s
        ORDER BY g.is_primary DESC, g.id ASC
        """,
        (child_id,),
    )
    rows = list(cur.fetchall() or [])
    for r in rows:
        r['display'] = guardian_display(r)
    return rows


def guardian_display(g: dict) -> str:
    if g.get('user_first') or g.get('user_last'):
        return f"{g.get('user_first') or ''} {g.get('user_last') or ''}".strip()
    return (g.get('full_name') or 'Guardian').strip()


def add_guardian(child_id: int, data: dict) -> int:
    db = get_db()
    cur = db.cursor()
    pin = (data.get('family_pin') or '').strip()
    if pin and (not pin.isdigit() or not (4 <= len(pin) <= 6)):
        raise ValueError('Family PIN must be 4–6 digits.')
    user_id = data.get('user_id') or None
    if user_id:
        user_id = int(user_id)
    cur.execute(
        """
        INSERT INTO child_guardians
            (child_id, user_id, full_name, relationship, phone, email, family_pin,
             is_primary, can_pickup, notify_email, notify_checkin, notify_checkout)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            child_id,
            user_id,
            (data.get('full_name') or '').strip()[:160] or None,
            (data.get('relationship') or 'parent').strip()[:40],
            (data.get('phone') or '').strip()[:40] or None,
            (data.get('email') or '').strip()[:255] or None,
            pin or None,
            1 if data.get('is_primary') else 0,
            1 if data.get('can_pickup', True) else 0,
            1 if data.get('notify_email', True) else 0,
            1 if data.get('notify_checkin', True) else 0,
            1 if data.get('notify_checkout', True) else 0,
        ),
    )
    db.commit()
    return cur.lastrowid


def remove_guardian(guardian_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM child_guardians WHERE id = %s", (guardian_id,))
    db.commit()


def children_for_user(user_id: int) -> list[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT c.*, g.relationship, g.can_pickup, g.family_pin, g.is_primary,
               g.notify_email, g.notify_checkin, g.notify_checkout, g.id AS guardian_link_id,
               r.name AS default_classroom_name
        FROM child_guardians g
        JOIN child_profiles c ON c.id = g.child_id
        LEFT JOIN child_classrooms r ON r.id = c.default_classroom_id
        WHERE g.user_id = %s AND c.active = 1
        ORDER BY c.last_name, c.first_name
        """,
        (user_id,),
    )
    rows = list(cur.fetchall() or [])
    for r in rows:
        r['display_name'] = child_display_name(r)
        r['age_label'] = age_label(r.get('birthdate'))
    return rows


# ── Kiosk family lookup ─────────────────────────────────────────────────────

def kiosk_search(query: str) -> list[dict]:
    """
    Fast family lookup by:
      - last name / first name
      - child PIN
      - family PIN
      - phone last 4+ digits
    Returns unique children with guardian hints.
    """
    q = (query or '').strip()
    if not q:
        return []
    cur = _cur()
    like = f"%{q}%"
    digits = ''.join(ch for ch in q if ch.isdigit())

    # Name / pin / phone search on children + guardians
    phone_like = f'%{digits}%' if len(digits) >= 4 else None
    cur.execute(
        """
        SELECT DISTINCT c.*
        FROM child_profiles c
        LEFT JOIN child_guardians g ON g.child_id = c.id
        WHERE c.active = 1 AND (
            c.last_name LIKE %s OR c.first_name LIKE %s OR c.nickname LIKE %s
            OR CONCAT(c.first_name, ' ', c.last_name) LIKE %s
            OR c.pin_code = %s
            OR g.family_pin = %s
            OR (%s IS NOT NULL AND g.phone LIKE %s)
        )
        ORDER BY c.last_name, c.first_name
        LIMIT 40
        """,
        (like, like, like, like, q, q, phone_like, phone_like or ''),
    )
    rows = list(cur.fetchall() or [])
    today = church_today_str()
    for r in rows:
        r['display_name'] = child_display_name(r)
        r['age_label'] = age_label(r.get('birthdate'))
        r['guardians'] = list_guardians(r['id'])
        r['active_checkin'] = get_active_checkin(r['id'], today)
    return rows


def get_active_checkin(child_id: int, service_date: str | None = None) -> Optional[dict]:
    d = service_date or church_today_str()
    cur = _cur()
    cur.execute(
        """
        SELECT ci.*, r.name AS classroom_name, r.color AS classroom_color
        FROM child_checkins ci
        LEFT JOIN child_classrooms r ON r.id = ci.classroom_id
        WHERE ci.child_id = %s AND ci.service_date = %s AND ci.status = 'checked_in'
        ORDER BY ci.check_in_at DESC
        LIMIT 1
        """,
        (child_id, d),
    )
    return cur.fetchone()


# ── Check-in / out ──────────────────────────────────────────────────────────

def _generate_code(length: int = 4) -> str:
    """Numeric pickup code — easy to read on labels, hard enough for a morning."""
    # Avoid leading zero confusion for some scanners; allow full range otherwise
    return ''.join(secrets.choice(string.digits) for _ in range(length))


def _unique_codes(service_date: str) -> tuple[str, str]:
    cur = _cur()
    for _ in range(30):
        pickup = _generate_code(4)
        security = _generate_code(4)
        # Keep them different for dual-code systems
        if pickup == security:
            security = _generate_code(4)
        cur.execute(
            """
            SELECT id FROM child_checkins
            WHERE service_date = %s AND (pickup_code = %s OR security_code = %s)
            LIMIT 1
            """,
            (service_date, pickup, security),
        )
        if not cur.fetchone():
            return pickup, security
    # Fallback longer
    return secrets.token_hex(3).upper(), secrets.token_hex(3).upper()


def check_in_child(
    *,
    child_id: int,
    classroom_id: int | None,
    guardian_user_id: int | None = None,
    guardian_name: str | None = None,
    checked_in_by: int | None = None,
    event_label: str | None = None,
    notes: str | None = None,
    service_date: str | None = None,
) -> dict:
    """Check a child in. Returns check-in row with codes. Idempotent if already in."""
    d = service_date or church_today_str()
    existing = get_active_checkin(child_id, d)
    if existing:
        return existing

    child = get_child(child_id)
    if not child or not child.get('active'):
        raise ValueError('Child not found or inactive.')

    room_id = classroom_id or child.get('default_classroom_id')
    if room_id:
        counts = room_live_counts(d)
        room = get_classroom(int(room_id))
        if room and room.get('capacity'):
            if counts.get(int(room_id), 0) >= int(room['capacity']):
                raise ValueError(f"{room['name']} is at capacity ({room['capacity']}). Choose another room.")

    pickup, security = _unique_codes(d)
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO child_checkins
            (child_id, classroom_id, service_date, event_label, status,
             pickup_code, security_code, check_in_at, guardian_user_id,
             guardian_name, checked_in_by, notes)
        VALUES (%s,%s,%s,%s,'checked_in',%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            child_id,
            int(room_id) if room_id else None,
            d,
            (event_label or '').strip()[:120] or None,
            pickup,
            security,
            utc_now(),
            guardian_user_id,
            (guardian_name or '').strip()[:160] or None,
            checked_in_by,
            (notes or '').strip()[:500] or None,
        ),
    )
    db.commit()
    cid = cur.lastrowid
    return get_checkin(cid)


def get_checkin(checkin_id: int) -> Optional[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT ci.*,
               c.first_name, c.last_name, c.nickname, c.allergies, c.medical_notes,
               c.special_needs, c.birthdate, c.photo_path,
               r.name AS classroom_name, r.short_code AS classroom_code,
               r.color AS classroom_color, r.location AS classroom_location
        FROM child_checkins ci
        JOIN child_profiles c ON c.id = ci.child_id
        LEFT JOIN child_classrooms r ON r.id = ci.classroom_id
        WHERE ci.id = %s
        """,
        (checkin_id,),
    )
    row = cur.fetchone()
    if row:
        row['display_name'] = child_display_name(row)
        row['age_label'] = age_label(row.get('birthdate'))
    return row


def mark_label_printed(checkin_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE child_checkins SET label_printed = 1 WHERE id = %s", (checkin_id,))
    db.commit()


def check_out_by_code(
    code: str,
    *,
    service_date: str | None = None,
    checked_out_by: int | None = None,
    method: str = 'code',
) -> dict:
    """Secure pickup: match pickup_code or security_code for today."""
    code = (code or '').strip()
    if not code:
        raise ValueError('Enter the pickup code from the label.')
    d = service_date or church_today_str()
    cur = _cur()
    cur.execute(
        """
        SELECT id FROM child_checkins
        WHERE service_date = %s AND status = 'checked_in'
          AND (pickup_code = %s OR security_code = %s)
        ORDER BY check_in_at DESC
        LIMIT 1
        """,
        (d, code, code),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError('No checked-in child matches that code for today.')
    return check_out(int(row['id']), checked_out_by=checked_out_by, method=method)


def check_out(
    checkin_id: int,
    *,
    checked_out_by: int | None = None,
    method: str = 'staff',
) -> dict:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        UPDATE child_checkins
        SET status = 'checked_out',
            check_out_at = %s,
            checked_out_by = %s,
            checkout_method = %s
        WHERE id = %s AND status = 'checked_in'
        """,
        (utc_now(), checked_out_by, method[:40], checkin_id),
    )
    if cur.rowcount == 0:
        db.rollback()
        raise ValueError('Check-in not found or already checked out.')
    db.commit()
    return get_checkin(checkin_id)


def list_checked_in(
    *,
    service_date: str | None = None,
    classroom_id: int | None = None,
) -> list[dict]:
    d = service_date or church_today_str()
    cur = _cur()
    sql = """
        SELECT ci.*,
               c.first_name, c.last_name, c.nickname, c.allergies, c.medical_notes,
               c.special_needs, c.birthdate,
               r.name AS classroom_name, r.color AS classroom_color, r.location AS classroom_location
        FROM child_checkins ci
        JOIN child_profiles c ON c.id = ci.child_id
        LEFT JOIN child_classrooms r ON r.id = ci.classroom_id
        WHERE ci.service_date = %s AND ci.status = 'checked_in'
    """
    params: list[Any] = [d]
    if classroom_id:
        sql += " AND ci.classroom_id = %s"
        params.append(int(classroom_id))
    sql += " ORDER BY r.sort_order, c.last_name, c.first_name"
    cur.execute(sql, params)
    rows = list(cur.fetchall() or [])
    for r in rows:
        r['display_name'] = child_display_name(r)
        r['age_label'] = age_label(r.get('birthdate'))
    return rows


def day_report(service_date: str | None = None) -> dict:
    d = service_date or church_today_str()
    cur = _cur()
    cur.execute(
        """
        SELECT status, COUNT(*) AS n
        FROM child_checkins
        WHERE service_date = %s
        GROUP BY status
        """,
        (d,),
    )
    by_status = {r['status']: int(r['n']) for r in (cur.fetchall() or [])}
    cur.execute(
        """
        SELECT COALESCE(r.name, 'Unassigned') AS room, COUNT(*) AS n
        FROM child_checkins ci
        LEFT JOIN child_classrooms r ON r.id = ci.classroom_id
        WHERE ci.service_date = %s AND ci.status = 'checked_in'
        GROUP BY room
        ORDER BY n DESC
        """,
        (d,),
    )
    by_room = list(cur.fetchall() or [])
    cur.execute(
        """
        SELECT ci.*, c.first_name, c.last_name, c.nickname,
               r.name AS classroom_name
        FROM child_checkins ci
        JOIN child_profiles c ON c.id = ci.child_id
        LEFT JOIN child_classrooms r ON r.id = ci.classroom_id
        WHERE ci.service_date = %s
        ORDER BY ci.check_in_at DESC
        LIMIT 300
        """,
        (d,),
    )
    rows = list(cur.fetchall() or [])
    for r in rows:
        r['display_name'] = child_display_name(r)
    return {
        'date': d,
        'checked_in': by_status.get('checked_in', 0),
        'checked_out': by_status.get('checked_out', 0),
        'total': sum(by_status.values()),
        'by_room': by_room,
        'rows': rows,
    }


def dashboard_stats() -> dict:
    d = church_today_str()
    cur = _cur()
    cur.execute("SELECT COUNT(*) AS n FROM child_profiles WHERE active = 1")
    kids = int((cur.fetchone() or {}).get('n') or 0)
    cur.execute("SELECT COUNT(*) AS n FROM child_classrooms WHERE active = 1")
    rooms = int((cur.fetchone() or {}).get('n') or 0)
    report = day_report(d)
    return {
        'active_children': kids,
        'classrooms': rooms,
        'today_in': report['checked_in'],
        'today_out': report['checked_out'],
        'today_total': report['total'],
        'by_room': report['by_room'],
        'date': d,
    }


# ── Notifications ───────────────────────────────────────────────────────────

def notify_guardians(checkin: dict, event: str = 'checkin') -> list[str]:
    """
    Email guardians who opted in. event: checkin | checkout
    Returns list of addresses attempted (best-effort).
    """
    settings = get_checkin_settings()
    if not settings.get('notify_default') and event == 'checkin':
        # still respect per-guardian flags
        pass
    child_id = checkin.get('child_id')
    guardians = list_guardians(child_id)
    sent = []
    name = child_display_name(checkin)
    room = checkin.get('classroom_name') or 'their classroom'
    code = checkin.get('pickup_code') or checkin.get('security_code') or ''
    church = settings.get('church_name') or 'Church'

    if event == 'checkin':
        subject = f"{name} checked in — {church}"
        body = (
            f"{name} has been checked in to {room}.\n\n"
            f"Pickup code: {code}\n"
            f"Keep this code to pick up your child.\n\n"
            f"Service date: {checkin.get('service_date')}\n"
            f"— {church} Child Check-In"
        )
        flag = 'notify_checkin'
    else:
        subject = f"{name} checked out — {church}"
        body = (
            f"{name} has been securely checked out from {room}.\n\n"
            f"If you did not pick them up, contact the church office immediately.\n\n"
            f"— {church} Child Check-In"
        )
        flag = 'notify_checkout'

    try:
        from app.utils.emailer import send_email
    except Exception:
        return sent

    for g in guardians:
        if not g.get(flag) or not g.get('notify_email'):
            continue
        email = (g.get('email') or g.get('user_email') or '').strip()
        if not email:
            continue
        try:
            send_email(email, subject, body)
            sent.append(email)
        except Exception:
            continue
    return sent
