# Schema definitions, themes, and safe validation for custom modules.

import re
import json
from datetime import datetime

SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$')
FIELD_KEY_RE = re.compile(r'^[a-z][a-z0-9_]{0,63}$')

ALLOWED_FIELD_TYPES = frozenset({
    'text', 'textarea', 'number', 'date', 'time', 'email', 'url', 'select', 'boolean',
})

MODULE_THEMES = {
    'ocean': {
        'label': 'Ocean',
        'icon_bg': 'rgba(0, 180, 220, 0.18)',
        'accent': '#00d4ff',
        'header_grad': 'linear-gradient(135deg, rgba(0,100,140,0.45), rgba(0,200,255,0.12))',
    },
    'sunset': {
        'label': 'Sunset',
        'icon_bg': 'rgba(255, 140, 60, 0.18)',
        'accent': '#ff9a4d',
        'header_grad': 'linear-gradient(135deg, rgba(180,70,20,0.45), rgba(255,160,80,0.12))',
    },
    'forest': {
        'label': 'Forest',
        'icon_bg': 'rgba(60, 180, 100, 0.18)',
        'accent': '#5cdb8b',
        'header_grad': 'linear-gradient(135deg, rgba(20,100,50,0.45), rgba(80,200,120,0.12))',
    },
    'royal': {
        'label': 'Royal',
        'icon_bg': 'rgba(140, 90, 220, 0.18)',
        'accent': '#b48cff',
        'header_grad': 'linear-gradient(135deg, rgba(80,40,160,0.45), rgba(160,100,255,0.12))',
    },
    'slate': {
        'label': 'Slate',
        'icon_bg': 'rgba(160, 170, 190, 0.15)',
        'accent': '#a8b4cc',
        'header_grad': 'linear-gradient(135deg, rgba(60,70,90,0.5), rgba(120,130,150,0.12))',
    },
    'youth': {
        'label': 'Youth Bright',
        'icon_bg': 'rgba(255, 80, 160, 0.15)',
        'accent': '#ff6eb4',
        'header_grad': 'linear-gradient(135deg, rgba(200,40,120,0.4), rgba(0,220,255,0.15))',
    },
}


def normalize_slug(raw: str) -> str:
    slug = (raw or '').strip().lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug[:64]


def validate_slug(slug: str) -> bool:
    return bool(slug and SLUG_RE.match(slug))


def parse_type_schema(schema_json) -> dict:
    if isinstance(schema_json, dict):
        return schema_json
    try:
        return json.loads(schema_json or '{}')
    except (json.JSONDecodeError, TypeError):
        return {}


def get_theme(theme_key: str) -> dict:
    return MODULE_THEMES.get(theme_key, MODULE_THEMES['ocean'])


def _clean_text(value, max_len=2000):
    if value is None:
        return ''
    text = str(value).strip()
    return text[:max_len]


def _clean_number(value):
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _clean_date(value):
    text = _clean_text(value, 32)
    if not text:
        return ''
    try:
        datetime.strptime(text, '%Y-%m-%d')
        return text
    except ValueError:
        return ''


def _clean_time(value):
    text = _clean_text(value, 16)
    if not text:
        return ''
    for fmt in ('%H:%M', '%H:%M:%S'):
        try:
            datetime.strptime(text, fmt)
            return text[:5]
        except ValueError:
            continue
    return ''


def _clean_email(value):
    text = _clean_text(value, 254).lower()
    if not text:
        return ''
    if re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', text):
        return text
    return ''


def _clean_url(value):
    text = _clean_text(value, 500)
    if not text:
        return ''
    if text.startswith(('http://', 'https://', '/')):
        return text
    return ''


def _clean_select(value, options):
    text = _clean_text(value, 120)
    if text in (options or []):
        return text
    return ''


def _clean_boolean(value):
    if value in (True, 'true', '1', 1, 'on', 'yes'):
        return True
    if value in (False, 'false', '0', 0, 'off', 'no', ''):
        return False
    return False


def enrich_schema_for_module(schema: dict, module: dict | None = None) -> dict:
    """
    Return a copy of schema with dynamic options filled in
    (e.g. approved bus route names from module settings).
    """
    import copy
    schema = copy.deepcopy(schema or {})
    if not module:
        return schema
    settings = module.get('settings') or {}
    if module.get('type_key') == 'bus_routes' or schema.get('bus_module'):
        routes = settings.get('approved_routes') or []
        names = [r.get('name') for r in routes if isinstance(r, dict) and r.get('name')]
        for field in schema.get('fields') or []:
            if field.get('key') == 'route_name':
                field['options'] = names
                if not names:
                    field['help'] = (
                        'No approved routes yet. A bus manager must add routes under Bus settings first.'
                    )
    return schema


def validate_bus_stop(cleaned: dict, settings: dict) -> str | None:
    """
    Enforce service area for bus stops.
    Stops must use an approved route and stay within max miles of the church.
    """
    settings = settings or {}
    routes = settings.get('approved_routes') or []
    if not routes:
        return (
            'No approved routes are set up yet. '
            'A bus manager must open Bus settings and add the routes they are willing to run first.'
        )

    route_name = (cleaned.get('route_name') or '').strip()
    if not route_name:
        return 'Choose an approved route for this stop.'

    route = next((r for r in routes if (r.get('name') or '') == route_name), None)
    if not route:
        return f'“{route_name}” is not an approved route. Pick one from the list or ask a manager to add it.'

    miles = cleaned.get('miles_from_church')
    if miles is None or miles == '':
        return 'Miles from church is required so we can keep stops inside the allowed area.'
    try:
        miles = float(miles)
    except (TypeError, ValueError):
        return 'Miles from church must be a number.'
    if miles < 0:
        return 'Miles from church cannot be negative.'

    try:
        global_max = float(settings.get('max_radius_miles') or 25)
    except (TypeError, ValueError):
        global_max = 25.0

    route_max = route.get('max_miles')
    try:
        route_max = float(route_max) if route_max not in (None, '') else None
    except (TypeError, ValueError):
        route_max = None

    limit = global_max
    if route_max is not None:
        limit = min(global_max, route_max)

    if miles > limit + 0.05:  # small float tolerance
        if route_max is not None and route_max < global_max:
            return (
                f'This stop is {miles:g} miles from church, but the “{route_name}” route '
                f'only allows up to {limit:g} miles (owner limit for that route).'
            )
        return (
            f'This stop is {miles:g} miles from church, but this bus only runs within '
            f'{limit:g} miles of the church. Pick a closer stop or ask a manager to raise the limit.'
        )

    cleaned['miles_from_church'] = miles
    return None


def validate_record_data(
    schema: dict,
    form_data,
    *,
    module: dict | None = None,
) -> tuple[dict | None, str | None]:
    """Validate POST data against a module type schema. Returns (clean_data, error)."""
    schema = enrich_schema_for_module(schema, module)
    fields = schema.get('fields') or []
    if not fields:
        return None, 'This module type has no field schema configured.'

    cleaned = {}
    title_field = schema.get('title_field')
    title_value = ''

    for field in fields:
        key = field.get('key', '')
        if not FIELD_KEY_RE.match(key):
            continue

        ftype = field.get('type', 'text')
        if ftype not in ALLOWED_FIELD_TYPES:
            continue

        raw = form_data.get(key)
        if ftype == 'textarea':
            val = _clean_text(raw, 8000)
        elif ftype == 'number':
            val = _clean_number(raw)
        elif ftype == 'date':
            val = _clean_date(raw)
        elif ftype == 'time':
            val = _clean_time(raw)
        elif ftype == 'email':
            val = _clean_email(raw)
        elif ftype == 'url':
            val = _clean_url(raw)
        elif ftype == 'select':
            val = _clean_select(raw, field.get('options'))
        elif ftype == 'boolean':
            val = _clean_boolean(raw)
        else:
            val = _clean_text(raw, 500)

        if field.get('required'):
            empty = val is None or val == ''
            if ftype == 'boolean':
                empty = False
            if empty:
                label = field.get('label', key)
                # Friendlier message when select options empty (no routes yet)
                if ftype == 'select' and not (field.get('options') or []):
                    return None, field.get('help') or f'{label} has no options yet.'
                return None, f'{label} is required.'

        cleaned[key] = val
        if key == title_field and val:
            title_value = str(val)[:255]

    if not title_value:
        for field in fields:
            if field.get('required'):
                key = field.get('key')
                if cleaned.get(key):
                    title_value = str(cleaned[key])[:255]
                    break

    if not title_value:
        title_value = 'Untitled'

    # Bus service-area rules
    if module and (
        module.get('type_key') == 'bus_routes' or schema.get('bus_module')
    ):
        bus_err = validate_bus_stop(cleaned, module.get('settings') or {})
        if bus_err:
            return None, bus_err
        # Title: "Route — Stop"
        rn = cleaned.get('route_name') or ''
        sn = cleaned.get('stop_name') or title_value
        if rn and sn:
            title_value = f'{rn} — {sn}'[:255]

    cleaned['_title'] = title_value
    return cleaned, None