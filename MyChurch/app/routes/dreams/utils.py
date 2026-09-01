# app/routes/dreams/utils.py
# Dreams: church participation policy + Access create/moderate.

from app.utils.community_participation import can_create_community_content
from app.utils.permissions import user_has_permission
from app.models.db import get_db
import pymysql


ADMIN_ROLES = ['Admin', 'Owner']


def can_create_dreams() -> bool:
    return can_create_community_content('dreams')


def can_moderate_dreams() -> bool:
    return user_has_permission('moderate_dreams')


def is_comment_owner(comment_id: int, user_id: int) -> bool:
    if not user_id:
        return False
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT user_id FROM dream_comments WHERE id = %s", (comment_id,))
    row = cur.fetchone()
    return row is not None and row['user_id'] == user_id
