from flask import render_template, request, redirect, url_for, flash, session
from app.models.db import get_db
from app.models.log import log_change
from app.utils.email_notifications import EMAIL_USAGE_CATALOG, get_notification_settings
from . import settings_bp, has_section_permission


def _ensure_settings_row(cur):
    cur.execute("SELECT id FROM settings WHERE id = 1")
    if not cur.fetchone():
        cur.execute("INSERT INTO settings (id) VALUES (1)")


@settings_bp.route('/notifications', methods=['GET', 'POST'])
def notifications():
    if request.method == 'POST' and not has_section_permission('notifications'):
        flash('Insufficient permission to edit notification settings.', 'error')
        return redirect(url_for('settings.notifications'))

    db = get_db()
    user_id = session['user_id']

    if request.method == 'POST':
        auto_approve = 1 if request.form.get('registration_auto_approve') else 0
        require_verify = 1 if request.form.get('registration_require_email_verification') else 0
        donation_receipts = 1 if request.form.get('email_send_donation_receipts') else 0
        bill_reminders = 1 if request.form.get('email_auto_bill_reminders') else 0
        cur = db.cursor()
        _ensure_settings_row(cur)
        cur.execute("""
            UPDATE settings SET
                registration_auto_approve = %s,
                registration_require_email_verification = %s,
                email_send_donation_receipts = %s,
                email_auto_bill_reminders = %s
            WHERE id = 1
        """, (auto_approve, require_verify, donation_receipts, bill_reminders))
        db.commit()
        log_change(user_id, 'update', None, None, 'Updated notification & registration email settings')
        flash('Notification settings saved.', 'success')
        return redirect(url_for('settings.notifications'))

    settings = get_notification_settings()
    return render_template(
        'settings/notifications.html',
        settings=settings,
        email_catalog=EMAIL_USAGE_CATALOG,
    )