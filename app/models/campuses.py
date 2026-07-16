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


def set_multi_campus_enabled(
    enabled: bool,
    default_campus_id: int | None = None,
    *,
    campus_all_view_admin_only: bool | None = None,
) -> None:
    db = get_db()
    cur = db.cursor()
    if campus_all_view_admin_only is None:
        cur.execute(
            """
            UPDATE settings SET multi_campus_enabled = %s, default_campus_id = %s
            WHERE id = 1
            """,
            (1 if enabled else 0, default_campus_id),
        )
    else:
        cur.execute(
            """
            UPDATE settings SET multi_campus_enabled = %s, default_campus_id = %s,
                   campus_all_view_admin_only = %s
            WHERE id = 1
            """,
            (1 if enabled else 0, default_campus_id, 1 if campus_all_view_admin_only else 0),
        )
    db.commit()


def campus_all_view_admin_only() -> bool:
    """If true, only Admin/Owner may use the All campuses switcher mode."""
    try:
        cur = _cur()
        cur.execute("SELECT campus_all_view_admin_only FROM settings WHERE id = 1")
        row = cur.fetchone() or {}
        return bool(row.get('campus_all_view_admin_only'))
    except Exception:
        return False


def user_is_org_admin(user_id: int | None = None) -> bool:
    """Owner/Admin can see across isolated branches when needed."""
    if not has_request_context() and user_id is None:
        return False
    role = None
    if has_request_context():
        role = session.get('user_role')
        if user_id is None:
            user_id = session.get('user_id')
    if role in ('Admin', 'Owner'):
        return True
    if not user_id:
        return False
    try:
        cur = _cur()
        cur.execute("SELECT role FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone() or {}
        return (row.get('role') or '') in ('Admin', 'Owner')
    except Exception:
        return False


def user_can_access_campus(user_id: int | None, campus_id: int | None) -> bool:
    """
    Whether this user may view content tagged to campus_id.
    Isolated campuses: only members + org admins.
    Open campuses / NULL: anyone (subject to active campus filter elsewhere).
    """
    if campus_id in (None, 0):
        return True
    if user_is_org_admin(user_id):
        return True
    campus = get_campus(int(campus_id))
    if not campus:
        return True
    if not campus.get('content_isolation'):
        return True
    if not user_id:
        return False
    return int(campus_id) in set(user_campus_ids(user_id))


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
    isolation = 1 if data.get('content_isolation') in (True, 1, '1', 'on', 'yes') else 0
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
        isolation,
    )
    if data.get('is_primary'):
        cur.execute("UPDATE campuses SET is_primary = 0")
    if campus_id:
        cur.execute(
            """
            UPDATE campuses SET
                code=%s, name=%s, short_name=%s, address=%s, city=%s, state=%s,
                postal_code=%s, phone=%s, email=%s, pastor_name=%s, timezone=%s,
                color=%s, is_primary=%s, is_active=%s, sort_order=%s, notes=%s,
                content_isolation=%s
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
             pastor_name, timezone, color, is_primary, is_active, sort_order, notes,
             content_isolation)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
        # Viewing all — still hide isolated campuses the user is not part of
        return content_isolation_sql(column)
    if include_null_as_org:
        return f' AND ({column} = %s OR {column} IS NULL)', [cid]
    return f' AND {column} = %s', [cid]


def content_isolation_sql(
    column: str = 'campus_id',
    *,
    user_id: int | None = None,
    owner_column: str | None = None,
) -> tuple[str, list]:
    """
    Hide content from isolated branches the current user does not belong to.

    Rules (when multi-campus is on):
      • content with campus_id NULL  → org-wide, always OK
      • content on an open campus   → OK in "all campuses" view
      • content on an isolated campus → only campus members + Admin/Owner
      • own content (owner_column)  → always OK for that user

    When multi-campus is off: no filter.
    When a single campus is selected: use campus_scope_sql (caller usually
    applies that separately); this helper still works for "all" view.
    """
    if not multi_campus_enabled():
        return '', []

    uid = user_id
    if uid is None and has_request_context():
        uid = session.get('user_id')

    # Admins/Owners see everything across branches
    if user_is_org_admin(uid):
        return '', []

    # If actively scoped to one campus, isolation is handled by that scope
    # (other campuses are already excluded). Still allow own rows if owner_column set.
    active = get_active_campus_id()
    if active is not None:
        # campus_scope_sql is applied by callers for list views; for single-item
        # checks we still enforce "not another campus's isolated content" via
        # the membership check below when owner is not self.
        parts = [f'({column} IS NULL OR {column} = %s)']
        params: list = [active]
        if owner_column and uid:
            parts.append(f'{owner_column} = %s')
            params.append(uid)
        return ' AND (' + ' OR '.join(parts) + ')', params

    # Viewing all campuses: hide isolated campuses unless member
    member_ids = user_campus_ids(uid) if uid else []
    parts = [
        f'{column} IS NULL',
        # Open campuses (or unknown campus ids treated as open via NOT EXISTS isolated)
        f'''NOT EXISTS (
              SELECT 1 FROM campuses c
              WHERE c.id = {column}
                AND c.content_isolation = 1
                AND c.is_active = 1
            )''',
    ]
    params = []
    if member_ids:
        placeholders = ','.join(['%s'] * len(member_ids))
        parts.append(f'{column} IN ({placeholders})')
        params.extend(member_ids)
    if owner_column and uid:
        parts.append(f'{owner_column} = %s')
        params.append(uid)

    return ' AND (' + ' OR '.join(parts) + ')', params


def content_campus_filter_sql(
    column: str = 'campus_id',
    *,
    user_id: int | None = None,
    owner_column: str | None = None,
    include_null_as_org: bool = True,
) -> tuple[str, list]:
    """
    Combined active-campus scope + isolation for pastoral/creator lists.
    Prefer this over campus_scope_sql alone for sermons, vault, illustrations.
    """
    if not multi_campus_enabled():
        return '', []
    return content_isolation_sql(column, user_id=user_id, owner_column=owner_column)


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


def switchable_campuses_for_user(user_id: int | None = None) -> list[dict]:
    """
    Campuses the user may select in the switcher.
    Open campuses: everyone. Isolated campuses: members + Admin/Owner only.
    """
    all_c = list_campuses(active_only=True)
    if not all_c:
        return []
    uid = user_id
    if uid is None and has_request_context():
        uid = session.get('user_id')
    if user_is_org_admin(uid):
        return all_c
    member = set(user_campus_ids(uid) if uid else [])
    out = []
    for c in all_c:
        if c.get('content_isolation') and int(c['id']) not in member:
            continue
        out.append(c)
    return out


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
            'can_view_all_campuses': True,
            'campus_all_view_admin_only': False,
        }
    uid = session.get('user_id') if has_request_context() else None
    campuses = switchable_campuses_for_user(uid)
    view_all = bool(session.get(SESSION_CAMPUS_ALL))
    admin = user_is_org_admin(uid)
    allow_all = admin or not campus_all_view_admin_only()
    if view_all and not allow_all:
        # Force out of all-view if policy forbids it
        view_all = False
        home = user_home_campus_id(uid) if uid else None
        if home:
            set_session_campus(home, view_all=False)
        elif campuses:
            set_session_campus(int(campuses[0]['id']), view_all=False)
        else:
            set_session_campus(None, view_all=False)
    active_id = None if view_all else get_active_campus_id()
    # If session points at an isolated campus the user cannot access, reset
    if active_id and not user_can_access_campus(uid, active_id):
        home = user_home_campus_id(uid) if uid else None
        if home and user_can_access_campus(uid, home):
            set_session_campus(home, view_all=False)
            active_id = home
        elif campuses:
            set_session_campus(int(campuses[0]['id']), view_all=False)
            active_id = int(campuses[0]['id'])
        else:
            set_session_campus(None, view_all=False)
            active_id = None
    active = get_campus(active_id) if active_id else None
    return {
        'multi_campus_enabled': True,
        'campuses': campuses,
        'active_campus': active,
        'active_campus_id': active_id,
        'viewing_all_campuses': view_all and allow_all,
        'can_view_all_campuses': allow_all,
        'campus_all_view_admin_only': campus_all_view_admin_only(),
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
