from flask import render_template, request, redirect, url_for, flash, session
from app.utils.decorators import login_required
from app.models.users import get_user_by_id
from app.models.db import get_db
from app.models.log import log_change
from app.utils.totp_auth import (
    generate_totp_secret,
    get_provisioning_uri,
    verify_totp_code,
    encrypt_totp_secret,
    decrypt_totp_secret,
)
from app.utils.email_notifications import get_notification_settings
from . import profile_bp

EMAIL_PREFERENCE_FIELDS = [
    ('accepts_emails', 'Receive church emails (master switch)'),
    ('accepts_bill_emails', 'Bill payment reminders'),
    ('accepts_event_emails', 'Event invitations & updates'),
    ('accepts_donation_emails', 'Donation receipts & giving updates'),
    ('accepts_announcement_emails', 'Announcement emails'),
    ('accepts_prayer_emails', 'Prayer request updates'),
    ('accepts_group_emails', 'Group messages'),
    ('accepts_newsletter_emails', 'Newsletter & church-wide updates'),
    ('accepts_volunteer_emails', 'Volunteer opportunities'),
    ('accepts_worship_emails', 'Worship Team setlists & personal notes'),
]


@profile_bp.route('/security', methods=['GET', 'POST'])
@login_required
def security():
    user_id = session['user_id']
    user = get_user_by_id(user_id)
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('dashboard.dashboard'))

    db = get_db()
    is_staff = session.get('user_role') in ('Owner', 'Admin', 'Staff')
    setup_secret = session.get('totp_setup_secret')
    setup_uri = None
    if setup_secret:
        setup_uri = get_provisioning_uri(setup_secret, user['username'], get_notification_settings()['church_name'])

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'email_preferences':
            updates = {field: 1 if request.form.get(field) else 0 for field, _ in EMAIL_PREFERENCE_FIELDS}
            if not updates['accepts_emails']:
                for field, _ in EMAIL_PREFERENCE_FIELDS:
                    if field != 'accepts_emails':
                        updates[field] = 0
            set_clause = ', '.join(f'{field} = %s' for field in updates)
            cur = db.cursor()
            cur.execute(
                f'UPDATE users SET {set_clause} WHERE id = %s',
                (*updates.values(), user_id),
            )
            db.commit()
            log_change(user_id, 'update', change_details='Updated email notification preferences')
            flash('Email preferences saved.', 'success')
            return redirect(url_for('profile.security'))

        if action == 'notify_registrations' and is_staff:
            notify = 1 if request.form.get('notify_new_registrations') else 0
            cur = db.cursor()
            cur.execute('UPDATE users SET notify_new_registrations = %s WHERE id = %s', (notify, user_id))
            db.commit()
            flash('Admin notification preference saved.', 'success')
            return redirect(url_for('profile.security'))

        if action == 'start_2fa':
            secret = generate_totp_secret()
            session['totp_setup_secret'] = secret
            return redirect(url_for('profile.security'))

        if action == 'confirm_2fa':
            secret = session.get('totp_setup_secret')
            code = request.form.get('totp_code', '').strip()
            if not secret or not verify_totp_code(secret, code):
                flash('Invalid code. Scan the QR / enter the secret in your app and try again.', 'error')
                return redirect(url_for('profile.security'))
            cur = db.cursor()
            cur.execute(
                'UPDATE users SET totp_secret = %s, totp_enabled = 1 WHERE id = %s',
                (encrypt_totp_secret(secret), user_id),
            )
            db.commit()
            session.pop('totp_setup_secret', None)
            log_change(user_id, 'update', change_details='Enabled two-factor authentication')
            flash('Two-factor authentication enabled.', 'success')
            return redirect(url_for('profile.security'))

        if action == 'disable_2fa':
            code = request.form.get('totp_code', '').strip()
            secret = decrypt_totp_secret(user.get('totp_secret') or '')
            if not verify_totp_code(secret, code):
                flash('Enter a valid code from your authenticator to disable 2FA.', 'error')
                return redirect(url_for('profile.security'))
            cur = db.cursor()
            cur.execute(
                'UPDATE users SET totp_secret = NULL, totp_enabled = 0 WHERE id = %s',
                (user_id,),
            )
            db.commit()
            log_change(user_id, 'update', change_details='Disabled two-factor authentication')
            flash('Two-factor authentication disabled.', 'success')
            return redirect(url_for('profile.security'))

        if action == 'cancel_2fa_setup':
            session.pop('totp_setup_secret', None)
            return redirect(url_for('profile.security'))

    user = get_user_by_id(user_id)
    return render_template(
        'profile/security.html',
        user=user,
        is_staff=is_staff,
        setup_uri=setup_uri,
        setup_secret=setup_secret,
        email_preferences=EMAIL_PREFERENCE_FIELDS,
    )