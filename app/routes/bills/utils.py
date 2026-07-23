# Permission helpers for recurring bills — fine-grained view / create / edit / delete.
# Assigned members may still view/pay their own bills without any bills tool grant.

from flask import session, flash, redirect, url_for, abort
from functools import wraps

from app.utils.permissions import user_has_permission
from app.models.db import get_db
import pymysql

BILLS_ANY = (
    'view_bills',
    'create_bills',
    'edit_bills',
    'delete_bills',
    'manage_bills',
)


def can_view_bills() -> bool:
    """See the full bills list (not only assigned)."""
    return user_has_permission('view_bills') or any(
        user_has_permission(k)
        for k in ('create_bills', 'edit_bills', 'delete_bills', 'manage_bills')
    )


def can_create_bills() -> bool:
    return user_has_permission('create_bills')


def can_edit_bills() -> bool:
    return user_has_permission('edit_bills')


def can_delete_bills() -> bool:
    return user_has_permission('delete_bills')


def can_manage_bills() -> bool:
    """
    Backward-compatible "manager" flag: any bills tool grant (not assignment-only).
    Used for seeing all bills and manager UI. Prefer specific can_* helpers for buttons.
    """
    return any(user_has_permission(k) for k in BILLS_ANY)


def is_bill_manager() -> bool:
    """True when user can manage / see all bills (not just assigned ones)."""
    return can_manage_bills()


def user_has_bill_assignment(user_id: int | None = None) -> bool:
    """True if this member is assigned to at least one recurring bill."""
    uid = user_id or session.get('user_id')
    if not uid:
        return False
    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute(
            "SELECT 1 FROM recurring_bill_assignments WHERE user_id = %s LIMIT 1",
            (uid,),
        )
        return bool(cur.fetchone())
    except Exception:
        return False


def can_access_bills(user_id: int | None = None) -> bool:
    """
    Nav + entry point gate:
    - any bills permission, OR
    - assigned to one or more bills (view/pay only their assignments).
    """
    if can_manage_bills():
        return True
    return user_has_bill_assignment(user_id)


def user_can_access_bill(bill_id: int, user_id: int | None = None) -> bool:
    """Single-bill access: manager or assigned."""
    if can_manage_bills():
        return True
    uid = user_id or session.get('user_id')
    if not uid or not bill_id:
        return False
    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute(
            "SELECT 1 FROM recurring_bill_assignments WHERE bill_id = %s AND user_id = %s LIMIT 1",
            (bill_id, uid),
        )
        return bool(cur.fetchone())
    except Exception:
        return False


def bills_access_required(f):
    """Decorator: login + can_access_bills (manager or assigned)."""
    from app.utils.decorators import login_required

    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not can_access_bills():
            flash('You do not have access to Bills. Contact a staff member if you need an assignment.', 'error')
            try:
                from app.models.log import log_change
                log_change(
                    session.get('user_id'),
                    'unauthorized_access_attempt',
                    details='Denied bills access (no bills permission, no assignments)',
                )
            except Exception:
                pass
            return redirect(url_for('dashboard.dashboard'))
        return f(*args, **kwargs)

    return decorated
