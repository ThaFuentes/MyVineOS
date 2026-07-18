# app/routes/groups/utils.py
# Full path: MyVineChurch/app/routes/groups/utils.py
# File name: utils.py
# Brief, detailed purpose: Utility functions and constants for the Groups module.
# - KNOWN_PERMISSIONS dictionary (central source of truth for all permissions)
# - PERMISSION_CATEGORIES for the enterprise permission editor UI
# - is_global_manager() and is_group_leader() helpers
# - build_group_permissions_context / resolve_group_permissions for delegation-safe editing

from flask import session
import pymysql
from app.models.db import get_db


# ----------------------------------------------------------------------
# Known Permissions - FULL ENTERPRISE CATALOG
# Keys must match user_has_permission / @permission_required checks in routes.
# ----------------------------------------------------------------------
KNOWN_PERMISSIONS = {
    # --- Content: create & moderate ---
    'create_announcements': 'Create and edit own announcements',
    'moderate_announcements': 'Delete or edit ANY announcement (moderation)',
    'create_events': 'Create and edit own events',
    'moderate_events': 'Delete or edit ANY event (moderation)',
    'manage_events': 'Full events management (create, edit, moderate any event)',
    'manage_event_registration': 'Manage event registrations, fees, and ticketing',
    'upload_sermons': 'Upload and manage public sermon library content',
    'moderate_sermons': 'Delete or edit ANY sermon or sermon comment',
    'moderate_prayers': 'Delete or edit ANY prayer request or response',
    'create_dreams': 'Create and share dreams / visions',
    'moderate_dreams': 'Delete or edit ANY dream/vision or comment',
    'moderate_prophecies': 'Delete or edit ANY prophecy or comment',

    # --- Financial & operations ---
    'view_donations': 'View donation records and reports (read-only)',
    'manage_donations': 'Full donation management (record, edit, delete — sensitive)',
    'manage_bills': 'Access and manage recurring bills',
    'manage_accounting': 'Full accounting: chart of accounts, expenses, budgets, payroll views',
    'manage_inventory': 'Access and manage church inventory (items, stock, audits)',
    'manage_tickets': 'Full Ticket Manager access (create, assign, resolve any ticket)',
    'submit_tickets': 'Submit and view own support tickets',

    # --- People, family, attendance, volunteers ---
    'view_members': 'View the member directory',
    'manage_members': 'Edit member profiles, directory settings, and family links',
    'manage_family_links': 'Approve/reject family relationship requests (admin override)',
    'manage_users': 'Create, edit, approve, or delete user accounts and site roles',
    'manage_attendance': 'Attendance kiosk, sessions, reports, and child check-in station',
    'manage_volunteers': 'Volunteer teams, schedules, rotations, and staff scheduling tools',
    'manage_child_checkin': 'Child check-in station, rooms, labels, and live board (also covered by manage_attendance)',

    # --- Communications ---
    'send_emails': 'Communications hub: mass email/SMS, drips, and automation',

    # --- Ministry areas (pastoral, worship, AI) ---
    'access_pastoral': 'Access the private Pastoral Care area (sermons, vault, curriculum, podium, care)',
    'access_worship': 'View Worship Team songs, setlists, and plans',
    'manage_worship': 'Manage Worship Team: songs, setlists, plans, and team settings',
    'use_ai_insights': 'Use AI Insights reports and analysis tools',

    # --- Administration & governance ---
    'manage_groups': 'Create/edit/delete permission groups and assign members',
    'manage_settings': 'Access and change church settings (name, email, themes, modules, campuses)',
    'manage_help': 'Create and edit help categories and how-to guides',
    'manage_legal_notices': 'Create and edit legal notices, policies, and community guidelines',
    'manage_security': 'Security console: attacks, IP bans, unlock false positives',
    'view_audit_logs': 'View the Change Records / audit log',
}


# ----------------------------------------------------------------------
# Categories for the permission editor (order = display order)
# Each category lists permission keys (must exist in KNOWN_PERMISSIONS).
# Church Apps are injected dynamically at render time.
# ----------------------------------------------------------------------
PERMISSION_CATEGORIES = [
    {
        'id': 'content',
        'label': 'Content & Community',
        'description': 'Announcements, events, sermons, prayers, dreams, and prophecies.',
        'icon': 'content',
        'keys': [
            'create_announcements',
            'moderate_announcements',
            'create_events',
            'moderate_events',
            'manage_events',
            'manage_event_registration',
            'upload_sermons',
            'moderate_sermons',
            'moderate_prayers',
            'create_dreams',
            'moderate_dreams',
            'moderate_prophecies',
        ],
    },
    {
        'id': 'finance',
        'label': 'Finance & Operations',
        'description': 'Donations, bills, accounting, inventory, and support tickets.',
        'icon': 'finance',
        'keys': [
            'view_donations',
            'manage_donations',
            'manage_bills',
            'manage_accounting',
            'manage_inventory',
            'manage_tickets',
            'submit_tickets',
        ],
    },
    {
        'id': 'people',
        'label': 'People & Serving',
        'description': 'Members, users, attendance, volunteers, and child check-in.',
        'icon': 'people',
        'keys': [
            'view_members',
            'manage_members',
            'manage_family_links',
            'manage_users',
            'manage_attendance',
            'manage_volunteers',
            'manage_child_checkin',
        ],
    },
    {
        'id': 'communications',
        'label': 'Communications',
        'description': 'Mass email, SMS, drips, and automation.',
        'icon': 'comms',
        'keys': [
            'send_emails',
        ],
    },
    {
        'id': 'ministry',
        'label': 'Ministry Areas',
        'description': 'Pastoral care, worship team, and AI insights.',
        'icon': 'ministry',
        'keys': [
            'access_pastoral',
            'access_worship',
            'manage_worship',
            'use_ai_insights',
        ],
    },
    {
        'id': 'admin',
        'label': 'Administration & Security',
        'description': 'Groups, settings, help, legal notices, security console, audit log.',
        'icon': 'admin',
        'keys': [
            'manage_groups',
            'manage_settings',
            'manage_help',
            'manage_legal_notices',
            'manage_security',
            'view_audit_logs',
        ],
    },
    # Church Apps category is built dynamically in build_group_permissions_context
]


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
            'May grant permissions only up to what they already have — not above their own level.'
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
    """Only site Owner/Admin (full operators) may promote someone to Group Manager."""
    return is_global_manager()


# ----------------------------------------------------------------------
# Permission Helpers
# ----------------------------------------------------------------------
def is_global_manager():
    """
    Full site operators (Owner + Admin) who can edit any permission group matrix.
    Staff never auto-qualifies — Admins assign Staff capabilities via groups.
    """
    from app.utils.permissions import role_has_full_access
    return role_has_full_access(session.get('user_role'))


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
    try:
        cur.execute("SELECT slug, name FROM custom_modules ORDER BY name")
        for row in cur.fetchall():
            slug = row['slug'] if isinstance(row, dict) else row[0]
            name = row['name'] if isinstance(row, dict) else row[1]
            access_key, manage_key = app_permission_keys(slug)
            labels[access_key] = f'View Church App: {name}'
            labels[manage_key] = f'Manage Church App: {name}'
    except Exception:
        # Table may not exist yet on fresh installs
        pass
    return labels


def _permission_visible(key: str, grantable, locked: list, global_manager: bool) -> bool:
    """Whether this permission should appear in the editor for the acting user."""
    if global_manager or grantable is None:
        return True
    return key in grantable or key in locked


def build_permission_categories(
    known_permissions: dict,
    app_permission_keys: list,
    grantable,
    locked: list,
    global_manager: bool,
) -> list:
    """
    Build ordered category sections for the enterprise permission editor.
    Only includes keys that exist in known_permissions and are visible to the actor.
    """
    categories = []
    seen = set()

    for cat in PERMISSION_CATEGORIES:
        perm_keys = []
        for key in cat['keys']:
            if key not in known_permissions:
                continue
            if not _permission_visible(key, grantable, locked, global_manager):
                continue
            perm_keys.append(key)
            seen.add(key)
        if perm_keys:
            categories.append({
                'id': cat['id'],
                'label': cat['label'],
                'description': cat.get('description', ''),
                'icon': cat.get('icon', ''),
                # Use permission_keys (not "keys") — Jinja dicts expose .keys as a method
                'permission_keys': perm_keys,
            })

    # Church Apps (dynamic)
    app_keys = []
    for key in (app_permission_keys or []):
        if key not in known_permissions:
            continue
        if not _permission_visible(key, grantable, locked, global_manager):
            continue
        app_keys.append(key)
        seen.add(key)
    if app_keys:
        categories.append({
            'id': 'church_apps',
            'label': 'Church Apps',
            'description': 'Custom church apps (view and manage access per app).',
            'icon': 'apps',
            'permission_keys': app_keys,
        })

    # Any known keys not listed in categories (forward-compat)
    orphan_keys = []
    for key in known_permissions:
        if key in seen:
            continue
        # Skip app keys already handled
        if key.startswith('access_app_') or key.startswith('manage_app_'):
            if key not in app_keys:
                if _permission_visible(key, grantable, locked, global_manager):
                    orphan_keys.append(key)
            continue
        if _permission_visible(key, grantable, locked, global_manager):
            orphan_keys.append(key)
    if orphan_keys:
        categories.append({
            'id': 'other',
            'label': 'Other Permissions',
            'description': 'Additional permissions not grouped above.',
            'icon': 'other',
            'permission_keys': sorted(orphan_keys),
        })

    return categories


def build_group_permissions_context(cur, user_id: int, user_role: str, current_permissions: list) -> dict:
    """
    Template context for the enterprise permission editor with delegation rules.
    Group managers see only grantable permissions as editable; higher perms stay locked.
    """
    from app.utils.permissions import get_grantable_permissions, get_all_app_permission_keys, role_has_full_access

    # Admin/Owner may grant any key; Staff only keys they already hold
    global_manager = role_has_full_access(user_role)
    grantable = get_grantable_permissions(cur, user_id, user_role)
    current = [p for p in (current_permissions or []) if p]
    locked = [] if global_manager else [p for p in current if p not in grantable]

    known_permissions = extend_known_permissions_with_apps(cur)
    try:
        all_app_keys = get_all_app_permission_keys(cur)
    except Exception:
        all_app_keys = []

    app_keys = []
    for key in all_app_keys:
        if global_manager or key in grantable or key in locked:
            app_keys.append(key)

    # grantable_permissions: None means "all editable" for global managers in the template
    grantable_for_template = None if global_manager else grantable

    categories = build_permission_categories(
        known_permissions=known_permissions,
        app_permission_keys=app_keys,
        grantable=grantable_for_template,
        locked=locked,
        global_manager=global_manager,
    )

    # Counts for toolbar
    total_visible = sum(len(c['permission_keys']) for c in categories)
    selected_count = sum(1 for p in current if p in known_permissions)

    return {
        'known_permissions': known_permissions,
        'permission_categories': categories,
        'grantable_permissions': grantable_for_template,
        'locked_permissions': locked,
        'app_permission_keys': app_keys,
        'permissions_limited': not global_manager,
        'current_permissions': current,
        'permission_total_count': total_visible,
        'permission_selected_count': selected_count,
    }


def resolve_group_permissions(
    cur,
    user_id: int,
    user_role: str,
    existing_permissions: list,
    submitted_permissions: list,
) -> list:
    """Validate and sanitize submitted group permissions for the acting user."""
    from app.utils.permissions import get_grantable_permissions, sanitize_group_permissions, role_has_full_access

    global_manager = role_has_full_access(user_role)
    grantable = get_grantable_permissions(cur, user_id, user_role)
    return sanitize_group_permissions(
        existing_permissions,
        submitted_permissions,
        grantable,
        is_global_manager=global_manager,
    )
