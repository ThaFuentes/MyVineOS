# app/routes/bills/utils.py
# Permission helpers for recurring bills - group-based with Staff/Admin/Owner global override.

from app.utils.permissions import user_has_permission


def can_manage_bills() -> bool:
    return user_has_permission('manage_bills')


def is_bill_manager() -> bool:
    """True when user can manage all bills (not just assigned ones)."""
    return can_manage_bills()