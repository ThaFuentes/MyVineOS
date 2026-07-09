# app/routes/members/utils.py
# Full path: MyVineChurch/app/routes/members/utils.py
# File name: utils.py
# Brief, detailed purpose: Utility functions and constants for the Members module.
# • REQUIRED_ROLES constant
# • current_user_id() helper for logging and ownership
# • Role permission helpers (get_allowed_roles)
# • Temporary password generator (used when adding new members)
# • 100% matches the original members.py helpers and logic.

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
    return user_has_permission('manage_users')


def can_moderate_account(target, actor_id, actor_role) -> bool:
    """Account security tools require manage_users plus role ceiling."""
    if not target or target['id'] == actor_id:
        return False
    if not can_manage_users():
        return False
    if target['role'] == 'Owner':
        return actor_role == 'Owner'
    if target['role'] == 'Admin':
        return actor_role == 'Owner'
    if target['role'] == 'Staff':
        return actor_role in ('Staff', 'Admin', 'Owner')
    return True


def get_assignable_groups(cur, user_id, user_role):
    """Groups the current user may assign on the member form."""
    cur.execute("SELECT id, name, description, permissions FROM groups ORDER BY name")
    all_groups = cur.fetchall()

    if user_role in ('Staff', 'Admin', 'Owner') or can_manage_users():
        available = []
        for g in all_groups:
            try:
                perms = json.loads(g['permissions'] or '[]')
            except (TypeError, json.JSONDecodeError):
                perms = []
            if (
                user_role == 'Owner'
                or user_role in perms
                or (not perms and user_role in ('Staff', 'Admin', 'Owner'))
                or can_manage_users()
            ):
                available.append(g)
        return available

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
    """Return list of roles the current user is allowed to assign to new members."""
    allowed = ['Member']
    if current_role in ['Staff', 'Admin', 'Owner']:
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