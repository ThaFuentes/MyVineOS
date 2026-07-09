# Scheduled / background email jobs (bill reminders, etc.)

from datetime import datetime, timedelta
import pymysql
from app.models.db import get_db
from app.utils.email_notifications import (
    get_notification_settings,
    send_bill_reminders_for_bill,
)
from app.utils.time_utils import utc_now


def _should_run_scheduler() -> bool:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT email_last_scheduler_run FROM settings WHERE id = 1")
    row = cur.fetchone()
    last = row.get('email_last_scheduler_run') if row else None
    if not last:
        return True
    if isinstance(last, datetime):
        now = utc_now()
        if last.tzinfo is None:
            from datetime import timezone
            last = last.replace(tzinfo=timezone.utc)
        return (now - last) > timedelta(hours=20)
    return True


def _mark_scheduler_run():
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE settings SET email_last_scheduler_run = %s WHERE id = 1", (utc_now(),))
    db.commit()


def run_bill_reminder_scheduler() -> int:
    """Send automatic bill reminders. Returns emails sent."""
    settings = get_notification_settings()
    if not settings['email_auto_bill_reminders']:
        return 0

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    today = utc_now().date()

    cur.execute("""
        SELECT * FROM recurring_bills
        WHERE next_due_date IS NOT NULL
          AND current_status IN ('pending', 'partial', 'overdue')
    """)
    bills = cur.fetchall()
    sent = 0

    for bill in bills:
        due = bill['next_due_date']
        if hasattr(due, 'date'):
            due_date = due.date() if hasattr(due, 'hour') else due
        else:
            continue
        days_before = int(bill.get('reminder_days_before') or 7)
        remind_on = due_date - timedelta(days=days_before)
        if today < remind_on:
            continue

        last_sent = bill.get('last_reminder_sent')
        if last_sent:
            ls = last_sent.date() if isinstance(last_sent, datetime) else last_sent
            if ls >= remind_on:
                continue

        sent += send_bill_reminders_for_bill(bill)

        cur.execute(
            "UPDATE recurring_bills SET last_reminder_sent = %s WHERE id = %s",
            (utc_now(), bill['id']),
        )
    db.commit()
    return sent


def maybe_run_scheduled_emails():
    """Called periodically (e.g. dashboard load). Runs at most ~once per 20 hours."""
    try:
        if not _should_run_scheduler():
            return
        run_bill_reminder_scheduler()
        _mark_scheduler_run()
    except Exception as e:
        print(f"Scheduled email run error: {e}")