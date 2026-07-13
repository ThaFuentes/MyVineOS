# Queries for PoweredByTop tables + account locks + security grants.

from __future__ import annotations

from datetime import datetime

import pymysql

from app.models.db import get_db
from poweredbytop.models.connect_db import get_security_db
from .utils import ensure_security_grants_table


def _sec():
    return get_security_db()


def summary_stats() -> dict:
    out = {
        'events_24h': 0,
        'events_total': 0,
        'active_temp_bans': 0,
        'perm_bans': 0,
        'low_reputation': 0,
        'account_login_locks': 0,
        'attack_types': 0,
    }
    db = _sec()
    if db is not None:
        cur = db.cursor(pymysql.cursors.DictCursor)
        try:
            cur.execute(
                "SELECT COUNT(*) AS c FROM pbt_security_events WHERE timestamp >= NOW() - INTERVAL 1 DAY"
            )
            out['events_24h'] = int((cur.fetchone() or {}).get('c') or 0)
            cur.execute("SELECT COUNT(*) AS c FROM pbt_security_events")
            out['events_total'] = int((cur.fetchone() or {}).get('c') or 0)
            cur.execute(
                """
                SELECT COUNT(*) AS c FROM pbt_reputation
                WHERE grade = 'temp_ban'
                   OR (ban_until IS NOT NULL AND ban_until > NOW())
                """
            )
            out['active_temp_bans'] = int((cur.fetchone() or {}).get('c') or 0)
            cur.execute("SELECT COUNT(*) AS c FROM pbt_reputation WHERE grade = 'perm_ban'")
            out['perm_bans'] = int((cur.fetchone() or {}).get('c') or 0)
            cur.execute(
                "SELECT COUNT(*) AS c FROM pbt_reputation WHERE score < 50 AND grade NOT IN ('perm_ban')"
            )
            out['low_reputation'] = int((cur.fetchone() or {}).get('c') or 0)
            cur.execute("SELECT COUNT(*) AS c FROM pbt_attack_stats")
            out['attack_types'] = int((cur.fetchone() or {}).get('c') or 0)
        except Exception as exc:
            print(f'security summary pbt: {exc}')

    try:
        adb = get_db()
        acur = adb.cursor(pymysql.cursors.DictCursor)
        acur.execute(
            """
            SELECT COUNT(*) AS c FROM users
            WHERE login_locked_until IS NOT NULL AND login_locked_until > NOW()
            """
        )
        out['account_login_locks'] = int((acur.fetchone() or {}).get('c') or 0)
    except Exception as exc:
        print(f'security summary locks: {exc}')
    return out


def list_security_events(
    *,
    search: str = '',
    event_type: str = '',
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict], int]:
    db = _sec()
    if db is None:
        return [], 0
    cur = db.cursor(pymysql.cursors.DictCursor)
    where = []
    params: list = []
    if search:
        where.append("(ip LIKE %s OR notes LIKE %s OR event_type LIKE %s)")
        like = f'%{search}%'
        params.extend([like, like, like])
    if event_type:
        where.append("event_type = %s")
        params.append(event_type)
    clause = ('WHERE ' + ' AND '.join(where)) if where else ''
    try:
        cur.execute(f"SELECT COUNT(*) AS c FROM pbt_security_events {clause}", params)
        total = int((cur.fetchone() or {}).get('c') or 0)
        cur.execute(
            f"""
            SELECT id, timestamp, event_type, ip, reputation_score, behavior_grade, notes
            FROM pbt_security_events
            {clause}
            ORDER BY timestamp DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        return list(cur.fetchall() or []), total
    except Exception as exc:
        print(f'list_security_events: {exc}')
        return [], 0


def list_event_types() -> list[str]:
    db = _sec()
    if db is None:
        return []
    cur = db.cursor(pymysql.cursors.DictCursor)
    try:
        cur.execute(
            "SELECT DISTINCT event_type FROM pbt_security_events ORDER BY event_type ASC LIMIT 100"
        )
        return [r['event_type'] for r in (cur.fetchall() or []) if r.get('event_type')]
    except Exception:
        return []


def list_attack_stats() -> list[dict]:
    db = _sec()
    if db is None:
        return []
    cur = db.cursor(pymysql.cursors.DictCursor)
    try:
        cur.execute(
            """
            SELECT attack_type, total_attempts, blocked_count, last_attack_ip,
                   last_attack_time, severity_level, notes
            FROM pbt_attack_stats
            ORDER BY last_attack_time DESC, total_attempts DESC
            """
        )
        return list(cur.fetchall() or [])
    except Exception as exc:
        print(f'list_attack_stats: {exc}')
        return []


def list_reputation_rows(
    *,
    filter_mode: str = 'bans',
    search: str = '',
    limit: int = 150,
) -> list[dict]:
    """
    filter_mode:
      bans — active temp/perm bans
      low — score under 50
      all — recent activity
    """
    db = _sec()
    if db is None:
        return []
    cur = db.cursor(pymysql.cursors.DictCursor)
    where = []
    params: list = []
    if filter_mode == 'bans':
        where.append(
            "(grade IN ('temp_ban', 'perm_ban') OR (ban_until IS NOT NULL AND ban_until > NOW()))"
        )
    elif filter_mode == 'low':
        where.append("score < 50")
    if search:
        where.append("(ip LIKE %s OR ban_reason LIKE %s OR grade LIKE %s)")
        like = f'%{search}%'
        params.extend([like, like, like])
    clause = ('WHERE ' + ' AND '.join(where)) if where else ''
    order = "ORDER BY ban_until DESC, last_seen DESC, score ASC"
    try:
        cur.execute(
            f"""
            SELECT ip, score, grade, positive_requests, negative_points,
                   ban_until, ban_reason, ban_count, first_seen, last_seen, last_bad_behavior
            FROM pbt_reputation
            {clause}
            {order}
            LIMIT %s
            """,
            params + [limit],
        )
        rows = list(cur.fetchall() or [])
        now = datetime.now()
        for r in rows:
            until = r.get('ban_until')
            r['is_active_ban'] = (
                r.get('grade') in ('temp_ban', 'perm_ban')
                or (until is not None and until > now)
            )
        return rows
    except Exception as exc:
        print(f'list_reputation_rows: {exc}')
        return []


def list_account_login_locks() -> list[dict]:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    try:
        cur.execute(
            """
            SELECT u.id, u.username, u.email, u.first_name, u.last_name, u.role,
                   u.login_locked_until, u.login_locked_by,
                   a.username AS locked_by_name
            FROM users u
            LEFT JOIN users a ON a.id = u.login_locked_by
            WHERE u.login_locked_until IS NOT NULL AND u.login_locked_until > NOW()
            ORDER BY u.login_locked_until ASC
            """
        )
        return list(cur.fetchall() or [])
    except Exception as exc:
        print(f'list_account_login_locks: {exc}')
        return []


def list_security_grants() -> list[dict]:
    ensure_security_grants_table()
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        """
        SELECT g.id, g.user_id, g.notes, g.created_at, g.granted_by,
               u.username, u.email, u.role, u.first_name, u.last_name,
               gb.username AS granted_by_name
        FROM security_area_grants g
        JOIN users u ON u.id = g.user_id
        LEFT JOIN users gb ON gb.id = g.granted_by
        ORDER BY g.created_at DESC
        """
    )
    return list(cur.fetchall() or [])


def grant_security_access(user_id: int, granted_by: int, notes: str | None = None) -> None:
    ensure_security_grants_table()
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO security_area_grants (user_id, granted_by, notes)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            granted_by = VALUES(granted_by),
            notes = VALUES(notes),
            created_at = CURRENT_TIMESTAMP
        """,
        (user_id, granted_by, (notes or '')[:255] or None),
    )
    db.commit()


def revoke_security_access(user_id: int) -> bool:
    ensure_security_grants_table()
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM security_area_grants WHERE user_id = %s", (user_id,))
    db.commit()
    return cur.rowcount > 0


def find_user_by_username(username: str) -> dict | None:
    if not username:
        return None
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        """
        SELECT id, username, email, role, first_name, last_name
        FROM users WHERE username = %s LIMIT 1
        """,
        (username.strip(),),
    )
    return cur.fetchone()
