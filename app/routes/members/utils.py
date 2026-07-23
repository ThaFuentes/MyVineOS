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

MEMBERS_VIEW_PERMISSIONS = (
    'view_members', 'create_members', 'edit_members', 'delete_members',
    'manage_members', 'manage_users', 'view_users', 'create_users', 'edit_users', 'delete_users',
)
MEMBERS_EDIT_PERMISSIONS = (
    'create_members', 'edit_members', 'delete_members', 'manage_members',
    'create_users', 'edit_users', 'delete_users', 'manage_users',
)


# ----------------------------------------------------------------------
# User Helpers
# ----------------------------------------------------------------------
def current_user_id():
    """Return current logged-in user ID for logging and ownership."""
    return session.get('user_id')


# ----------------------------------------------------------------------
# Role hierarchy (strict: higher rank only manages people BELOW them)
# ----------------------------------------------------------------------
# Owner > Admin > Staff > Member > pending/banned
ROLE_RANK = {
    'owner': 40,
    'admin': 30,
    'staff': 20,
    'member': 10,
    'pending': 0,
    'banned': 0,
}


def role_rank(role) -> int:
    """Numeric rank for hierarchy checks. Unknown roles rank as Member."""
    key = (role or 'Member').strip().lower()
    return int(ROLE_RANK.get(key, ROLE_RANK['member']))


def normalize_role_name(role) -> str:
    raw = (role or 'Member').strip()
    mapping = {
        'owner': 'Owner',
        'admin': 'Admin',
        'staff': 'Staff',
        'member': 'Member',
        'pending': 'pending',
        'banned': 'banned',
    }
    return mapping.get(raw.lower(), raw)


def can_outrank(actor_role, target_role) -> bool:
    """True only when actor is strictly above target (never equals, never below)."""
    return role_rank(actor_role) > role_rank(target_role)


def can_manage_target_user(
    target,
    actor_id=None,
    actor_role=None,
    *,
    require_manage_users: bool = False,
    allow_self: bool = False,
) -> tuple[bool, str]:
    """
    Hard rule: tools/permissions never override rank.

    Staff with "edit users" / manage_users still cannot touch Admin or Owner.
    Admin cannot touch Admin peers or Owner.
    Only a higher rank may edit, demote, ban, or set tools for a person.

    Owner may manage anyone else (including other Owners for profile/tools).
    """
    if not target:
        return False, 'Member not found.'

    role = (actor_role if actor_role is not None else session.get('user_role') or '').strip()
    actor = actor_id if actor_id is not None else session.get('user_id')
    target_role = (target.get('role') or 'Member').strip()
    target_id = target.get('id')

    if not allow_self and target_id is not None and actor is not None and int(target_id) == int(actor):
        return False, 'You cannot manage your own account this way. Use Profile for your own details.'

    if require_manage_users and not can_manage_users() and role != 'Owner':
        return False, 'You do not have permission to manage user accounts.'

    # Strict hierarchy — equal rank peers have no power over each other
    if not can_outrank(role, target_role):
        return False, (
            f'Your role ({role or "none"}) cannot manage a {target_role}. '
            'Only someone above them in rank can change their account, role, or tools.'
        )
    return True, ''


# ----------------------------------------------------------------------
# Group Permission Helpers
# ----------------------------------------------------------------------
def can_view_members() -> bool:
    return any(user_has_permission(key) for key in MEMBERS_VIEW_PERMISSIONS)


def can_manage_members() -> bool:
    return any(user_has_permission(key) for key in MEMBERS_EDIT_PERMISSIONS) or user_has_permission('edit_members') or user_has_permission('create_members')


def can_manage_users() -> bool:
    """Owner always; others need manage_users permission (still subject to rank)."""
    if session.get('user_role') == 'Owner':
        return True
    return user_has_permission('manage_users')


def can_delete_member(target, actor_id, actor_role) -> tuple[bool, str]:
    """
    Who may permanently delete a user account.

    Hierarchy first (must outrank target), then:
    - Owner: may delete anyone except self and the last Owner.
    - Admin: may delete people below them (Member/Staff/pending), never peers/above.
    - Staff / others: no account deletion (even with manage_users).
    """
    if not target:
        return False, 'Member not found.'

    role = (actor_role or session.get('user_role') or '').strip()
    target_role = (target.get('role') or 'Member').strip()
    target_id = target.get('id')

    if target_id == actor_id:
        return False, 'You cannot delete your own account.'

    ok, reason = can_manage_target_user(
        target, actor_id=actor_id, actor_role=role, require_manage_users=False,
    )
    if not ok:
        return False, reason

    if role == 'Owner':
        if target_role == 'Owner':
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
        # Already outranks; still no deleting other Admins/Owners (outrank blocks that)
        return True, ''

    return False, 'Only Owner or Admin can delete accounts.'


def can_moderate_account(target, actor_id, actor_role) -> bool:
    """Ban / unlock / shadow tools: manage_users + must strictly outrank the target."""
    if not target:
        return False
    ok, _ = can_manage_target_user(
        target,
        actor_id=actor_id,
        actor_role=actor_role,
        require_manage_users=True,
    )
    return ok


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
    """
    Roles the actor may assign — only ranks strictly BELOW the actor.
    Staff → Member only (cannot mint peer Staff or touch Admin).
    Admin → Member, Staff (cannot mint Admin/Owner).
    Owner → Member, Staff, Admin, Owner.
    """
    allowed = []
    actor_r = role_rank(current_role)
    for name in ('Member', 'Staff', 'Admin', 'Owner'):
        if role_rank(name) < actor_r:
            allowed.append(name)
    # Owner may also assign Owner (still cannot demote last Owner elsewhere)
    if (current_role or '').strip() == 'Owner':
        if 'Owner' not in allowed:
            allowed.append('Owner')
    # Always allow Member if actor is above Member (Staff+)
    if actor_r > role_rank('Member') and 'Member' not in allowed:
        allowed.insert(0, 'Member')
    return allowed or ['Member']


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