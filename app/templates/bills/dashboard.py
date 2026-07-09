# app/routes/bills/dashboard.py
# Full path: MyVineChurch/app/routes/bills/dashboard.py
# File name: dashboard.py
# Brief, detailed purpose: Bills dashboard listing (/bills).
# Managers see all bills with assigned count.
# Regular assigned users see only their assigned bills.
# Nice next due date formatting + passes is_manager flag.

from flask import render_template, session
from app.utils.decorators import login_required
from app.models.db import get_db
from app.models.log import log_change
from datetime import datetime, date
import pymysql

def register_dashboard_routes(bp):
    @bp.route('/')
    @login_required
    def bills():
        user_id = session['user_id']
        is_manager = session.get('user_role') in ['Staff', 'Admin', 'Owner']

        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)

        if is_manager:
            cur.execute("""
                SELECT b.*,
                       (SELECT COUNT(*) FROM recurring_bill_assignments a WHERE a.bill_id = b.id) AS assigned_count
                FROM recurring_bills b
                ORDER BY b.next_due_date ASC, b.bill_name ASC
            """)
        else:
            cur.execute("""
                SELECT b.*
                FROM recurring_bills b
                JOIN recurring_bill_assignments a ON b.id = a.bill_id
                WHERE a.user_id = %s
                ORDER BY b.next_due_date ASC, b.bill_name ASC
            """, (user_id,))

        bills_list = cur.fetchall()
        today = date.today()

        stats = {
            'total_count': len(bills_list),
            'pending_count': 0,
            'overdue_count': 0,
            'upcoming_count': 0,
            'paid_this_month': 0,
        }

        # Nice next due date formatting + summary counts
        for b in bills_list:
            next_due = b.get('next_due_date')
            due_date = None
            if next_due:
                try:
                    if isinstance(next_due, str):
                        due_date = datetime.strptime(next_due, '%Y-%m-%d').date()
                    elif isinstance(next_due, datetime):
                        due_date = next_due.date()
                    else:
                        due_date = next_due
                    b['nice_next_due'] = due_date.strftime('%A, %B %d, %Y')
                except Exception:
                    b['nice_next_due'] = 'Invalid date'
            else:
                b['nice_next_due'] = 'Not set'

            status = str(b.get('current_status') or 'pending').lower().strip()
            if status == 'pending':
                stats['pending_count'] += 1
            if status == 'overdue' or (due_date and due_date < today and status != 'paid'):
                stats['overdue_count'] += 1
            if due_date and due_date >= today:
                stats['upcoming_count'] += 1

        bill_ids = [b['id'] for b in bills_list]
        if bill_ids:
            placeholders = ','.join(['%s'] * len(bill_ids))
            cur.execute(f"""
                SELECT COUNT(*) AS cnt
                FROM bill_payment_history
                WHERE bill_id IN ({placeholders})
                  AND YEAR(payment_date) = YEAR(CURDATE())
                  AND MONTH(payment_date) = MONTH(CURDATE())
            """, bill_ids)
            row = cur.fetchone()
            stats['paid_this_month'] = int((row or {}).get('cnt') or 0)

        cur.close()
        log_change(user_id, 'view', change_details='Viewed recurring bills dashboard')

        return render_template(
            'bills/bills_dashboard.html',
            bills=bills_list,
            is_manager=is_manager,
            today_iso=today.isoformat(),
            bill_stats=stats,
            paid_this_month=stats['paid_this_month'],
        )