# Bridge: recurring bill payments → accounting expenses + double-entry ledger.

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional


def _as_date(val) -> date | None:
    if val is None or val == '':
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    try:
        return datetime.strptime(str(val)[:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def advance_next_due_date(bill: dict, from_date: date | None = None) -> Optional[str]:
    """Compute the next due date after a payment based on bill frequency."""
    freq = (bill.get('frequency') or 'monthly').lower()
    base = from_date or _as_date(bill.get('next_due_date')) or date.today()
    if freq == 'daily':
        nxt = base + timedelta(days=1)
    elif freq == 'weekly':
        nxt = base + timedelta(days=7)
    elif freq == 'biweekly':
        nxt = base + timedelta(days=14)
    elif freq == 'quarterly':
        # ~3 months
        month = base.month - 1 + 3
        year = base.year + month // 12
        month = month % 12 + 1
        day = min(base.day, 28)
        nxt = date(year, month, day)
    elif freq == 'yearly':
        try:
            nxt = date(base.year + 1, base.month, base.day)
        except ValueError:
            nxt = date(base.year + 1, base.month, 28)
    else:  # monthly
        month = base.month - 1 + 1
        year = base.year + month // 12
        month = month % 12 + 1
        day = min(base.day, 28)
        due_day = bill.get('due_day')
        if due_day:
            try:
                day = min(int(due_day), 28)
            except (TypeError, ValueError):
                pass
        nxt = date(year, month, day)
    return nxt.isoformat()


def find_or_create_vendor_for_bill(bill: dict) -> Optional[int]:
    """Match/create an accounting vendor from the bill's vendor_name."""
    name = (bill.get('vendor_name') or bill.get('bill_name') or '').strip()
    if not name:
        return None
    try:
        from app.models import accounting as acct
        vendors = acct.list_vendors(active_only=True, search=name)
        for v in vendors or []:
            if (v.get('name') or '').strip().lower() == name.lower():
                return int(v['id'])
        # create lightweight vendor
        return acct.save_vendor({
            'name': name[:255],
            'phone': (bill.get('phone1') or '').strip()[:40] or None,
            'address': (bill.get('address') or '').strip() or None,
            'website': (bill.get('payment_url') or bill.get('login_url') or '').strip()[:500] or None,
            'default_expense_account_id': bill.get('expense_account_id'),
            'notes': f'Auto-created from recurring bill #{bill.get("id")}',
            'is_active': True,
        })
    except Exception as e:
        print(f"find_or_create_vendor_for_bill: {e}")
        return None


def resolve_accounts_for_payment(bill: dict, form: dict | None = None) -> dict[str, Any]:
    """Pick expense + payment accounts from form, bill defaults, or chart defaults."""
    from app.models import accounting as acct
    form = form or {}

    exp_id = form.get('expense_account_id') or bill.get('expense_account_id')
    pay_id = form.get('payment_account_id') or bill.get('payment_account_id')
    try:
        exp_id = int(exp_id) if exp_id else None
    except (TypeError, ValueError):
        exp_id = None
    try:
        pay_id = int(pay_id) if pay_id else None
    except (TypeError, ValueError):
        pay_id = None

    if not exp_id:
        # Prefer Facilities & Utilities for common utilities bills, else Other Expenses
        for code in ('5200', '5500', '5800'):
            a = acct.get_account_by_code(code)
            if a:
                exp_id = int(a['id'])
                break
    if not pay_id:
        cash = acct.get_account_by_code('1000')
        if cash:
            pay_id = int(cash['id'])

    return {'expense_account_id': exp_id, 'payment_account_id': pay_id}


def post_bill_payment_to_accounting(
    *,
    bill: dict,
    payment_id: int,
    amount: float,
    payment_date: str,
    notes: str = '',
    payment_method: str = '',
    expense_account_id: int | None = None,
    payment_account_id: int | None = None,
    created_by: int | None = None,
) -> dict:
    """
    Create acct_expenses row + balanced journal entry for a bill payment.
    Returns {ok, expense_id, journal_entry_id, error}.
    """
    from app.models import accounting as acct
    from app.models.db import get_db
    import pymysql

    try:
        accounts = resolve_accounts_for_payment(
            bill,
            {
                'expense_account_id': expense_account_id,
                'payment_account_id': payment_account_id,
            },
        )
        exp_id = accounts.get('expense_account_id')
        pay_acct = accounts.get('payment_account_id')
        if not exp_id or not pay_acct:
            return {
                'ok': False,
                'error': 'Accounting chart missing expense or cash account. Open Accounting → Chart of Accounts first.',
            }

        vendor_id = find_or_create_vendor_for_bill(bill)
        vendor_name = (bill.get('vendor_name') or bill.get('bill_name') or 'Vendor').strip()[:255]
        desc = (
            f"Bill payment: {bill.get('bill_name') or 'Bill'}"
            + (f" — {notes}" if notes else '')
        )[:500]
        ref = f"BILL-{bill.get('id')}-PAY-{payment_id}"

        expense_id = acct.create_expense(
            {
                'expense_date': payment_date,
                'vendor_id': vendor_id,
                'vendor_name': vendor_name,
                'amount': amount,
                'expense_account_id': exp_id,
                'payment_account_id': pay_acct,
                'payment_method': (payment_method or '').strip()[:40] or 'bill_pay',
                'reference': ref,
                'description': desc,
                'bill_id': bill.get('id'),
                'bill_payment_id': payment_id,
            },
            created_by=created_by,
            post_ledger=True,
        )

        # Link expense back to bill payment
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute("SELECT journal_entry_id FROM acct_expenses WHERE id=%s", (expense_id,))
        row = cur.fetchone() or {}
        je_id = row.get('journal_entry_id')
        try:
            cur.execute(
                "UPDATE acct_expenses SET bill_id=%s, bill_payment_id=%s WHERE id=%s",
                (bill.get('id'), payment_id, expense_id),
            )
        except Exception:
            pass
        cur.execute(
            """
            UPDATE bill_payment_history
               SET expense_id=%s, journal_entry_id=%s, posted_to_accounting=1,
                   payment_method=COALESCE(payment_method, %s)
             WHERE id=%s
            """,
            (expense_id, je_id, (payment_method or 'bill_pay')[:40], payment_id),
        )
        db.commit()
        return {
            'ok': True,
            'expense_id': expense_id,
            'journal_entry_id': je_id,
            'error': None,
        }
    except Exception as e:
        print(f"post_bill_payment_to_accounting: {e}")
        import traceback
        traceback.print_exc()
        return {'ok': False, 'error': str(e)[:300]}
