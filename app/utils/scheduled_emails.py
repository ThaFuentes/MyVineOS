# Scheduled / background email jobs (bill reminders, communications, etc.)

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


def run_communications_jobs() -> dict:
    """Mass campaigns, drip steps, and full automation auto-enroll suite."""
    result = {
        'campaigns': 0,
        'drip_messages': 0,
        'new_member_enrolls': 0,
        'auto_enrolls': {},
    }
    try:
        from app.models import communications as comm
        result['campaigns'] = comm.process_due_campaigns()
        result['drip_messages'] = comm.process_due_enrollments(limit=100)
        enrolls = comm.run_all_auto_enrolls()
        result['auto_enrolls'] = enrolls
        result['new_member_enrolls'] = int(enrolls.get('new_member') or 0)
        result['total_auto_enrolls'] = sum(int(v or 0) for v in enrolls.values())
    except Exception as e:
        print(f"Communications scheduler error: {e}")
    return result


def run_volunteer_reminders() -> int:
    """Email volunteer assignment reminders based on vol_reminder_days_before."""
    try:
        from app.models import volunteers as vol
        return vol.send_pending_reminders()
    except Exception as e:
        print(f"Volunteer reminders error: {e}")
        return 0


def _should_run_automation() -> bool:
    """Drips/automation should tick often (every ~20 minutes), not once a day."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    try:
        cur.execute("SELECT automation_last_run FROM settings WHERE id = 1")
        row = cur.fetchone() or {}
    except Exception:
        return True
    last = row.get('automation_last_run')
    if not last:
        return True
    if isinstance(last, datetime):
        now = utc_now()
        if last.tzinfo is None:
            from datetime import timezone
            last = last.replace(tzinfo=timezone.utc)
        return (now - last) > timedelta(minutes=20)
    return True


def _mark_automation_run():
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("UPDATE settings SET automation_last_run = %s WHERE id = 1", (utc_now(),))
        db.commit()
    except Exception:
        pass


def maybe_run_scheduled_emails():
    """
    Called periodically (e.g. dashboard load).
    - Automation/drips: ~every 20 minutes
    - Bill reminders + volunteer assignment reminders: ~every 20 hours
    """
    try:
        if _should_run_automation():
            run_communications_jobs()
            _mark_automation_run()
        if _should_run_scheduler():
            run_bill_reminder_scheduler()
            run_volunteer_reminders()
            _mark_scheduler_run()
    except Exception as e:
        print(f"Scheduled email run error: {e}")
