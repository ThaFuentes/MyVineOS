# app/routes/bills/views.py
# Full path: MyVineChurch/app/routes/bills/views.py
# File name: views.py
# Brief, detailed purpose: Single bill detail view (/bills/<int:bill_id>).
# Clean full separate page.
# Decrypts credentials for display (using centralized model).
# Requires login + access check (manager or assigned user).

from flask import render_template, session, redirect, url_for, flash, request, jsonify
from app.utils.decorators import login_required
from .utils import is_bill_manager, bills_access_required, user_can_access_bill
from app.models.db import get_db
from app.models.log import log_change
from app.models.credentials import decrypt_credential
from datetime import date
from werkzeug.security import check_password_hash
import pymysql

def register_view_routes(bp):
    @bp.route('/<int:bill_id>')
    @bills_access_required
    def view_bill(bill_id):
        user_id = session['user_id']
        is_manager = is_bill_manager()

        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)

        # Fetch the bill
        cur.execute("SELECT * FROM recurring_bills WHERE id = %s", (bill_id,))
        bill = cur.fetchone()

        if not bill:
            flash('Failed to load bill.', 'error')
            return redirect(url_for('bills.bills'))

        # Access check: manager OR assigned user
        if not user_can_access_bill(bill_id, user_id):
            flash('You do not have access to this bill.', 'error')
            log_change(
                user_id, 'unauthorized_access_attempt',
                target_id=bill_id,
                change_details=f'Denied view_bill #{bill_id}',
            )
            return redirect(url_for('dashboard.dashboard'))

        # Fetch assignments
        cur.execute("""
            SELECT u.id, u.first_name, u.last_name, u.username, u.email,
                   rb.remind_me
            FROM recurring_bill_assignments rb
            JOIN users u ON rb.user_id = u.id
            WHERE rb.bill_id = %s
        """, (bill_id,))
        assignments = cur.fetchall()

        # Fetch payment history (+ optional accounting links + payer name)
        cur.execute("""
            SELECT h.*,
                   CONCAT(IFNULL(u.first_name,''), ' ', IFNULL(u.last_name,'')) AS paid_by_name
            FROM bill_payment_history h
            LEFT JOIN users u ON u.id = h.paid_by
            WHERE h.bill_id = %s
            ORDER BY h.payment_date DESC, h.id DESC
        """, (bill_id,))
        history = cur.fetchall()

        # Today's date for Record Payment form
        today_str = date.today().isoformat()

        # Accounting account choices for payment form
        expense_accounts = []
        payment_accounts = []
        try:
            from app.models import accounting as acct
            expense_accounts = acct.list_accounts(active_only=True, account_type='expense')
            # Cash / bank-style assets for payment side
            assets = acct.list_accounts(active_only=True, account_type='asset')
            payment_accounts = assets or []
        except Exception as e:
            print(f"view_bill accounting accounts: {e}")

        # === DECRYPT CREDENTIALS FOR VIEW PAGE ===
        bill['username'] = decrypt_credential(bill.get('encrypted_username'))
        bill['password'] = decrypt_credential(bill.get('encrypted_password'))

        log_change(user_id, 'view_bill', target_id=bill_id,
                   change_details=f"Viewed bill: {bill['bill_name']}")

        return render_template(
            'bills/view_bill.html',
            bill=bill,
            assignments=assignments,
            history=history,
            is_manager=is_manager,
            today_str=today_str,
            expense_accounts=expense_accounts,
            payment_accounts=payment_accounts,
        )

    # ----------------------------------------------------------------------
    # Secure Credential Reveal (re-auth required)
    # ----------------------------------------------------------------------
    @bp.route('/reveal_credentials/<int:bill_id>', methods=['POST'])
    @login_required
    def reveal_credentials(bill_id):
        user_id = session['user_id']
        entered_password = request.json.get('password')

        if not entered_password:
            return jsonify({'success': False})


        if not user_can_access_bill(bill_id, user_id):
            return jsonify({'success': False, 'error': 'access_denied'}), 403

        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)

        # Verify user's own password
        cur.execute("SELECT password FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()

        if not user or not check_password_hash(user['password'], entered_password):
            return jsonify({'success': False})

        # Log the reveal action
        log_change(user_id, 'reveal_credentials', bill_id,
                   change_details=f"Revealed credentials for bill ID {bill_id}")

        return jsonify({'success': True})