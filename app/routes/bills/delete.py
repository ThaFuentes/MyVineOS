# app/routes/bills/delete.py
# Full path: MyVineChurch/app/routes/bills/delete.py
# File name: delete.py
# Brief, detailed purpose: Delete bill route (/bills/delete/<int:bill_id>).
# Restricted to Admin/Owner only for safety.
# Deletes assignments + payment history + the bill itself.
# Full audit logging.

from flask import redirect, url_for, flash, session
from app.utils.decorators import login_required, permission_required
from app.models.db import get_db
from app.models.log import log_change
import pymysql

def register_delete_routes(bp):
    @bp.route('/delete/<int:bill_id>', methods=['POST'])
    @login_required
    @permission_required('manage_bills')
    def delete_bill(bill_id):
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)

        # Get bill name for log
        cur.execute("SELECT bill_name FROM recurring_bills WHERE id = %s", (bill_id,))
        row = cur.fetchone()
        if not row:
            flash('Bill not found.', 'error')
            return redirect(url_for('bills.bills'))

        bill_name = row['bill_name']

        try:
            cur = db.cursor()
            # Delete related data first
            cur.execute("DELETE FROM recurring_bill_assignments WHERE bill_id = %s", (bill_id,))
            cur.execute("DELETE FROM bill_payment_history WHERE bill_id = %s", (bill_id,))
            # Delete the bill
            cur.execute("DELETE FROM recurring_bills WHERE id = %s", (bill_id,))
            db.commit()

            log_change(session['user_id'], 'delete_bill', bill_id, bill_name, 'Deleted recurring bill')
            flash('Recurring bill deleted permanently.', 'success')
        except Exception as exc:
            db.rollback()
            flash('Failed to delete bill.', 'error')
            print(f"Delete bill error (ID {bill_id}): {exc}")

        return redirect(url_for('bills.bills'))