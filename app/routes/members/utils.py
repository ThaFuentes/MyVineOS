# app/routes/members/utils.py
# Full path: MyVineChurch/app/routes/members/utils.py
# File name: utils.py
# Brief, detailed purpose: Utility functions and constants for the Members module.
# - REQUIRED_ROLES constant
# - current_user_id() helper for logging and ownership
# - Role permission helpers (get_allowed_roles)
# - Temporary password generator (used when adding new members)
# - 100% matches the original members.py helpers and logic.

from flask import session
import json
import random
import string

from app.utils.permissions import user_has_permission


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
REQUIRED_ROLES = ['Staff', 'Admin', 'Owner']

MEMBERS_VIEW_PERMISSIONS = ('view_members', 'manage_members', 'manage_users')
MEMBERS_EDIT_PERMISSIONS = ('manage_members', 'manage_users')


# ----------------------------------------------------------------------
# User Helpers
# ----------------------------------------------------------------------
def current_user_id():
    """Return current logged-in user ID for logging and ownership."""
    return session.get('user_id')


# ----------------------------------------------------------------------
# Group Permission Helpers
# ----------------------------------------------------------------------
def can_view_members() -> bool:
    return any(user_has_permission(key) for key in MEMBERS_VIEW_PERMISSIONS)


def can_manage_members() -> bool:
    return any(user_has_permission(key) for key in MEMBERS_EDIT_PERMISSIONS)


def can_manage_users() -> bool:
    """Owner always; Admin via full access; Staff only with manage_users group key."""
    if session.get('user_role') == 'Owner':
        return True
    return user_has_permission('manage_users')


def can_delete_member(target, actor_id, actor_role) -> tuple[bool, str]:
    """
    Who may permanently delete a user account.

    - Owner: full reign (may delete anyone except self and the last Owner).
    - Admin: may delete Member/Staff/pending/banned, but never Admin or Owner.
    - Others: no (even with manage_users from a group).
    """
    if not target:
        return False, 'Member not found.'

    role = (actor_role or session.get('user_role') or '').strip()
    target_role = (target.get('role') or 'Member').strip()
    target_id = target.get('id')

    if not can_manage_users() and role not in ('Owner', 'Admin'):
        return False, 'You do not have permission to delete accounts.'

    if target_id == actor_id:
        return False, 'You cannot delete your own account.'

    if role == 'Owner':
        if target_role == 'Owner':
            # Never remove the last Owner
            try:
                from app.models.db import get_db
                import pymysql
                db = get_db()
                cur = db.cursor(pymysql.cursors.DictCursor)
                cur.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'Owner'")
                n = int((cur.fetchone() or {}).get('n') or 0)
                if n <= 1:
                    return False, 'Cannot delete the last Owner account.'
            except Exception:
                return False, 'Could not verify Owner count; delete blocked for safety.'
        return True, ''

    if role == 'Admin':
        if target_role in ('Admin', 'Owner'):
            return False, 'Admins cannot delete Admin or Owner accounts. Only the Owner can.'
        return True, ''

    return False, 'Only Owner or Admin can delete accounts.'


def can_moderate_account(target, actor_id, actor_role) -> bool:
    """Account security tools require manage_users plus role ceiling.
    Owner: full reign over others. Admin: not Admin/Owner targets.
    """
    if not target or target['id'] == actor_id:
        return False
    if (actor_role or session.get('user_role')) == 'Owner':
        return True
    if not can_manage_users():
        return False
    if target['role'] == 'Owner':
        return False
    if target['role'] == 'Admin':
        return actor_role == 'Owner'
    # Staff targets: Admin/Owner or anyone with manage_users (not bare Staff role)
    if target['role'] == 'Staff':
        return actor_role in ('Admin', 'Owner') or can_manage_users()
    # Members etc.: need manage_users (Admin/Owner pass via full access)
    return can_manage_users()


def get_assignable_groups(cur, user_id, user_role):
    """Groups the current user may assign on the member form."""
    cur.execute("SELECT id, name, description, permissions FROM groups ORDER BY name")
    all_groups = cur.fetchall()

    # Admin/Owner or manage_users / manage_groups: full roster assignment
    if user_role in ('Admin', 'Owner') or can_manage_users() or user_has_permission('manage_groups'):
        return list(all_groups)

    if can_manage_members():
        from app.routes.groups.gathering_place import can_manage_group_members
        return [
            g for g in all_groups
            if can_manage_group_members(g['id'], user_id, user_role)
        ]

    return []


# ----------------------------------------------------------------------
# Role Permission Helpers
# ----------------------------------------------------------------------
def get_allowed_roles(current_role):
    """Return list of roles the current user is allowed to assign to new members.
    Promoting to Staff requires manage_users (or Admin/Owner). Bare Staff role alone is not enough.
    """
    allowed = ['Member']
    if current_role in ['Admin', 'Owner'] or can_manage_users():
        allowed.append('Staff')
    if current_role in ['Admin', 'Owner']:
        allowed.append('Admin')
    if current_role == 'Owner':
        allowed.append('Owner')
    return allowed


# ----------------------------------------------------------------------
# Password Helpers
# ----------------------------------------------------------------------
def generate_temporary_password(length=12):
    """Generate a secure temporary password for new members."""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choices(characters, k=length))


# ----------------------------------------------------------------------
# Future Growth Placeholders
# ----------------------------------------------------------------------
# These can be expanded when you add more member features (export, bulk import, etc.)
def get_default_member_role():
    """Default role for new members."""
    return 'Member'