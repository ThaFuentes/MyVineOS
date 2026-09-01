# Church accounting suite: COA, ledger, vendors, expenses, budgets, payroll.

from flask import Blueprint

accounting_bp = Blueprint(
    'accounting',
    __name__,
    url_prefix='/accounting',
)

from . import views  # noqa: E402, F401

__all__ = ['accounting_bp']
