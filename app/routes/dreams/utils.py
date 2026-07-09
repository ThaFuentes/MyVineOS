# app/routes/dreams/utils.py
# Full path: MyVineChurch/app/routes/dreams/utils.py
# File name: utils.py
# Brief, detailed purpose: Utility functions and constants for the Dreams module.
# - Group permission helpers using the central user_has_permission system
# - ADMIN_ROLES kept for backward compatibility
# - is_comment_owner() - critical for proper comment delete/update permissions
# - Clean and consistent with the rest of the app

from app.utils.decorators import user_has_permission
from app.models.db import get_db
import pymysql


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
ADMIN_ROLES = ['Admin', 'Owner']


# ----------------------------------------------------------------------
# Group Permission Helpers
# ----------------------------------------------------------------------
def can_create_dreams():
    """Can the current user submit new dreams?"""
    return user_has_permission('create_dreams')


def can_moderate_dreams():
    """Can the current user edit/delete ANY dream (including others')?"""
    return user_has_permission('moderate_dreams')


# ----------------------------------------------------------------------
# Comment Ownership Check
# ----------------------------------------------------------------------
def is_comment_owner(comment_id: int, user_id: int) -> bool:
    """Return True if the user is the owner of this specific comment."""
    if not user_id:
        return False
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT user_id FROM dream_comments WHERE id = %s", (comment_id,))
    row = cur.fetchone()
    return row is not None and row['user_id'] == user_id