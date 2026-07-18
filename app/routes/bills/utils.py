# app/routes/bills/utils.py
# Permission helpers for recurring bills — group-based capability keys.
# Admin/Owner: full access via user_has_permission. Staff/Member: manage_bills or assignment.

from flask import session, flash, redirect, url_for, abort
from functools import wraps

from app.utils.permissions import user_has_permission
from app.models.db import get_db
import pymysql


def can_manage_bills() -> bool:
    """Full bills management (create, assign, delete) via manage_bills (Admin/Owner auto-pass)."""
    return user_has_permission('manage_bills')


def is_bill_manager() -> bool:
    """True when user can manage all bills (not just assigned ones)."""
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
    - manage_bills (Admin/Owner always have this via full access), OR
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
                    details=f'Denied bills access (no manage_bills, no assignments)',
                )
            except Exception:
                pass
            return redirect(url_for('dashboard.dashboard'))
        return f(*args, **kwargs)

    return decorated
