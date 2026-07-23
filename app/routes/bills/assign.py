# app/routes/bills/assign.py
# Full path: MyVineChurch/app/routes/bills/assign.py
# File name: assign.py
# Brief, detailed purpose: Assign users to a bill (/bills/assign/<int:bill_id>).
# Restricted to Staff/Admin/Owner only.
# Shows all users with checkboxes + remind_me option.
# Clears old assignments and saves new ones.

from flask import render_template, request, redirect, url_for, flash, session
from app.utils.decorators import login_required, permission_required
from app.models.db import get_db
from app.models.log import log_change
import pymysql

def register_assign_routes(bp):
    @bp.route('/assign/<int:bill_id>', methods=['GET', 'POST'])
    @login_required
    @permission_required('edit_bills', 'manage_bills')
    def assign_bill(bill_id):
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)

        # Verify bill exists
        cur.execute("SELECT id, bill_name FROM recurring_bills WHERE id = %s", (bill_id,))
        bill_row = cur.fetchone()
        if not bill_row:
            flash('Bill not found.', 'error')
            return redirect(url_for('bills.bills'))

        bill = dict(bill_row)

        # All users for selection
        cur.execute("""
            SELECT id, username, first_name, last_name, email 
            FROM users 
            ORDER BY first_name, last_name
        """)
        all_users = cur.fetchall()

        # Current assignments
        cur.execute("""
            SELECT user_id, remind_me 
            FROM recurring_bill_assignments 
            WHERE bill_id = %s
        """, (bill_id,))
        current = {row['user_id']: bool(row['remind_me']) for row in cur.fetchall()}

        if request.method == 'POST':
            selected_users = request.form.getlist('assigned')

            try:
                # Clear existing assignments
                cur.execute("DELETE FROM recurring_bill_assignments WHERE bill_id = %s", (bill_id,))

                # Add new assignments
                for uid_str in selected_users:
                    uid = int(uid_str)
                    remind = 1 if request.form.get(f'remind_{uid}') else 0
                    cur.execute("""
                        INSERT INTO recurring_bill_assignments 
                        (bill_id, user_id, remind_me) 
                        VALUES (%s, %s, %s)
                    """, (bill_id, uid, remind))

                db.commit()
                log_change(session['user_id'], 'assign_bill', bill_id,
                           change_details=f"Updated assignments for bill: {bill['bill_name']}")
                flash('Assignments updated successfully.', 'success')
                return redirect(url_for('bills.view_bill', bill_id=bill_id))

            except Exception as exc:
                db.rollback()
                flash('Failed to update assignments.', 'error')
                print(f"Assign bill error: {exc}")

        return render_template('bills/assign_bill.html',
                               bill=bill,
                               all_users=all_users,
                               current=current)