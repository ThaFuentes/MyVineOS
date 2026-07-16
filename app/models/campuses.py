# Multi-campus: registry, membership, session scope helpers.

from __future__ import annotations

from typing import Any, Optional

import pymysql
from flask import g, has_request_context, session

from app.models.db import get_db

# Session keys
SESSION_CAMPUS_ID = 'campus_id'          # int or None
SESSION_CAMPUS_ALL = 'campus_view_all'    # bool — org-wide view


def _cur():
    return get_db().cursor(pymysql.cursors.DictCursor)


def multi_campus_enabled() -> bool:
    try:
        cur = _cur()
        cur.execute("SELECT multi_campus_enabled FROM settings WHERE id = 1")
        row = cur.fetchone() or {}
        return bool(row.get('multi_campus_enabled'))
    except Exception:
        return False


def set_multi_campus_enabled(enabled: bool, default_campus_id: int | None = None) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        UPDATE settings SET multi_campus_enabled = %s, default_campus_id = %s
        WHERE id = 1
        """,
        (1 if enabled else 0, default_campus_id),
    )
    db.commit()


def list_campuses(active_only: bool = True) -> list[dict]:
    cur = _cur()
    sql = "SELECT * FROM campuses"
    if active_only:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY is_primary DESC, sort_order ASC, name ASC"
    try:
        cur.execute(sql)
        return list(cur.fetchall() or [])
    except Exception:
        return []


def get_campus(campus_id: int) -> Optional[dict]:
    cur = _cur()
    cur.execute("SELECT * FROM campuses WHERE id = %s", (campus_id,))
    return cur.fetchone()


def get_primary_campus() -> Optional[dict]:
    cur = _cur()
    cur.execute("SELECT * FROM campuses WHERE is_primary = 1 AND is_active = 1 LIMIT 1")
    row = cur.fetchone()
    if row:
        return row
    cur.execute("SELECT * FROM campuses WHERE is_active = 1 ORDER BY sort_order, id LIMIT 1")
    return cur.fetchone()


def save_campus(data: dict, campus_id: int | None = None) -> int:
    db = get_db()
    cur = db.cursor()
    code = (data.get('code') or '').strip().upper()[:32]
    name = (data.get('name') or '').strip()[:160]
    if not code or not name:
        raise ValueError('Campus code and name are required.')
    fields = (
        code,
        name,
        (data.get('short_name') or '').strip()[:80] or None,
        (data.get('address') or '').strip() or None,
        (data.get('city') or '').strip()[:120] or None,
        (data.get('state') or '').strip()[:80] or None,
        (data.get('postal_code') or '').strip()[:24] or None,
        (data.get('phone') or '').strip()[:40] or None,
        (data.get('email') or '').strip()[:255] or None,
        (data.get('pastor_name') or '').strip()[:160] or None,
        (data.get('timezone') or '').strip()[:64] or None,
        (data.get('color') or '#22d3ee')[:24],
        1 if data.get('is_primary') else 0,
        1 if data.get('is_active', True) else 0,
        int(data.get('sort_order') or 0),
        (data.get('notes') or '').strip() or None,
    )
    if data.get('is_primary'):
        cur.execute("UPDATE campuses SET is_primary = 0")
    if campus_id:
        cur.execute(
            """
            UPDATE campuses SET
                code=%s, name=%s, short_name=%s, address=%s, city=%s, state=%s,
                postal_code=%s, phone=%s, email=%s, pastor_name=%s, timezone=%s,
                color=%s, is_primary=%s, is_active=%s, sort_order=%s, notes=%s
            WHERE id=%s
            """,
            (*fields, campus_id),
        )
        db.commit()
        return campus_id
    cur.execute(
        """
        INSERT INTO campuses
            (code, name, short_name, address, city, state, postal_code, phone, email,
             pastor_name, timezone, color, is_primary, is_active, sort_order, notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        fields,
    )
    db.commit()
    return cur.lastrowid


def delete_campus(campus_id: int) -> None:
    """Soft-deactivate; keep history on records that reference it."""
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE campuses SET is_active = 0, is_primary = 0 WHERE id = %s", (campus_id,))
    db.commit()


def list_campus_members(campus_id: int) -> list[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT cm.*, u.first_name, u.last_name, u.email, u.username, u.role
        FROM campus_members cm
        JOIN users u ON u.id = cm.user_id
        WHERE cm.campus_id = %s
        ORDER BY cm.is_home DESC, u.last_name, u.first_name
        """,
        (campus_id,),
    )
    return list(cur.fetchall() or [])


def set_user_campuses(user_id: int, campus_ids: list[int], home_campus_id: int | None = None) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM campus_members WHERE user_id = %s", (user_id,))
    for cid in campus_ids:
        cur.execute(
            """
            INSERT INTO campus_members (campus_id, user_id, is_home)
            VALUES (%s,%s,%s)
            """,
            (int(cid), user_id, 1 if home_campus_id and int(cid) == int(home_campus_id) else 0),
        )
    if home_campus_id:
        cur.execute(
            "UPDATE users SET primary_campus_id = %s WHERE id = %s",
            (int(home_campus_id), user_id),
        )
    elif campus_ids:
        cur.execute(
            "UPDATE users SET primary_campus_id = %s WHERE id = %s",
            (int(campus_ids[0]), user_id),
        )
    db.commit()


def add_user_to_campus(user_id: int, campus_id: int, is_home: bool = False) -> None:
    db = get_db()
    cur = db.cursor()
    if is_home:
        cur.execute("UPDATE campus_members SET is_home = 0 WHERE user_id = %s", (user_id,))
        cur.execute("UPDATE users SET primary_campus_id = %s WHERE id = %s", (campus_id, user_id))
    cur.execute(
        """
        INSERT INTO campus_members (campus_id, user_id, is_home)
        VALUES (%s,%s,%s)
        ON DUPLICATE KEY UPDATE is_home = VALUES(is_home)
        """,
        (campus_id, user_id, 1 if is_home else 0),
    )
    db.commit()


def remove_user_from_campus(user_id: int, campus_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "DELETE FROM campus_members WHERE user_id = %s AND campus_id = %s",
        (user_id, campus_id),
    )
    db.commit()


def user_campus_ids(user_id: int) -> list[int]:
    cur = _cur()
    cur.execute("SELECT campus_id FROM campus_members WHERE user_id = %s", (user_id,))
    return [int(r['campus_id']) for r in (cur.fetchall() or [])]


def user_home_campus_id(user_id: int) -> Optional[int]:
    cur = _cur()
    cur.execute("SELECT primary_campus_id FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    if row and row.get('primary_campus_id'):
        return int(row['primary_campus_id'])
    cur.execute(
        "SELECT campus_id FROM campus_members WHERE user_id = %s AND is_home = 1 LIMIT 1",
        (user_id,),
    )
    row = cur.fetchone()
    return int(row['campus_id']) if row else None


# ── Session / request scope ─────────────────────────────────────────────────

def set_session_campus(campus_id: int | None, view_all: bool = False) -> None:
    """campus_id=None + view_all=True → all campuses; campus_id=int → single."""
    if view_all or campus_id in (None, 0, '0', 'all'):
        session[SESSION_CAMPUS_ALL] = True
        session.pop(SESSION_CAMPUS_ID, None)
    else:
        session[SESSION_CAMPUS_ALL] = False
        session[SESSION_CAMPUS_ID] = int(campus_id)


def get_active_campus_id() -> Optional[int]:
    """
    Current campus filter for queries.
    None means show all campuses (org-wide) OR multi-campus disabled.
    """
    if not has_request_context():
        return None
    if not multi_campus_enabled():
        return None
    if session.get(SESSION_CAMPUS_ALL):
        return None
    cid = session.get(SESSION_CAMPUS_ID)
    if cid:
        return int(cid)
    # Default: user's home campus, else primary campus (not "all")
    uid = session.get('user_id')
    if uid:
        home = user_home_campus_id(uid)
        if home:
            return home
    primary = get_primary_campus()
    return int(primary['id']) if primary else None


def get_active_campus() -> Optional[dict]:
    cid = get_active_campus_id()
    if not cid:
        return None
    return get_campus(cid)


def is_viewing_all_campuses() -> bool:
    if not multi_campus_enabled():
        return True
    if session.get(SESSION_CAMPUS_ALL):
        return True
    return get_active_campus_id() is None and bool(session.get(SESSION_CAMPUS_ALL))


def campus_scope_sql(column: str = 'campus_id', *, include_null_as_org: bool = True) -> tuple[str, list]:
    """
    Return (sql_fragment, params) for filtering by active campus.
    When viewing all campuses or multi-campus off: empty fragment.
    When a campus is selected: (col = %s OR col IS NULL) if include_null_as_org else (col = %s).
    """
    if not multi_campus_enabled():
        return '', []
    cid = get_active_campus_id()
    if cid is None:
        return '', []
    if include_null_as_org:
        return f' AND ({column} = %s OR {column} IS NULL)', [cid]
    return f' AND {column} = %s', [cid]


def resolve_campus_id_for_write(explicit: Any = None) -> Optional[int]:
    """
    Campus to stamp on new records.
    Prefer form value, else active campus, else primary, else None.
    """
    if explicit not in (None, '', 0, '0'):
        try:
            return int(explicit)
        except (TypeError, ValueError):
            pass
    if not multi_campus_enabled():
        return None
    cid = get_active_campus_id()
    if cid:
        return cid
    primary = get_primary_campus()
    return int(primary['id']) if primary else None


def inject_campus_context() -> dict:
    """For Flask context processor / templates."""
    try:
        enabled = multi_campus_enabled()
    except Exception:
        enabled = False
    if not enabled:
        return {
            'multi_campus_enabled': False,
            'campuses': [],
            'active_campus': None,
            'active_campus_id': None,
            'viewing_all_campuses': True,
        }
    campuses = list_campuses(active_only=True)
    view_all = bool(session.get(SESSION_CAMPUS_ALL))
    active_id = None if view_all else get_active_campus_id()
    active = get_campus(active_id) if active_id else None
    return {
        'multi_campus_enabled': True,
        'campuses': campuses,
        'active_campus': active,
        'active_campus_id': active_id,
        'viewing_all_campuses': view_all,
    }


def ensure_session_campus_default() -> None:
    """On login / first request: set a sensible campus if multi-campus and unset."""
    if not multi_campus_enabled():
        return
    if SESSION_CAMPUS_ID in session or session.get(SESSION_CAMPUS_ALL):
        return
    uid = session.get('user_id')
    if not uid:
        return
    home = user_home_campus_id(uid)
    if home:
        set_session_campus(home, view_all=False)
        return
    primary = get_primary_campus()
    if primary:
        set_session_campus(int(primary['id']), view_all=False)
