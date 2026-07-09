# Gathering Place Managers — system group identified by stable system_key (name may be edited in UI).

from typing import Optional
import pymysql
from app.models.db import get_db

GATHERING_PLACE_GROUP_NAME = 'Gathering Place Managers'
GATHERING_PLACE_SYSTEM_KEY = 'gathering_place'


def get_gathering_place_group_id() -> Optional[int]:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute('SELECT id FROM groups WHERE system_key = %s LIMIT 1', (GATHERING_PLACE_SYSTEM_KEY,))
    row = cur.fetchone()
    if row:
        return row['id']
    cur.execute('SELECT id FROM groups WHERE name = %s LIMIT 1', (GATHERING_PLACE_GROUP_NAME,))
    row = cur.fetchone()
    return row['id'] if row else None


def is_gathering_place_group_id(group_id: int) -> bool:
    if not group_id:
        return False
    gp_id = get_gathering_place_group_id()
    return bool(gp_id and int(group_id) == int(gp_id))


def is_gathering_place_group_name(name: str) -> bool:
    gp_id = get_gathering_place_group_id()
    if not gp_id:
        return (name or '').strip() == GATHERING_PLACE_GROUP_NAME
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute('SELECT name FROM groups WHERE id = %s', (gp_id,))
    row = cur.fetchone()
    return bool(row and (row.get('name') or '').strip() == (name or '').strip())


def is_gathering_place_member(user_id: int) -> bool:
    if not user_id:
        return False
    gp_id = get_gathering_place_group_id()
    if not gp_id:
        return False
    db = get_db()
    cur = db.cursor()
    cur.execute(
        'SELECT 1 FROM user_groups WHERE user_id = %s AND group_id = %s LIMIT 1',
        (user_id, gp_id),
    )
    return cur.fetchone() is not None


def can_access_gathering_place(user_id: int, user_role: str) -> bool:
    """Route access: Owner always, otherwise must be in the Gathering Place group."""
    if (user_role or '') == 'Owner':
        return True
    return is_gathering_place_member(user_id)


def can_manage_gathering_place_membership(user_id: int, user_role: str) -> bool:
    """Global Staff/Admin/Owner may manage membership; regular group members may not."""
    from .utils import is_global_manager
    return is_global_manager()


def can_edit_gathering_place_group_settings(user_role: str) -> bool:
    from .utils import is_global_manager
    return is_global_manager()


def can_manage_group_members(group_id: int, user_id: int, user_role: str) -> bool:
    from .utils import is_global_manager
    from .queries import is_group_leader
    if is_global_manager():
        return True
    return is_group_leader(group_id, user_id)


def can_edit_group_record(group_id: int, user_id: int, user_role: str) -> bool:
    from .utils import is_global_manager
    from .queries import is_group_leader
    if is_global_manager():
        return True
    return is_group_leader(group_id, user_id)