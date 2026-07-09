# app/utils/account_moderation.py
# Account-level moderation: shadow bans, login locks, content visibility.

from datetime import datetime
from typing import Optional

from flask import g, has_request_context, session

SHADOW_BANNED_USERS_SUBQUERY = (
    "SELECT id FROM users WHERE COALESCE(is_shadow_banned, 0) = 1"
)


def refresh_viewer_context(user: dict | None = None) -> None:
    """Populate g.viewer_* for shadow-ban filtering (call from before_request)."""
    g.viewer_id = session.get('user_id')
    g.viewer_role = session.get('user_role')
    g.viewer_is_staff_admin = (g.viewer_role or '') in ('Staff', 'Admin', 'Owner')
    if user is not None:
        g.viewer_is_shadow_banned = bool(user.get('is_shadow_banned'))
    else:
        g.viewer_is_shadow_banned = bool(session.get('is_shadow_banned'))


def is_user_shadow_banned(user: dict | None) -> bool:
    return bool(user and user.get('is_shadow_banned'))


def is_account_login_locked(user: dict | None) -> bool:
    if not user:
        return False
    locked_until = user.get('login_locked_until')
    if not locked_until:
        return False
    if isinstance(locked_until, datetime):
        return locked_until > datetime.now()
    return False


def content_author_clause(
    author_column: str,
    *,
    viewer_id: Optional[int] = None,
    viewer_is_shadow_banned: Optional[bool] = None,
    admin_bypass: bool = True,
) -> tuple[str, list]:
    """
    SQL fragment hiding shadow-banned authors' content.
    Shadow-banned viewers only see their own rows (author_column = viewer_id).
    Staff/Admin/Owner bypass unless they are shadow-banned.
    """
    if has_request_context():
        if viewer_id is None:
            viewer_id = getattr(g, 'viewer_id', None) or session.get('user_id')
        if viewer_is_shadow_banned is None:
            viewer_is_shadow_banned = getattr(g, 'viewer_is_shadow_banned', False)
        if admin_bypass and getattr(g, 'viewer_is_staff_admin', False) and not viewer_is_shadow_banned:
            return '', []

    if viewer_is_shadow_banned and viewer_id:
        return f" AND ({author_column} = %s)", [viewer_id]

    if viewer_id:
        return (
            f" AND ({author_column} IS NULL OR {author_column} NOT IN ({SHADOW_BANNED_USERS_SUBQUERY})"
            f" OR {author_column} = %s)",
            [viewer_id],
        )
    return (
        f" AND ({author_column} IS NULL OR {author_column} NOT IN ({SHADOW_BANNED_USERS_SUBQUERY}))",
        [],
    )


def member_directory_clause(*, admin_view: bool = False) -> tuple[str, list]:
    """Hide shadow-banned members from directory unless admin is viewing."""
    if admin_view or (has_request_context() and getattr(g, 'viewer_is_staff_admin', False)):
        return '', []
    return f" AND id NOT IN ({SHADOW_BANNED_USERS_SUBQUERY})", []