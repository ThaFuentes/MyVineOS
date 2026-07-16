# Church-wide feature toggles: which modules appear in nav / are available.
# Core modules are always on. Optional modules default ON so upgrades stay familiar.

from __future__ import annotations

import json
from typing import Any, Optional

import pymysql

from app.models.db import get_db

# key, label, description, category, default_enabled
# Categories group the Settings UI.
OPTIONAL_MODULES: list[dict[str, Any]] = [
    # Member-facing
    {
        'key': 'my_kids',
        'label': 'My Kids (parent portal)',
        'description': 'Parents manage children and see check-in status under My Stuff.',
        'category': 'Member tools',
        'default': True,
    },
    {
        'key': 'my_serving',
        'label': 'My Serving (volunteer schedule)',
        'description': 'Members see their volunteer assignments and respond.',
        'category': 'Member tools',
        'default': True,
    },
    {
        'key': 'self_checkin',
        'label': 'Self check-in',
        'description': 'Members can check themselves into services from My Stuff.',
        'category': 'Member tools',
        'default': True,
    },
    {
        'key': 'support_tickets',
        'label': 'My Tickets / Support',
        'description': 'Member support ticket submission and history.',
        'category': 'Member tools',
        'default': True,
    },
    {
        'key': 'curriculum',
        'label': 'Study Courses',
        'description': 'Member discipleship / curriculum catalog.',
        'category': 'Member tools',
        'default': True,
    },
    # Church office / ministry ops
    {
        'key': 'child_checkin',
        'label': 'Child Check-In (staff station)',
        'description': 'Staff kiosk, rooms, labels, and live board.',
        'category': 'Church office',
        'default': True,
    },
    {
        'key': 'volunteers',
        'label': 'Volunteer Schedule (staff)',
        'description': 'Teams, events, rotations, and scheduling tools for staff.',
        'category': 'Church office',
        'default': True,
    },
    {
        'key': 'communications',
        'label': 'Communications & Automation',
        'description': 'Mass email/SMS, drips, and the automation engine.',
        'category': 'Church office',
        'default': True,
    },
    {
        'key': 'attendance',
        'label': 'Attendance (admin)',
        'description': 'Attendance sessions and kiosk management for staff.',
        'category': 'Church office',
        'default': True,
    },
    {
        'key': 'donations',
        'label': 'Donations',
        'description': 'Donation entry, import, receipts, and reports.',
        'category': 'Church office',
        'default': True,
    },
    {
        'key': 'bills',
        'label': 'Bills',
        'description': 'Recurring bills and payment tracking.',
        'category': 'Church office',
        'default': True,
    },
    {
        'key': 'accounting',
        'label': 'Accounting',
        'description': 'Chart of accounts, expenses, budgets, payroll views.',
        'category': 'Church office',
        'default': True,
    },
    {
        'key': 'inventory',
        'label': 'Inventory',
        'description': 'Church inventory and stock tools.',
        'category': 'Church office',
        'default': True,
    },
    {
        'key': 'worship',
        'label': 'Worship Team',
        'description': 'Songs, setlists, plans, and worship podium tools.',
        'category': 'Church office',
        'default': True,
    },
    # Community extras (events/prayers/sermons/announcements stay core)
    {
        'key': 'dreams',
        'label': 'Dreams & Visions',
        'description': 'Community dreams module.',
        'category': 'Community extras',
        'default': True,
    },
    {
        'key': 'prophecies',
        'label': 'Prophecies',
        'description': 'Community prophecies module.',
        'category': 'Community extras',
        'default': True,
    },
    {
        'key': 'bible_study',
        'label': 'Bible study page',
        'description': 'In-app Bible reader for members.',
        'category': 'Community extras',
        'default': True,
    },
    # Admin extras
    {
        'key': 'ai_insights',
        'label': 'AI Insights',
        'description': 'AI-assisted church insights reports.',
        'category': 'Admin extras',
        'default': True,
    },
    {
        'key': 'gathering_manager',
        'label': 'Gathering Manager',
        'description': 'Moderation tools for the gathering place.',
        'category': 'Admin extras',
        'default': True,
    },
    {
        'key': 'ticket_manager',
        'label': 'Ticket Manager (staff)',
        'description': 'Staff ticket queue / assignment tools.',
        'category': 'Admin extras',
        'default': True,
    },
    {
        'key': 'change_log',
        'label': 'Change Log',
        'description': 'Audit log of site changes (staff/admin).',
        'category': 'Admin extras',
        'default': True,
    },
]

# Always visible / never toggleable (documented for the Settings page)
CORE_ALWAYS_ON = [
    ('dashboard', 'Home / Dashboard'),
    ('profile', 'Profile'),
    ('settings', 'Settings'),
    ('help', 'Help'),
    ('groups', 'Groups'),
    ('pastoral', 'Pastoral area'),
    ('events', 'Events'),
    ('prayers', 'Prayers'),
    ('sermons', 'Sermons (public library)'),
    ('announcements', 'Announcements'),
    ('members', 'Members (permission-gated)'),
    ('security', 'Security console (permission-gated)'),
]

_DEFAULTS = {m['key']: bool(m['default']) for m in OPTIONAL_MODULES}
_LABELS = {m['key']: m['label'] for m in OPTIONAL_MODULES}


def _loads(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def get_module_toggles(raw_settings: dict | None = None) -> dict[str, bool]:
    """Merged toggles: defaults + saved overrides. Missing keys default ON."""
    if raw_settings is None:
        try:
            db = get_db()
            cur = db.cursor(pymysql.cursors.DictCursor)
            cur.execute("SELECT module_toggles_json FROM settings WHERE id = 1")
            row = cur.fetchone() or {}
            raw = row.get('module_toggles_json')
        except Exception:
            raw = None
    else:
        raw = raw_settings.get('module_toggles_json') if raw_settings else None

    saved = _loads(raw)
    out = dict(_DEFAULTS)
    for key, val in saved.items():
        if key in out:
            out[key] = bool(val)
    return out


def is_module_enabled(key: str, toggles: dict | None = None) -> bool:
    """Core keys always True. Unknown optional keys default True."""
    if key in dict(CORE_ALWAYS_ON):
        return True
    if key not in _DEFAULTS:
        return True
    t = toggles if toggles is not None else get_module_toggles()
    return bool(t.get(key, _DEFAULTS.get(key, True)))


def save_module_toggles(enabled_keys: set[str] | list[str] | dict) -> dict[str, bool]:
    """
    Persist toggles. enabled_keys may be a set of keys that are ON,
    or a dict of key->bool.
    """
    if isinstance(enabled_keys, dict):
        merged = dict(_DEFAULTS)
        for k, v in enabled_keys.items():
            if k in merged:
                merged[k] = bool(v)
    else:
        on = set(enabled_keys or [])
        merged = {k: (k in on) for k in _DEFAULTS}

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE settings SET module_toggles_json = %s WHERE id = 1",
        (json.dumps(merged, ensure_ascii=False),),
    )
    db.commit()
    return merged


def modules_by_category() -> list[tuple[str, list[dict]]]:
    cats: dict[str, list] = {}
    for m in OPTIONAL_MODULES:
        cats.setdefault(m['category'], []).append(m)
    order = ['Member tools', 'Church office', 'Community extras', 'Admin extras']
    out = []
    for c in order:
        if c in cats:
            out.append((c, cats[c]))
    for c, items in cats.items():
        if c not in order:
            out.append((c, items))
    return out


def module_for_endpoint(endpoint: str | None) -> Optional[str]:
    """Map a Flask endpoint to an optional module key, or None if core/unknown."""
    if not endpoint:
        return None
    ep = endpoint

    # Member portals first (more specific)
    if ep == 'child_checkin.my_kids':
        return 'my_kids'
    if ep in ('volunteers.my_schedule', 'volunteers.my_respond', 'volunteers.respond'):
        return 'my_serving'
    if ep == 'attendance.self_checkin':
        return 'self_checkin'

    prefixes = (
        ('child_checkin.', 'child_checkin'),
        ('volunteers.', 'volunteers'),
        ('communications.', 'communications'),
        ('attendance.', 'attendance'),
        ('donations.', 'donations'),
        ('bills.', 'bills'),
        ('accounting.', 'accounting'),
        ('inventory.', 'inventory'),
        ('worship.', 'worship'),
        ('curriculum.', 'curriculum'),
        ('dreams.', 'dreams'),
        ('prophecies.', 'prophecies'),
        ('bible.', 'bible_study'),
        ('ai_insights.', 'ai_insights'),
        ('the_gathering.', 'gathering_manager'),
        ('tickets.', 'ticket_manager'),
        ('support_tickets.', 'support_tickets'),
        ('log.', 'change_log'),
    )
    for prefix, key in prefixes:
        if ep.startswith(prefix):
            return key
    return None
