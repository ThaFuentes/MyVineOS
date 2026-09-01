# myvinechurchonline/app/routes/settings/email.py
# Full path: myvinechurchonline/app/routes/settings/email.py
# File name: email.py
# Brief, detailed purpose: Multi-account email configuration + test send.
# FIXED: Imports changed to package-relative (from .) - loads shared items from settings/__init__.py.
# Added missing pymysql import for DictCursor.

from flask import render_template, request, redirect, url_for, flash, session
from app.models.db import get_db
from app.models.log import log_change
from . import (
    settings_bp, encrypt, decrypt, DONATIONS_FOLDER, has_section_permission,
    load_settings, load_email_accounts, ensure_email_account_role_columns,
)
from app.models.settings import get_settings
import os
import smtplib
import pymysql
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.utils.smtp_client import send_smtp_message, smtp_mode_label


def _normalize_smtp_settings(form):
    """Coerce port/encryption pairs that mail servers commonly require."""
    port_raw = form.get('outgoing_port') or '587'
    try:
        port = int(port_raw)
    except ValueError:
        port = 587
    encryption = (form.get('outgoing_encryption') or 'TLS').strip()
    if port == 465:
        encryption = 'SSL'
    elif port == 587 and encryption.upper() == 'SSL':
        encryption = 'TLS'
    return port, encryption


@settings_bp.route('/email', methods=['GET', 'POST'])
def email():
    if request.method == 'POST' and not has_section_permission('email'):
        flash('Insufficient permission to edit Email settings.', 'error')
        return redirect(url_for('settings.email'))

    os.makedirs(DONATIONS_FOLDER, exist_ok=True)
    ensure_email_account_role_columns()

    db = get_db()
    user_id = session['user_id']
    cur = db.cursor(pymysql.cursors.DictCursor)

    settings = load_settings()
    accounts = load_email_accounts()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_account':
            name = request.form.get('name', '').strip()
            # Outgoing optional if this is only a giving inbox with POP3/IMAP
            is_giving = 1 if request.form.get('is_giving_inbox') in ('1', 'on') else 0
            has_out = bool((request.form.get('outgoing_server') or '').strip())
            if not name:
                flash('Account name is required (e.g. Main Email, Giving inbox).', 'error')
            elif not has_out and not is_giving:
                flash('Outgoing server is required unless this is a Giving inbox with POP3/IMAP.', 'error')
            elif is_giving and not (request.form.get('incoming_server') or '').strip():
                flash('Giving inbox accounts need incoming POP3/IMAP server details.', 'error')
            else:
                is_default = 1 if 'make_default' in request.form else 0
                if is_default:
                    cur.execute("UPDATE email_accounts SET is_default = 0")

                out_port, out_enc = _normalize_smtp_settings(request.form)
                in_user = (request.form.get('incoming_username') or request.form.get('outgoing_username') or '').strip()
                out_user = (request.form.get('outgoing_username') or '').strip()
                cur.execute("""
                    INSERT INTO email_accounts 
                    (name, outgoing_server, outgoing_port, outgoing_encryption, outgoing_username, outgoing_password,
                     incoming_protocol, incoming_server, incoming_port, incoming_encryption, incoming_username, incoming_password,
                     is_default, is_giving_inbox)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    name,
                    request.form.get('outgoing_server') or None,
                    out_port if has_out else None,
                    out_enc if has_out else None,
                    encrypt(out_user) if out_user else None,
                    encrypt(request.form.get('outgoing_password', '').strip()) if request.form.get('outgoing_password') else None,
                    request.form.get('incoming_protocol') or None,
                    request.form.get('incoming_server') or None,
                    request.form.get('incoming_port') or None,
                    request.form.get('incoming_encryption') or None,
                    encrypt(in_user) if in_user else None,
                    encrypt(request.form.get('incoming_password', '').strip()) if request.form.get('incoming_password') else None,
                    is_default,
                    is_giving,
                ))
                db.commit()
                log_change(user_id, 'create', None, name, f'Added email account: {name}')
                flash('Email account added.', 'success')

        elif action == 'update_account':
            account_id = request.form.get('account_id')
            if not account_id:
                flash('Invalid account.', 'error')
            else:
                name = request.form.get('name', '').strip()
                if not name:
                    flash('Account name required.', 'error')
                else:
                    old_out_pass = request.form.get('old_outgoing_password', '')
                    new_out_pass = request.form.get('outgoing_password', '').strip()
                    outgoing_password = encrypt(new_out_pass) if new_out_pass else old_out_pass

                    old_in_pass = request.form.get('old_incoming_password', '')
                    new_in_pass = request.form.get('incoming_password', '').strip()
                    incoming_password = encrypt(new_in_pass) if new_in_pass else old_in_pass

                    is_default = 1 if 'make_default' in request.form else 0
                    is_giving = 1 if request.form.get('is_giving_inbox') in ('1', 'on') else 0
                    if is_default:
                        cur.execute("UPDATE email_accounts SET is_default = 0")

                    updates = """
                        name = %s,
                        outgoing_server = %s,
                        outgoing_port = %s,
                        outgoing_encryption = %s,
                        outgoing_username = %s,
                        outgoing_password = %s,
                        incoming_protocol = %s,
                        incoming_server = %s,
                        incoming_port = %s,
                        incoming_encryption = %s,
                        incoming_username = %s,
                        incoming_password = %s,
                        is_default = %s,
                        is_giving_inbox = %s
                    """
                    out_port, out_enc = _normalize_smtp_settings(request.form)
                    values = (
                        name,
                        request.form.get('outgoing_server') or None,
                        out_port,
                        out_enc,
                        encrypt(request.form.get('outgoing_username', '').strip()),
                        outgoing_password,
                        request.form.get('incoming_protocol') or None,
                        request.form.get('incoming_server') or None,
                        request.form.get('incoming_port') or None,
                        request.form.get('incoming_encryption') or None,
                        encrypt(request.form.get('incoming_username', '').strip()),
                        incoming_password,
                        is_default,
                        is_giving,
                    )
                    cur.execute(f"UPDATE email_accounts SET {updates} WHERE id = %s", values + (account_id,))
                    db.commit()
                    log_change(user_id, 'update', account_id, name, f'Updated email account: {name}')
                    flash('Email account updated.', 'success')

        elif action == 'delete_account':
            account_id = request.form.get('account_id')
            if account_id:
                cur.execute("SELECT is_default FROM email_accounts WHERE id = %s", (account_id,))
                row = cur.fetchone()
                if row and row['is_default']:
                    flash('Cannot delete the default account. Set another as default first.', 'error')
                else:
                    cur.execute("DELETE FROM email_accounts WHERE id = %s", (account_id,))
                    db.commit()
                    log_change(user_id, 'delete', account_id, None, f'Deleted email account ID {account_id}')
                    flash('Email account deleted.', 'success')

        elif action == 'send_test':
            account_id = request.form.get('test_account')
            if not account_id:
                flash('Select an account to test.', 'error')
            else:
                cur.execute("SELECT * FROM email_accounts WHERE id = %s", (account_id,))
                acc = cur.fetchone()
                if not acc:
                    flash('Account not found.', 'error')
                else:
                    username = decrypt(acc['outgoing_username'])
                    password = decrypt(acc['outgoing_password'])
                    if not username:
                        flash('No username/email set for outgoing on this account.', 'error')
                    elif not password:
                        flash('No password set for outgoing on this account.', 'error')
                    else:
                        try:
                            test_to = request.form.get('test_to', '').strip()
                            if not test_to:
                                flash('Enter a recipient address for the test.', 'error')
                            else:
                                msg = MIMEMultipart()
                                msg['From'] = username
                                msg['To'] = test_to
                                msg['Subject'] = request.form.get(
                                    'test_subject', 'MyVineChurch.Online Test Email'
                                )
                                body = request.form.get(
                                    'test_body',
                                    f"This is a test email from {settings.get('church_name', 'MyVineChurch.Online')}.",
                                )
                                msg.attach(MIMEText(body, 'plain'))

                                stored_enc = (acc.get('outgoing_encryption') or '').upper()
                                send_smtp_message(
                                    acc['outgoing_server'],
                                    acc['outgoing_port'],
                                    acc.get('outgoing_encryption'),
                                    username,
                                    password,
                                    msg,
                                )
                                success = (
                                    f'Test email sent to {test_to} via {smtp_mode_label(acc["outgoing_port"], acc.get("outgoing_encryption"))}.'
                                )
                                if int(acc['outgoing_port'] or 0) == 465 and stored_enc == 'TLS':
                                    success += ' (Port 465 uses SSL - update Encryption to SSL in account settings to match.)'
                                flash(success, 'success')
                        except smtplib.SMTPAuthenticationError:
                            flash('Test failed: SMTP authentication rejected. Check username and password.', 'error')
                        except smtplib.SMTPException as e:
                            flash(f'Test failed: {e}', 'error')
                        except Exception as e:
                            flash(f'Test failed: {str(e)}', 'error')

        accounts = load_email_accounts()

    return render_template('settings/email.html', accounts=accounts, settings=settings)