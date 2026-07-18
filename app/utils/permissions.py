# app/utils/permissions.py
# Enterprise capability checks for MyVine.
#
# MODEL (how it is supposed to work)
# ----------------------------------
# 1) Site ROLE (Member / Staff / Admin / Owner) = account tier, not a free buffet of features.
# 2) GROUPS hold capability keys (manage_bills, manage_accounting, access_worship, …).
# 3) Effective permissions = union of all group permission lists for that user.
# 4) FULL ACCESS bypass: Owner (and Admin) only — they can always fix the site.
# 5) Staff and Member: ONLY what their groups grant. No automatic “Staff sees everything.”
#
# Example:
#   Put Alice (Staff) in group "Finance Team" with manage_accounting + manage_bills.
#   Put Bob (Staff) in "Worship Team" with access_worship + manage_worship.
#   Bob does not see Accounting. Alice does not see Worship management.

import json
import re

from flask import session
from app.models.db import get_db
import pymysql

# Full bypass of permission keys (site operators who must never be locked out).
FULL_ACCESS_ROLES = frozenset(['Owner', 'Admin'])

# Legacy name kept for imports; do NOT put Staff here.
GLOBAL_MANAGER_ROLES = FULL_ACCESS_ROLES

APP_ACCESS_KEY_RE = re.compile(r'^access_app_[a-z0-9_]{1,48}$')
APP_MANAGE_KEY_RE = re.compile(r'^manage_app_[a-z0-9_]{1,48}$')


def _known_permission_keys():
    from app.routes.groups.utils import KNOWN_PERMISSIONS
    return frozenset(KNOWN_PERMISSIONS.keys())


def is_valid_permission_key(key: str) -> bool:
    if not key:
        return False
    if key in _known_permission_keys():
        return True
    return bool(APP_ACCESS_KEY_RE.match(key) or APP_MANAGE_KEY_RE.match(key))


def get_all_app_permission_keys(cur) -> list[str]:
    cur.execute("SELECT slug FROM custom_modules")
    keys = []
    for row in cur.fetchall():
        slug = row['slug'] if isinstance(row, dict) else row[0]
        safe = (slug or 'app').replace('-', '_')[:48]
        keys.append(f'access_app_{safe}')
        keys.append(f'manage_app_{safe}')
    return keys


def _union_group_permissions(cur, user_id: int) -> set[str]:
    cur.execute(
        """
        SELECT g.permissions
        FROM groups g
        JOIN user_groups ug ON ug.group_id = g.id
        WHERE ug.user_id = %s
        """,
        (user_id,),
    )
    effective = set()
    for row in cur.fetchall():
        perms_json = row['permissions'] if isinstance(row, dict) else row[0]
        try:
            perms = json.loads(perms_json or '[]')
        except (TypeError, json.JSONDecodeError):
            perms = []
        if isinstance(perms, list):
            effective.update(p for p in perms if is_valid_permission_key(p))
    return effective


def role_has_full_access(user_role: str | None) -> bool:
    """Owner/Admin only — not Staff."""
    return (user_role or '') in FULL_ACCESS_ROLES


def get_user_effective_permissions(cur, user_id: int, user_role: str | None = None) -> set[str]:
    role = user_role if user_role is not None else session.get('user_role')
    if role_has_full_access(role):
        return set(_known_permission_keys()) | set(get_all_app_permission_keys(cur))
    if not user_id:
        return set()
    return _union_group_permissions(cur, user_id)


def get_grantable_permissions(cur, user_id: int, user_role: str | None = None) -> set[str]:
    """Permissions this user may assign to a group (at or below their own level)."""
    return get_user_effective_permissions(cur, user_id, user_role)


def sanitize_group_permissions(
    existing: list[str],
    selected: list[str],
    grantable: set[str],
    *,
    is_global_manager: bool,
) -> list[str]:
    """
    Merge submitted permissions with locked admin-granted permissions.
    Group managers cannot add permissions above their level or remove locked ones.
    """
    existing = [p for p in (existing or []) if is_valid_permission_key(p)]
    selected = [p for p in (selected or []) if is_valid_permission_key(p)]

    if is_global_manager:
        return list(dict.fromkeys(selected))

    grantable_set = set(grantable)
    locked = [p for p in existing if p not in grantable_set]
    editable = [p for p in selected if p in grantable_set]
    return list(dict.fromkeys(locked + editable))


def user_has_permission_for_user(cur, user_id: int, user_role: str | None, permission_key: str) -> bool:
    if not user_id:
        return False
    if role_has_full_access(user_role):
        return True
    if not is_valid_permission_key(permission_key):
        return False
    return permission_key in _union_group_permissions(cur, user_id)


def user_has_permission(permission_key: str) -> bool:
    """
    Return True if the current user has the specified permission.
    - Owner / Admin: always True (full site operators)
    - Staff / Member: only keys granted via Permission Groups
    """
    user_id = session.get('user_id')
    if not user_id:
        return False

    role = session.get('user_role')
    if role_has_full_access(role):
        return True

    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        # Refresh role from DB if session is stale / missing
        if not role:
            cur.execute("SELECT role FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            role = (row or {}).get('role')
            if role:
                session['user_role'] = role
            if role_has_full_access(role):
                return True
        return user_has_permission_for_user(cur, user_id, role, permission_key)
    except Exception as e:
        print(f"Permission check error: {e}")
        return False
