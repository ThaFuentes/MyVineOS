# app/utils/permissions.py
# Enterprise capability checks for MyVine.
#
# MODEL
# -----
# 1) ROLE (Member / Staff / Admin / Owner) = identity + operator bypass.
#    Owner + Admin: full access (never lock site operators out).
#    Staff + Member: NOT automatic tools — only grants below.
# 2) GROUPS: shared packs of permission keys (JSON on groups.permissions).
# 3) DIRECT per-user grants: user_permissions table (one-off fine grain).
# 4) Effective (non-Admin) = union(groups) ∪ union(direct grants).
# 5) Templates (Member Start / Staff Start) are system groups attached on
#    create/promote — editable, not a hard ceiling.

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
    Staff/Member: (groups ∪ personal YES) minus personal NO blocks.
    Role never adds tools by itself.
    """
    role = user_role if user_role is not None else session.get('user_role')
    if role_has_full_access(role):
        return set(_known_permission_keys()) | set(get_all_app_permission_keys(cur))
    if not user_id:
        return set()
    granted = _union_group_permissions(cur, user_id) | _union_direct_permissions(cur, user_id)
    blocked = _union_blocked_permissions(cur, user_id)
    return granted - blocked


def get_user_permission_breakdown(cur, user_id: int, user_role: str | None = None) -> dict:
    """For Access UI: effective keys + sources."""
    role = user_role if user_role is not None else session.get('user_role')
    if role_has_full_access(role):
        all_keys = set(_known_permission_keys()) | set(get_all_app_permission_keys(cur))
        return {
            'role': role,
            'full_access': True,
            'group_keys': set(),
            'direct_keys': set(),
            'blocked_keys': set(),
            'effective': all_keys,
            'groups': [],
        }

    group_keys = _union_group_permissions(cur, user_id)
    direct_keys = _union_direct_permissions(cur, user_id)
    blocked_keys = _union_blocked_permissions(cur, user_id)
    cur.execute(
        """
        SELECT g.id, g.name, g.system_key, g.permissions
        FROM groups g
        JOIN user_groups ug ON ug.group_id = g.id
        WHERE ug.user_id = %s
        ORDER BY g.name
        """,
        (user_id,),
    )
    groups = []
    for row in cur.fetchall() or []:
        try:
            perms = json.loads((row.get('permissions') if isinstance(row, dict) else row[3]) or '[]')
        except (TypeError, json.JSONDecodeError):
            perms = []
        if not isinstance(perms, list):
            perms = []
        groups.append({
            'id': row['id'] if isinstance(row, dict) else row[0],
            'name': row['name'] if isinstance(row, dict) else row[1],
            'system_key': (row.get('system_key') if isinstance(row, dict) else row[2]),
            'permissions': [p for p in perms if is_valid_permission_key(p)],
        })
    return {
        'role': role,
        'full_access': False,
        'group_keys': group_keys,
        'direct_keys': direct_keys,
        'blocked_keys': blocked_keys,
        'effective': (group_keys | direct_keys) - blocked_keys,
        'groups': groups,
    }


def set_user_direct_permissions(cur, user_id: int, keys: list[str], granted_by: int | None = None) -> None:
    """Replace all direct YES grants for a user."""
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
    """
    Make effective access match desired_keys exactly for Staff/Member.

    - Writes desired keys as personal YES grants.
    - Blocks every known key NOT in desired (so groups cannot sneak access back).
    - Owner/Admin not handled here (full access).
    """
    desired = set(k for k in (desired_keys or []) if is_valid_permission_key(k))
    # All known catalog keys we can block
    all_keys = set(_known_permission_keys())
    try:
        all_keys |= set(get_all_app_permission_keys(cur))
    except Exception:
        pass

    set_user_direct_permissions(cur, user_id, list(desired), granted_by)

    blocked = list(all_keys - desired)
    try:
        cur.execute("DELETE FROM user_permission_blocks WHERE user_id = %s", (user_id,))
        for key in blocked:
            cur.execute(
                """
                INSERT INTO user_permission_blocks (user_id, permission_key, blocked_by)
                VALUES (%s, %s, %s)
                """,
                (user_id, key, granted_by),
            )
    except Exception as e:
        # Table may not exist yet on first request before builddb
        print(f"user_permission_blocks write skipped: {e}")


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
    return permission_key in get_user_effective_permissions(cur, user_id, user_role)


def user_has_permission(permission_key: str) -> bool:
    """
    Return True if the current user has the specified permission.
    - Owner / Admin: always True (full site operators)
    - Staff / Member: groups ∪ direct personal grants only
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
