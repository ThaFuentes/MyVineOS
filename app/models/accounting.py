# Accounting: chart of accounts, double-entry ledger, vendors, expenses, budgets, payroll.

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

import pymysql

from app.models.db import get_db
from app.utils.time_utils import now_church, utc_now

ACCOUNT_TYPES = (
    ('asset', 'Asset'),
    ('liability', 'Liability'),
    ('equity', 'Equity / Net Assets'),
    ('income', 'Income'),
    ('expense', 'Expense'),
)


def _cur():
    return get_db().cursor(pymysql.cursors.DictCursor)


def _money(val) -> Decimal:
    try:
        d = Decimal(str(val or 0))
    except Exception:
        d = Decimal('0')
    return d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _f(val) -> float:
    return float(_money(val))


def church_today() -> date:
    return now_church().date()


def church_today_str() -> str:
    return church_today().strftime('%Y-%m-%d')


def church_year() -> int:
    return church_today().year


# ── Chart of accounts ───────────────────────────────────────────────────────

def list_accounts(active_only=True, account_type: str | None = None) -> list[dict]:
    cur = _cur()
    sql = "SELECT * FROM acct_accounts WHERE 1=1"
    params: list[Any] = []
    if active_only:
        sql += " AND is_active = 1"
    if account_type:
        sql += " AND account_type = %s"
        params.append(account_type)
    sql += " ORDER BY sort_order, code"
    cur.execute(sql, params)
    return list(cur.fetchall() or [])


def get_account(account_id: int) -> Optional[dict]:
    cur = _cur()
    cur.execute("SELECT * FROM acct_accounts WHERE id=%s", (account_id,))
    return cur.fetchone()


def get_account_by_code(code: str) -> Optional[dict]:
    cur = _cur()
    cur.execute("SELECT * FROM acct_accounts WHERE code=%s", (code,))
    return cur.fetchone()


def save_account(data: dict, account_id: int | None = None) -> int:
    db = get_db()
    cur = db.cursor()
    atype = (data.get('account_type') or 'expense').lower()
    if atype not in dict(ACCOUNT_TYPES):
        atype = 'expense'
    fields = (
        (data.get('code') or '').strip()[:32],
        (data.get('name') or 'Account').strip()[:255],
        atype,
        int(data['parent_id']) if data.get('parent_id') else None,
        1 if data.get('is_active', True) else 0,
        (data.get('description') or '').strip()[:500] or None,
        int(data.get('sort_order') or 0),
    )
    if not fields[0]:
        raise ValueError('Account code is required.')
    if account_id:
        cur.execute(
            """
            UPDATE acct_accounts SET
                code=%s, name=%s, account_type=%s, parent_id=%s,
                is_active=%s, description=%s, sort_order=%s
            WHERE id=%s
            """,
            (*fields, account_id),
        )
        db.commit()
        return account_id
    cur.execute(
        """
        INSERT INTO acct_accounts
            (code, name, account_type, parent_id, is_active, description, sort_order)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        """,
        fields,
    )
    db.commit()
    return cur.lastrowid


def account_balance(account_id: int, as_of: str | None = None, start: str | None = None) -> dict:
    """Returns {debit, credit, balance} with sign by account type."""
    cur = _cur()
    sql = """
        SELECT COALESCE(SUM(l.debit),0) AS debits, COALESCE(SUM(l.credit),0) AS credits
        FROM acct_journal_lines l
        JOIN acct_journal_entries e ON e.id = l.entry_id
        WHERE l.account_id = %s AND e.status = 'posted'
    """
    params: list[Any] = [account_id]
    if start:
        sql += " AND e.entry_date >= %s"
        params.append(start)
    if as_of:
        sql += " AND e.entry_date <= %s"
        params.append(as_of)
    cur.execute(sql, params)
    row = cur.fetchone() or {}
    debits = _money(row.get('debits'))
    credits = _money(row.get('credits'))
    acct = get_account(account_id) or {}
    atype = acct.get('account_type') or 'expense'
    # Assets & expenses increase with debit; liabilities, equity, income with credit
    if atype in ('asset', 'expense'):
        bal = debits - credits
    else:
        bal = credits - debits
    return {'debit': _f(debits), 'credit': _f(credits), 'balance': _f(bal)}


# ── Journal / ledger ────────────────────────────────────────────────────────

def post_journal_entry(
    *,
    entry_date: str,
    lines: list[dict],
    memo: str = '',
    reference: str = '',
    source: str = 'manual',
    source_id: int | None = None,
    created_by: int | None = None,
) -> int:
    """
    lines: [{account_id, debit, credit, description}]
    Must balance (sum debit == sum credit).
    """
    cleaned = []
    total_d = Decimal('0')
    total_c = Decimal('0')
    for ln in lines:
        d = _money(ln.get('debit'))
        c = _money(ln.get('credit'))
        if d < 0 or c < 0:
            raise ValueError('Debit/credit cannot be negative.')
        if d > 0 and c > 0:
            raise ValueError('A line cannot have both debit and credit.')
        if d == 0 and c == 0:
            continue
        aid = int(ln.get('account_id') or 0)
        if not aid:
            raise ValueError('Each line needs an account.')
        cleaned.append({
            'account_id': aid,
            'debit': d,
            'credit': c,
            'description': (ln.get('description') or '').strip()[:500] or None,
        })
        total_d += d
        total_c += c
    if not cleaned:
        raise ValueError('Add at least one journal line.')
    if total_d != total_c:
        raise ValueError(f'Entry does not balance (debits {total_d} ≠ credits {total_c}).')

    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO acct_journal_entries
            (entry_date, reference, memo, source, source_id, status, created_by)
        VALUES (%s,%s,%s,%s,%s,'posted',%s)
        """,
        (
            entry_date or church_today_str(),
            (reference or '').strip()[:80] or None,
            (memo or '').strip()[:500] or None,
            source[:40],
            source_id,
            created_by,
        ),
    )
    eid = cur.lastrowid
    for ln in cleaned:
        cur.execute(
            """
            INSERT INTO acct_journal_lines (entry_id, account_id, description, debit, credit)
            VALUES (%s,%s,%s,%s,%s)
            """,
            (eid, ln['account_id'], ln['description'], _f(ln['debit']), _f(ln['credit'])),
        )
    db.commit()
    return eid


def list_journal_entries(limit=50, start=None, end=None) -> list[dict]:
    cur = _cur()
    sql = "SELECT * FROM acct_journal_entries WHERE status='posted'"
    params: list[Any] = []
    if start:
        sql += " AND entry_date >= %s"
        params.append(start)
    if end:
        sql += " AND entry_date <= %s"
        params.append(end)
    sql += " ORDER BY entry_date DESC, id DESC LIMIT %s"
    params.append(int(limit))
    cur.execute(sql, params)
    rows = list(cur.fetchall() or [])
    for r in rows:
        r['lines'] = get_journal_lines(r['id'])
        r['total'] = sum(_f(l['debit']) for l in r['lines'])
    return rows


def get_journal_entry(entry_id: int) -> Optional[dict]:
    cur = _cur()
    cur.execute("SELECT * FROM acct_journal_entries WHERE id=%s", (entry_id,))
    row = cur.fetchone()
    if row:
        row['lines'] = get_journal_lines(entry_id)
    return row


def get_journal_lines(entry_id: int) -> list[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT l.*, a.code AS account_code, a.name AS account_name, a.account_type
        FROM acct_journal_lines l
        JOIN acct_accounts a ON a.id = l.account_id
        WHERE l.entry_id = %s
        ORDER BY l.id
        """,
        (entry_id,),
    )
    return list(cur.fetchall() or [])


def void_journal_entry(entry_id: int) -> None:
    """Soft-void by marking status (lines remain for audit)."""
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE acct_journal_entries SET status='void' WHERE id=%s", (entry_id,))
    db.commit()


# ── Vendors ─────────────────────────────────────────────────────────────────

def list_vendors(active_only=True, search: str | None = None) -> list[dict]:
    cur = _cur()
    sql = "SELECT * FROM acct_vendors WHERE 1=1"
    params: list[Any] = []
    if active_only:
        sql += " AND is_active = 1"
    if search:
        like = f"%{search}%"
        sql += " AND (name LIKE %s OR contact_name LIKE %s OR email LIKE %s)"
        params.extend([like, like, like])
    sql += " ORDER BY name"
    cur.execute(sql, params)
    return list(cur.fetchall() or [])


def get_vendor(vendor_id: int) -> Optional[dict]:
    cur = _cur()
    cur.execute("SELECT * FROM acct_vendors WHERE id=%s", (vendor_id,))
    return cur.fetchone()


def save_vendor(data: dict, vendor_id: int | None = None) -> int:
    db = get_db()
    cur = db.cursor()
    fields = (
        (data.get('name') or '').strip()[:255],
        (data.get('contact_name') or '').strip()[:160] or None,
        (data.get('email') or '').strip()[:255] or None,
        (data.get('phone') or '').strip()[:40] or None,
        (data.get('address') or '').strip() or None,
        (data.get('website') or '').strip()[:500] or None,
        (data.get('tax_id') or '').strip()[:64] or None,
        int(data['default_expense_account_id']) if data.get('default_expense_account_id') else None,
        (data.get('payment_terms') or '').strip()[:80] or None,
        (data.get('notes') or '').strip() or None,
        1 if data.get('is_active', True) else 0,
    )
    if not fields[0]:
        raise ValueError('Vendor name is required.')
    if vendor_id:
        cur.execute(
            """
            UPDATE acct_vendors SET
                name=%s, contact_name=%s, email=%s, phone=%s, address=%s, website=%s,
                tax_id=%s, default_expense_account_id=%s, payment_terms=%s, notes=%s, is_active=%s
            WHERE id=%s
            """,
            (*fields, vendor_id),
        )
        db.commit()
        return vendor_id
    cur.execute(
        """
        INSERT INTO acct_vendors
            (name, contact_name, email, phone, address, website, tax_id,
             default_expense_account_id, payment_terms, notes, is_active)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        fields,
    )
    db.commit()
    return cur.lastrowid


# ── Expenses ────────────────────────────────────────────────────────────────

def list_expenses(limit=80, start=None, end=None) -> list[dict]:
    cur = _cur()
    sql = """
        SELECT x.*, v.name AS vendor_display,
               ea.code AS expense_code, ea.name AS expense_account_name,
               pa.code AS payment_code, pa.name AS payment_account_name
        FROM acct_expenses x
        LEFT JOIN acct_vendors v ON v.id = x.vendor_id
        LEFT JOIN acct_accounts ea ON ea.id = x.expense_account_id
        LEFT JOIN acct_accounts pa ON pa.id = x.payment_account_id
        WHERE 1=1
    """
    params: list[Any] = []
    if start:
        sql += " AND x.expense_date >= %s"
        params.append(start)
    if end:
        sql += " AND x.expense_date <= %s"
        params.append(end)
    sql += " ORDER BY x.expense_date DESC, x.id DESC LIMIT %s"
    params.append(int(limit))
    cur.execute(sql, params)
    return list(cur.fetchall() or [])


def get_expense(expense_id: int) -> Optional[dict]:
    cur = _cur()
    cur.execute("SELECT * FROM acct_expenses WHERE id=%s", (expense_id,))
    return cur.fetchone()


def create_expense(data: dict, created_by: int | None = None, post_ledger: bool = True) -> int:
    amount = _money(data.get('amount'))
    if amount <= 0:
        raise ValueError('Amount must be greater than zero.')
    expense_account_id = int(data.get('expense_account_id') or 0)
    if not expense_account_id:
        raise ValueError('Expense account is required.')
    payment_account_id = int(data['payment_account_id']) if data.get('payment_account_id') else None
    if not payment_account_id:
        cash = get_account_by_code('1000')
        payment_account_id = cash['id'] if cash else None
    if not payment_account_id:
        raise ValueError('Payment (cash) account is required.')

    vendor_id = int(data['vendor_id']) if data.get('vendor_id') else None
    vendor_name = (data.get('vendor_name') or '').strip()[:255] or None
    if vendor_id and not vendor_name:
        v = get_vendor(vendor_id)
        vendor_name = v['name'] if v else None

    db = get_db()
    cur = db.cursor()
    bill_id = int(data['bill_id']) if data.get('bill_id') else None
    bill_payment_id = int(data['bill_payment_id']) if data.get('bill_payment_id') else None
    try:
        cur.execute(
            """
            INSERT INTO acct_expenses
                (expense_date, vendor_id, vendor_name, amount, expense_account_id,
                 payment_account_id, payment_method, reference, description, status,
                 bill_id, bill_payment_id, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'posted',%s,%s,%s)
            """,
            (
                data.get('expense_date') or church_today_str(),
                vendor_id,
                vendor_name,
                _f(amount),
                expense_account_id,
                payment_account_id,
                (data.get('payment_method') or '').strip()[:40] or None,
                (data.get('reference') or '').strip()[:80] or None,
                (data.get('description') or '').strip()[:500] or None,
                bill_id,
                bill_payment_id,
                created_by,
            ),
        )
    except Exception:
        cur.execute(
            """
            INSERT INTO acct_expenses
                (expense_date, vendor_id, vendor_name, amount, expense_account_id,
                 payment_account_id, payment_method, reference, description, status, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'posted',%s)
            """,
            (
                data.get('expense_date') or church_today_str(),
                vendor_id,
                vendor_name,
                _f(amount),
                expense_account_id,
                payment_account_id,
                (data.get('payment_method') or '').strip()[:40] or None,
                (data.get('reference') or '').strip()[:80] or None,
                (data.get('description') or '').strip()[:500] or None,
                created_by,
            ),
        )
    eid = cur.lastrowid
    db.commit()

    if post_ledger:
        je = post_journal_entry(
            entry_date=data.get('expense_date') or church_today_str(),
            memo=data.get('description') or f'Expense #{eid}',
            reference=data.get('reference') or f'EXP-{eid}',
            source='expense',
            source_id=eid,
            created_by=created_by,
            lines=[
                {'account_id': expense_account_id, 'debit': amount, 'credit': 0,
                 'description': data.get('description')},
                {'account_id': payment_account_id, 'debit': 0, 'credit': amount,
                 'description': data.get('description')},
            ],
        )
        cur.execute("UPDATE acct_expenses SET journal_entry_id=%s WHERE id=%s", (je, eid))
        db.commit()
    return eid


# ── Budgets ─────────────────────────────────────────────────────────────────

def list_budgets() -> list[dict]:
    cur = _cur()
    cur.execute("SELECT * FROM acct_budgets ORDER BY fiscal_year DESC, name")
    return list(cur.fetchall() or [])


def get_budget(budget_id: int) -> Optional[dict]:
    cur = _cur()
    cur.execute("SELECT * FROM acct_budgets WHERE id=%s", (budget_id,))
    return cur.fetchone()


def create_budget(data: dict, created_by: int | None = None) -> int:
    year = int(data.get('fiscal_year') or church_year())
    start = data.get('start_date') or f'{year}-01-01'
    end = data.get('end_date') or f'{year}-12-31'
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO acct_budgets (name, fiscal_year, start_date, end_date, status, notes, created_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            (data.get('name') or f'{year} Budget').strip()[:160],
            year,
            start,
            end,
            data.get('status') or 'active',
            (data.get('notes') or '').strip() or None,
            created_by,
        ),
    )
    db.commit()
    return cur.lastrowid


def list_budget_lines(budget_id: int) -> list[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT bl.*, a.code, a.name AS account_name, a.account_type
        FROM acct_budget_lines bl
        JOIN acct_accounts a ON a.id = bl.account_id
        WHERE bl.budget_id = %s
        ORDER BY a.sort_order, a.code
        """,
        (budget_id,),
    )
    return list(cur.fetchall() or [])


def set_budget_line(budget_id: int, account_id: int, amount, notes: str = '') -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO acct_budget_lines (budget_id, account_id, amount, notes)
        VALUES (%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE amount=VALUES(amount), notes=VALUES(notes)
        """,
        (budget_id, account_id, _f(_money(amount)), (notes or '').strip()[:255] or None),
    )
    db.commit()


def budget_vs_actual(budget_id: int) -> list[dict]:
    budget = get_budget(budget_id)
    if not budget:
        return []
    lines = list_budget_lines(budget_id)
    out = []
    for ln in lines:
        actual = account_balance(
            ln['account_id'],
            start=str(budget['start_date'])[:10],
            as_of=str(budget['end_date'])[:10],
        )['balance']
        # For income, balance is positive income; for expense, positive expense
        budgeted = _f(ln['amount'])
        variance = budgeted - abs(actual) if ln['account_type'] == 'expense' else abs(actual) - budgeted
        # Simpler: show budgeted, actual (absolute for comparison), variance budgeted-actual for expenses
        act = abs(actual)
        if ln['account_type'] == 'expense':
            variance = budgeted - act  # under budget is positive
        else:
            variance = act - budgeted  # income over budget is positive
        out.append({
            **ln,
            'budgeted': budgeted,
            'actual': act,
            'variance': round(variance, 2),
            'pct': round(100.0 * act / budgeted, 1) if budgeted else None,
        })
    return out


# ── Payroll ─────────────────────────────────────────────────────────────────

def list_employees(active_only=True) -> list[dict]:
    cur = _cur()
    sql = "SELECT * FROM acct_employees"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY last_name, first_name"
    cur.execute(sql)
    return list(cur.fetchall() or [])


def get_employee(employee_id: int) -> Optional[dict]:
    cur = _cur()
    cur.execute("SELECT * FROM acct_employees WHERE id=%s", (employee_id,))
    return cur.fetchone()


def save_employee(data: dict, employee_id: int | None = None) -> int:
    db = get_db()
    cur = db.cursor()
    fields = (
        int(data['user_id']) if data.get('user_id') else None,
        (data.get('first_name') or '').strip()[:100],
        (data.get('last_name') or '').strip()[:100],
        (data.get('email') or '').strip()[:255] or None,
        (data.get('phone') or '').strip()[:40] or None,
        (data.get('title') or '').strip()[:120] or None,
        (data.get('pay_type') or 'salary')[:24],
        _f(_money(data.get('pay_rate'))),
        (data.get('pay_frequency') or 'biweekly')[:24],
        int(data['expense_account_id']) if data.get('expense_account_id') else None,
        1 if data.get('active', True) else 0,
        data.get('hire_date') or None,
        (data.get('notes') or '').strip() or None,
    )
    if not fields[1] or not fields[2]:
        raise ValueError('First and last name are required.')
    if employee_id:
        cur.execute(
            """
            UPDATE acct_employees SET
                user_id=%s, first_name=%s, last_name=%s, email=%s, phone=%s, title=%s,
                pay_type=%s, pay_rate=%s, pay_frequency=%s, expense_account_id=%s,
                active=%s, hire_date=%s, notes=%s
            WHERE id=%s
            """,
            (*fields, employee_id),
        )
        db.commit()
        return employee_id
    cur.execute(
        """
        INSERT INTO acct_employees
            (user_id, first_name, last_name, email, phone, title, pay_type, pay_rate,
             pay_frequency, expense_account_id, active, hire_date, notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        fields,
    )
    db.commit()
    return cur.lastrowid


def list_pay_runs(limit=40) -> list[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT pr.*,
               (SELECT COUNT(*) FROM acct_pay_items i WHERE i.pay_run_id = pr.id) AS item_count,
               (SELECT COALESCE(SUM(net_pay),0) FROM acct_pay_items i WHERE i.pay_run_id = pr.id) AS total_net
        FROM acct_pay_runs pr
        ORDER BY pr.pay_date DESC, pr.id DESC
        LIMIT %s
        """,
        (limit,),
    )
    return list(cur.fetchall() or [])


def get_pay_run(pay_run_id: int) -> Optional[dict]:
    cur = _cur()
    cur.execute("SELECT * FROM acct_pay_runs WHERE id=%s", (pay_run_id,))
    return cur.fetchone()


def list_pay_items(pay_run_id: int) -> list[dict]:
    cur = _cur()
    cur.execute(
        """
        SELECT i.*, e.first_name, e.last_name, e.title
        FROM acct_pay_items i
        JOIN acct_employees e ON e.id = i.employee_id
        WHERE i.pay_run_id = %s
        ORDER BY e.last_name, e.first_name
        """,
        (pay_run_id,),
    )
    return list(cur.fetchall() or [])


def create_pay_run(data: dict, created_by: int | None = None, fill_active: bool = True) -> int:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO acct_pay_runs (period_start, period_end, pay_date, status, notes, created_by)
        VALUES (%s,%s,%s,'draft',%s,%s)
        """,
        (
            data.get('period_start') or church_today_str(),
            data.get('period_end') or church_today_str(),
            data.get('pay_date') or church_today_str(),
            (data.get('notes') or '').strip() or None,
            created_by,
        ),
    )
    rid = cur.lastrowid
    db.commit()
    if fill_active:
        for emp in list_employees(active_only=True):
            rate = _money(emp.get('pay_rate'))
            add_pay_item(rid, {
                'employee_id': emp['id'],
                'description': emp.get('title') or emp.get('pay_type'),
                'gross_pay': rate,
                'deductions': 0,
                'net_pay': rate,
            })
    return rid


def add_pay_item(pay_run_id: int, data: dict) -> int:
    gross = _money(data.get('gross_pay'))
    ded = _money(data.get('deductions'))
    net = _money(data.get('net_pay')) if data.get('net_pay') not in (None, '') else (gross - ded)
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO acct_pay_items
            (pay_run_id, employee_id, description, gross_pay, deductions, net_pay, hours, notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            pay_run_id,
            int(data['employee_id']),
            (data.get('description') or '').strip()[:255] or None,
            _f(gross),
            _f(ded),
            _f(net),
            float(data['hours']) if data.get('hours') not in (None, '') else None,
            (data.get('notes') or '').strip()[:500] or None,
        ),
    )
    db.commit()
    return cur.lastrowid


def post_pay_run(pay_run_id: int, created_by: int | None = None) -> int:
    """Post payroll to ledger: Dr Salaries, Cr Cash (net total)."""
    run = get_pay_run(pay_run_id)
    if not run:
        raise ValueError('Pay run not found')
    if run['status'] == 'posted':
        raise ValueError('Pay run already posted')
    items = list_pay_items(pay_run_id)
    if not items:
        raise ValueError('Add pay items before posting.')
    total_gross = sum(_money(i['gross_pay']) for i in items)
    total_net = sum(_money(i['net_pay']) for i in items)
    total_ded = sum(_money(i['deductions']) for i in items)

    sal = get_account_by_code('5000') or get_account_by_code('5800')
    cash = get_account_by_code('1000')
    liab = get_account_by_code('2100')
    if not sal or not cash:
        raise ValueError('Chart of accounts missing Salaries (5000) or Cash (1000).')

    lines = [
        {'account_id': sal['id'], 'debit': total_gross, 'credit': 0, 'description': f'Payroll run #{pay_run_id}'},
        {'account_id': cash['id'], 'debit': 0, 'credit': total_net, 'description': f'Payroll net #{pay_run_id}'},
    ]
    if total_ded > 0 and liab:
        lines.append({
            'account_id': liab['id'], 'debit': 0, 'credit': total_ded,
            'description': f'Payroll withholdings #{pay_run_id}',
        })
    # If no liability account and deductions, fold into cash reduction already using net
    je = post_journal_entry(
        entry_date=str(run['pay_date'])[:10],
        memo=f'Payroll {run["period_start"]} – {run["period_end"]}',
        reference=f'PAY-{pay_run_id}',
        source='payroll',
        source_id=pay_run_id,
        created_by=created_by,
        lines=lines,
    )
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE acct_pay_runs SET status='posted', journal_entry_id=%s, posted_at=%s WHERE id=%s",
        (je, utc_now(), pay_run_id),
    )
    db.commit()
    return je


# ── Reports & dashboard ─────────────────────────────────────────────────────

def trial_balance(as_of: str | None = None) -> list[dict]:
    accounts = list_accounts(active_only=True)
    rows = []
    for a in accounts:
        bal = account_balance(a['id'], as_of=as_of)
        if bal['debit'] == 0 and bal['credit'] == 0:
            continue
        rows.append({**a, **bal})
    return rows


def profit_and_loss(start: str, end: str) -> dict:
    income_accts = list_accounts(account_type='income')
    expense_accts = list_accounts(account_type='expense')
    income_rows, expense_rows = [], []
    total_income = Decimal('0')
    total_expense = Decimal('0')
    for a in income_accts:
        b = account_balance(a['id'], start=start, as_of=end)
        if b['balance'] == 0:
            continue
        income_rows.append({**a, 'amount': b['balance']})
        total_income += _money(b['balance'])
    for a in expense_accts:
        b = account_balance(a['id'], start=start, as_of=end)
        if b['balance'] == 0:
            continue
        expense_rows.append({**a, 'amount': b['balance']})
        total_expense += _money(b['balance'])
    return {
        'start': start,
        'end': end,
        'income': income_rows,
        'expenses': expense_rows,
        'total_income': _f(total_income),
        'total_expenses': _f(total_expense),
        'net': _f(total_income - total_expense),
    }


def dashboard_stats() -> dict:
    y = church_year()
    start = f'{y}-01-01'
    end = church_today_str()
    pl = profit_and_loss(start, end)
    cur = _cur()
    stats = {
        'year': y,
        'ytd_income': pl['total_income'],
        'ytd_expenses': pl['total_expenses'],
        'ytd_net': pl['net'],
    }
    for key, sql in [
        ('vendors', "SELECT COUNT(*) AS n FROM acct_vendors WHERE is_active=1"),
        ('accounts', "SELECT COUNT(*) AS n FROM acct_accounts WHERE is_active=1"),
        ('employees', "SELECT COUNT(*) AS n FROM acct_employees WHERE active=1"),
        ('open_pay_runs', "SELECT COUNT(*) AS n FROM acct_pay_runs WHERE status='draft'"),
    ]:
        try:
            cur.execute(sql)
            stats[key] = int((cur.fetchone() or {}).get('n') or 0)
        except Exception:
            stats[key] = 0
    try:
        cur.execute(
            """
            SELECT COALESCE(SUM(amount),0) AS n FROM acct_expenses
            WHERE expense_date >= %s AND expense_date <= %s
            """,
            (start, end),
        )
        stats['ytd_expense_entries'] = _f((cur.fetchone() or {}).get('n'))
    except Exception:
        stats['ytd_expense_entries'] = 0
    cash = get_account_by_code('1000')
    stats['cash_balance'] = account_balance(cash['id'])['balance'] if cash else 0
    return stats


def post_donation_income(donation_id: int, amount, donation_date: str, memo: str = '', created_by=None) -> int | None:
    """
    Post a donation into the ledger: Debit Cash (1000) / Credit Tithes & Offerings (4000).
    Idempotent — one journal entry per donation id.
    """
    if not donation_id:
        return None
    # Already posted?
    cur = _cur()
    cur.execute(
        """
        SELECT id FROM acct_journal_entries
        WHERE source = 'donation' AND source_id = %s AND status = 'posted'
        LIMIT 1
        """,
        (int(donation_id),),
    )
    existing = cur.fetchone()
    if existing:
        return int(existing['id'])

    income = get_account_by_code('4000')
    cash = get_account_by_code('1000')
    if not income or not cash:
        return None
    amt = _money(amount)
    if amt <= 0:
        return None
    return post_journal_entry(
        entry_date=donation_date or church_today_str(),
        memo=memo or f'Donation #{donation_id}',
        reference=f'DON-{donation_id}',
        source='donation',
        source_id=int(donation_id),
        created_by=created_by,
        lines=[
            {'account_id': cash['id'], 'debit': amt, 'credit': 0, 'description': memo or f'Donation #{donation_id}'},
            {'account_id': income['id'], 'debit': 0, 'credit': amt, 'description': memo or f'Donation #{donation_id}'},
        ],
    )


def void_donation_income(donation_id: int) -> bool:
    """Void the ledger entry for a donation (if any)."""
    if not donation_id:
        return False
    cur = _cur()
    cur.execute(
        """
        SELECT id FROM acct_journal_entries
        WHERE source = 'donation' AND source_id = %s AND status = 'posted'
        """,
        (int(donation_id),),
    )
    rows = cur.fetchall() or []
    if not rows:
        return False
    for row in rows:
        void_journal_entry(int(row['id']))
    return True
