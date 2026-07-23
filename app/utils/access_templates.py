# app/utils/access_templates.py
# Attach Member Start / Staff Start system groups on create or promote.

from __future__ import annotations

import json
import pymysql


TEMPLATE_ROLE_MAP = {
    'Member': 'member_start',
    'Staff': 'staff_start',
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
    # Attach on create (no old) or when role changes into Member/Staff
    if old == new:
        return ensure_user_in_template(cur, user_id, new, assigned_by)
    if new != old:
        return ensure_user_in_template(cur, user_id, new, assigned_by)
    return False
