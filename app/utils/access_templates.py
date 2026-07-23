# app/utils/access_templates.py
# Role start templates: what NEW Members / NEW Staff get by default.
# Stored as system groups (system_key member_start / staff_start).
# Admin/Owner are not templated — they always have full access.

from __future__ import annotations

import json


TEMPLATE_ROLE_MAP = {
    'Member': 'member_start',
    'Staff': 'staff_start',
}

TEMPLATE_META = {
    'member_start': {
        'role': 'Member',
        'title': 'New Member template',
        'blurb': 'Default tools for every brand-new Member (signup or add). You can still change any person later under Tools.',
    },
    'staff_start': {
        'role': 'Staff',
        'title': 'New Staff template',
        'blurb': 'Default tools when someone is first made Staff. Not automatic forever — edit anyone under Tools anytime.',
    },
}


def get_template_group_id(cur, system_key: str) -> int | None:
    cur.execute(
        "SELECT id FROM groups WHERE system_key = %s LIMIT 1",
        (system_key,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return row['id'] if isinstance(row, dict) else row[0]


def get_template_group(cur, system_key: str) -> dict | None:
    cur.execute(
        """
        SELECT id, name, description, permissions, system_key
        FROM groups
        WHERE system_key = %s
        LIMIT 1
        """,
        (system_key,),
    )
    row = cur.fetchone()
    if not row:
        return None
    if not isinstance(row, dict):
        row = {
            'id': row[0],
            'name': row[1],
            'description': row[2],
            'permissions': row[3],
            'system_key': row[4],
        }
    try:
        perms = json.loads(row.get('permissions') or '[]')
    except (TypeError, json.JSONDecodeError):
        perms = []
    if not isinstance(perms, list):
        perms = []
    row['permission_list'] = perms
    return row


def save_template_permissions(cur, system_key: str, keys: list[str]) -> bool:
    """Update the system group permissions JSON for a start template."""
    gid = get_template_group_id(cur, system_key)
    if not gid:
        return False
    clean = list(dict.fromkeys([k for k in (keys or []) if k]))
    cur.execute(
        "UPDATE groups SET permissions = %s WHERE id = %s",
        (json.dumps(clean), gid),
    )
    return True


def ensure_user_in_template(cur, user_id: int, role: str, assigned_by: int | None = None) -> bool:
    """
    Attach the start pack for Member or Staff if not already a member of that system group.
    Returns True if membership was added.
    """
    system_key = TEMPLATE_ROLE_MAP.get((role or '').strip())
    if not system_key or not user_id:
        return False
    gid = get_template_group_id(cur, system_key)
    if not gid:
        return False
    cur.execute(
        "SELECT 1 FROM user_groups WHERE user_id = %s AND group_id = %s",
        (user_id, gid),
    )
    if cur.fetchone():
        return False
    cur.execute(
        """
        INSERT INTO user_groups (user_id, group_id, role_in_group, assigned_by)
        VALUES (%s, %s, 'member', %s)
        """,
        (user_id, gid, assigned_by),
    )
    return True


def apply_role_template_on_role_change(
    cur,
    user_id: int,
    old_role: str | None,
    new_role: str | None,
    assigned_by: int | None = None,
) -> bool:
    """
    When promoting to Member/Staff (or creating as such), attach start pack.
    Does not remove other groups. Does not strip access when demoting.
    """
    old = (old_role or '').strip()
    new = (new_role or '').strip()
    if new not in TEMPLATE_ROLE_MAP:
        return False
    if old == new or new != old:
        return ensure_user_in_template(cur, user_id, new, assigned_by)
    return False


def apply_template_to_all_with_role(cur, role: str, assigned_by: int | None = None) -> int:
    """
    Attach the start template group to every user with this role who is missing it.
    Does not remove personal NO blocks or other groups.
    Returns number of users newly attached.
    """
    system_key = TEMPLATE_ROLE_MAP.get((role or '').strip())
    if not system_key:
        return 0
    gid = get_template_group_id(cur, system_key)
    if not gid:
        return 0
    cur.execute(
        """
        SELECT u.id
        FROM users u
        WHERE u.role = %s
          AND u.id NOT IN (
              SELECT ug.user_id FROM user_groups ug WHERE ug.group_id = %s
          )
        """,
        (role, gid),
    )
    ids = []
    for row in cur.fetchall() or []:
        ids.append(row['id'] if isinstance(row, dict) else row[0])
    n = 0
    for uid in ids:
        cur.execute(
            """
            INSERT IGNORE INTO user_groups (user_id, group_id, role_in_group, assigned_by)
            VALUES (%s, %s, 'member', %s)
            """,
            (uid, gid, assigned_by),
        )
        n += 1
    return n


def count_template_members(cur, system_key: str) -> int:
    gid = get_template_group_id(cur, system_key)
    if not gid:
        return 0
    cur.execute(
        "SELECT COUNT(*) AS n FROM user_groups WHERE group_id = %s",
        (gid,),
    )
    row = cur.fetchone()
    if not row:
        return 0
    return int(row['n'] if isinstance(row, dict) else row[0])
