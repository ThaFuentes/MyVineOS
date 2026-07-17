# Record payment for a recurring bill — optionally posts into Accounting.

from flask import redirect, url_for, flash, session, request
from app.utils.decorators import login_required
from .utils import is_bill_manager, user_can_access_bill
from app.models.db import get_db
from app.models.log import log_change
from datetime import datetime
import pymysql

from .accounting_bridge import (
    advance_next_due_date,
    post_bill_payment_to_accounting,
    resolve_accounts_for_payment,
)


def register_payment_routes(bp):
    @bp.route('/record_payment/<int:bill_id>', methods=['POST'])
    @login_required
    def record_payment(bill_id):
        user_id = session['user_id']
        is_manager = is_bill_manager()

        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)

        # Access check: manager or assigned only
        if not user_can_access_bill(bill_id, user_id):
            flash('You do not have access to record payment for this bill.', 'error')
            return redirect(url_for('dashboard.dashboard'))

        cur.execute("SELECT * FROM recurring_bills WHERE id = %s", (bill_id,))
        bill = cur.fetchone()
        if not bill:
            flash('Bill not found.', 'error')
            return redirect(url_for('bills.bills'))

        amount_raw = request.form.get('amount')
        payment_date = request.form.get('payment_date') or datetime.today().strftime('%Y-%m-%d')
        notes = request.form.get('notes', '').strip()
        payment_method = (request.form.get('payment_method') or '').strip()[:40]
        post_acct = request.form.get('post_to_accounting')
        # Default ON if bill says so and form didn't uncheck
        if post_acct is None:
            do_post = bool(bill.get('post_to_accounting', 1))
        else:
            do_post = post_acct in ('1', 'on', 'true', 'yes')

        if not amount_raw:
            flash('Amount is required.', 'error')
            return redirect(url_for('bills.view_bill', bill_id=bill_id))

        try:
            amount = float(amount_raw)
        except (TypeError, ValueError):
            flash('Invalid amount.', 'error')
            return redirect(url_for('bills.view_bill', bill_id=bill_id))

        if amount <= 0:
            flash('Amount must be greater than zero.', 'error')
            return redirect(url_for('bills.view_bill', bill_id=bill_id))

        accounts = resolve_accounts_for_payment(bill, {
            'expense_account_id': request.form.get('expense_account_id'),
            'payment_account_id': request.form.get('payment_account_id'),
        })

        try:
            cur2 = db.cursor()
            # Prefer columns if migrated
            try:
                cur2.execute(
                    """
                    INSERT INTO bill_payment_history
                        (bill_id, payment_date, amount, paid_by, notes, payment_method, posted_to_accounting)
                    VALUES (%s, %s, %s, %s, %s, %s, 0)
                    """,
                    (bill_id, payment_date, amount, user_id, notes or None, payment_method or None),
                )
            except Exception:
                cur2.execute(
                    """
                    INSERT INTO bill_payment_history (bill_id, payment_date, amount, paid_by, notes)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (bill_id, payment_date, amount, user_id, notes or None),
                )
            payment_id = cur2.lastrowid

            # Advance schedule for next cycle + mark current period paid
            next_due = advance_next_due_date(bill)
            try:
                cur2.execute(
                    """
                    UPDATE recurring_bills
                       SET current_status = 'pending',
                           next_due_date = %s,
                           updated_by = %s
                     WHERE id = %s
                    """,
                    (next_due, user_id, bill_id),
                )
            except Exception:
                cur2.execute(
                    """
                    UPDATE recurring_bills
                       SET current_status = 'paid', updated_by = %s
                     WHERE id = %s
                    """,
                    (user_id, bill_id),
                )

            db.commit()

            acct_ok = False
            acct_detail = ''
            if do_post:
                result = post_bill_payment_to_accounting(
                    bill=bill,
                    payment_id=payment_id,
                    amount=amount,
                    payment_date=payment_date,
                    notes=notes,
                    payment_method=payment_method or 'bill_pay',
                    expense_account_id=accounts.get('expense_account_id'),
                    payment_account_id=accounts.get('payment_account_id'),
                    created_by=user_id,
                )
                if result.get('ok'):
                    acct_ok = True
                    acct_detail = (
                        f"expense #{result.get('expense_id')}"
                        + (f", journal #{result.get('journal_entry_id')}" if result.get('journal_entry_id') else '')
                    )
                else:
                    flash(
                        f"Payment saved, but Accounting post failed: {result.get('error')}. "
                        "You can still find the payment under this bill; fix Chart of Accounts and re-check settings.",
                        'error',
                    )

            log_change(
                user_id,
                'record_payment',
                bill_id,
                change_details=(
                    f"Recorded payment of ${amount:.2f}"
                    + (f"; next due {next_due}" if next_due else '')
                    + (f"; accounting {acct_detail}" if acct_ok else '')
                ),
            )

            msg = f'Payment of ${amount:.2f} recorded.'
            if next_due:
                msg += f' Next due date set to {next_due}.'
            if acct_ok:
                msg += f' Posted to Accounting ({acct_detail}).'
            flash(msg, 'success')
            return redirect(url_for('bills.view_bill', bill_id=bill_id))

        except Exception as exc:
            db.rollback()
            flash('Failed to record payment.', 'error')
            print(f"Record payment error (ID {bill_id}): {exc}")
            import traceback
            traceback.print_exc()
            return redirect(url_for('bills.view_bill', bill_id=bill_id))
