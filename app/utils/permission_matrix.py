# app/utils/permission_matrix.py
# Single-source access model: only per-user grants (user_permissions).
# RULE: every checkbox maps to exactly ONE permission key.
# view ≠ create ≠ edit ≠ delete (never a combined "full access" box).

from __future__ import annotations

# Each action.keys list must contain exactly one key.
AREA_MATRIX = [
    {
        'id': 'accounting',
        'label': 'Accounting',
        'description': 'Chart of accounts, expenses, budgets, payroll, reports.',
        'icon': 'fa-calculator',
        'actions': [
            {'id': 'view', 'label': 'Can view (dashboard, ledger, reports)', 'keys': ['view_accounting']},
            {'id': 'create', 'label': 'Can create records', 'keys': ['create_accounting']},
            {'id': 'edit', 'label': 'Can edit records', 'keys': ['edit_accounting']},
            {'id': 'delete', 'label': 'Can delete records', 'keys': ['delete_accounting']},
        ],
    },
    {
        'id': 'donations',
        'label': 'Donations',
        'description': 'Giving records and donation tools.',
        'icon': 'fa-hand-holding-dollar',
        'actions': [
            {'id': 'view', 'label': 'Can view donations and reports', 'keys': ['view_donations']},
            {'id': 'create', 'label': 'Can record new donations', 'keys': ['create_donations']},
            {'id': 'edit', 'label': 'Can edit donations', 'keys': ['edit_donations']},
            {'id': 'delete', 'label': 'Can delete donations', 'keys': ['delete_donations']},
        ],
    },
    {
        'id': 'bills',
        'label': 'Bills',
        'description': 'Church bills and recurring payables.',
        'icon': 'fa-file-invoice-dollar',
        'actions': [
            {'id': 'view', 'label': 'Can view all bills', 'keys': ['view_bills']},
            {'id': 'create', 'label': 'Can add new bills', 'keys': ['create_bills']},
            {'id': 'edit', 'label': 'Can edit bills', 'keys': ['edit_bills']},
            {'id': 'delete', 'label': 'Can delete bills', 'keys': ['delete_bills']},
        ],
    },
    {
        'id': 'tickets',
        'label': 'Ticket Manager',
        'description': 'Staff ticket desk (all tickets).',
        'icon': 'fa-ticket',
        'actions': [
            {'id': 'view', 'label': 'Can view tickets', 'keys': ['view_tickets']},
            {'id': 'create', 'label': 'Can create tickets', 'keys': ['create_tickets']},
            {'id': 'edit', 'label': 'Can edit / assign / resolve tickets', 'keys': ['edit_tickets']},
            {'id': 'delete', 'label': 'Can delete tickets', 'keys': ['delete_tickets']},
        ],
    },
    {
        'id': 'my_tickets',
        'label': 'My own tickets',
        'description': 'Submit and see only their own support tickets.',
        'icon': 'fa-ticket-simple',
        'actions': [
            {'id': 'view', 'label': 'Can view own tickets', 'keys': ['view_own_tickets']},
            {'id': 'create', 'label': 'Can submit own tickets', 'keys': ['submit_tickets']},
        ],
    },
    {
        'id': 'inventory',
        'label': 'Inventory',
        'description': 'Items, stock, audits, barcodes.',
        'icon': 'fa-boxes-stacked',
        'actions': [
            {'id': 'view', 'label': 'Can view inventory', 'keys': ['view_inventory']},
            {'id': 'create', 'label': 'Can add items', 'keys': ['create_inventory']},
            {'id': 'edit', 'label': 'Can edit items / stock moves', 'keys': ['edit_inventory']},
            {'id': 'delete', 'label': 'Can delete items', 'keys': ['delete_inventory']},
        ],
    },
    {
        'id': 'members',
        'label': 'Members',
        'description': 'Member directory and profiles.',
        'icon': 'fa-address-book',
        'actions': [
            {'id': 'view', 'label': 'Can view the directory', 'keys': ['view_members']},
            {'id': 'create', 'label': 'Can create member profiles', 'keys': ['create_members']},
            {'id': 'edit', 'label': 'Can edit member profiles', 'keys': ['edit_members']},
            {'id': 'delete', 'label': 'Can delete member profiles', 'keys': ['delete_members']},
            {'id': 'family', 'label': 'Can manage family links', 'keys': ['manage_family_links']},
        ],
    },
    {
        'id': 'users',
        'label': 'User accounts',
        'description': 'Create accounts, approve people, change roles (powerful).',
        'icon': 'fa-user-gear',
        'actions': [
            {'id': 'view', 'label': 'Can view user accounts', 'keys': ['view_users']},
            {'id': 'create', 'label': 'Can create / approve accounts', 'keys': ['create_users']},
            {'id': 'edit', 'label': 'Can edit accounts / roles', 'keys': ['edit_users']},
            {'id': 'delete', 'label': 'Can delete accounts', 'keys': ['delete_users']},
        ],
    },
    {
        'id': 'attendance',
        'label': 'Attendance',
        'description': 'Kiosk, sessions, reports.',
        'icon': 'fa-clipboard-user',
        'actions': [
            {'id': 'view', 'label': 'Can view attendance', 'keys': ['view_attendance']},
            {'id': 'create', 'label': 'Can create sessions / check-ins', 'keys': ['create_attendance']},
            {'id': 'edit', 'label': 'Can edit attendance records', 'keys': ['edit_attendance']},
            {'id': 'delete', 'label': 'Can delete attendance records', 'keys': ['delete_attendance']},
        ],
    },
    {
        'id': 'child_checkin',
        'label': 'Child check-in',
        'description': 'Rooms, labels, live board.',
        'icon': 'fa-children',
        'actions': [
            {'id': 'view', 'label': 'Can view child check-in', 'keys': ['view_child_checkin']},
            {'id': 'create', 'label': 'Can check children in', 'keys': ['create_child_checkin']},
            {'id': 'edit', 'label': 'Can edit rooms / check-in records', 'keys': ['edit_child_checkin']},
            {'id': 'delete', 'label': 'Can delete check-in records', 'keys': ['delete_child_checkin']},
        ],
    },
    {
        'id': 'volunteers',
        'label': 'Volunteers',
        'description': 'Teams, schedules, rotations.',
        'icon': 'fa-hands-helping',
        'actions': [
            {'id': 'view', 'label': 'Can view volunteer tools', 'keys': ['view_volunteers']},
            {'id': 'create', 'label': 'Can create teams / schedules', 'keys': ['create_volunteers']},
            {'id': 'edit', 'label': 'Can edit volunteer schedules', 'keys': ['edit_volunteers']},
            {'id': 'delete', 'label': 'Can delete volunteer data', 'keys': ['delete_volunteers']},
        ],
    },
    {
        'id': 'events',
        'label': 'Events',
        'description': 'Church events and registration.',
        'icon': 'fa-calendar-days',
        'actions': [
            {'id': 'view', 'label': 'Can view events admin tools', 'keys': ['view_events']},
            {'id': 'create', 'label': 'Can create events', 'keys': ['create_events']},
            {'id': 'edit', 'label': 'Can edit events', 'keys': ['edit_events']},
            {'id': 'delete', 'label': 'Can delete events', 'keys': ['delete_events']},
            {'id': 'moderate', 'label': 'Can moderate any event', 'keys': ['moderate_events']},
            {'id': 'registration', 'label': 'Can manage event registration & fees', 'keys': ['manage_event_registration']},
        ],
    },
    {
        'id': 'announcements',
        'label': 'Announcements',
        'description': 'Church announcements.',
        'icon': 'fa-bullhorn',
        'actions': [
            {'id': 'view', 'label': 'Can view announcements admin', 'keys': ['view_announcements']},
            {'id': 'create', 'label': 'Can create announcements', 'keys': ['create_announcements']},
            {'id': 'edit', 'label': 'Can edit announcements', 'keys': ['edit_announcements']},
            {'id': 'delete', 'label': 'Can delete announcements', 'keys': ['delete_announcements']},
            {'id': 'moderate', 'label': 'Can moderate any announcement', 'keys': ['moderate_announcements']},
        ],
    },
    {
        'id': 'sermons_public',
        'label': 'Public sermon library',
        'description': 'Uploaded public sermons.',
        'icon': 'fa-book-bible',
        'actions': [
            {'id': 'view', 'label': 'Can view sermon library admin', 'keys': ['view_sermons']},
            {'id': 'create', 'label': 'Can upload sermons', 'keys': ['upload_sermons']},
            {'id': 'edit', 'label': 'Can edit sermons', 'keys': ['edit_sermons']},
            {'id': 'delete', 'label': 'Can delete sermons', 'keys': ['delete_sermons']},
            {'id': 'moderate', 'label': 'Can moderate any sermon', 'keys': ['moderate_sermons']},
        ],
    },
    {
        'id': 'dreams',
        'label': 'Dreams & visions',
        'description': 'Share and moderate community dreams / visions.',
        'icon': 'fa-cloud-moon',
        'actions': [
            {'id': 'view', 'label': 'Can view dreams admin', 'keys': ['view_dreams']},
            {'id': 'create', 'label': 'Can post dreams / visions', 'keys': ['create_dreams']},
            {'id': 'edit', 'label': 'Can edit dreams', 'keys': ['edit_dreams']},
            {'id': 'delete', 'label': 'Can delete dreams', 'keys': ['delete_dreams']},
            {'id': 'moderate', 'label': 'Can moderate any dream', 'keys': ['moderate_dreams']},
        ],
    },
    {
        'id': 'prophecies',
        'label': 'Prophecies',
        'description': 'Share and moderate community prophecies.',
        'icon': 'fa-scroll',
        'actions': [
            {'id': 'view', 'label': 'Can view prophecies admin', 'keys': ['view_prophecies']},
            {'id': 'create', 'label': 'Can post prophecies', 'keys': ['create_prophecies']},
            {'id': 'edit', 'label': 'Can edit prophecies', 'keys': ['edit_prophecies']},
            {'id': 'delete', 'label': 'Can delete prophecies', 'keys': ['delete_prophecies']},
            {'id': 'moderate', 'label': 'Can moderate any prophecy', 'keys': ['moderate_prophecies']},
        ],
    },
    {
        'id': 'prayers',
        'label': 'Prayers',
        'description': 'Prayer requests (logged-in tools). Visitors use Access → Visitors.',
        'icon': 'fa-hands-praying',
        'actions': [
            {'id': 'view', 'label': 'Can view prayers admin', 'keys': ['view_prayers']},
            {'id': 'create', 'label': 'Can submit prayers', 'keys': ['create_prayers']},
            {'id': 'edit', 'label': 'Can edit prayers', 'keys': ['edit_prayers']},
            {'id': 'delete', 'label': 'Can delete prayers', 'keys': ['delete_prayers']},
            {'id': 'moderate', 'label': 'Can moderate any prayer', 'keys': ['moderate_prayers']},
        ],
    },
    {
        'id': 'pastoral',
        'label': 'Pastoral area',
        'description': 'Sermons, vault, curriculum, care, podium.',
        'icon': 'fa-hands-praying',
        'actions': [
            {'id': 'view', 'label': 'Can open the pastoral area', 'keys': ['access_pastoral']},
            {'id': 'create', 'label': 'Can create pastoral content', 'keys': ['create_pastoral']},
            {'id': 'edit', 'label': 'Can edit pastoral content', 'keys': ['edit_pastoral']},
            {'id': 'delete', 'label': 'Can delete pastoral content', 'keys': ['delete_pastoral']},
        ],
    },
    {
        'id': 'worship',
        'label': 'Worship team',
        'description': 'Songs, setlists, plans.',
        'icon': 'fa-music',
        'actions': [
            {'id': 'view', 'label': 'Can view worship tools', 'keys': ['access_worship']},
            {'id': 'create', 'label': 'Can create songs / setlists', 'keys': ['create_worship']},
            {'id': 'edit', 'label': 'Can edit worship content', 'keys': ['edit_worship']},
            {'id': 'delete', 'label': 'Can delete worship content', 'keys': ['delete_worship']},
        ],
    },
    {
        'id': 'communications',
        'label': 'Communications',
        'description': 'Mass email / SMS and automation.',
        'icon': 'fa-envelope',
        'actions': [
            {'id': 'view', 'label': 'Can view communications', 'keys': ['view_communications']},
            {'id': 'create', 'label': 'Can send email / SMS', 'keys': ['send_emails']},
            {'id': 'edit', 'label': 'Can edit campaigns / drips', 'keys': ['edit_communications']},
            {'id': 'delete', 'label': 'Can delete campaigns', 'keys': ['delete_communications']},
        ],
    },
    {
        'id': 'ai_insights',
        'label': 'AI insights',
        'description': 'AI reports and analysis.',
        'icon': 'fa-robot',
        'actions': [
            {'id': 'view', 'label': 'Can view AI insights', 'keys': ['view_ai_insights']},
            {'id': 'create', 'label': 'Can run AI reports', 'keys': ['use_ai_insights']},
        ],
    },
    {
        'id': 'settings',
        'label': 'Church settings',
        'description': 'Name, email, themes, modules, campuses.',
        'icon': 'fa-gear',
        'actions': [
            {'id': 'view', 'label': 'Can view settings', 'keys': ['view_settings']},
            {'id': 'edit', 'label': 'Can change settings', 'keys': ['manage_settings']},
        ],
    },
    {
        'id': 'security',
        'label': 'Security console',
        'description': 'Attacks, IP bans, unlocks.',
        'icon': 'fa-shield-halved',
        'actions': [
            {'id': 'view', 'label': 'Can view security console', 'keys': ['view_security']},
            {'id': 'edit', 'label': 'Can ban / unlock / act', 'keys': ['manage_security']},
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
            {'id': 'view_help', 'label': 'Can view help admin', 'keys': ['view_help']},
            {'id': 'edit_help', 'label': 'Can edit help content', 'keys': ['manage_help']},
            {'id': 'view_legal', 'label': 'Can view legal admin', 'keys': ['view_legal']},
            {'id': 'edit_legal', 'label': 'Can edit legal notices', 'keys': ['manage_legal_notices']},
        ],
    },
]


def _area_all_keys(area: dict) -> list[str]:
    keys = []
    for act in area.get('actions') or []:
        keys.extend(act.get('keys') or [])
    return list(dict.fromkeys(keys))


def _expanded_granted(granted: set[str] | list[str]) -> set[str]:
    """Expand legacy manage_* so UI checkboxes reflect real effective access."""
    try:
        from app.utils.permissions import expand_permission_keys
        return expand_permission_keys(granted)
    except Exception:
        return set(granted or [])


def can_see_area(area: dict, granted: set[str] | list[str]) -> bool:
    g = _expanded_granted(granted)
    return any(k in g for k in _area_all_keys(area))


def action_checked(action: dict, granted: set[str] | list[str]) -> bool:
    g = _expanded_granted(granted)
    keys = action.get('keys') or []
    if not keys:
        return False
    # Exactly one key per action — checked if that key is held (after expansion).
    return any(k in g for k in keys)


def area_status_rows(granted: set[str] | list[str], *, full_access: bool = False) -> list[dict]:
    """Rows for the expandable table UI."""
    g = _expanded_granted(granted)
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
      enable_<area_id> = '1' if area is on
      act_<area_id>_<action_id> = '1' if checked
    Only checked actions grant keys (one key each).
    """
    get = form.get if hasattr(form, 'get') else (lambda k, d=None: form.get(k, d) if isinstance(form, dict) else d)
    keys: list[str] = []
    for area in AREA_MATRIX:
        aid = area['id']
        enable_raw = get(f'enable_{aid}')
        any_act = False
        area_keys = []
        for act in area.get('actions') or []:
            field = f"act_{aid}_{act['id']}"
            on = get(field) in ('1', 'on', 'yes', 'true', True)
            if on:
                any_act = True
                # enforce single key per action
                klist = act.get('keys') or []
                if klist:
                    area_keys.append(klist[0])
        if enable_raw is not None and enable_raw not in ('1', 'on', 'yes', 'true', True):
            continue
        if enable_raw in ('1', 'on', 'yes', 'true', True) and not any_act:
            acts = area.get('actions') or []
            if acts and acts[0].get('keys'):
                area_keys.append(acts[0]['keys'][0])
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
    keys: list[str] = []
    for area in AREA_MATRIX:
        see = (get(f"access_{area['id']}", 'no') or 'no').lower() == 'yes'
        if not see:
            continue
        keys.extend(_area_all_keys(area))
    return list(dict.fromkeys(keys))


def keys_from_form_levels(form) -> list[str]:
    """Alias used by older forms."""
    get = form.get if hasattr(form, 'get') else (lambda k, d=None: form.get(k, d) if isinstance(form, dict) else d)
    form_keys = []
    try:
        form_keys = list(form.keys())
    except Exception:
        form_keys = []

    if any(str(k).startswith('act_') or str(k).startswith('enable_') or str(k).startswith('access_') for k in form_keys):
        return keys_from_yes_no_form(form)

    keys: list[str] = []
    try:
        if hasattr(form, 'getlist'):
            keys.extend(form.getlist('permissions') or [])
            keys.extend(form.getlist('permission_keys') or [])
    except Exception:
        pass
    for k in form_keys:
        sk = str(k)
        if sk.startswith('perm_') and get(sk) in ('1', 'on', 'yes', 'true', True):
            keys.append(sk[5:])
        elif sk.startswith('permission_') and get(sk) in ('1', 'on', 'yes', 'true', True):
            keys.append(sk[len('permission_'):])
    return list(dict.fromkeys(k for k in keys if k))


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


TEMPLATE_MEMBER_START_KEYS = ['submit_tickets', 'view_own_tickets']
TEMPLATE_STAFF_START_KEYS = ['view_members', 'view_attendance', 'create_attendance', 'submit_tickets', 'view_own_tickets']
