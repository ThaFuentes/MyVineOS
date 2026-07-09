# app/routes/bills/payment.py
# Full path: MyVineChurch/app/routes/bills/payment.py
# File name: payment.py
# Brief, detailed purpose: Record payment route (/bills/record_payment/<int:bill_id>).
# Accessible to managers or assigned users.
# Updates bill status to 'paid' after recording.
# Full audit logging.

from flask import redirect, url_for, flash, session
from app.utils.decorators import login_required
from app.models.db import get_db
from app.models.log import log_change
from datetime import datetime
import pymysql

def register_payment_routes(bp):
    @bp.route('/record_payment/<int:bill_id>', methods=['POST'])
    @login_required
    def record_payment(bill_id):
        user_id = session['user_id']
        is_manager = session.get('user_role') in ['Staff', 'Admin', 'Owner']

        # Access check
        if not is_manager:
            db = get_db()
            cur = db.cursor()
            cur.execute("SELECT 1 FROM recurring_bill_assignments WHERE bill_id = %s AND user_id = %s", (bill_id, user_id))
            if not cur.fetchone():
                flash('You do not have access to record payment for this bill.', 'error')
                return redirect(url_for('bills.bills'))

        amount = request.form.get('amount')
        payment_date = request.form.get('payment_date') or datetime.today().strftime('%Y-%m-%d')
        notes = request.form.get('notes', '').strip()

        if not amount:
            flash('Amount is required.', 'error')
            return redirect(url_for('bills.view_bill', bill_id=bill_id))

        try:
            db = get_db()
            cur = db.cursor()
            cur.execute("""
                INSERT INTO bill_payment_history (bill_id, payment_date, amount, paid_by, notes)
                VALUES (%s, %s, %s, %s, %s)
            """, (bill_id, payment_date, amount, user_id, notes))

            # Update bill status to paid
            cur.execute("""
                UPDATE recurring_bills 
                SET current_status = 'paid', updated_by = %s 
                WHERE id = %s
            """, (user_id, bill_id))

            db.commit()

            log_change(user_id, 'record_payment', bill_id,
                       change_details=f"Recorded payment of ${amount}")

            flash('Payment recorded successfully.', 'success')
            return redirect(url_for('bills.view_bill', bill_id=bill_id))

        except Exception as exc:
            db.rollback()
            flash('Failed to record payment.', 'error')
            print(f"Record payment error (ID {bill_id}): {exc}")
            return redirect(url_for('bills.view_bill', bill_id=bill_id))