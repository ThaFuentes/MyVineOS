# app/utils/permission_matrix.py
# Single-source access model: only per-user grants (user_permissions).
# UI: enable a tool → expand fine-grained actions (view / create-edit / delete).

from __future__ import annotations

# Each area has optional actions. keys = permission keys granted when that action is checked.
# "enabled" is derived: any action on ⇒ area is on.
AREA_MATRIX = [
    {
        'id': 'accounting',
        'label': 'Accounting',
        'description': 'Chart of accounts, expenses, budgets, payroll.',
        'icon': 'fa-calculator',
        'actions': [
            {'id': 'full', 'label': 'Full access (view, create, edit, delete)', 'keys': ['manage_accounting']},
        ],
    },
    {
        'id': 'tickets',
        'label': 'Ticket Manager',
        'description': 'See and run the full ticket desk.',
        'icon': 'fa-ticket',
        'actions': [
            {'id': 'manage', 'label': 'Manage all tickets (view, assign, resolve)', 'keys': ['manage_tickets']},
        ],
    },
    {
        'id': 'my_tickets',
        'label': 'My own tickets',
        'description': 'Submit and see only their own support tickets.',
        'icon': 'fa-ticket-simple',
        'actions': [
            {'id': 'submit', 'label': 'Can submit and view own tickets', 'keys': ['submit_tickets']},
        ],
    },
    {
        'id': 'donations',
        'label': 'Donations',
        'description': 'Giving records and donation tools.',
        'icon': 'fa-hand-holding-dollar',
        'actions': [
            {'id': 'view', 'label': 'Can view donations', 'keys': ['view_donations']},
            {'id': 'manage', 'label': 'Can create, edit, and delete donations', 'keys': ['manage_donations']},
        ],
    },
    {
        'id': 'bills',
        'label': 'Bills',
        'description': 'Church bills and recurring payables.',
        'icon': 'fa-file-invoice-dollar',
        'actions': [
            {'id': 'full', 'label': 'Full access (view, create, edit, pay)', 'keys': ['manage_bills']},
        ],
    },
    {
        'id': 'inventory',
        'label': 'Inventory',
        'description': 'Items, stock, audits, barcodes.',
        'icon': 'fa-boxes-stacked',
        'actions': [
            {'id': 'full', 'label': 'Full access (view, add, edit, stock moves)', 'keys': ['manage_inventory']},
        ],
    },
    {
        'id': 'members',
        'label': 'Members',
        'description': 'Member directory and profiles.',
        'icon': 'fa-address-book',
        'actions': [
            {'id': 'view', 'label': 'Can view the directory', 'keys': ['view_members']},
            {'id': 'edit', 'label': 'Can create and edit member profiles', 'keys': ['manage_members']},
            {'id': 'family', 'label': 'Can manage family links', 'keys': ['manage_family_links']},
        ],
    },
    {
        'id': 'users',
        'label': 'User accounts',
        'description': 'Create accounts, approve people, change roles (powerful).',
        'icon': 'fa-user-gear',
        'actions': [
            {'id': 'full', 'label': 'Can create, approve, and change roles', 'keys': ['manage_users']},
        ],
    },
    {
        'id': 'attendance',
        'label': 'Attendance',
        'description': 'Kiosk, sessions, reports.',
        'icon': 'fa-clipboard-user',
        'actions': [
            {'id': 'full', 'label': 'Full access (kiosk, sessions, reports)', 'keys': ['manage_attendance']},
        ],
    },
    {
        'id': 'child_checkin',
        'label': 'Child check-in',
        'description': 'Rooms, labels, live board.',
        'icon': 'fa-children',
        'actions': [
            {'id': 'full', 'label': 'Full child check-in access', 'keys': ['manage_child_checkin']},
        ],
    },
    {
        'id': 'volunteers',
        'label': 'Volunteers',
        'description': 'Teams, schedules, rotations.',
        'icon': 'fa-hands-helping',
        'actions': [
            {'id': 'full', 'label': 'Full volunteer management', 'keys': ['manage_volunteers']},
        ],
    },
    {
        'id': 'events',
        'label': 'Events',
        'description': 'Church events and registration.',
        'icon': 'fa-calendar-days',
        'actions': [
            {'id': 'create', 'label': 'Can create and edit own events', 'keys': ['create_events']},
            {'id': 'manage', 'label': 'Can manage / moderate any event', 'keys': ['manage_events', 'moderate_events']},
            {'id': 'registration', 'label': 'Can manage event registration & fees', 'keys': ['manage_event_registration']},
        ],
    },
    {
        'id': 'announcements',
        'label': 'Announcements',
        'description': 'Church announcements.',
        'icon': 'fa-bullhorn',
        'actions': [
            {'id': 'create', 'label': 'Can create and edit own announcements', 'keys': ['create_announcements']},
            {'id': 'moderate', 'label': 'Can delete / edit any announcement', 'keys': ['moderate_announcements']},
        ],
    },
    {
        'id': 'sermons_public',
        'label': 'Public sermon library',
        'description': 'Uploaded public sermons.',
        'icon': 'fa-book-bible',
        'actions': [
            {'id': 'upload', 'label': 'Can upload and manage own uploads', 'keys': ['upload_sermons']},
            {'id': 'moderate', 'label': 'Can delete / edit any sermon', 'keys': ['moderate_sermons']},
        ],
    },
    {
        'id': 'community_mod',
        'label': 'Community moderation',
        'description': 'Prayers, dreams, prophecies moderation.',
        'icon': 'fa-comments',
        'actions': [
            {'id': 'dreams_create', 'label': 'Can post dreams / visions', 'keys': ['create_dreams']},
            {'id': 'moderate_prayers', 'label': 'Can moderate prayers', 'keys': ['moderate_prayers']},
            {'id': 'moderate_dreams', 'label': 'Can moderate dreams', 'keys': ['moderate_dreams']},
            {'id': 'moderate_prophecies', 'label': 'Can moderate prophecies', 'keys': ['moderate_prophecies']},
        ],
    },
    {
        'id': 'pastoral',
        'label': 'Pastoral area',
        'description': 'Sermons, vault, curriculum, care, podium.',
        'icon': 'fa-hands-praying',
        'actions': [
            {'id': 'access', 'label': 'Can open the pastoral area', 'keys': ['access_pastoral']},
        ],
    },
    {
        'id': 'worship',
        'label': 'Worship team',
        'description': 'Songs, setlists, plans.',
        'icon': 'fa-music',
        'actions': [
            {'id': 'view', 'label': 'Can view worship tools', 'keys': ['access_worship']},
            {'id': 'manage', 'label': 'Can manage songs, setlists, plans', 'keys': ['manage_worship']},
        ],
    },
    {
        'id': 'communications',
        'label': 'Communications',
        'description': 'Mass email / SMS and automation.',
        'icon': 'fa-envelope',
        'actions': [
            {'id': 'full', 'label': 'Full communications access', 'keys': ['send_emails']},
        ],
    },
    {
        'id': 'ai_insights',
        'label': 'AI insights',
        'description': 'AI reports and analysis.',
        'icon': 'fa-robot',
        'actions': [
            {'id': 'use', 'label': 'Can use AI insights', 'keys': ['use_ai_insights']},
        ],
    },
    {
        'id': 'settings',
        'label': 'Church settings',
        'description': 'Name, email, themes, modules, campuses.',
        'icon': 'fa-gear',
        'actions': [
            {'id': 'full', 'label': 'Can change church settings', 'keys': ['manage_settings']},
        ],
    },
    {
        'id': 'security',
        'label': 'Security console',
        'description': 'Attacks, IP bans, unlocks.',
        'icon': 'fa-shield-halved',
        'actions': [
            {'id': 'full', 'label': 'Full security console access', 'keys': ['manage_security']},
        ],
    },
    {
        'id': 'audit',
        'label': 'Audit / change log',
        'description': 'View change records.',
        'icon': 'fa-clipboard-list',
        'actions': [
            {'id': 'view', 'label': 'Can view the audit log', 'keys': ['view_audit_logs']},
        ],
    },
    {
        'id': 'help_legal',
        'label': 'Help & legal content',
        'description': 'Edit help guides and legal notices.',
        'icon': 'fa-circle-question',
        'actions': [
            {'id': 'help', 'label': 'Can edit help content', 'keys': ['manage_help']},
            {'id': 'legal', 'label': 'Can edit legal notices', 'keys': ['manage_legal_notices']},
        ],
    },
]


def _area_all_keys(area: dict) -> list[str]:
    keys = []
    for act in area.get('actions') or []:
        keys.extend(act.get('keys') or [])
    return list(dict.fromkeys(keys))


def can_see_area(area: dict, granted: set[str] | list[str]) -> bool:
    g = set(granted or [])
    return any(k in g for k in _area_all_keys(area))


def action_checked(action: dict, granted: set[str] | list[str]) -> bool:
    g = set(granted or [])
    keys = action.get('keys') or []
    if not keys:
        return False
    return all(k in g for k in keys) or any(k in g for k in keys)


def area_status_rows(granted: set[str] | list[str], *, full_access: bool = False) -> list[dict]:
    """Rows for the expandable table UI."""
    g = set(granted or [])
    rows = []
    for area in AREA_MATRIX:
        actions_out = []
        for act in area.get('actions') or []:
            checked = full_access or action_checked(act, g)
            actions_out.append({**act, 'checked': checked})
        enabled = full_access or any(a['checked'] for a in actions_out)
        rows.append({
            **area,
            'enabled': enabled,
            'actions': actions_out,
            'status_label': 'ON' if enabled else 'OFF',
        })
    return rows


def keys_from_action_form(form) -> list[str]:
    """
    Form fields:
      enable_<area_id> = '1' if area is on (optional; if missing, any action implies on)
      act_<area_id>_<action_id> = '1' if checked
    If enable is off, no keys for that area.
    If enable is on but no actions checked, grant first action as default (safe minimum)
    or grant nothing — we grant only checked actions.
    """
    get = form.get if hasattr(form, 'get') else (lambda k, d=None: form.get(k, d) if isinstance(form, dict) else d)
    keys: list[str] = []
    for area in AREA_MATRIX:
        aid = area['id']
        # enable checkbox: if present and not checked → skip
        # if any act_* present for area, use those; enable may be '1' or missing when JS syncs
        enable_raw = get(f'enable_{aid}')
        any_act = False
        area_keys = []
        for act in area.get('actions') or []:
            field = f"act_{aid}_{act['id']}"
            on = get(field) in ('1', 'on', 'yes', 'true', True)
            if on:
                any_act = True
                area_keys.extend(act.get('keys') or [])
        if enable_raw is not None and enable_raw not in ('1', 'on', 'yes', 'true', True):
            # explicitly disabled
            continue
        if enable_raw in ('1', 'on', 'yes', 'true', True) and not any_act:
            # Enabled but no sub-actions: turn on first action as baseline
            acts = area.get('actions') or []
            if acts:
                area_keys.extend(acts[0].get('keys') or [])
        elif not any_act and enable_raw is None:
            continue
        keys.extend(area_keys)
    return list(dict.fromkeys(keys))


def keys_from_yes_no_form(form) -> list[str]:
    """Backward-compatible: prefer action form, else old access_ yes/no. """
    get = form.get if hasattr(form, 'get') else (lambda k, d=None: form.get(k, d) if isinstance(form, dict) else d)
    form_keys = []
    try:
        form_keys = list(form.keys())
    except Exception:
        form_keys = []
    if any(str(k).startswith('act_') or str(k).startswith('enable_') for k in form_keys):
        return keys_from_action_form(form)
    # legacy simple yes/no
    keys: list[str] = []
    for area in AREA_MATRIX:
        see = (get(f"access_{area['id']}", 'no') or 'no').lower() == 'yes'
        if not see:
            continue
        keys.extend(_area_all_keys(area))
    return list(dict.fromkeys(keys))


def human_summary(granted: set[str] | list[str], *, full_access: bool = False) -> list[str]:
    if full_access:
        return ['Everything — full access']
    lines = []
    for row in area_status_rows(granted, full_access=False):
        if not row['enabled']:
            continue
        acts = [a['label'] for a in row['actions'] if a.get('checked')]
        if acts:
            lines.append(f"{row['label']}: " + '; '.join(acts))
        else:
            lines.append(f"{row['label']}: on")
    return lines


def preview_labels(granted: set[str] | list[str], *, full_access: bool = False) -> dict:
    if full_access:
        return {'nav': ['Everything'], 'dash': ['All tools']}
    nav = [row['label'] for row in area_status_rows(granted) if row['enabled']]
    return {'nav': nav, 'dash': nav}


# Starter template key packs (seed only)
TEMPLATE_MEMBER_START_KEYS = ['submit_tickets']
TEMPLATE_STAFF_START_KEYS = ['view_members', 'manage_attendance', 'submit_tickets']
