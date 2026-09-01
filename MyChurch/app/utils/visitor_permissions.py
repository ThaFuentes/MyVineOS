# Visitor (not logged in) capabilities — same fine-grained model as Access tools.
# Stored per church site in settings.visitor_permissions_json.
# These are NOT user_permissions rows (visitors have no account).

from __future__ import annotations

import json
from typing import Any

import pymysql

from app.models.db import get_db

# Same idea as AREA_MATRIX, but only public community areas and visitor-safe actions.
# view = see public content in that tab
# create = submit new items
# comment = respond / comment (interact)
VISITOR_AREA_MATRIX = [
    {
        'id': 'prayers',
        'label': 'Prayers',
        'description': 'Public prayer requests and responses.',
        'icon': 'fa-hands-praying',
        'actions': [
            {'id': 'view', 'label': 'Can see public prayers', 'keys': ['visitor_view_prayers']},
            {'id': 'create', 'label': 'Can submit a prayer request', 'keys': ['visitor_create_prayers']},
            {'id': 'comment', 'label': 'Can comment / respond', 'keys': ['visitor_comment_prayers']},
        ],
    },
    {
        'id': 'dreams',
        'label': 'Dreams & visions',
        'description': 'Public dreams and visions.',
        'icon': 'fa-cloud-moon',
        'actions': [
            {'id': 'view', 'label': 'Can see public dreams', 'keys': ['visitor_view_dreams']},
            {'id': 'create', 'label': 'Can submit a dream / vision', 'keys': ['visitor_create_dreams']},
            {'id': 'comment', 'label': 'Can comment / respond', 'keys': ['visitor_comment_dreams']},
        ],
    },
    {
        'id': 'prophecies',
        'label': 'Prophecies',
        'description': 'Public prophecies.',
        'icon': 'fa-scroll',
        'actions': [
            {'id': 'view', 'label': 'Can see public prophecies', 'keys': ['visitor_view_prophecies']},
            {'id': 'create', 'label': 'Can submit a prophecy', 'keys': ['visitor_create_prophecies']},
            {'id': 'comment', 'label': 'Can comment / respond', 'keys': ['visitor_comment_prophecies']},
        ],
    },
    {
        'id': 'sermons',
        'label': 'Sermons (public library)',
        'description': 'Public sermon library.',
        'icon': 'fa-book-open',
        'actions': [
            {'id': 'view', 'label': 'Can see public sermons', 'keys': ['visitor_view_sermons']},
            {'id': 'create', 'label': 'Can submit / share a sermon', 'keys': ['visitor_create_sermons']},
            {'id': 'comment', 'label': 'Can comment / respond', 'keys': ['visitor_comment_sermons']},
        ],
    },
    {
        'id': 'announcements',
        'label': 'Announcements',
        'description': 'Public announcements.',
        'icon': 'fa-bullhorn',
        'actions': [
            {'id': 'view', 'label': 'Can see public announcements', 'keys': ['visitor_view_announcements']},
            {'id': 'create', 'label': 'Can post an announcement', 'keys': ['visitor_create_announcements']},
            {'id': 'comment', 'label': 'Can comment / respond', 'keys': ['visitor_comment_announcements']},
        ],
    },
    {
        'id': 'events',
        'label': 'Events',
        'description': 'Public events.',
        'icon': 'fa-calendar-days',
        'actions': [
            {'id': 'view', 'label': 'Can see public events', 'keys': ['visitor_view_events']},
            {'id': 'create', 'label': 'Can submit an event', 'keys': ['visitor_create_events']},
            {'id': 'comment', 'label': 'Can comment / respond', 'keys': ['visitor_comment_events']},
        ],
    },
]

# Open-by-default: visitors can browse + comment on core community; submit only on prayers
# (matches prior public behavior as closely as possible).
DEFAULT_VISITOR_KEYS = [
    'visitor_view_prayers',
    'visitor_create_prayers',
    'visitor_comment_prayers',
    'visitor_view_dreams',
    'visitor_comment_dreams',
    'visitor_view_prophecies',
    'visitor_comment_prophecies',
    'visitor_view_sermons',
    'visitor_comment_sermons',
    'visitor_view_announcements',
    'visitor_comment_announcements',
    'visitor_view_events',
    'visitor_comment_events',
]

_ALL_VISITOR_KEYS: frozenset[str] = frozenset(
    k
    for area in VISITOR_AREA_MATRIX
    for act in area['actions']
    for k in (act.get('keys') or [])
)


def _ensure_column() -> None:
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute("""
            SELECT COUNT(*) AS c FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'settings'
              AND COLUMN_NAME = 'visitor_permissions_json'
        """)
        row = cur.fetchone()
        n = row[0] if isinstance(row, (list, tuple)) else (row or {}).get('c', 0)
        if not n:
            cur.execute(
                "ALTER TABLE settings ADD COLUMN visitor_permissions_json MEDIUMTEXT NULL"
            )
            db.commit()
    except Exception as e:
        print(f'visitor_permissions column ensure: {e}')


def _loads(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if x]
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data if x]
        if isinstance(data, dict) and isinstance(data.get('keys'), list):
            return [str(x) for x in data['keys'] if x]
    except (TypeError, json.JSONDecodeError):
        pass
    return []


def get_visitor_permission_keys() -> set[str]:
    """Effective visitor grants for this church site."""
    _ensure_column()
    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute("SELECT visitor_permissions_json FROM settings WHERE id = 1")
        row = cur.fetchone()
        if not row or row.get('visitor_permissions_json') in (None, ''):
            return set(DEFAULT_VISITOR_KEYS)
        keys = _loads(row.get('visitor_permissions_json'))
        return {k for k in keys if k in _ALL_VISITOR_KEYS}
    except Exception as e:
        print(f'get_visitor_permission_keys: {e}')
        return set(DEFAULT_VISITOR_KEYS)


def set_visitor_permission_keys(keys: list[str] | set[str]) -> list[str]:
    """Replace visitor grants. Returns cleaned list saved."""
    _ensure_column()
    clean = [k for k in list(dict.fromkeys(keys or [])) if k in _ALL_VISITOR_KEYS]
    payload = json.dumps(clean)
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "UPDATE settings SET visitor_permissions_json = %s WHERE id = 1",
            (payload,),
        )
        if cur.rowcount == 0:
            cur.execute(
                "INSERT INTO settings (id, visitor_permissions_json) VALUES (1, %s)",
                (payload,),
            )
        db.commit()
    except Exception as e:
        print(f'set_visitor_permission_keys: {e}')
        raise
    return clean


def visitor_has_permission(key: str) -> bool:
    if not key or key not in _ALL_VISITOR_KEYS:
        return False
    return key in get_visitor_permission_keys()


def visitor_can_view(area_id: str) -> bool:
    return visitor_has_permission(f'visitor_view_{area_id}')


def visitor_can_create(area_id: str) -> bool:
    return visitor_has_permission(f'visitor_create_{area_id}')


def visitor_can_comment(area_id: str) -> bool:
    return visitor_has_permission(f'visitor_comment_{area_id}')


def _area_all_keys(area: dict) -> list[str]:
    keys = []
    for act in area.get('actions') or []:
        keys.extend(act.get('keys') or [])
    return list(dict.fromkeys(keys))


def visitor_area_status_rows(granted: set[str] | list[str] | None = None) -> list[dict]:
    """Rows for the same expandable Access table UI."""
    g = set(granted if granted is not None else get_visitor_permission_keys())
    rows = []
    for area in VISITOR_AREA_MATRIX:
        actions_out = []
        for act in area.get('actions') or []:
            keys = act.get('keys') or []
            checked = any(k in g for k in keys)
            actions_out.append({**act, 'checked': checked})
        enabled = any(a['checked'] for a in actions_out)
        rows.append({
            **area,
            'enabled': enabled,
            'actions': actions_out,
            'status_label': 'ON' if enabled else 'OFF',
        })
    return rows


def keys_from_visitor_action_form(form) -> list[str]:
    """Same form fields as people Access: enable_<id>, act_<area>_<action>."""
    get = form.get if hasattr(form, 'get') else (lambda k, d=None: form.get(k, d) if isinstance(form, dict) else d)
    keys: list[str] = []
    for area in VISITOR_AREA_MATRIX:
        aid = area['id']
        enable_raw = get(f'enable_{aid}')
        any_act = False
        area_keys: list[str] = []
        for act in area.get('actions') or []:
            field = f"act_{aid}_{act['id']}"
            on = get(field) in ('1', 'on', 'yes', 'true', True)
            if on:
                any_act = True
                area_keys.extend(act.get('keys') or [])
        if enable_raw is not None and enable_raw not in ('1', 'on', 'yes', 'true', True):
            continue
        if enable_raw in ('1', 'on', 'yes', 'true', True) and not any_act:
            acts = area.get('actions') or []
            if acts:
                area_keys.extend(acts[0].get('keys') or [])
        elif not any_act and enable_raw is None:
            continue
        keys.extend(area_keys)
    return list(dict.fromkeys(k for k in keys if k in _ALL_VISITOR_KEYS))


def human_summary_visitor(granted: set[str] | list[str] | None = None) -> list[str]:
    lines = []
    for row in visitor_area_status_rows(granted):
        if not row['enabled']:
            continue
        acts = [a['label'] for a in row['actions'] if a.get('checked')]
        if acts:
            lines.append(f"{row['label']}: " + '; '.join(acts))
    return lines or ['Nothing — visitors cannot use community areas']
