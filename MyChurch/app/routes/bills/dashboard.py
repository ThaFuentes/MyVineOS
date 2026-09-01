# app/routes/bills/dashboard.py
# Full path: MyVineChurch/app/routes/bills/dashboard.py
# File name: dashboard.py
# Brief, detailed purpose: Bills dashboard listing (/bills).
# Managers see all bills with assigned count.
# Regular assigned users see only their assigned bills.
# Nice next due date formatting + passes is_manager flag.

from flask import render_template, session
from .utils import is_bill_manager, bills_access_required
from app.models.db import get_db
from app.models.log import log_change
from datetime import datetime, date
import pymysql

def register_dashboard_routes(bp):
    @bp.route('/')
    @bills_access_required
    def bills():
        user_id = session['user_id']
        is_manager = is_bill_manager()

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
            'total': len(bills_list),
            'pending': 0,
            'overdue': 0,
            'upcoming': 0,
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
            b['status_lower'] = status
            b['due_iso'] = due_date.isoformat() if due_date else ''
            b['is_pending'] = status == 'pending'
            b['is_overdue'] = status == 'overdue' or (
                bool(due_date and due_date < today and status != 'paid')
            )
            b['is_upcoming'] = bool(due_date and due_date >= today)
            if b['is_pending']:
                stats['pending'] += 1
            if b['is_overdue']:
                stats['overdue'] += 1
            if b['is_upcoming']:
                stats['upcoming'] += 1

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