import pymysql
from app.models.db import get_db
from app.routes.groups.queries import is_group_leader


def _is_in_group(user_id: int, group_id: int) -> bool:
    if not user_id or not group_id:
        return False
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT 1 FROM user_groups WHERE user_id = %s AND group_id = %s LIMIT 1",
        (user_id, group_id),
    )
    return cur.fetchone() is not None


def can_view_module(module: dict, user_id: int, user_role: str, is_logged_in: bool) -> bool:
    if not module or not module.get('is_enabled'):
        return False
    if (user_role or '') in ('Owner', 'Admin', 'Staff'):
        return True

    visibility = module.get('visibility', 'members')
    if visibility == 'public':
        return True
    if not is_logged_in or not user_id:
        return False
    if visibility == 'members':
        return True
    if visibility == 'group':
        group_id = module.get('group_id')
        return _is_in_group(user_id, group_id)
    return False


def can_manage_module(module: dict, user_id: int, user_role: str) -> bool:
    if not module or not module.get('is_enabled'):
        return False
    if (user_role or '') in ('Owner', 'Admin', 'Staff'):
        return True
    if not user_id:
        return False

    manage_group_id = module.get('manage_group_id') or module.get('group_id')
    if not manage_group_id:
        return False

    if is_group_leader(manage_group_id, user_id):
        return True
    return _is_in_group(user_id, manage_group_id) and module.get('visibility') == 'group'