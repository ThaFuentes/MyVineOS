# app/utils/access_templates.py
# Named tool templates you create freely (e.g. "Ticket desk", "New Member basics").
# Optional: mark one as default for new Members and one for new Staff.
# Apply any template to any person from Tools. Admin/Owner stay full access.

from __future__ import annotations

import json


VALID_FOR_ROLES = frozenset({'', 'Member', 'Staff', 'Admin', 'any'})


def ensure_templates_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS access_templates (
            id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            description TEXT NULL,
            for_role VARCHAR(20) NOT NULL DEFAULT 'any',
            is_default TINYINT(1) NOT NULL DEFAULT 0,
            permissions TEXT NOT NULL,
            created_by INT UNSIGNED NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_access_templates_name (name),
            KEY idx_access_templates_role (for_role),
            KEY idx_access_templates_default (is_default)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )


def _parse_perms(raw) -> list[str]:
    try:
        perms = json.loads(raw or '[]')
    except (TypeError, json.JSONDecodeError):
        perms = []
    if not isinstance(perms, list):
        return []
    return [str(p) for p in perms if p]


def _row(row) -> dict | None:
    if not row:
        return None
    if not isinstance(row, dict):
        # id, name, description, for_role, is_default, permissions, ...
        row = {
            'id': row[0],
            'name': row[1],
            'description': row[2],
            'for_role': row[3],
            'is_default': row[4],
            'permissions': row[5],
        }
    out = dict(row)
    out['permission_list'] = _parse_perms(out.get('permissions'))
    out['is_default'] = bool(out.get('is_default'))
    out['for_role'] = (out.get('for_role') or 'any') or 'any'
    return out


def list_templates(cur) -> list[dict]:
    ensure_templates_table(cur)
    cur.execute(
        """
        SELECT id, name, description, for_role, is_default, permissions,
               created_at, updated_at
        FROM access_templates
        ORDER BY is_default DESC, for_role, name
        """
    )
    return [_row(r) for r in (cur.fetchall() or []) if r]


def get_template(cur, template_id: int) -> dict | None:
    ensure_templates_table(cur)
    cur.execute(
        """
        SELECT id, name, description, for_role, is_default, permissions,
               created_at, updated_at
        FROM access_templates
        WHERE id = %s
        LIMIT 1
        """,
        (int(template_id),),
    )
    return _row(cur.fetchone())


def get_default_template_for_role(cur, role: str) -> dict | None:
    role = (role or '').strip()
    if role not in ('Member', 'Staff'):
        return None
    ensure_templates_table(cur)
    cur.execute(
        """
        SELECT id, name, description, for_role, is_default, permissions
        FROM access_templates
        WHERE is_default = 1 AND for_role = %s
        LIMIT 1
        """,
        (role,),
    )
    return _row(cur.fetchone())


def create_template(
    cur,
    *,
    name: str,
    description: str = '',
    for_role: str = 'any',
    is_default: bool = False,
    permissions: list[str] | None = None,
    created_by: int | None = None,
) -> int:
    ensure_templates_table(cur)
    name = (name or '').strip()
    if not name:
        raise ValueError('Name is required')
    for_role = (for_role or 'any').strip() or 'any'
    if for_role not in ('Member', 'Staff', 'Admin', 'any'):
        for_role = 'any'
    perms = list(dict.fromkeys(permissions or []))
    # Only one default per role
    if is_default and for_role in ('Member', 'Staff'):
        cur.execute(
            "UPDATE access_templates SET is_default = 0 WHERE for_role = %s AND is_default = 1",
            (for_role,),
        )
    elif is_default:
        is_default = False  # Admin/any cannot be "default for role" onboarding
    cur.execute(
        """
        INSERT INTO access_templates (name, description, for_role, is_default, permissions, created_by)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (name, (description or '').strip() or None, for_role, 1 if is_default else 0, json.dumps(perms), created_by),
    )
    return int(cur.lastrowid)


def update_template(
    cur,
    template_id: int,
    *,
    name: str,
    description: str = '',
    for_role: str = 'any',
    is_default: bool = False,
    permissions: list[str] | None = None,
) -> None:
    ensure_templates_table(cur)
    name = (name or '').strip()
    if not name:
        raise ValueError('Name is required')
    for_role = (for_role or 'any').strip() or 'any'
    if for_role not in ('Member', 'Staff', 'Admin', 'any'):
        for_role = 'any'
    perms = list(dict.fromkeys(permissions or []))
    if is_default and for_role in ('Member', 'Staff'):
        cur.execute(
            """
            UPDATE access_templates SET is_default = 0
            WHERE for_role = %s AND is_default = 1 AND id != %s
            """,
            (for_role, int(template_id)),
        )
    elif is_default:
        is_default = False
    cur.execute(
        """
        UPDATE access_templates
           SET name = %s,
               description = %s,
               for_role = %s,
               is_default = %s,
               permissions = %s
         WHERE id = %s
        """,
        (
            name,
            (description or '').strip() or None,
            for_role,
            1 if is_default else 0,
            json.dumps(perms),
            int(template_id),
        ),
    )


def delete_template(cur, template_id: int) -> bool:
    ensure_templates_table(cur)
    cur.execute("DELETE FROM access_templates WHERE id = %s", (int(template_id),))
    return cur.rowcount > 0


def apply_template_to_user(
    cur,
    user_id: int,
    template_id: int,
    granted_by: int | None = None,
    *,
    exact: bool = True,
) -> bool:
    """
    Apply a named template's tools to a user.
    exact=True: set_user_exact_access (YES/NO board matches template).
    """
    from app.utils.permissions import set_user_exact_access, set_user_direct_permissions

    tmpl = get_template(cur, template_id)
    if not tmpl:
        return False
    keys = tmpl.get('permission_list') or []
    if exact:
        set_user_exact_access(cur, user_id, keys, granted_by)
    else:
        set_user_direct_permissions(cur, user_id, keys, granted_by)
    return True


def apply_default_template_for_role(
    cur,
    user_id: int,
    role: str,
    granted_by: int | None = None,
) -> bool:
    """On create/promote: if a default template exists for Member/Staff, apply it."""
    tmpl = get_default_template_for_role(cur, role)
    if not tmpl:
        return False
    return apply_template_to_user(cur, user_id, tmpl['id'], granted_by, exact=True)


def seed_starter_templates(cur) -> None:
    """Create a couple of starter templates if the table is empty (first run only)."""
    ensure_templates_table(cur)
    cur.execute("SELECT COUNT(*) AS n FROM access_templates")
    row = cur.fetchone()
    n = int(row['n'] if isinstance(row, dict) else row[0]) if row else 0
    if n > 0:
        return
    from app.utils.permission_matrix import TEMPLATE_MEMBER_START_KEYS, TEMPLATE_STAFF_START_KEYS

    create_template(
        cur,
        name='New Member basics',
        description='Default for brand-new Members. Edit or make more templates anytime.',
        for_role='Member',
        is_default=True,
        permissions=list(TEMPLATE_MEMBER_START_KEYS),
    )
    create_template(
        cur,
        name='New Staff basics',
        description='Default when someone is first made Staff. Add more templates for special roles.',
        for_role='Staff',
        is_default=True,
        permissions=list(TEMPLATE_STAFF_START_KEYS),
    )
    print('Seeded starter access templates (New Member basics, New Staff basics)')


# --- legacy helpers used by older call sites (promote/create) ---

def ensure_user_in_template(cur, user_id: int, role: str, assigned_by: int | None = None) -> bool:
    """Apply default named template for role (replaces old system-group attach)."""
    return apply_default_template_for_role(cur, user_id, role, assigned_by)


def apply_role_template_on_role_change(
    cur,
    user_id: int,
    old_role: str | None,
    new_role: str | None,
    assigned_by: int | None = None,
) -> bool:
    old = (old_role or '').strip()
    new = (new_role or '').strip()
    if new not in ('Member', 'Staff'):
        return False
    if old == new:
        return False
    return apply_default_template_for_role(cur, user_id, new, assigned_by)
