# app/models/pastoral/shared.py
# Pastoral access is Access-only: permission key access_pastoral (or Owner/Admin).
# Legacy function names kept so existing imports keep working.

import pymysql
from app.models.db import get_db


def is_in_pastoral_group(user_id):
    """
    May this user open the Pastoral Area?

    True if:
      - role is Owner or Admin, OR
      - they have the Access tool key access_pastoral in user_permissions

    Group membership is NOT used for tools.
    """
    if not user_id:
        return False

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("SELECT role FROM users WHERE id = %s LIMIT 1", (user_id,))
    row = cur.fetchone()
    role = (row or {}).get('role') if isinstance(row, dict) else None
    if role in ('Owner', 'Admin'):
        return True

    try:
        cur.execute(
            """
            SELECT 1 FROM user_permissions
            WHERE user_id = %s AND permission_key = 'access_pastoral'
            LIMIT 1
            """,
            (user_id,),
        )
        return bool(cur.fetchone())
    except Exception:
        return False


def get_pastoral_team_members():
    """
    People who can do pastoral care work: Access access_pastoral, or Owner/Admin.
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    try:
        cur.execute("""
            SELECT DISTINCT u.id, u.first_name, u.last_name, u.email
            FROM users u
            LEFT JOIN user_permissions up
              ON up.user_id = u.id AND up.permission_key = 'access_pastoral'
            WHERE u.role IN ('Owner', 'Admin')
               OR up.permission_key = 'access_pastoral'
            ORDER BY u.last_name, u.first_name
        """)
        return list(cur.fetchall() or [])
    except Exception:
        cur.execute("""
            SELECT id, first_name, last_name, email
            FROM users
            WHERE role IN ('Owner', 'Admin')
            ORDER BY last_name, first_name
        """)
        return list(cur.fetchall() or [])


def get_active_members_for_care():
    """Members directory for care assignment dropdowns."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT id, first_name, last_name, email, username
        FROM users
        WHERE COALESCE(is_shadow_banned, 0) = 0
          AND role NOT IN ('banned', 'pending')
        ORDER BY last_name, first_name
        LIMIT 1000
    """)
    return list(cur.fetchall() or [])
