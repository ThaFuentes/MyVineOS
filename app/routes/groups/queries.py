# app/routes/groups/queries.py
# Full path: MyVineChurch/app/routes/groups/queries.py
# File name: queries.py
# Brief, detailed purpose: All database queries and operations for the Groups module.
# - Pure data-access layer - no Flask routes, no templates, no flash messages.
# - Every function name and signature from the original groups.py is preserved exactly.
# - 100% original behavior preserved.

import pymysql
import json
from flask import session
from app.models.db import get_db
from .utils import KNOWN_PERMISSIONS


# ----------------------------------------------------------------------
# Permission Helpers (exact same as original)
# ----------------------------------------------------------------------
def is_global_manager():
    """Owner/Admin only — Staff uses Permission Groups, not automatic full access."""
    return session.get('user_role') in ['Admin', 'Owner']


def is_group_leader(group_id: int, user_id: int) -> bool:
    """True if user has role_in_group = 'leader' in the specific group."""
    if not user_id:
        return False
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT 1 FROM user_groups
        WHERE group_id = %s AND user_id = %s AND role_in_group = 'leader'
    """, (group_id, user_id))
    return cur.fetchone() is not None


# ----------------------------------------------------------------------
# Fetch groups with details (exact same signature as original)
# ----------------------------------------------------------------------
def fetch_groups_with_details(cur, base_sql, params=[], current_user_id=None):
    cur.execute(base_sql, params)
    groups = cur.fetchall()  # List of dicts (DictCursor)

    global_manager = is_global_manager()

    for group in groups:
        # Member count
        cur.execute("SELECT COUNT(*) AS member_count FROM user_groups WHERE group_id = %s", (group['id'],))
        row = cur.fetchone()
        group['member_count'] = row['member_count'] if row else 0

        # Member details
        cur.execute("""
            SELECT u.id AS user_id, u.first_name, u.last_name, u.username, ug.role_in_group
            FROM user_groups ug
            JOIN users u ON ug.user_id = u.id
            WHERE ug.group_id = %s
            ORDER BY u.last_name, u.first_name
        """, (group['id'],))
        group['members'] = cur.fetchall()

        # Parse permissions (labels include Church App keys when present)
        perms_json = group.get('permissions') or '[]'
        try:
            permission_list = json.loads(perms_json)
        except (TypeError, json.JSONDecodeError):
            permission_list = []
        if not isinstance(permission_list, list):
            permission_list = []
        group['permission_list'] = permission_list
        try:
            from .utils import extend_known_permissions_with_apps
            label_map = extend_known_permissions_with_apps(cur)
        except Exception:
            label_map = KNOWN_PERMISSIONS
        group['permission_labels'] = [
            label_map.get(p, p.replace('_', ' ').title()) for p in permission_list
        ]

        # Can current user manage this group?
        from .gathering_place import can_manage_group_members, can_edit_group_record
        user_role = session.get('user_role')
        group['can_manage_members'] = bool(
            current_user_id and can_manage_group_members(group['id'], current_user_id, user_role)
        )
        group['can_edit'] = bool(
            current_user_id and can_edit_group_record(group['id'], current_user_id, user_role)
        )
        group['can_manage'] = group['can_manage_members'] or group['can_edit']
        from .utils import can_assign_group_manager_role
        group['can_change_roles'] = can_assign_group_manager_role()
        from .gathering_place import is_gathering_place_group_id
        group['is_gathering_place_group'] = is_gathering_place_group_id(group.get('id'))

    return groups


# ----------------------------------------------------------------------
# List Groups
# ----------------------------------------------------------------------
def get_groups_list(is_logged_in=False, role=None, user_id=None):
    sql = """
        SELECT g.*, u.username AS creator_name
        FROM groups g
        LEFT JOIN users u ON u.id = g.created_by
    """
    params = []

    if not is_logged_in or role not in ['Admin', 'Owner', 'Staff']:
        sql += " WHERE g.visibility = 'public'"

    sql += " ORDER BY g.name"

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    return fetch_groups_with_details(cur, sql, params, user_id)


# ----------------------------------------------------------------------
# Search Groups
# ----------------------------------------------------------------------
def search_groups(query, visibility_filter='all', is_logged_in=False, role=None, user_id=None):
    sql = """
        SELECT g.*, u.username AS creator_name
        FROM groups g
        LEFT JOIN users u ON u.id = g.created_by
    """
    where_clauses = []
    params = []

    if query:
        where_clauses.append("(g.name LIKE %s OR g.description LIKE %s)")
        params += [f'%{query}%', f'%{query}%']

    if visibility_filter != 'all':
        where_clauses.append("g.visibility = %s")
        params.append(visibility_filter)

    if not is_logged_in or role not in ['Admin', 'Owner', 'Staff']:
        where_clauses.append("g.visibility = 'public'")

    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)

    sql += " ORDER BY g.name"

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    return fetch_groups_with_details(cur, sql, params, user_id)


# ----------------------------------------------------------------------
# CRUD Operations (exact same as original)
# ----------------------------------------------------------------------
def create_group(name, description, visibility, permissions, user_id):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO groups (name, description, visibility, permissions, created_by, updated_by)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (name, description, visibility, permissions, user_id, user_id))
        group_id = cur.lastrowid

        # Auto-add creator as leader
        cur.execute("""
            INSERT INTO user_groups (user_id, group_id, role_in_group, assigned_by)
            VALUES (%s, %s, 'leader', %s)
        """, (user_id, group_id, user_id))

        db.commit()
        return group_id
    except Exception:
        db.rollback()
        raise


def update_group(group_id, name, description, visibility, permissions, user_id):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            UPDATE groups
            SET name = %s, description = %s, visibility = %s, permissions = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (name, description, visibility, permissions, user_id, group_id))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def delete_group(group_id):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM groups WHERE id = %s", (group_id,))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def assign_user_to_group(group_id, target_user_id, role_in_group, assigned_by):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO user_groups (user_id, group_id, role_in_group, assigned_by)
            VALUES (%s, %s, %s, %s)
        """, (target_user_id, group_id, role_in_group, assigned_by))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def remove_user_from_group(group_id, user_id):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM user_groups WHERE group_id = %s AND user_id = %s", (group_id, user_id))
        db.commit()
        return cur.rowcount > 0
    except Exception:
        db.rollback()
        raise


def update_user_role_in_group(group_id, user_id, new_role):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            UPDATE user_groups
            SET role_in_group = %s
            WHERE group_id = %s AND user_id = %s
        """, (new_role, group_id, user_id))
        db.commit()
        return cur.rowcount > 0
    except Exception:
        db.rollback()
        raise


def lookup_user_by_username_or_email(identifier: str):
    """Find an active user by exact username or email."""
    identifier = (identifier or '').strip()
    if not identifier:
        return None
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT id, username, email, first_name, last_name, role
        FROM users
        WHERE (username = %s OR email = %s)
          AND role NOT IN ('pending', 'banned')
        LIMIT 1
    """, (identifier, identifier))
    return cur.fetchone()


def search_users_for_group_assignment(group_id: int, query: str, limit: int = 20):
    """Live search for users not already assigned to the group."""
    query = (query or '').strip()
    if len(query) < 2:
        return []

    like = f'%{query}%'
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT u.id, u.username, u.email, u.first_name, u.last_name
        FROM users u
        WHERE u.role NOT IN ('pending', 'banned')
          AND (
              u.first_name LIKE %s OR u.last_name LIKE %s
              OR u.username LIKE %s OR u.email LIKE %s
              OR CONCAT(u.first_name, ' ', u.last_name) LIKE %s
          )
          AND u.id NOT IN (
              SELECT ug.user_id FROM user_groups ug WHERE ug.group_id = %s
          )
        ORDER BY u.last_name, u.first_name
        LIMIT %s
    """, (like, like, like, like, like, group_id, limit))

    users = cur.fetchall()
    for user in users:
        user['full_name'] = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
    return users