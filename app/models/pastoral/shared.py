# app/models/pastoral/shared.py
# Full path: WebChurchMan/app/models/pastoral/shared.py
# File name: shared.py
# Brief, detailed purpose:
#   Shared / cross-cutting helper functions used across multiple Pastoral Area sub-modules.
#   Currently contains only the core permission check: is_in_pastoral_group().
#   More shared utilities can be added here later (e.g. common visibility helpers,
#   date formatting for pastoral views, team member counts, permission checks, etc.).
#   Uses DictCursor for consistency where needed.
#   Parameterized queries for MariaDB / PyMySQL safety.

import pymysql
from app.models.db import get_db


# ----------------------------------------------------------------------
# Pastoral Group Membership Check
# ----------------------------------------------------------------------
def is_in_pastoral_group(user_id):
    """
    Gatekeeper for the Pastoral Area.

    True if the user:
      - is a member of the named 'Pastoral Group' (or system_key = pastoral), OR
      - belongs to any group that grants the 'access_pastoral' permission

    Owner/Admin/Staff bypass is handled by callers that also check role.
    """
    if not user_id:
        return False

    import json as _json

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT g.name, g.system_key, g.permissions
        FROM groups g
        JOIN user_groups ug ON g.id = ug.group_id
        WHERE ug.user_id = %s
    """, (user_id,))

    for row in cur.fetchall() or []:
        name = (row.get('name') or '') if isinstance(row, dict) else (row[0] or '')
        system_key = (row.get('system_key') or '') if isinstance(row, dict) else (row[1] or '')
        if name == 'Pastoral Group' or system_key == 'pastoral':
            return True
        raw = row.get('permissions') if isinstance(row, dict) else row[2]
        try:
            perms = _json.loads(raw or '[]')
        except (TypeError, ValueError):
            perms = []
        if isinstance(perms, list) and 'access_pastoral' in perms:
            return True

    return False


def get_pastoral_team_members():
    """
    Return users in the Pastoral Group (for care assignment dropdowns).

    Returns:
        list[dict]: id, first_name, last_name, email
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT u.id, u.first_name, u.last_name, u.email
        FROM users u
        JOIN user_groups ug ON u.id = ug.user_id
        JOIN groups g ON ug.group_id = g.id
        WHERE g.name = 'Pastoral Group'
        ORDER BY u.last_name, u.first_name
    """)
    return cur.fetchall()


def get_active_members_for_care():
    """
    Return members eligible to receive pastoral care (not banned/pending).

    Returns:
        list[dict]: id, first_name, last_name, email
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT id, first_name, last_name, email
        FROM users
        WHERE role NOT IN ('banned', 'pending')
        ORDER BY last_name, first_name
    """)
    return cur.fetchall()