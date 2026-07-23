# app/utils/permission_matrix.py
# Human-friendly area matrix for permissions UI.
# Each area maps simple levels (off / view / manage) onto existing KNOWN_PERMISSIONS keys.
# Phase 1: no new capability keys — only presentation + form glue.

from __future__ import annotations

# Levels used in UI forms
LEVEL_OFF = 'off'
LEVEL_VIEW = 'view'
LEVEL_MANAGE = 'manage'
VALID_LEVELS = frozenset({LEVEL_OFF, LEVEL_VIEW, LEVEL_MANAGE})

# Area catalog for matrix UI (order = display order).
# view_keys: granted when level is view or manage
# manage_keys: granted only when level is manage (in addition to view_keys)
AREA_MATRIX = [
    {
        'id': 'tickets',
        'label': 'Support tickets',
        'description': 'Submit help tickets or manage the full ticket desk.',
        'icon': 'fa-ticket',
        'view_keys': ['submit_tickets'],
        'manage_keys': ['manage_tickets'],
        'preview': {
            'nav': ['My Tickets', 'Ticket Manager'],
            'dash': ['Tickets tile'],
        },
    },
    {
        'id': 'donations',
        'label': 'Donations',
        'description': 'See giving records or fully manage donations.',
        'icon': 'fa-hand-holding-dollar',
        'view_keys': ['view_donations'],
        'manage_keys': ['manage_donations'],
        'preview': {
            'nav': ['Donations'],
            'dash': ['Donations tile'],
        },
    },
    {
        'id': 'bills',
        'label': 'Bills',
        'description': 'Church bills and recurring payables.',
        'icon': 'fa-file-invoice-dollar',
        'view_keys': ['manage_bills'],
        'manage_keys': ['manage_bills'],
        'preview': {
            'nav': ['Bills'],
            'dash': ['Bills tile'],
        },
    },
    {
        'id': 'accounting',
        'label': 'Accounting',
        'description': 'Chart of accounts, expenses, budgets, payroll views.',
        'icon': 'fa-calculator',
        'view_keys': ['manage_accounting'],
        'manage_keys': ['manage_accounting'],
        'preview': {
            'nav': ['Accounting'],
            'dash': ['Accounting tile'],
        },
    },
    {
        'id': 'inventory',
        'label': 'Inventory',
        'description': 'Items, stock, audits, barcode tools.',
        'icon': 'fa-boxes-stacked',
        'view_keys': ['manage_inventory'],
        'manage_keys': ['manage_inventory'],
        'preview': {
            'nav': ['Inventory'],
            'dash': ['Inventory tile'],
        },
    },
    {
        'id': 'members',
        'label': 'Members & directory',
        'description': 'View the directory or edit profiles and family links.',
        'icon': 'fa-address-book',
        'view_keys': ['view_members'],
        'manage_keys': ['manage_members', 'manage_family_links'],
        'preview': {
            'nav': ['Members'],
            'dash': ['Members tile'],
        },
    },
    {
        'id': 'users',
        'label': 'User accounts',
        'description': 'Create/approve accounts and change site roles (powerful).',
        'icon': 'fa-user-gear',
        'view_keys': ['manage_users'],
        'manage_keys': ['manage_users'],
        'preview': {
            'nav': ['Members (account tools)'],
            'dash': [],
        },
    },
    {
        'id': 'attendance',
        'label': 'Attendance',
        'description': 'Kiosk, sessions, reports, and related check-in tools.',
        'icon': 'fa-clipboard-user',
        'view_keys': ['manage_attendance'],
        'manage_keys': ['manage_attendance'],
        'preview': {
            'nav': ['Attendance'],
            'dash': ['Attendance tile'],
        },
    },
    {
        'id': 'child_checkin',
        'label': 'Child check-in',
        'description': 'Child check-in station, rooms, labels, live board.',
        'icon': 'fa-children',
        'view_keys': ['manage_child_checkin', 'manage_attendance'],
        'manage_keys': ['manage_child_checkin', 'manage_attendance'],
        'preview': {
            'nav': ['Child Check-In'],
            'dash': [],
        },
    },
    {
        'id': 'volunteers',
        'label': 'Volunteers',
        'description': 'Teams, schedules, rotations, serving tools.',
        'icon': 'fa-hands-helping',
        'view_keys': ['manage_volunteers'],
        'manage_keys': ['manage_volunteers'],
        'preview': {
            'nav': ['Volunteers'],
            'dash': ['Volunteers tile'],
        },
    },
    {
        'id': 'events',
        'label': 'Events',
        'description': 'Create events or moderate all church events.',
        'icon': 'fa-calendar-days',
        'view_keys': ['create_events'],
        'manage_keys': ['manage_events', 'moderate_events', 'manage_event_registration'],
        'preview': {
            'nav': ['Events'],
            'dash': ['Events tile'],
        },
    },
    {
        'id': 'announcements',
        'label': 'Announcements',
        'description': 'Post announcements or moderate any announcement.',
        'icon': 'fa-bullhorn',
        'view_keys': ['create_announcements'],
        'manage_keys': ['moderate_announcements'],
        'preview': {
            'nav': ['Announcements'],
            'dash': [],
        },
    },
    {
        'id': 'sermons_public',
        'label': 'Public sermon library',
        'description': 'Upload public sermons or moderate the library.',
        'icon': 'fa-book-bible',
        'view_keys': ['upload_sermons'],
        'manage_keys': ['moderate_sermons'],
        'preview': {
            'nav': ['Sermons (public library)'],
            'dash': [],
        },
    },
    {
        'id': 'community_mod',
        'label': 'Community moderation',
        'description': 'Moderate prayers, dreams, and prophecies.',
        'icon': 'fa-comments',
        'view_keys': ['create_dreams'],
        'manage_keys': ['moderate_prayers', 'moderate_dreams', 'moderate_prophecies'],
        'preview': {
            'nav': ['Prayers', 'Dreams', 'Prophecies'],
            'dash': [],
        },
    },
    {
        'id': 'pastoral',
        'label': 'Pastoral care',
        'description': 'Private pastoral area: sermons, vault, curriculum, care, podium.',
        'icon': 'fa-hands-praying',
        'view_keys': ['access_pastoral'],
        'manage_keys': ['access_pastoral'],
        'preview': {
            'nav': ['Pastoral'],
            'dash': ['Pastoral tile'],
        },
    },
    {
        'id': 'worship',
        'label': 'Worship team',
        'description': 'View worship tools or fully manage songs and setlists.',
        'icon': 'fa-music',
        'view_keys': ['access_worship'],
        'manage_keys': ['manage_worship'],
        'preview': {
            'nav': ['Worship Team'],
            'dash': ['Worship tile'],
        },
    },
    {
        'id': 'communications',
        'label': 'Communications',
        'description': 'Mass email/SMS, drips, and automation.',
        'icon': 'fa-envelope',
        'view_keys': ['send_emails'],
        'manage_keys': ['send_emails'],
        'preview': {
            'nav': ['Communications'],
            'dash': [],
        },
    },
    {
        'id': 'ai_insights',
        'label': 'AI insights',
        'description': 'AI reports and analysis tools.',
        'icon': 'fa-robot',
        'view_keys': ['use_ai_insights'],
        'manage_keys': ['use_ai_insights'],
        'preview': {
            'nav': ['AI Insights'],
            'dash': [],
        },
    },
    {
        'id': 'groups_admin',
        'label': 'Permission groups',
        'description': 'Create and edit permission groups and memberships.',
        'icon': 'fa-people-group',
        'view_keys': ['manage_groups'],
        'manage_keys': ['manage_groups'],
        'preview': {
            'nav': ['Permission Groups'],
            'dash': [],
        },
    },
    {
        'id': 'settings',
        'label': 'Church settings',
        'description': 'Name, email, themes, modules, campuses.',
        'icon': 'fa-gear',
        'view_keys': ['manage_settings'],
        'manage_keys': ['manage_settings'],
        'preview': {
            'nav': ['Settings'],
            'dash': [],
        },
    },
    {
        'id': 'security',
        'label': 'Security console',
        'description': 'Attacks, IP bans, unlock false positives.',
        'icon': 'fa-shield-halved',
        'view_keys': ['manage_security'],
        'manage_keys': ['manage_security'],
        'preview': {
            'nav': ['Security'],
            'dash': [],
        },
    },
    {
        'id': 'audit',
        'label': 'Audit log',
        'description': 'View change records / audit trail.',
        'icon': 'fa-clipboard-list',
        'view_keys': ['view_audit_logs'],
        'manage_keys': ['view_audit_logs'],
        'preview': {
            'nav': ['Change Records'],
            'dash': [],
        },
    },
    {
        'id': 'help_legal',
        'label': 'Help & legal content',
        'description': 'Edit help guides and legal notices.',
        'icon': 'fa-circle-question',
        'view_keys': ['manage_help'],
        'manage_keys': ['manage_help', 'manage_legal_notices'],
        'preview': {
            'nav': ['Help (edit)', 'Legal'],
            'dash': [],
        },
    },
]


def keys_for_level(area: dict, level: str) -> list[str]:
    """Expand a UI level into concrete permission keys for one area."""
    level = (level or LEVEL_OFF).lower()
    if level not in VALID_LEVELS or level == LEVEL_OFF:
        return []
    view = list(area.get('view_keys') or [])
    manage = list(area.get('manage_keys') or [])
    if level == LEVEL_VIEW:
        return list(dict.fromkeys(view))
    # manage includes view
    return list(dict.fromkeys(view + manage))


def level_for_keys(area: dict, granted: set[str] | list[str]) -> str:
    """Infer UI level from a set of granted keys for one area."""
    granted_set = set(granted or [])
    manage = set(area.get('manage_keys') or [])
    view = set(area.get('view_keys') or [])
    if manage and manage.issubset(granted_set):
        return LEVEL_MANAGE
    # If manage keys equal view keys, any hit is manage
    if manage and manage == view and manage.intersection(granted_set):
        return LEVEL_MANAGE
    if view and view.intersection(granted_set):
        # partial manage (some manage keys) → show manage if any manage key present
        if manage.intersection(granted_set):
            return LEVEL_MANAGE
        return LEVEL_VIEW
    if manage.intersection(granted_set):
        return LEVEL_MANAGE
    return LEVEL_OFF


def matrix_from_keys(granted: set[str] | list[str]) -> list[dict]:
    """Return AREA_MATRIX rows with current level for display."""
    g = set(granted or [])
    rows = []
    for area in AREA_MATRIX:
        level = level_for_keys(area, g)
        rows.append({
            **area,
            'level': level,
            'active_keys': keys_for_level(area, level),
        })
    return rows


def keys_from_form_levels(form, *, include_raw_checkboxes: bool = False) -> list[str]:
    """
    Read area_level_<id> selects from a Flask request.form (or dict-like).
    When any area_level_* field is present, matrix is authoritative (avoids
    advanced checkboxes re-adding keys after you set an area to Off).
    Set include_raw_checkboxes=True only when there is no matrix UI.
    """
    keys: list[str] = []
    get = form.get if hasattr(form, 'get') else (lambda k, d=None: form.get(k, d) if isinstance(form, dict) else d)
    # Detect multi-dict keys (ImmutableMultiDict)
    form_keys = []
    try:
        form_keys = list(form.keys())
    except Exception:
        form_keys = []
    has_matrix = any(str(k).startswith('area_level_') for k in form_keys)
    for area in AREA_MATRIX:
        level = get(f"area_level_{area['id']}", LEVEL_OFF) or LEVEL_OFF
        keys.extend(keys_for_level(area, level))
    if (not has_matrix or include_raw_checkboxes) and hasattr(form, 'getlist'):
        raw = form.getlist('permissions') or []
        keys.extend([p for p in raw if p])
    return list(dict.fromkeys(keys))

def human_summary(granted: set[str] | list[str]) -> list[str]:
    """Plain-language bullets for what a key set can do."""
    g = set(granted or [])
    lines = []
    for area in AREA_MATRIX:
        level = level_for_keys(area, g)
        if level == LEVEL_OFF:
            continue
        if level == LEVEL_VIEW:
            lines.append(f"{area['label']}: view / use")
        else:
            lines.append(f"{area['label']}: manage")
    return lines


def preview_labels(granted: set[str] | list[str]) -> dict:
    """Nav + dashboard labels that would appear for this key set (approx)."""
    g = set(granted or [])
    nav, dash = [], []
    for area in AREA_MATRIX:
        if level_for_keys(area, g) == LEVEL_OFF:
            continue
        nav.extend(area.get('preview', {}).get('nav') or [])
        dash.extend(area.get('preview', {}).get('dash') or [])
    return {
        'nav': list(dict.fromkeys(nav)),
        'dash': list(dict.fromkeys(dash)),
    }


# System template packs (applied as system groups + optional direct seed)
TEMPLATE_MEMBER_START_KEYS = [
    'submit_tickets',
]
TEMPLATE_STAFF_START_KEYS = [
    'view_members',
    'manage_attendance',
    'submit_tickets',
]

SYSTEM_TEMPLATE_GROUPS = [
    {
        'system_key': 'member_start',
        'name': 'Member Start Pack',
        'description': (
            'Default access for new Members. Edit this pack to change what every new Member starts with. '
            'Fine-grained: add people to other groups or grant personal access for exceptions.'
        ),
        'permissions': TEMPLATE_MEMBER_START_KEYS,
    },
    {
        'system_key': 'staff_start',
        'name': 'Staff Start Pack',
        'description': (
            'Default access when someone is promoted to Staff. Not “all tools” — only this pack plus any groups you add. '
            'A Staff person can have less access than a Member if you set it that way.'
        ),
        'permissions': TEMPLATE_STAFF_START_KEYS,
    },
]
