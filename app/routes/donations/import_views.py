# Donation email import, receipt modes, enterprise reporting, payment provider settings.

from flask import render_template, request, redirect, url_for, flash, session, jsonify

from app.models.log import log_change
from app.utils.decorators import permission_required
from app.utils.field_crypto import encrypt
from app.models.db import get_db
import pymysql

from . import donations_bp
from .utils import get_church_info
from app.donations_import import service as import_service
from app.donations_import.mailbox import scan_mailbox


@donations_bp.route('/email-import')
@permission_required('manage_donations')
def email_import_queue():
    status = request.args.get('status') or None
    messages = import_service.list_messages(status=status, limit=150)
    mailboxes = import_service.list_mailboxes()
    settings = import_service.get_receipt_settings()
    log_change(session['user_id'], 'view', change_details='Viewed donation email import queue')
    return render_template(
        'donations/email_import.html',
        messages=messages,
        mailboxes=mailboxes,
        settings=settings,
        filter_status=status or '',
    )


@donations_bp.route('/email-import/settings', methods=['GET', 'POST'])
@permission_required('manage_donations')
def email_import_settings():
    if request.method == 'POST':
        action = request.form.get('action') or 'save_settings'
        if action == 'save_mailbox':
            mid = request.form.get('mailbox_id')
            data = {
                'label': request.form.get('label'),
                'protocol': request.form.get('protocol') or 'pop3',
                'host': request.form.get('host'),
                'port': request.form.get('port') or 995,
                'username': request.form.get('username'),
                'password': request.form.get('password'),
                'use_ssl': request.form.get('use_ssl') == '1',
                'enabled': request.form.get('enabled') == '1',
            }
            if not data['host'] or not data['username']:
                flash('Host and username are required.', 'error')
            else:
                import_service.save_mailbox(data, int(mid) if mid else None)
                flash('Mailbox saved.', 'success')
                log_change(session['user_id'], 'update', change_details='Updated donation email mailbox')
        elif action == 'save_settings':
            import_service.save_receipt_settings({
                'receipt_mode': request.form.get('receipt_mode'),
                'auto_import': request.form.get('auto_import') == '1',
                'auto_post': request.form.get('auto_post') == '1',
                'test_email': request.form.get('test_email'),
            })
            flash('Giving automation settings saved.', 'success')
            log_change(session['user_id'], 'update', change_details='Updated donation receipt/import settings')
        elif action == 'save_provider':
            _save_payment_provider(request.form)
            flash('Payment provider settings saved.', 'success')
        return redirect(url_for('donations.email_import_settings'))

    return render_template(
        'donations/email_import_settings.html',
        mailboxes=import_service.list_mailboxes(),
        settings=import_service.get_receipt_settings(),
        providers=_list_payment_providers(),
    )


@donations_bp.route('/email-import/load-fixtures', methods=['POST'])
@permission_required('manage_donations')
def email_import_load_fixtures():
    n = import_service.load_fixtures(force=request.form.get('force') == '1')
    flash(f'Loaded {n} mock payment emails (Stripe, PayPal, Cash App, ACH, Venmo, Tithe.ly, Zelle).', 'success')
    log_change(session['user_id'], 'create', change_details=f'Loaded {n} donation email fixtures')
    return redirect(url_for('donations.email_import_queue'))


@donations_bp.route('/email-import/scan/<int:mailbox_id>', methods=['POST'])
@permission_required('manage_donations')
def email_import_scan(mailbox_id):
    result = scan_mailbox(mailbox_id, limit=50)
    errs = result.get('errors') or []
    flash(
        f"Scan complete: fetched {result.get('fetched', 0)}, new {result.get('new', 0)}."
        + (f" Issues: {'; '.join(errs[:3])}" if errs else ''),
        'success' if not errs else 'error',
    )
    log_change(session['user_id'], 'update', change_details=f'Scanned donation mailbox #{mailbox_id}')
    return redirect(url_for('donations.email_import_queue'))


@donations_bp.route('/email-import/<int:message_id>')
@permission_required('manage_donations')
def email_import_detail(message_id):
    msg = import_service.get_message(message_id)
    if not msg:
        flash('Message not found.', 'error')
        return redirect(url_for('donations.email_import_queue'))
    return render_template('donations/email_import_detail.html', msg=msg)


@donations_bp.route('/email-import/<int:message_id>/reparse', methods=['POST'])
@permission_required('manage_donations')
def email_import_reparse(message_id):
    mode = (request.form.get('parse_mode') or 'auto').strip().lower()
    if mode not in ('rules', 'auto', 'ai'):
        mode = 'auto'
    try:
        gift = import_service.reparse_message(message_id, use_ai=mode)
        extras = (gift or {}).get('extras') or {}
        how = extras.get('parse_mode') or mode
        flash(
            f'Re-parsed ({how}'
            + (', AI assisted' if extras.get('ai_used') else ', rules only')
            + f'). Confidence ~{int(gift.get("confidence") or 0)}%.',
            'success',
        )
    except Exception as e:
        flash(str(e), 'error')
    return redirect(url_for('donations.email_import_detail', message_id=message_id))


@donations_bp.route('/email-import/paste', methods=['POST'])
@permission_required('manage_donations')
def email_import_paste():
    """Paste a payment notification email → parse (rules / auto / AI) → queue."""
    subject = (request.form.get('subject') or '').strip()
    body = (request.form.get('body') or '').strip()
    from_address = (request.form.get('from_address') or '').strip()
    mode = (request.form.get('parse_mode') or 'auto').strip().lower()
    if mode not in ('rules', 'auto', 'ai'):
        mode = 'auto'
    if not body:
        flash('Paste the email body to import.', 'error')
        return redirect(url_for('donations.email_import_queue'))
    try:
        mid = import_service.ingest_pasted_email(
            subject=subject,
            body=body,
            from_address=from_address,
            use_ai=mode,
        )
        flash('Email added to the import queue.', 'success')
        log_change(session['user_id'], 'create', change_details=f'Pasted donation email #{mid} ({mode})')
        return redirect(url_for('donations.email_import_detail', message_id=mid))
    except Exception as e:
        flash(str(e), 'error')
        return redirect(url_for('donations.email_import_queue'))


@donations_bp.route('/email-import/<int:message_id>/post', methods=['POST'])
@permission_required('manage_donations')
def email_import_post(message_id):
    overrides = {
        'donor_name': request.form.get('donor_name'),
        'donor_email': request.form.get('donor_email'),
        'amount': request.form.get('amount'),
        'date': request.form.get('date'),
        'method': request.form.get('method'),
        'confirmation_number': request.form.get('confirmation_number'),
        'fund_label': request.form.get('fund_label'),
        'notes': request.form.get('notes'),
    }
    # Coerce amount
    if overrides.get('amount'):
        try:
            overrides['amount'] = float(str(overrides['amount']).replace(',', '').replace('$', ''))
        except ValueError:
            flash('Invalid amount.', 'error')
            return redirect(url_for('donations.email_import_detail', message_id=message_id))
    try:
        donation_id = import_service.post_message_as_donation(message_id, overrides)
        flash(f'Posted as donation #{donation_id}.', 'success')
        log_change(session['user_id'], 'create', donation_id, change_details='Posted donation from email import')

        if request.form.get('send_receipt') == '1':
            from app.models.donation import get_donation_by_id
            donation = get_donation_by_id(donation_id)
            church = get_church_info()
            result = import_service.send_or_preview_receipt(donation or {}, church)
            flash(f"Receipt: {result.get('status')} → {result.get('to') or 'n/a'}", 'info')
    except Exception as e:
        flash(str(e), 'error')
    return redirect(url_for('donations.email_import_detail', message_id=message_id))


@donations_bp.route('/receipts/test/<int:donation_id>', methods=['POST'])
@permission_required('manage_donations')
def receipt_test(donation_id):
    from app.models.donation import get_donation_by_id
    donation = get_donation_by_id(donation_id)
    if not donation:
        flash('Donation not found.', 'error')
        return redirect(url_for('donations.donations_dashboard'))
    # Force test path by temporarily respecting settings
    result = import_service.send_or_preview_receipt(donation, get_church_info())
    if result.get('status') in ('test_sent', 'sent'):
        flash(f"Receipt {result['status']} to {result.get('to')}.", 'success')
    elif result.get('status') == 'test_pending':
        flash(result.get('message') or 'Configure test email first.', 'error')
    else:
        flash(f"Receipt status: {result.get('status')} {result.get('error') or ''}", 'info')
    return redirect(request.referrer or url_for('donations.donations_dashboard'))


@donations_bp.route('/enterprise-report')
@permission_required('manage_donations')
def enterprise_report():
    year = request.args.get('year', type=int)
    report = import_service.enterprise_report(year)
    return render_template('donations/enterprise_report.html', report=report)


def _list_payment_providers():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    try:
        cur.execute("SELECT * FROM donation_payment_providers ORDER BY provider, mode")
        rows = cur.fetchall() or []
    except Exception:
        return []
    for r in rows:
        r['has_secret'] = bool(r.get('secret_key_enc'))
        r['has_webhook'] = bool(r.get('webhook_secret_enc'))
        r.pop('secret_key_enc', None)
        r.pop('webhook_secret_enc', None)
    return rows


def _save_payment_provider(form):
    provider = (form.get('provider') or 'stripe').lower()
    mode = (form.get('mode') or 'test').lower()
    if mode not in ('test', 'live'):
        mode = 'test'
    secret = (form.get('secret_key') or '').strip()
    webhook = (form.get('webhook_secret') or '').strip()
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "SELECT id, secret_key_enc, webhook_secret_enc FROM donation_payment_providers WHERE provider=%s AND mode=%s",
        (provider, mode),
    )
    existing = cur.fetchone()
    secret_enc = encrypt(secret) if secret else (existing or {}).get('secret_key_enc')
    webhook_enc = encrypt(webhook) if webhook else (existing or {}).get('webhook_secret_enc')
    fields = (
        (form.get('display_name') or provider.title()).strip(),
        mode,
        1 if form.get('enabled') == '1' else 0,
        (form.get('publishable_key') or '').strip() or None,
        secret_enc,
        webhook_enc,
        1 if form.get('supports_ach') == '1' else 0,
        1 if form.get('supports_recurring') == '1' else 0,
    )
    if existing:
        cur.execute(
            """
            UPDATE donation_payment_providers
            SET display_name=%s, mode=%s, enabled=%s, publishable_key=%s,
                secret_key_enc=%s, webhook_secret_enc=%s, supports_ach=%s, supports_recurring=%s
            WHERE id=%s
            """,
            (*fields, existing['id']),
        )
    else:
        cur.execute(
            """
            INSERT INTO donation_payment_providers
                (provider, display_name, mode, enabled, publishable_key, secret_key_enc,
                 webhook_secret_enc, supports_ach, supports_recurring)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (provider, *fields),
        )
    db.commit()
