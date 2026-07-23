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
    # --- Content (one key per action) ---
    'view_announcements': 'View announcements admin tools',
    'create_announcements': 'Create announcements',
    'edit_announcements': 'Edit announcements',
    'delete_announcements': 'Delete announcements',
    'moderate_announcements': 'Moderate any announcement',

    'view_events': 'View events admin tools',
    'create_events': 'Create events',
    'edit_events': 'Edit events',
    'delete_events': 'Delete events',
    'moderate_events': 'Moderate any event',
    'manage_events': 'Legacy full events (implies view/create/edit/delete/moderate)',
    'manage_event_registration': 'Manage event registration & fees',

    'view_sermons': 'View public sermon library admin',
    'upload_sermons': 'Upload sermons',
    'edit_sermons': 'Edit sermons',
    'delete_sermons': 'Delete sermons',
    'moderate_sermons': 'Moderate any sermon',

    'view_prayers': 'View prayers admin',
    'create_prayers': 'Submit prayers',
    'edit_prayers': 'Edit prayers',
    'delete_prayers': 'Delete prayers',
    'moderate_prayers': 'Moderate any prayer',

    'view_dreams': 'View dreams admin',
    'create_dreams': 'Post dreams / visions',
    'edit_dreams': 'Edit dreams',
    'delete_dreams': 'Delete dreams',
    'moderate_dreams': 'Moderate any dream',

    'view_prophecies': 'View prophecies admin',
    'create_prophecies': 'Post prophecies',
    'edit_prophecies': 'Edit prophecies',
    'delete_prophecies': 'Delete prophecies',
    'moderate_prophecies': 'Moderate any prophecy',

    # --- Finance ---
    'view_donations': 'View donations and reports',
    'create_donations': 'Record new donations',
    'edit_donations': 'Edit donations',
    'delete_donations': 'Delete donations',
    'manage_donations': 'Legacy full donations',

    'view_bills': 'View all bills',
    'create_bills': 'Add new bills',
    'edit_bills': 'Edit bills',
    'delete_bills': 'Delete bills',
    'manage_bills': 'Legacy full bills',

    'view_accounting': 'View accounting (read only)',
    'create_accounting': 'Create accounting records',
    'edit_accounting': 'Edit accounting records',
    'delete_accounting': 'Delete accounting records',
    'manage_accounting': 'Legacy full accounting',

    'view_inventory': 'View inventory',
    'create_inventory': 'Add inventory items',
    'edit_inventory': 'Edit inventory / stock',
    'delete_inventory': 'Delete inventory items',
    'manage_inventory': 'Legacy full inventory',

    'view_tickets': 'View ticket manager tickets',
    'create_tickets': 'Create tickets in ticket manager',
    'edit_tickets': 'Edit / assign / resolve tickets',
    'delete_tickets': 'Delete tickets',
    'manage_tickets': 'Legacy full ticket manager',
    'view_own_tickets': 'View own support tickets',
    'submit_tickets': 'Submit own support tickets',

    # --- People ---
    'view_members': 'View member directory',
    'create_members': 'Create member profiles',
    'edit_members': 'Edit member profiles',
    'delete_members': 'Delete member profiles',
    'manage_members': 'Legacy create/edit members',
    'manage_family_links': 'Manage family links',

    'view_users': 'View user accounts',
    'create_users': 'Create / approve user accounts',
    'edit_users': 'Edit user accounts / roles',
    'delete_users': 'Delete user accounts',
    'manage_users': 'Legacy full user management',

    'view_attendance': 'View attendance',
    'create_attendance': 'Create sessions / check-ins',
    'edit_attendance': 'Edit attendance',
    'delete_attendance': 'Delete attendance',
    'manage_attendance': 'Legacy full attendance',

    'view_child_checkin': 'View child check-in',
    'create_child_checkin': 'Check children in',
    'edit_child_checkin': 'Edit child check-in',
    'delete_child_checkin': 'Delete child check-in records',
    'manage_child_checkin': 'Legacy full child check-in',

    'view_volunteers': 'View volunteer tools',
    'create_volunteers': 'Create teams / schedules',
    'edit_volunteers': 'Edit volunteer schedules',
    'delete_volunteers': 'Delete volunteer data',
    'manage_volunteers': 'Legacy full volunteers',

    # --- Comms / ministry / admin ---
    'view_communications': 'View communications hub',
    'send_emails': 'Send mass email / SMS',
    'edit_communications': 'Edit campaigns / drips',
    'delete_communications': 'Delete campaigns',

    'access_pastoral': 'Open pastoral area',
    'create_pastoral': 'Create pastoral content',
    'edit_pastoral': 'Edit pastoral content',
    'delete_pastoral': 'Delete pastoral content',

    'access_worship': 'View worship tools',
    'create_worship': 'Create songs / setlists',
    'edit_worship': 'Edit worship content',
    'delete_worship': 'Delete worship content',
    'manage_worship': 'Legacy full worship manage',

    'view_ai_insights': 'View AI insights',
    'use_ai_insights': 'Run AI reports',

    'view_settings': 'View church settings',
    'manage_settings': 'Change church settings',

    'view_help': 'View help admin',
    'manage_help': 'Edit help content',
    'view_legal': 'View legal admin',
    'manage_legal_notices': 'Edit legal notices',

    'view_security': 'View security console',
    'manage_security': 'Ban / unlock / act in security',

    'view_audit_logs': 'View the audit log',
}


# ----------------------------------------------------------------------
# Categories for the permission editor (order = display order)
# Each category lists permission keys (must exist in KNOWN_PERMISSIONS).
# Church Apps are injected dynamically at render time.
# ----------------------------------------------------------------------
# Category lists are derived from KNOWN_PERMISSIONS so new fine keys always appear.
def _keys_matching(*prefixes: str) -> list[str]:
    out = []
    for k in KNOWN_PERMISSIONS:
        if any(k == p or k.startswith(p) for p in prefixes):
            out.append(k)
    return out


PERMISSION_CATEGORIES = [
    {
        'id': 'content',
        'label': 'Content & Community',
        'description': 'Announcements, events, sermons, prayers, dreams, and prophecies.',
        'icon': 'content',
        'keys': sorted(k for k in KNOWN_PERMISSIONS if any(
            x in k for x in (
                'announcement', 'event', 'sermon', 'prayer', 'dream', 'prophec',
            )
        )),
    },
    {
        'id': 'finance',
        'label': 'Finance & Operations',
        'description': 'Donations, bills, accounting, inventory, and support tickets.',
        'icon': 'finance',
        'keys': sorted(k for k in KNOWN_PERMISSIONS if any(
            x in k for x in (
                'donation', 'bill', 'accounting', 'inventory', 'ticket',
            )
        )),
    },
    {
        'id': 'people',
        'label': 'People & Serving',
        'description': 'Members, users, attendance, volunteers, and child check-in.',
        'icon': 'people',
        'keys': sorted(k for k in KNOWN_PERMISSIONS if any(
            x in k for x in (
                'member', 'user', 'attendance', 'volunteer', 'child_checkin', 'family',
            )
        ) and 'donation' not in k),
    },
    {
        'id': 'communications',
        'label': 'Communications',
        'description': 'Mass email, SMS, drips, and automation.',
        'icon': 'comms',
        'keys': sorted(k for k in KNOWN_PERMISSIONS if 'email' in k or 'communication' in k),
    },
    {
        'id': 'ministry',
        'label': 'Ministry Areas',
        'description': 'Pastoral care, worship team, and AI insights.',
        'icon': 'ministry',
        'keys': sorted(k for k in KNOWN_PERMISSIONS if any(
            x in k for x in ('pastoral', 'worship', 'ai_insight')
        )),
    },
    {
        'id': 'admin',
        'label': 'Administration & Security',
        'description': 'Settings, help, legal notices, security console, audit log.',
        'icon': 'admin',
        'keys': sorted(k for k in KNOWN_PERMISSIONS if any(
            x in k for x in ('setting', 'help', 'legal', 'security', 'audit')
        )),
    },
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

    try:
        from app.utils.permission_matrix import matrix_from_keys, human_summary
        area_matrix_rows = matrix_from_keys(current)
        area_matrix_summary = human_summary(current)
    except Exception:
        area_matrix_rows = []
        area_matrix_summary = []

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
        'area_matrix_rows': area_matrix_rows,
        'area_matrix_summary': area_matrix_summary,
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
