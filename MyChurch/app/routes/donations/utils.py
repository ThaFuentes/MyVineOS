# app/routes/donations/utils.py
# Fine-grained donation permissions: view ≠ create ≠ edit ≠ delete.

from app.models.db import get_db
import pymysql

from app.utils.permissions import user_has_permission


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
REQUIRED_ROLES = ['Staff', 'Admin', 'Owner']
ADMIN_OWNER_ONLY = ['Admin', 'Owner']

# View pages: any donation key that expands to view, or legacy manage.
DONATIONS_VIEW_PERMISSIONS = (
    'view_donations',
    'create_donations',
    'edit_donations',
    'delete_donations',
    'manage_donations',
)


def can_view_donations() -> bool:
    """See donation lists / reports (read-only is enough)."""
    return user_has_permission('view_donations') or any(
        user_has_permission(k)
        for k in ('create_donations', 'edit_donations', 'delete_donations', 'manage_donations')
    )


def can_create_donations() -> bool:
    return user_has_permission('create_donations')


def can_edit_donations() -> bool:
    return user_has_permission('edit_donations')


def can_delete_donations() -> bool:
    return user_has_permission('delete_donations')


def can_manage_donations() -> bool:
    """
    Backward-compatible: True if user has any write capability.
    Prefer can_create / can_edit / can_delete in new templates.
    """
    return (
        can_create_donations()
        or can_edit_donations()
        or can_delete_donations()
        or user_has_permission('manage_donations')
    )


# ----------------------------------------------------------------------
# Church Info Helper
# ----------------------------------------------------------------------
def get_church_info():
    """Fetch church details from settings table - used in templates and exports."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute('''
        SELECT church_name, address, phone_number, pastor, tax_status 
        FROM settings LIMIT 1
    ''')
    row = cur.fetchone()
    return row or {}
