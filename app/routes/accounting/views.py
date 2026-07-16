# Accounting suite routes.

from __future__ import annotations

from flask import flash, redirect, render_template, request, session, url_for

from app.models import accounting as acct
from app.models.log import log_change
from app.utils.decorators import login_required, permission_required

from . import accounting_bp


def _uid():
    return session.get('user_id')


@accounting_bp.route('/')
@login_required
@permission_required('manage_accounting', 'manage_bills', 'manage_donations')
def dashboard():
    stats = acct.dashboard_stats()
    y = stats['year']
    recent_exp = acct.list_expenses(limit=8, start=f'{y}-01-01')
    recent_je = acct.list_journal_entries(limit=6)
    log_change(_uid(), 'view', change_details='Opened Accounting suite')
    return render_template(
        'accounting/dashboard.html',
        stats=stats,
        recent_exp=recent_exp,
        recent_je=recent_je,
    )


# ── Chart of accounts ───────────────────────────────────────────────────────

@accounting_bp.route('/accounts', methods=['GET', 'POST'])
@login_required
@permission_required('manage_accounting', 'manage_bills')
def accounts():
    if request.method == 'POST':
        try:
            aid = request.form.get('account_id')
            acct.save_account({
                'code': request.form.get('code'),
                'name': request.form.get('name'),
                'account_type': request.form.get('account_type'),
                'description': request.form.get('description'),
                'sort_order': request.form.get('sort_order') or 0,
                'is_active': request.form.get('is_active') == '1' if aid else True,
            }, int(aid) if aid else None)
            flash('Account saved.', 'success')
        except Exception as e:
            flash(str(e), 'error')
        return redirect(url_for('accounting.accounts'))

    rows = acct.list_accounts(active_only=False)
    for r in rows:
        r['bal'] = acct.account_balance(r['id'])
    return render_template(
        'accounting/accounts.html',
        accounts=rows,
        account_types=acct.ACCOUNT_TYPES,
    )


# ── Ledger ──────────────────────────────────────────────────────────────────

@accounting_bp.route('/ledger')
@login_required
@permission_required('manage_accounting', 'manage_bills')
def ledger():
    start = request.args.get('start') or f'{acct.church_year()}-01-01'
    end = request.args.get('end') or acct.church_today_str()
    entries = acct.list_journal_entries(limit=100, start=start, end=end)
    return render_template(
        'accounting/ledger.html',
        entries=entries,
        start=start,
        end=end,
    )


@accounting_bp.route('/ledger/new', methods=['GET', 'POST'])
@login_required
@permission_required('manage_accounting', 'manage_bills')
def journal_new():
    if request.method == 'POST':
        account_ids = request.form.getlist('account_id')
        debits = request.form.getlist('debit')
        credits = request.form.getlist('credit')
        descs = request.form.getlist('line_desc')
        lines = []
        for i, aid in enumerate(account_ids):
            if not aid:
                continue
            lines.append({
                'account_id': aid,
                'debit': debits[i] if i < len(debits) else 0,
                'credit': credits[i] if i < len(credits) else 0,
                'description': descs[i] if i < len(descs) else '',
            })
        try:
            eid = acct.post_journal_entry(
                entry_date=request.form.get('entry_date') or acct.church_today_str(),
                memo=request.form.get('memo'),
                reference=request.form.get('reference'),
                source='manual',
                created_by=_uid(),
                lines=lines,
            )
            flash(f'Journal entry #{eid} posted.', 'success')
            log_change(_uid(), 'create', eid, change_details='Posted journal entry')
            return redirect(url_for('accounting.ledger'))
        except Exception as e:
            flash(str(e), 'error')
    return render_template(
        'accounting/journal_form.html',
        accounts=acct.list_accounts(),
        today=acct.church_today_str(),
    )


@accounting_bp.route('/ledger/<int:entry_id>')
@login_required
@permission_required('manage_accounting', 'manage_bills')
def journal_detail(entry_id):
    entry = acct.get_journal_entry(entry_id)
    if not entry:
        flash('Entry not found.', 'error')
        return redirect(url_for('accounting.ledger'))
    return render_template('accounting/journal_detail.html', entry=entry)


# ── Vendors ─────────────────────────────────────────────────────────────────

@accounting_bp.route('/vendors', methods=['GET', 'POST'])
@login_required
@permission_required('manage_accounting', 'manage_bills')
def vendors():
    if request.method == 'POST':
        try:
            vid = request.form.get('vendor_id')
            is_active = True
            if vid:
                # checkbox: only present when checked
                is_active = request.form.get('is_active') in ('1', 'on', 'true', 'yes')
            new_id = acct.save_vendor({
                'name': request.form.get('name'),
                'contact_name': request.form.get('contact_name'),
                'email': request.form.get('email'),
                'phone': request.form.get('phone'),
                'address': request.form.get('address'),
                'website': request.form.get('website'),
                'tax_id': request.form.get('tax_id'),
                'default_expense_account_id': request.form.get('default_expense_account_id') or None,
                'payment_terms': request.form.get('payment_terms'),
                'notes': request.form.get('notes'),
                'is_active': is_active,
            }, int(vid) if vid else None)
            flash('Vendor updated.' if vid else f'Vendor added (#{new_id}).', 'success')
            log_change(_uid(), 'update' if vid else 'create', new_id, change_details='Vendor saved')
        except Exception as e:
            flash(str(e), 'error')
        return redirect(url_for('accounting.vendors'))

    q = request.args.get('q') or ''
    edit_id = request.args.get('edit')
    edit_vendor = None
    if edit_id:
        try:
            edit_vendor = acct.get_vendor(int(edit_id))
        except (TypeError, ValueError):
            edit_vendor = None
    return render_template(
        'accounting/vendors.html',
        vendors=acct.list_vendors(active_only=False, search=q or None),
        expense_accounts=acct.list_accounts(account_type='expense'),
        search_q=q,
        edit_vendor=edit_vendor,
    )


# ── Expenses ────────────────────────────────────────────────────────────────

@accounting_bp.route('/expenses')
@login_required
@permission_required('manage_accounting', 'manage_bills')
def expenses():
    start = request.args.get('start') or f'{acct.church_year()}-01-01'
    end = request.args.get('end') or acct.church_today_str()
    return render_template(
        'accounting/expenses.html',
        expenses=acct.list_expenses(limit=150, start=start, end=end),
        start=start,
        end=end,
    )


@accounting_bp.route('/expenses/new', methods=['GET', 'POST'])
@login_required
@permission_required('manage_accounting', 'manage_bills')
def expense_new():
    if request.method == 'POST':
        try:
            vendor_id = request.form.get('vendor_id') or None
            vendor_name = (request.form.get('vendor_name') or '').strip()
            # If they typed a new vendor name without picking an existing one, create it
            if vendor_name and not vendor_id:
                try:
                    vendor_id = acct.save_vendor({
                        'name': vendor_name,
                        'is_active': True,
                        'default_expense_account_id': request.form.get('expense_account_id') or None,
                        'notes': 'Created from expense form',
                    })
                    flash(f'New vendor “{vendor_name}” added to the vendor list.', 'info')
                except Exception as ve:
                    print(f'expense_new auto-vendor: {ve}')
            eid = acct.create_expense({
                'expense_date': request.form.get('expense_date'),
                'vendor_id': vendor_id,
                'vendor_name': vendor_name,
                'amount': request.form.get('amount'),
                'expense_account_id': request.form.get('expense_account_id'),
                'payment_account_id': request.form.get('payment_account_id') or None,
                'payment_method': request.form.get('payment_method'),
                'reference': request.form.get('reference'),
                'description': request.form.get('description'),
            }, created_by=_uid())
            flash(f'Expense #{eid} recorded and posted to the ledger.', 'success')
            log_change(_uid(), 'create', eid, change_details='Recorded expense')
            return redirect(url_for('accounting.expenses'))
        except Exception as e:
            flash(str(e), 'error')
    return render_template(
        'accounting/expense_form.html',
        vendors=acct.list_vendors(),
        expense_accounts=acct.list_accounts(account_type='expense'),
        asset_accounts=acct.list_accounts(account_type='asset'),
        today=acct.church_today_str(),
    )


# ── Budgets ─────────────────────────────────────────────────────────────────

@accounting_bp.route('/budgets')
@login_required
@permission_required('manage_accounting', 'manage_bills')
def budgets():
    return render_template('accounting/budgets.html', budgets=acct.list_budgets())


@accounting_bp.route('/budgets/new', methods=['GET', 'POST'])
@login_required
@permission_required('manage_accounting', 'manage_bills')
def budget_new():
    if request.method == 'POST':
        year = int(request.form.get('fiscal_year') or acct.church_year())
        bid = acct.create_budget({
            'name': request.form.get('name') or f'{year} Operating Budget',
            'fiscal_year': year,
            'start_date': request.form.get('start_date') or f'{year}-01-01',
            'end_date': request.form.get('end_date') or f'{year}-12-31',
            'notes': request.form.get('notes'),
        }, created_by=_uid())
        # Seed expense + income lines at 0
        for a in acct.list_accounts(account_type='expense') + acct.list_accounts(account_type='income'):
            acct.set_budget_line(bid, a['id'], 0)
        flash('Budget created — set line amounts.', 'success')
        return redirect(url_for('accounting.budget_detail', budget_id=bid))
    return render_template('accounting/budget_form.html', year=acct.church_year())


@accounting_bp.route('/budgets/<int:budget_id>', methods=['GET', 'POST'])
@login_required
@permission_required('manage_accounting', 'manage_bills')
def budget_detail(budget_id):
    budget = acct.get_budget(budget_id)
    if not budget:
        flash('Budget not found.', 'error')
        return redirect(url_for('accounting.budgets'))

    if request.method == 'POST':
        account_ids = request.form.getlist('account_id')
        amounts = request.form.getlist('amount')
        for i, aid in enumerate(account_ids):
            if not aid:
                continue
            amt = amounts[i] if i < len(amounts) else 0
            acct.set_budget_line(budget_id, int(aid), amt)
        flash('Budget lines saved.', 'success')
        return redirect(url_for('accounting.budget_detail', budget_id=budget_id))

    return render_template(
        'accounting/budget_detail.html',
        budget=budget,
        lines=acct.budget_vs_actual(budget_id),
    )


# ── Payroll ─────────────────────────────────────────────────────────────────

@accounting_bp.route('/payroll')
@login_required
@permission_required('manage_accounting', 'manage_bills')
def payroll():
    edit_employee = None
    edit_id = request.args.get('edit')
    if edit_id:
        try:
            edit_employee = acct.get_employee(int(edit_id))
        except (TypeError, ValueError):
            edit_employee = None
    system_users = []
    try:
        from app.models.db import get_db
        import pymysql
        cur = get_db().cursor(pymysql.cursors.DictCursor)
        cur.execute("""
            SELECT id, username, first_name, last_name
            FROM users
            WHERE COALESCE(is_shadow_banned,0)=0
              AND role NOT IN ('banned')
            ORDER BY last_name, first_name
            LIMIT 500
        """)
        system_users = list(cur.fetchall() or [])
    except Exception as e:
        print(f'payroll system users: {e}')
    return render_template(
        'accounting/payroll.html',
        employees=acct.list_employees(active_only=False),
        pay_runs=acct.list_pay_runs(),
        edit_employee=edit_employee,
        system_users=system_users,
    )


@accounting_bp.route('/payroll/employees', methods=['POST'])
@login_required
@permission_required('manage_accounting', 'manage_bills')
def employee_save():
    try:
        eid = request.form.get('employee_id')
        active = True
        if eid:
            active = request.form.get('active') in ('1', 'on', 'true', 'yes')
        uid = request.form.get('user_id') or None
        new_id = acct.save_employee({
            'user_id': uid,
            'first_name': request.form.get('first_name'),
            'last_name': request.form.get('last_name'),
            'email': request.form.get('email'),
            'phone': request.form.get('phone'),
            'title': request.form.get('title'),
            'pay_type': request.form.get('pay_type'),
            'pay_rate': request.form.get('pay_rate'),
            'pay_frequency': request.form.get('pay_frequency'),
            'expense_account_id': request.form.get('expense_account_id') or None,
            'hire_date': request.form.get('hire_date') or None,
            'active': active,
            'notes': request.form.get('notes'),
        }, int(eid) if eid else None)
        flash('Person updated on payroll.' if eid else 'Person added to payroll (no system login required).', 'success')
        log_change(_uid(), 'update' if eid else 'create', new_id, change_details='Payroll person saved')
    except Exception as e:
        flash(str(e), 'error')
    return redirect(url_for('accounting.payroll'))


@accounting_bp.route('/payroll/runs/new', methods=['POST'])
@login_required
@permission_required('manage_accounting', 'manage_bills')
def pay_run_new():
    try:
        rid = acct.create_pay_run({
            'period_start': request.form.get('period_start'),
            'period_end': request.form.get('period_end'),
            'pay_date': request.form.get('pay_date'),
            'notes': request.form.get('notes'),
        }, created_by=_uid(), fill_active=request.form.get('fill_active') == '1')
        flash('Pay run created as draft.', 'success')
        return redirect(url_for('accounting.pay_run_detail', pay_run_id=rid))
    except Exception as e:
        flash(str(e), 'error')
        return redirect(url_for('accounting.payroll'))


@accounting_bp.route('/payroll/runs/<int:pay_run_id>', methods=['GET', 'POST'])
@login_required
@permission_required('manage_accounting', 'manage_bills')
def pay_run_detail(pay_run_id):
    run = acct.get_pay_run(pay_run_id)
    if not run:
        flash('Pay run not found.', 'error')
        return redirect(url_for('accounting.payroll'))

    if request.method == 'POST':
        action = request.form.get('action')
        try:
            if action == 'add_item' and run['status'] == 'draft':
                acct.add_pay_item(pay_run_id, {
                    'employee_id': request.form.get('employee_id'),
                    'description': request.form.get('description'),
                    'gross_pay': request.form.get('gross_pay'),
                    'deductions': request.form.get('deductions') or 0,
                    'hours': request.form.get('hours'),
                })
                flash('Pay item added.', 'success')
            elif action == 'post':
                je = acct.post_pay_run(pay_run_id, created_by=_uid())
                flash(f'Pay run posted to ledger (JE #{je}).', 'success')
                log_change(_uid(), 'update', pay_run_id, change_details='Posted payroll run')
        except Exception as e:
            flash(str(e), 'error')
        return redirect(url_for('accounting.pay_run_detail', pay_run_id=pay_run_id))

    items = acct.list_pay_items(pay_run_id)
    total_gross = sum(float(i['gross_pay'] or 0) for i in items)
    total_net = sum(float(i['net_pay'] or 0) for i in items)
    return render_template(
        'accounting/pay_run_detail.html',
        run=run,
        items=items,
        employees=acct.list_employees(),
        total_gross=total_gross,
        total_net=total_net,
    )


# ── Reports ─────────────────────────────────────────────────────────────────

@accounting_bp.route('/reports')
@login_required
@permission_required('manage_accounting', 'manage_bills', 'manage_donations')
def reports():
    start = request.args.get('start') or f'{acct.church_year()}-01-01'
    end = request.args.get('end') or acct.church_today_str()
    report = request.args.get('report') or 'pnl'
    data = None
    if report == 'pnl':
        data = acct.profit_and_loss(start, end)
    elif report == 'trial':
        data = acct.trial_balance(as_of=end)
    elif report == 'budget':
        budgets = acct.list_budgets()
        bid = request.args.get('budget_id', type=int)
        if not bid and budgets:
            bid = budgets[0]['id']
        data = {'budgets': budgets, 'budget_id': bid, 'lines': acct.budget_vs_actual(bid) if bid else []}
    return render_template(
        'accounting/reports.html',
        report=report,
        start=start,
        end=end,
        data=data,
    )
