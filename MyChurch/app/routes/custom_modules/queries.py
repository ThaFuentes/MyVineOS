import json
import pymysql
from app.models.db import get_db
from .schemas import parse_type_schema, get_theme


def app_permission_keys(slug: str) -> tuple[str, str]:
    """Stable permission keys stored on the auto-created group."""
    safe = (slug or 'app').replace('-', '_')[:48]
    return f'access_app_{safe}', f'manage_app_{safe}'


def create_permission_group_for_module(name: str, slug: str, description: str, user_id: int) -> int:
    """Create a dedicated permission group for a Church App."""
    from app.routes.groups.queries import create_group

    access_key, manage_key = app_permission_keys(slug)
    group_description = (
        f'Auto-created for Church App "{name}". '
        f'Members can view the app; Group Managers can add, edit, and delete entries. '
        f'{description or ""}'.strip()
    )
    permissions = json.dumps([access_key, manage_key])
    group_name = f'App: {name}'[:255]

    return create_group(
        name=group_name,
        description=group_description[:2000],
        visibility='private',
        permissions=permissions,
        user_id=user_id,
    )


def parse_module_settings(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw or '{}')
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def default_bus_settings() -> dict:
    return {
        'bus_start_location': '',
        'church_location': '',
        'max_radius_miles': 25,
        'approved_routes': [],  # [{name, max_miles, notes}]
    }


def _hydrate_module(row: dict) -> dict:
    if not row:
        return row
    row['schema'] = parse_type_schema(row.get('schema_json'))
    row['theme_config'] = get_theme(row.get('theme') or 'ocean')
    settings = parse_module_settings(row.get('settings_json'))
    if (row.get('type_key') or '') == 'bus_routes':
        base = default_bus_settings()
        base.update(settings or {})
        # Normalize approved routes
        routes = base.get('approved_routes') or []
        clean_routes = []
        for r in routes:
            if not isinstance(r, dict):
                continue
            name = (r.get('name') or '').strip()
            if not name:
                continue
            try:
                max_m = r.get('max_miles')
                max_m = float(max_m) if max_m not in (None, '') else None
            except (TypeError, ValueError):
                max_m = None
            clean_routes.append({
                'name': name[:120],
                'max_miles': max_m,
                'notes': (r.get('notes') or '').strip()[:500],
            })
        base['approved_routes'] = clean_routes
        try:
            base['max_radius_miles'] = float(base.get('max_radius_miles') or 25)
        except (TypeError, ValueError):
            base['max_radius_miles'] = 25.0
        settings = base
    row['settings'] = settings
    return row


def get_module_types(active_only=True):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    sql = "SELECT * FROM custom_module_types"
    if active_only:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY FIELD(type_key, 'bus_routes', 'youth_group', 'weekly_schedule', 'resource_list'), name"
    cur.execute(sql)
    rows = cur.fetchall()
    for row in rows:
        row['schema'] = parse_type_schema(row.get('schema_json'))
    return rows


def get_module_type(type_key: str):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM custom_module_types WHERE type_key = %s", (type_key,))
    row = cur.fetchone()
    if row:
        row['schema'] = parse_type_schema(row.get('schema_json'))
    return row


def get_all_modules(include_disabled=False):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    sql = """
        SELECT m.*, t.name AS type_name, t.icon AS type_icon, t.schema_json,
               g.name AS group_name, mg.name AS manage_group_name
        FROM custom_modules m
        JOIN custom_module_types t ON t.type_key = m.type_key
        LEFT JOIN groups g ON g.id = m.group_id
        LEFT JOIN groups mg ON mg.id = m.manage_group_id
    """
    if not include_disabled:
        sql += " WHERE m.is_enabled = 1"
    sql += " ORDER BY m.name"
    cur.execute(sql)
    return [_hydrate_module(r) for r in cur.fetchall()]


def get_module_by_slug(slug: str):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT m.*, t.name AS type_name, t.icon AS type_icon, t.schema_json,
               g.name AS group_name, mg.name AS manage_group_name
        FROM custom_modules m
        JOIN custom_module_types t ON t.type_key = m.type_key
        LEFT JOIN groups g ON g.id = m.group_id
        LEFT JOIN groups mg ON mg.id = m.manage_group_id
        WHERE m.slug = %s AND m.is_enabled = 1
    """, (slug,))
    return _hydrate_module(cur.fetchone())


def get_module_by_id(module_id: int):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT m.*, t.name AS type_name, t.icon AS type_icon, t.schema_json,
               g.name AS group_name, mg.name AS manage_group_name
        FROM custom_modules m
        JOIN custom_module_types t ON t.type_key = m.type_key
        LEFT JOIN groups g ON g.id = m.group_id
        LEFT JOIN groups mg ON mg.id = m.manage_group_id
        WHERE m.id = %s
    """, (module_id,))
    return _hydrate_module(cur.fetchone())


def get_dashboard_modules(user_id, user_role, is_logged_in):
    modules = get_all_modules(include_disabled=False)
    from .permissions import can_view_module
    return [
        m for m in modules
        if m.get('show_on_dashboard') and can_view_module(m, user_id, user_role, is_logged_in)
    ]


def create_module(data: dict, user_id: int):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO custom_modules
                (type_key, name, slug, description, theme, visibility,
                 group_id, manage_group_id, show_on_dashboard, is_enabled, created_by, updated_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data['type_key'], data['name'], data['slug'], data.get('description', ''),
            data.get('theme', 'ocean'), data.get('visibility', 'members'),
            data.get('group_id'), data.get('manage_group_id'),
            1 if data.get('show_on_dashboard', True) else 0,
            1 if data.get('is_enabled', True) else 0,
            user_id, user_id,
        ))
        db.commit()
        return cur.lastrowid
    except Exception:
        db.rollback()
        raise


def update_module(module_id: int, data: dict, user_id: int):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            UPDATE custom_modules
            SET name = %s, slug = %s, description = %s, theme = %s, visibility = %s,
                group_id = %s, manage_group_id = %s, show_on_dashboard = %s, is_enabled = %s,
                updated_by = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (
            data['name'], data['slug'], data.get('description', ''),
            data.get('theme', 'ocean'), data.get('visibility', 'members'),
            data.get('group_id'), data.get('manage_group_id'),
            1 if data.get('show_on_dashboard', True) else 0,
            1 if data.get('is_enabled', True) else 0,
            user_id, module_id,
        ))
        db.commit()
        return cur.rowcount > 0
    except Exception:
        db.rollback()
        raise


def delete_module(module_id: int):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM custom_modules WHERE id = %s", (module_id,))
        db.commit()
        return cur.rowcount > 0
    except Exception:
        db.rollback()
        raise


def get_records(module_id: int, published_only=True):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    sql = """
        SELECT r.*, u.username AS creator_username,
               u.first_name AS creator_first, u.last_name AS creator_last
        FROM custom_module_records r
        LEFT JOIN users u ON u.id = r.created_by
        WHERE r.module_id = %s
    """
    if published_only:
        sql += " AND r.is_published = 1"
    sql += " ORDER BY r.updated_at DESC, r.id DESC"
    cur.execute(sql, (module_id,))
    rows = cur.fetchall()
    for row in rows:
        try:
            row['data'] = json.loads(row.get('data_json') or '{}')
        except json.JSONDecodeError:
            row['data'] = {}
    return rows


def get_record(record_id: int, module_id: int):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT r.*, u.username AS creator_username
        FROM custom_module_records r
        LEFT JOIN users u ON u.id = r.created_by
        WHERE r.id = %s AND r.module_id = %s
    """, (record_id, module_id))
    row = cur.fetchone()
    if row:
        try:
            row['data'] = json.loads(row.get('data_json') or '{}')
        except json.JSONDecodeError:
            row['data'] = {}
    return row


def create_record(module_id: int, title: str, data: dict, user_id: int):
    db = get_db()
    cur = db.cursor()
    payload = {k: v for k, v in data.items() if not k.startswith('_')}
    try:
        cur.execute("""
            INSERT INTO custom_module_records
                (module_id, title, data_json, is_published, created_by, updated_by)
            VALUES (%s, %s, %s, 1, %s, %s)
        """, (module_id, title[:255], json.dumps(payload), user_id, user_id))
        db.commit()
        return cur.lastrowid
    except Exception:
        db.rollback()
        raise


def update_record(record_id: int, module_id: int, title: str, data: dict, user_id: int):
    db = get_db()
    cur = db.cursor()
    payload = {k: v for k, v in data.items() if not k.startswith('_')}
    try:
        cur.execute("""
            UPDATE custom_module_records
            SET title = %s, data_json = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND module_id = %s
        """, (title[:255], json.dumps(payload), user_id, record_id, module_id))
        db.commit()
        return cur.rowcount > 0
    except Exception:
        db.rollback()
        raise


def delete_record(record_id: int, module_id: int):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            "DELETE FROM custom_module_records WHERE id = %s AND module_id = %s",
            (record_id, module_id),
        )
        db.commit()
        return cur.rowcount > 0
    except Exception:
        db.rollback()
        raise


def ensure_settings_column():
    """Idempotent: add settings_json if missing (for installs without full rebuild)."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'custom_modules'
              AND COLUMN_NAME = 'settings_json'
            """
        )
        if not cur.fetchone():
            cur.execute("ALTER TABLE custom_modules ADD COLUMN settings_json TEXT NULL")
            db.commit()
    except Exception:
        db.rollback()


def update_module_settings(module_id: int, settings: dict, user_id: int) -> bool:
    ensure_settings_column()
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            UPDATE custom_modules
            SET settings_json = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (json.dumps(settings or {}), user_id, module_id),
        )
        db.commit()
        return cur.rowcount > 0
    except Exception:
        db.rollback()
        raise


def get_groups_for_select():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT id, name FROM groups ORDER BY name")
    return cur.fetchall()