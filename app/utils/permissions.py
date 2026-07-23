# app/utils/permissions.py
# Enterprise capability checks for MyVine.
#
# MODEL (single source — no group permission grants)
# --------------------------------------------------
# 1) ROLE: Owner + Admin = full access (never lock operators out).
#    Staff + Member = NO tools from role alone.
# 2) ONE source for Staff/Member: user_permissions (set via Access UI / templates).
# 3) Groups are NOT used for tool access (avoids accidental grants).
# 4) Templates only write into user_permissions when applied / on new Member/Staff.

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

# Legacy "manage_*" (and similar) expand into fine-grained keys.
# Holding manage_tickets ⇒ view/create/edit/delete_tickets all pass checks.
# New Access UI stores one key per checkbox only.
PERMISSION_SUPERSETS: dict[str, frozenset[str]] = {
    'manage_accounting': frozenset([
        'view_accounting', 'create_accounting', 'edit_accounting', 'delete_accounting',
    ]),
    'manage_donations': frozenset([
        'view_donations', 'create_donations', 'edit_donations', 'delete_donations',
    ]),
    'manage_bills': frozenset([
        'view_bills', 'create_bills', 'edit_bills', 'delete_bills',
    ]),
    'manage_inventory': frozenset([
        'view_inventory', 'create_inventory', 'edit_inventory', 'delete_inventory',
    ]),
    'manage_tickets': frozenset([
        'view_tickets', 'create_tickets', 'edit_tickets', 'delete_tickets',
    ]),
    'submit_tickets': frozenset(['view_own_tickets', 'submit_tickets']),
    'manage_members': frozenset([
        'view_members', 'create_members', 'edit_members', 'delete_members',
    ]),
    'manage_users': frozenset([
        'view_users', 'create_users', 'edit_users', 'delete_users',
    ]),
    'manage_attendance': frozenset([
        'view_attendance', 'create_attendance', 'edit_attendance', 'delete_attendance',
        # attendance often covered child check-in too historically
        'view_child_checkin', 'create_child_checkin', 'edit_child_checkin', 'delete_child_checkin',
        'manage_child_checkin',
    ]),
    'manage_child_checkin': frozenset([
        'view_child_checkin', 'create_child_checkin', 'edit_child_checkin', 'delete_child_checkin',
    ]),
    'manage_volunteers': frozenset([
        'view_volunteers', 'create_volunteers', 'edit_volunteers', 'delete_volunteers',
    ]),
    'manage_events': frozenset([
        'view_events', 'create_events', 'edit_events', 'delete_events', 'moderate_events',
    ]),
    'create_announcements': frozenset(['view_announcements', 'create_announcements', 'edit_announcements']),
    'moderate_announcements': frozenset([
        'view_announcements', 'edit_announcements', 'delete_announcements', 'moderate_announcements',
    ]),
    'upload_sermons': frozenset(['view_sermons', 'upload_sermons', 'edit_sermons']),
    'moderate_sermons': frozenset([
        'view_sermons', 'edit_sermons', 'delete_sermons', 'moderate_sermons',
    ]),
    'create_dreams': frozenset(['view_dreams', 'create_dreams', 'edit_dreams']),
    'moderate_dreams': frozenset(['view_dreams', 'edit_dreams', 'delete_dreams', 'moderate_dreams']),
    'create_prophecies': frozenset(['view_prophecies', 'create_prophecies', 'edit_prophecies']),
    'moderate_prophecies': frozenset([
        'view_prophecies', 'edit_prophecies', 'delete_prophecies', 'moderate_prophecies',
    ]),
    'create_prayers': frozenset(['view_prayers', 'create_prayers', 'edit_prayers']),
    'moderate_prayers': frozenset(['view_prayers', 'edit_prayers', 'delete_prayers', 'moderate_prayers']),
    'access_pastoral': frozenset(['access_pastoral']),
    'manage_worship': frozenset([
        'access_worship', 'create_worship', 'edit_worship', 'delete_worship',
    ]),
    'send_emails': frozenset([
        'view_communications', 'send_emails', 'edit_communications', 'delete_communications',
    ]),
    'use_ai_insights': frozenset(['view_ai_insights', 'use_ai_insights']),
    'manage_settings': frozenset(['view_settings', 'manage_settings']),
    'manage_help': frozenset(['view_help', 'manage_help']),
    'manage_legal_notices': frozenset(['view_legal', 'manage_legal_notices']),
    'manage_security': frozenset(['view_security', 'manage_security']),
}


def expand_permission_keys(keys) -> set[str]:
    """Expand legacy manage_* supersets into fine-grained keys for checks / UI."""
    out = set(keys or [])
    # Multiple passes so chained expansions settle (e.g. manage_attendance → child_checkin)
    for _ in range(3):
        before = len(out)
        for super_key, implied in PERMISSION_SUPERSETS.items():
            if super_key in out:
                out |= implied
        if len(out) == before:
            break
    return out


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


def _union_direct_permissions(cur, user_id: int) -> set[str]:
    """Personal grants from user_permissions (table may be missing on old hosts)."""
    try:
        cur.execute(
            """
            SELECT permission_key
            FROM user_permissions
            WHERE user_id = %s
            """,
            (user_id,),
        )
    except Exception:
        return set()
    keys = set()
    for row in cur.fetchall() or []:
        key = row['permission_key'] if isinstance(row, dict) else row[0]
        if is_valid_permission_key(key):
            keys.add(key)
    return keys


def _union_blocked_permissions(cur, user_id: int) -> set[str]:
    """Explicit NO overrides — always win over groups for Staff/Member."""
    try:
        cur.execute(
            """
            SELECT permission_key
            FROM user_permission_blocks
            WHERE user_id = %s
            """,
            (user_id,),
        )
    except Exception:
        return set()
    keys = set()
    for row in cur.fetchall() or []:
        key = row['permission_key'] if isinstance(row, dict) else row[0]
        if is_valid_permission_key(key):
            keys.add(key)
    return keys


def role_has_full_access(user_role: str | None) -> bool:
    """Owner/Admin only — not Staff."""
    return (user_role or '') in FULL_ACCESS_ROLES


def get_user_effective_permissions(cur, user_id: int, user_role: str | None = None) -> set[str]:
    """
    Owner/Admin: all keys.
    Staff/Member: ONLY user_permissions (single source). Groups never grant tools.
    """
    role = user_role if user_role is not None else session.get('user_role')
    if role_has_full_access(role):
        return set(_known_permission_keys()) | set(get_all_app_permission_keys(cur))
    if not user_id:
        return set()
    return _union_direct_permissions(cur, user_id)


def get_user_permission_breakdown(cur, user_id: int, user_role: str | None = None) -> dict:
    """For Access UI: single-source effective keys."""
    role = user_role if user_role is not None else session.get('user_role')
    if role_has_full_access(role):
        all_keys = set(_known_permission_keys()) | set(get_all_app_permission_keys(cur))
        return {
            'role': role,
            'full_access': True,
            'direct_keys': set(),
            'effective': all_keys,
        }

    direct_keys = _union_direct_permissions(cur, user_id)
    return {
        'role': role,
        'full_access': False,
        'direct_keys': direct_keys,
        'effective': set(direct_keys),
    }


def set_user_direct_permissions(cur, user_id: int, keys: list[str], granted_by: int | None = None) -> None:
    """Replace all tool grants for a user (the only source for Staff/Member)."""
    clean = [k for k in (keys or []) if is_valid_permission_key(k)]
    clean = list(dict.fromkeys(clean))
    cur.execute("DELETE FROM user_permissions WHERE user_id = %s", (user_id,))
    for key in clean:
        cur.execute(
            """
            INSERT INTO user_permissions (user_id, permission_key, granted_by)
            VALUES (%s, %s, %s)
            """,
            (user_id, key, granted_by),
        )


def set_user_exact_access(
    cur,
    user_id: int,
    desired_keys: list[str],
    granted_by: int | None = None,
) -> None:
    """Set this person's tools exactly (single source)."""
    set_user_direct_permissions(cur, user_id, list(desired_keys or []), granted_by)
    # Clear legacy blocks table if present (no longer used)
    try:
        cur.execute("DELETE FROM user_permission_blocks WHERE user_id = %s", (user_id,))
    except Exception:
        pass


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
    effective = expand_permission_keys(
        get_user_effective_permissions(cur, user_id, user_role)
    )
    if permission_key in effective:
        return True
    # Legacy routes still ask for manage_*: true if user holds any fine key that manage_* expands to.
    implied = PERMISSION_SUPERSETS.get(permission_key)
    if implied and (effective & implied):
        return True
    return False


def user_has_permission(permission_key: str) -> bool:
    """
    Return True if the current user has the specified permission.
    - Owner / Admin: always True (full site operators)
    - Staff / Member: only keys on their Access tools list (user_permissions)
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
