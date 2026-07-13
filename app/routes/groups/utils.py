# app/routes/groups/utils.py
# Full path: MyVineChurch/app/routes/groups/utils.py
# File name: utils.py
# Brief, detailed purpose: Utility functions and constants for the Groups module.
# - KNOWN_PERMISSIONS dictionary (central source of truth for all permissions in the application)
# - is_global_manager() and is_group_leader() helpers
# - Clean, reusable, and consistent with the rest of the app.
# - Designed for easy future growth (add new permission helpers, group validation, etc.)

from flask import session
import pymysql
from app.models.db import get_db


# ----------------------------------------------------------------------
# Known Permissions - FULLY EXPANDED
# ----------------------------------------------------------------------
KNOWN_PERMISSIONS = {
    # Core Content Creation/Moderation
    'create_announcements': 'Create and edit own announcements',
    'moderate_announcements': 'Delete or edit ANY announcement (moderation)',
    'create_events': 'Create and edit own events',
    'moderate_events': 'Delete or edit ANY event (moderation)',
    'manage_event_registration': 'Manage event registrations, fees, and ticketing',
    'upload_sermons': 'Upload and manage sermons',
    'moderate_sermons': 'Delete or edit ANY sermon or comment',
    'moderate_prayers': 'Delete or edit ANY prayer request or response',
    'moderate_dreams': 'Delete or edit ANY dream/vision or comment',
    'moderate_prophecies': 'Delete or edit ANY prophecy or comment',

    # Financial & Operational
    'view_donations': 'View donation records and reports (no editing)',
    'manage_donations': 'Full donation management (record, edit, delete - sensitive)',
    'manage_bills': 'Access and manage Recurring Bills (/bills/)',
    'manage_inventory': 'Access and manage church inventory (items, stock, audits)',
    'manage_tickets': 'Full Ticket Manager access (/tickets/manage - create, assign, resolve any ticket)',
    'submit_tickets': 'Submit and view own support/event tickets (/tickets/)',

    # Member & Attendance Management
    'view_members': 'View the member directory',
    'manage_members': 'Edit member profiles, directory settings, and family links',
    'manage_family_links': 'Approve/reject family relationship requests (admin override)',
    'manage_attendance': 'Access Attendance Kiosk and full attendance records',

    # User & System Administration
    'manage_users': 'Create, edit, approve, or delete user accounts and roles',
    'manage_groups': 'Create/edit/delete permission groups and assign members',
    'send_emails': 'Use the email tool to send messages to members',
    'manage_settings': 'Access and change church settings (name, email config, themes, etc.)',
    'view_audit_logs': 'View the Change Records / audit log',
    'access_pastoral': 'Access to the private Pastoral Care section',
    'manage_legal_notices': 'Create and edit legal notices, policies, and community guidelines',
    'manage_help': 'Create and edit help categories and how-to guides',
    'manage_security': 'Access Security console (attacks, IP bans, unlock false positives)',

    # Add even more here as new features are built
}


# ----------------------------------------------------------------------
# In-group roles (stored as role_in_group on user_groups)
# ----------------------------------------------------------------------
GROUP_ROLES = {
    'member': {
        'label': 'Member',
        'short': 'Permissions only',
        'description': 'Receives this group\'s site permissions. Cannot add/remove members or edit group settings.',
    },
    'leader': {
        'label': 'Group Manager',
        'short': 'Manage this group',
        'description': (
            'Can add/remove members and edit this group\'s settings. '
            'May grant permissions only up to what they already have - not above their own level.'
        ),
    },
}

VALID_GROUP_ROLES = frozenset(GROUP_ROLES.keys())


def normalize_group_role(role: str, default: str = 'member') -> str:
    """Normalize UI / legacy values to member or leader."""
    value = (role or default).strip().lower()
    if value in VALID_GROUP_ROLES:
        return value
    if value in ('group manager', 'manager', 'admin', 'group_admin'):
        return 'leader'
    return default


def group_role_label(role: str) -> str:
    return GROUP_ROLES.get(normalize_group_role(role), {}).get('label', (role or 'Member').title())


def can_assign_group_manager_role() -> bool:
    """Only site Owner, Admin, or Staff may promote someone to Group Manager."""
    return is_global_manager()


# ----------------------------------------------------------------------
# Permission Helpers
# ----------------------------------------------------------------------
def is_global_manager():
    """True if user has global management rights (Staff/Admin/Owner)."""
    return session.get('user_role') in ['Staff', 'Admin', 'Owner']


def is_group_leader(group_id: int, user_id: int) -> bool:
    """True if user has role_in_group = 'leader' in the specific group."""
    if not user_id:
        return False
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT 1 FROM user_groups
        WHERE group_id = %s AND user_id = %s AND role_in_group = 'leader'
    """, (group_id, user_id))
    return cur.fetchone() is not None


def extend_known_permissions_with_apps(cur, base=None) -> dict:
    """Merge Church App permission keys into the label map for group forms."""
    from app.routes.custom_modules.queries import app_permission_keys

    labels = dict(base or KNOWN_PERMISSIONS)
    cur.execute("SELECT slug, name FROM custom_modules ORDER BY name")
    for row in cur.fetchall():
        slug = row['slug'] if isinstance(row, dict) else row[0]
        name = row['name'] if isinstance(row, dict) else row[1]
        access_key, manage_key = app_permission_keys(slug)
        labels[access_key] = f'View Church App: {name}'
        labels[manage_key] = f'Manage Church App: {name}'
    return labels


def build_group_permissions_context(cur, user_id: int, user_role: str, current_permissions: list) -> dict:
    """
    Template context for permission checkboxes with delegation rules.
    Group managers see only grantable permissions as editable; higher perms stay locked.
    """
    from app.utils.permissions import get_grantable_permissions, get_all_app_permission_keys

    global_manager = (user_role or '') in ['Staff', 'Admin', 'Owner']
    grantable = get_grantable_permissions(cur, user_id, user_role)
    current = [p for p in (current_permissions or []) if p]
    locked = [] if global_manager else [p for p in current if p not in grantable]

    known_permissions = extend_known_permissions_with_apps(cur)
    app_keys = []
    for key in get_all_app_permission_keys(cur):
        if global_manager or key in grantable or key in locked:
            app_keys.append(key)

    return {
        'known_permissions': known_permissions,
        'grantable_permissions': grantable,
        'locked_permissions': locked,
        'app_permission_keys': app_keys,
        'permissions_limited': not global_manager,
    }


def resolve_group_permissions(
    cur,
    user_id: int,
    user_role: str,
    existing_permissions: list,
    submitted_permissions: list,
) -> list:
    """Validate and sanitize submitted group permissions for the acting user."""
    from app.utils.permissions import get_grantable_permissions, sanitize_group_permissions

    global_manager = (user_role or '') in ['Staff', 'Admin', 'Owner']
    grantable = get_grantable_permissions(cur, user_id, user_role)
    return sanitize_group_permissions(
        existing_permissions,
        submitted_permissions,
        grantable,
        is_global_manager=global_manager,
    )