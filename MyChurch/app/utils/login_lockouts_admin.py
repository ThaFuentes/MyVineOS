# app/utils/login_lockouts_admin.py
# Admin utilities for IP login lockouts (pbt_login_lockouts table).

from datetime import datetime

from poweredbytop.models.connect_db import get_security_db


def list_ip_lockouts(limit: int = 100) -> list[dict]:
    db = get_security_db()
    if db is None:
        return []
    cur = db.cursor()
    try:
        cur.execute(
            """
            SELECT ip, failed_attempts, locked_until, last_attempt_at, updated_at
            FROM pbt_login_lockouts
            ORDER BY COALESCE(locked_until, last_attempt_at) DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
        out = []
        now = datetime.now()
        for row in rows:
            item = {
                'ip': row[0],
                'failed_attempts': row[1],
                'locked_until': row[2],
                'last_attempt_at': row[3],
                'updated_at': row[4],
                'is_active': bool(row[2] and row[2] > now),
            }
            out.append(item)
        return out
    except Exception:
        return []


def clear_ip_lockout(ip: str) -> bool:
    if not ip:
        return False
    db = get_security_db()
    if db is None:
        return False
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM pbt_login_lockouts WHERE ip = %s", (ip.strip(),))
        db.commit()
        return cur.rowcount > 0
    except Exception:
        return False


def clear_all_ip_lockouts() -> int:
    db = get_security_db()
    if db is None:
        return 0
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM pbt_login_lockouts")
        db.commit()
        return cur.rowcount
    except Exception:
        return 0