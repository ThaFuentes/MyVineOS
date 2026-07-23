# app/utils/permission_matrix.py
# Definitive per-user access areas: YES / NO (and Manage where needed).
# Maps onto existing KNOWN_PERMISSIONS keys — no role ladder for tools.

from __future__ import annotations

LEVEL_OFF = 'off'
LEVEL_VIEW = 'view'
LEVEL_MANAGE = 'manage'
VALID_LEVELS = frozenset({LEVEL_OFF, LEVEL_VIEW, LEVEL_MANAGE})

# Every managed product area — shown on the Access Control screens.
# can_see_keys: any of these ⇒ YES they can open the area
# can_manage_keys: any of these ⇒ they can manage (not only peek)
AREA_MATRIX = [
    {
        'id': 'accounting',
        'label': 'Accounting',
        'description': 'Chart of accounts, expenses, budgets, payroll views.',
        'icon': 'fa-calculator',
        'view_keys': ['manage_accounting'],
        'manage_keys': ['manage_accounting'],
        'nav_label': 'Accounting',
    },
    {
        'id': 'tickets',
        'label': 'Ticket Manager',
        'description': 'Full ticket desk (see/assign/resolve tickets).',
        'icon': 'fa-ticket',
        'view_keys': ['manage_tickets'],
        'manage_keys': ['manage_tickets'],
        'nav_label': 'Ticket Manager',
    },
    {
        'id': 'my_tickets',
        'label': 'Submit my own tickets',
        'description': 'Member can open support tickets for themselves.',
        'icon': 'fa-ticket-simple',
        'view_keys': ['submit_tickets'],
        'manage_keys': ['submit_tickets'],
        'nav_label': 'My Tickets',
    },
    {
        'id': 'donations',
        'label': 'Donations',
        'description': 'View giving records and/or manage donations.',
        'icon': 'fa-hand-holding-dollar',
        'view_keys': ['view_donations'],
        'manage_keys': ['manage_donations'],
        'nav_label': 'Donations',
    },
    {
        'id': 'bills',
        'label': 'Bills',
        'description': 'Church bills and recurring payables.',
        'icon': 'fa-file-invoice-dollar',
        'view_keys': ['manage_bills'],
        'manage_keys': ['manage_bills'],
        'nav_label': 'Bills',
    },
    {
        'id': 'inventory',
        'label': 'Inventory',
        'description': 'Items, stock, audits, barcode tools.',
        'icon': 'fa-boxes-stacked',
        'view_keys': ['manage_inventory'],
        'manage_keys': ['manage_inventory'],
        'nav_label': 'Inventory',
    },
    {
        'id': 'members',
        'label': 'Members directory',
        'description': 'View directory and/or edit member profiles.',
        'icon': 'fa-address-book',
        'view_keys': ['view_members'],
        'manage_keys': ['manage_members', 'manage_family_links'],
        'nav_label': 'Members',
    },
    {
        'id': 'users',
        'label': 'User accounts',
        'description': 'Create/approve accounts and change site roles (powerful).',
        'icon': 'fa-user-gear',
        'view_keys': ['manage_users'],
        'manage_keys': ['manage_users'],
        'nav_label': 'User accounts',
    },
    {
        'id': 'attendance',
        'label': 'Attendance',
        'description': 'Kiosk, sessions, reports.',
        'icon': 'fa-clipboard-user',
        'view_keys': ['manage_attendance'],
        'manage_keys': ['manage_attendance'],
        'nav_label': 'Attendance',
    },
    {
        'id': 'child_checkin',
        'label': 'Child check-in',
        'description': 'Child check-in station, rooms, labels, board.',
        'icon': 'fa-children',
        'view_keys': ['manage_child_checkin', 'manage_attendance'],
        'manage_keys': ['manage_child_checkin', 'manage_attendance'],
        'nav_label': 'Child Check-In',
    },
    {
        'id': 'volunteers',
        'label': 'Volunteers',
        'description': 'Teams, schedules, rotations.',
        'icon': 'fa-hands-helping',
        'view_keys': ['manage_volunteers'],
        'manage_keys': ['manage_volunteers'],
        'nav_label': 'Volunteers',
    },
    {
        'id': 'events',
        'label': 'Events (manage)',
        'description': 'Create or fully manage church events.',
        'icon': 'fa-calendar-days',
        'view_keys': ['create_events'],
        'manage_keys': ['manage_events', 'moderate_events', 'manage_event_registration'],
        'nav_label': 'Events',
    },
    {
        'id': 'announcements',
        'label': 'Announcements (manage)',
        'description': 'Post or moderate announcements.',
        'icon': 'fa-bullhorn',
        'view_keys': ['create_announcements'],
        'manage_keys': ['moderate_announcements'],
        'nav_label': 'Announcements',
    },
    {
        'id': 'pastoral',
        'label': 'Pastoral area',
        'description': 'Sermons, vault, curriculum, care, podium.',
        'icon': 'fa-hands-praying',
        'view_keys': ['access_pastoral'],
        'manage_keys': ['access_pastoral'],
        'nav_label': 'Pastoral',
    },
    {
        'id': 'worship',
        'label': 'Worship team',
        'description': 'View or manage worship songs/setlists.',
        'icon': 'fa-music',
        'view_keys': ['access_worship'],
        'manage_keys': ['manage_worship'],
        'nav_label': 'Worship Team',
    },
    {
        'id': 'communications',
        'label': 'Communications',
        'description': 'Mass email/SMS and automation.',
        'icon': 'fa-envelope',
        'view_keys': ['send_emails'],
        'manage_keys': ['send_emails'],
        'nav_label': 'Communications',
    },
    {
        'id': 'ai_insights',
        'label': 'AI insights',
        'description': 'AI reports and analysis.',
        'icon': 'fa-robot',
        'view_keys': ['use_ai_insights'],
        'manage_keys': ['use_ai_insights'],
        'nav_label': 'AI Insights',
    },
    {
        'id': 'groups_admin',
        'label': 'Permission groups admin',
        'description': 'Create/edit shared permission groups.',
        'icon': 'fa-people-group',
        'view_keys': ['manage_groups'],
        'manage_keys': ['manage_groups'],
        'nav_label': 'Permission Groups',
    },
    {
        'id': 'settings',
        'label': 'Church settings',
        'description': 'Name, email, themes, modules, campuses.',
        'icon': 'fa-gear',
        'view_keys': ['manage_settings'],
        'manage_keys': ['manage_settings'],
        'nav_label': 'Settings',
    },
    {
        'id': 'security',
        'label': 'Security console',
        'description': 'Attacks, IP bans, unlocks.',
        'icon': 'fa-shield-halved',
        'view_keys': ['manage_security'],
        'manage_keys': ['manage_security'],
        'nav_label': 'Security',
    },
    {
        'id': 'audit',
        'label': 'Audit / change log',
        'description': 'View change records.',
        'icon': 'fa-clipboard-list',
        'view_keys': ['view_audit_logs'],
        'manage_keys': ['view_audit_logs'],
        'nav_label': 'Change Records',
    },
    {
        'id': 'help_legal',
        'label': 'Help & legal content',
        'description': 'Edit help guides and legal notices.',
        'icon': 'fa-circle-question',
        'view_keys': ['manage_help'],
        'manage_keys': ['manage_help', 'manage_legal_notices'],
        'nav_label': 'Help / Legal',
    },
    {
        'id': 'sermons_public',
        'label': 'Public sermon library',
        'description': 'Upload or moderate public sermons.',
        'icon': 'fa-book-bible',
        'view_keys': ['upload_sermons'],
        'manage_keys': ['moderate_sermons'],
        'nav_label': 'Sermons library',
    },
    {
        'id': 'community_mod',
        'label': 'Community moderation',
        'description': 'Moderate prayers, dreams, prophecies.',
        'icon': 'fa-comments',
        'view_keys': ['create_dreams'],
        'manage_keys': ['moderate_prayers', 'moderate_dreams', 'moderate_prophecies'],
        'nav_label': 'Community mod',
    },
]


def keys_for_level(area: dict, level: str) -> list[str]:
    level = (level or LEVEL_OFF).lower()
    if level not in VALID_LEVELS or level == LEVEL_OFF:
        return []
    view = list(area.get('view_keys') or [])
    manage = list(area.get('manage_keys') or [])
    if level == LEVEL_VIEW:
        return list(dict.fromkeys(view))
    return list(dict.fromkeys(view + manage))


def level_for_keys(area: dict, granted: set[str] | list[str]) -> str:
    granted_set = set(granted or [])
    manage = set(area.get('manage_keys') or [])
    view = set(area.get('view_keys') or [])
    if manage and manage.intersection(granted_set):
        # If manage keys == view keys, any hit is full access
        if manage <= granted_set or manage == view:
            return LEVEL_MANAGE
        return LEVEL_MANAGE
    if view and view.intersection(granted_set):
        return LEVEL_VIEW
    return LEVEL_OFF


def can_see_area(area: dict, granted: set[str] | list[str]) -> bool:
    return level_for_keys(area, granted) != LEVEL_OFF


def can_manage_area(area: dict, granted: set[str] | list[str]) -> bool:
    return level_for_keys(area, granted) == LEVEL_MANAGE


def area_status_rows(granted: set[str] | list[str], *, full_access: bool = False) -> list[dict]:
    """Every area with definitive YES/NO for open + manage."""
    g = set(granted or [])
    rows = []
    for area in AREA_MATRIX:
        if full_access:
            see, manage = True, True
            level = LEVEL_MANAGE
        else:
            level = level_for_keys(area, g)
            see = level != LEVEL_OFF
            manage = level == LEVEL_MANAGE
        rows.append({
            **area,
            'level': level,
            'can_see': see,
            'can_manage': manage,
            'status_label': 'YES' if see else 'NO',
            'manage_label': 'YES' if manage else ('—' if not see else 'NO'),
        })
    return rows


def matrix_from_keys(granted: set[str] | list[str]) -> list[dict]:
    g = set(granted or [])
    return [{**area, 'level': level_for_keys(area, g)} for area in AREA_MATRIX]


def keys_from_form_levels(form, *, include_raw_checkboxes: bool = False) -> list[str]:
    """
    Read area_level_<id> selects. Matrix is authoritative when present.
    """
    keys: list[str] = []
    get = form.get if hasattr(form, 'get') else (lambda k, d=None: form.get(k, d) if isinstance(form, dict) else d)
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


def keys_from_yes_no_form(form) -> list[str]:
    """
    Form fields:
      access_<area_id> = 'yes' | 'no'   (can open)
      manage_<area_id> = 'yes' | 'no'   (optional manage upgrade)
    """
    get = form.get if hasattr(form, 'get') else (lambda k, d=None: form.get(k, d) if isinstance(form, dict) else d)
    keys: list[str] = []
    for area in AREA_MATRIX:
        see = (get(f"access_{area['id']}", 'no') or 'no').lower() == 'yes'
        if not see:
            continue
        manage = (get(f"manage_{area['id']}", 'no') or 'no').lower() == 'yes'
        # If view and manage keys are the same, YES = those keys
        level = LEVEL_MANAGE if manage else LEVEL_VIEW
        # Areas with only manage-type keys: "yes" alone means full access
        view = set(area.get('view_keys') or [])
        mkeys = set(area.get('manage_keys') or [])
        if view == mkeys or not view:
            level = LEVEL_MANAGE if see else LEVEL_OFF
        keys.extend(keys_for_level(area, level))
    return list(dict.fromkeys(keys))


def human_summary(granted: set[str] | list[str], *, full_access: bool = False) -> list[str]:
    if full_access:
        return ['FULL ACCESS — every area (Admin/Owner)']
    lines = []
    for row in area_status_rows(granted, full_access=False):
        if not row['can_see']:
            continue
        if row['can_manage']:
            lines.append(f"{row['label']}: YES (manage)")
        else:
            lines.append(f"{row['label']}: YES (open)")
    return lines


def preview_labels(granted: set[str] | list[str], *, full_access: bool = False) -> dict:
    if full_access:
        return {'nav': ['Everything'], 'dash': ['All operator tiles']}
    nav = []
    for row in area_status_rows(granted):
        if row['can_see']:
            nav.append(row.get('nav_label') or row['label'])
    return {'nav': nav, 'dash': nav}


# Start packs (system groups) — defaults only; person Access YES/NO is the source of truth for individuals
TEMPLATE_MEMBER_START_KEYS = ['submit_tickets']
TEMPLATE_STAFF_START_KEYS = ['view_members', 'manage_attendance', 'submit_tickets']

SYSTEM_TEMPLATE_GROUPS = [
    {
        'system_key': 'member_start',
        'name': 'Member Start Pack',
        'description': 'Default for NEW Members only. Change any person anytime under Members → Access Control.',
        'permissions': TEMPLATE_MEMBER_START_KEYS,
    },
    {
        'system_key': 'staff_start',
        'name': 'Staff Start Pack',
        'description': 'Default when someone is first set to Staff. Not automatic forever — edit each person under Access Control.',
        'permissions': TEMPLATE_STAFF_START_KEYS,
    },
]
