import pymysql
from flask import session
from app.models.db import get_db

WORSHIP_TEAM_GROUP_NAME = 'Worship Team Group'


def is_in_worship_team(user_id: int) -> bool:
    if not user_id:
        return False
    if session.get('user_role') in ('Owner', 'Admin', 'Staff'):
        return True
    import json as _json
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT g.system_key, g.name, g.permissions
        FROM user_groups ug
        JOIN groups g ON g.id = ug.group_id
        WHERE ug.user_id = %s
    """, (user_id,))
    for row in cur.fetchall() or []:
        if row.get('system_key') == 'worship_team' or row.get('name') == WORSHIP_TEAM_GROUP_NAME:
            return True
        try:
            perms = _json.loads(row.get('permissions') or '[]')
        except (TypeError, ValueError):
            perms = []
        if isinstance(perms, list) and (
            'access_worship' in perms or 'manage_worship' in perms
        ):
            return True
    return False


def is_worship_group_manager(user_id: int) -> bool:
    if not user_id:
        return False
    import json as _json
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT g.system_key, g.name, g.permissions, ug.role_in_group
        FROM user_groups ug
        JOIN groups g ON g.id = ug.group_id
        WHERE ug.user_id = %s
    """, (user_id,))
    for row in cur.fetchall() or []:
        try:
            perms = _json.loads(row.get('permissions') or '[]')
        except (TypeError, ValueError):
            perms = []
        if isinstance(perms, list) and 'manage_worship' in perms:
            return True
        if (
            (row.get('system_key') == 'worship_team' or row.get('name') == WORSHIP_TEAM_GROUP_NAME)
            and row.get('role_in_group') == 'leader'
        ):
            return True
    return False


def can_manage_worship(user_id: int = None) -> bool:
    user_id = user_id or session.get('user_id')
    if session.get('user_role') in ('Owner', 'Admin', 'Staff'):
        return True
    return is_worship_group_manager(user_id)


def can_view_worship(user_id: int = None) -> bool:
    return is_in_worship_team(user_id or session.get('user_id'))


def can_edit_worship_charts(user_id: int = None) -> bool:
    """
    Worship lead/managers AND team members may edit role charts
    (guitar/bass/vocals/lyrics) so each person can tailor their part.
    Create/delete library songs stays manage-only.
    """
    user_id = user_id or session.get('user_id')
    if can_manage_worship(user_id):
        return True
    return can_view_worship(user_id)


def get_worship_team_members():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT u.id, u.username, u.first_name, u.last_name, u.email, ug.role_in_group
        FROM user_groups ug
        JOIN groups g ON g.id = ug.group_id
        JOIN users u ON u.id = ug.user_id
        WHERE g.system_key = 'worship_team' OR g.name = %s
        ORDER BY u.last_name, u.first_name
    """, (WORSHIP_TEAM_GROUP_NAME,))

    # Returning as a list for consistency
    return list(cur.fetchall())


def get_worship_leaders():
    """Group managers (leader role) plus Owner/Admin/Staff worship access."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT u.id, u.username, u.first_name, u.last_name, u.role AS site_role,
               ug.role_in_group
        FROM user_groups ug
        JOIN groups g ON g.id = ug.group_id
        JOIN users u ON u.id = ug.user_id
        WHERE (g.system_key = 'worship_team' OR g.name = %s)
          AND ug.role_in_group = 'leader'
        ORDER BY u.last_name, u.first_name
    """, (WORSHIP_TEAM_GROUP_NAME,))
    # Cast to list so .append() works when merging site staff
    leaders = list(cur.fetchall())
    cur.execute("""
        SELECT id, username, first_name, last_name, role AS site_role, 'site_staff' AS role_in_group
        FROM users WHERE role IN ('Owner', 'Admin', 'Staff')
        ORDER BY last_name, first_name
    """)
    staff = cur.fetchall()

    seen = {l['id'] for l in leaders}
    for s in staff:
        if s['id'] not in seen:
            leaders.append(s)

    return leaders
