# Accounting permission helpers — fine-grained view / create / edit / delete.
from flask import abort, flash, session

from app.utils.permissions import user_has_permission
from app.models.log import log_change

# Any accounting key opens the suite in nav / dashboard.
ACCOUNTING_ANY = (
    'view_accounting',
    'create_accounting',
    'edit_accounting',
    'delete_accounting',
    'manage_accounting',
)


def can_view_accounting() -> bool:
    return user_has_permission('view_accounting')


def can_create_accounting() -> bool:
    return user_has_permission('create_accounting')


def can_edit_accounting() -> bool:
    return user_has_permission('edit_accounting')


def can_delete_accounting() -> bool:
    return user_has_permission('delete_accounting')


def can_access_accounting() -> bool:
    """Nav / suite entry: any accounting action (view alone is enough)."""
    return any(user_has_permission(k) for k in ACCOUNTING_ANY)


def deny_accounting(needed: str) -> None:
    flash('You do not have permission for that accounting action.', 'error')
    try:
        log_change(
            user_id=session.get('user_id'),
            action='unauthorized_access_attempt',
            details=f'Denied accounting action needing {needed}',
        )
    except Exception:
        pass
    abort(403)


def require_view_accounting() -> None:
    if not can_view_accounting():
        deny_accounting('view_accounting')


def require_create_accounting() -> None:
    if not can_create_accounting():
        deny_accounting('create_accounting')


def require_edit_accounting() -> None:
    if not can_edit_accounting():
        deny_accounting('edit_accounting')


def require_delete_accounting() -> None:
    if not can_delete_accounting():
        deny_accounting('delete_accounting')
