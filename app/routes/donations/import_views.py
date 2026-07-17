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
from app.donations_import.mailbox import scan_mailbox, scan_all_enabled_mailboxes


def _parse_mode_from_request(default: str | None = None) -> str:
    """rules = software only; auto/ai = AI help (API keys from Settings → AI)."""
    raw = (request.form.get('parse_mode') or default or '').strip().lower()
    if raw in ('rules', 'auto', 'ai'):
        return raw
    # Friendly aliases from the Check emails form
    if raw in ('software', 'software_only', 'rules_only'):
        return 'rules'
    if raw in ('ai_help', 'with_ai', 'ai_assist'):
        return 'auto'
    return import_service.configured_parse_mode()


def _parse_mode_label(mode: str) -> str:
    if mode == 'rules':
        return 'software check only'
    if mode == 'ai':
        return 'AI assist on every email'
    return 'AI help when software is unsure'


@donations_bp.route('/email-import', methods=['GET', 'POST'])
@permission_required('manage_donations')
def email_import_queue():
    # Optional: save simple automation toggles on this same page (no separate settings screen)
    if request.method == 'POST' and request.form.get('action') == 'save_automation':
        import_service.save_receipt_settings({
            'receipt_mode': request.form.get('receipt_mode') or 'test',
            'auto_import': request.form.get('auto_import') == '1',
            'auto_post': request.form.get('auto_post') == '1',
            'auto_post_min_confidence': request.form.get('auto_post_min_confidence') or 90,
            'auto_receipt': request.form.get('auto_receipt') == '1',
            'receipt_policy': request.form.get('receipt_policy') or 'all',
            'receipt_email_list': request.form.get('receipt_email_list') or '',
            'staff_notify': request.form.get('staff_notify') or '',
            'import_enabled': True,  # always on when using this page
            'test_email': request.form.get('test_email'),
            'parse_mode': request.form.get('parse_mode') or 'auto',
        })
        flash('Automation options saved.', 'success')
        log_change(session['user_id'], 'update', change_details='Updated email gift automation options')
        return redirect(url_for('donations.email_import_queue'))

    status = request.args.get('status') or 'inbox'
    # Hide old “no amount” / false-gift rows from Needs you
    try:
        import_service.reclassify_non_gifts()
    except Exception:
        pass
    messages = import_service.list_messages(status=status, limit=150)
    mailboxes = import_service.list_mailboxes()
    settings = import_service.get_receipt_settings()
    counts = import_service.queue_counts()
    focus_id = request.args.get('focus', type=int)
    log_change(session['user_id'], 'view', change_details='Viewed donation email import inbox')
    return render_template(
        'donations/email_import.html',
        messages=messages,
        mailboxes=mailboxes,
        settings=settings,
        counts=counts,
        filter_status=status or 'inbox',
        focus_id=focus_id,
    )


@donations_bp.route('/email-import/settings', methods=['GET', 'POST'])
@permission_required('manage_donations')
def email_import_settings():
    """This URL must never show a settings form. Email = Settings → Email only."""
    return redirect(url_for('donations.email_import_queue'), code=302)


@donations_bp.route('/email-import/load-fixtures', methods=['POST'])
@permission_required('manage_donations')
def email_import_load_fixtures():
    n = import_service.load_fixtures(force=request.form.get('force') == '1')
    flash(
        f'Loaded {n} sample gifts into the queue (Stripe, PayPal, Cash App, ACH, Venmo, Tithe.ly, Zelle, Pushpay). '
        f'No SMTP — ready to review now.',
        'success',
    )
    log_change(session['user_id'], 'create', change_details=f'Loaded {n} donation email fixtures')
    return redirect(url_for('donations.email_import_queue', status='inbox'))


@donations_bp.route('/email-import/send-samples', methods=['POST'])
@permission_required('manage_donations')
def email_import_send_samples():
    """SMTP: send sample payment emails only to an address the staff types in (no defaults)."""
    to_email = (request.form.get('to_email') or '').strip()
    if not to_email or '@' not in to_email:
        flash(
            'Type a destination email for samples. '
            'We never send test gifts to admin or your real mailboxes by default.',
            'error',
        )
        return redirect(url_for('donations.email_import_queue', status='inbox'))
    try:
        result = import_service.send_sample_payment_emails(to_email)
        errs = result.get('errors') or []
        flash(
            f"Sent {result.get('sent', 0)}/{result.get('total', 0)} sample payment emails to "
            f"{result.get('to')}. Wait a moment, then Check emails to practice parsing."
            + (f" Issues: {'; '.join(errs[:2])}" if errs else ''),
            'success' if result.get('sent') else 'error',
        )
        log_change(
            session['user_id'], 'create',
            change_details=f"Sent {result.get('sent')} sample gift emails to {result.get('to')}",
        )
    except Exception as e:
        flash(str(e), 'error')
    return redirect(url_for('donations.email_import_queue', status='inbox'))


@donations_bp.route('/email-import/revalidate', methods=['POST'])
@permission_required('manage_donations')
def email_import_revalidate():
    """Re-parse open rows with current rules (clears cPanel/IP false gifts)."""
    result = import_service.revalidate_open_parses(use_ai='rules', limit=120)
    flash(
        f"Re-checked {result.get('reparsed', 0)} open email(s) with software rules. "
        f"{result.get('now_skipped', 0)} now skipped as non-gifts.",
        'success',
    )
    log_change(session['user_id'], 'update', change_details='Revalidated donation email parses (rules)')
    return redirect(url_for('donations.email_import_queue', status='inbox'))


def _flash_check_result(result: dict, mode: str, label: str | None = None):
    """Explain check results in plain language (not cryptic error codes)."""
    fetched = int(result.get('fetched') or 0)
    new = int(result.get('new') or 0)
    errs = result.get('errors') or []
    who = label or f"{result.get('scanned', 0)} mailbox(es)"
    mode_txt = _parse_mode_label(mode)

    if fetched == 0 and new == 0 and errs:
        flash(
            f"Checked {who} ({mode_txt}) but could not import any messages. "
            f"Details: {'; '.join(errs[:2])}"
            + (f" (+{len(errs) - 2} more)" if len(errs) > 2 else ''),
            'error',
        )
        return
    if fetched == 0 and new == 0 and not errs:
        flash(
            f"Checked {who} ({mode_txt}): mailbox is empty or no new mail to read.",
            'success',
        )
        return

    # Already-seen messages count as “read” but not “new”
    already = max(0, fetched - new)
    try:
        import_service.reclassify_non_gifts()
        counts = import_service.queue_counts()
        gifts_waiting = int(counts.get('inbox') or 0)
        skipped_total = int(counts.get('manual') or 0)
    except Exception:
        gifts_waiting = None
        skipped_total = None
    parts = [
        f"Checked {who} ({mode_txt}): read {fetched} message(s).",
    ]
    if new:
        parts.append(
            f"{new} new row(s) stored. Real gifts go under Needs you; "
            f"no-amount / AI “not found” emails are auto-skipped."
        )
    if already and not new:
        parts.append(
            f"All {already} were already stored (no duplicates). Open Needs you to continue."
        )
    elif already and new:
        parts.append(f"{already} were already stored.")
    if gifts_waiting is not None:
        parts.append(f"Needs you now: {gifts_waiting}.")
    if skipped_total:
        parts.append(f"Skipped / not gifts: {skipped_total} (Manually check other emails).")
    if errs:
        parts.append(f"Some messages had problems ({len(errs)}): {errs[0]}")
        flash(' '.join(parts), 'error' if new == 0 and not gifts_waiting else 'success')
    else:
        flash(' '.join(parts), 'success')


@donations_bp.route('/email-import/check', methods=['POST'])
@permission_required('manage_donations')
def email_import_check_all():
    """Primary action: pull POP3/IMAP → parse (software or AI) → human review queue."""
    mode = _parse_mode_from_request()
    result = scan_all_enabled_mailboxes(limit=60, use_ai=mode)
    errs = result.get('errors') or []
    if not result.get('mailboxes'):
        flash(
            errs[0] if errs else 'Add a POP3/IMAP account under Settings → Email, then try again.',
            'error',
        )
        return redirect(url_for('settings.email'))
    _flash_check_result(result, mode)
    log_change(
        session['user_id'], 'update',
        change_details=(
            f"Checked donation mailboxes ({mode}): fetched {result.get('fetched', 0)}, "
            f"new {result.get('new', 0)}"
        ),
    )
    return redirect(url_for('donations.email_import_queue', status='inbox'))


@donations_bp.route('/email-import/scan/<int:mailbox_id>', methods=['POST'])
@permission_required('manage_donations')
def email_import_scan(mailbox_id):
    mode = _parse_mode_from_request()
    result = scan_mailbox(mailbox_id, limit=60, use_ai=mode)
    _flash_check_result(result, mode, label=f"“{result.get('label') or mailbox_id}”")
    log_change(
        session['user_id'], 'update',
        change_details=f'Scanned donation mailbox #{mailbox_id} ({mode})',
    )
    return redirect(url_for('donations.email_import_queue', status='inbox'))


@donations_bp.route('/email-import/<int:message_id>')
@permission_required('manage_donations')
def email_import_detail(message_id):
    from app.utils.html_sanitize import sanitize_rich_html
    from markupsafe import Markup

    msg = import_service.get_message(message_id)
    if not msg:
        flash('Message not found.', 'error')
        return redirect(url_for('donations.email_import_queue'))
    # Safe HTML for side-by-side preview when plain text is missing
    if msg.get('body_html') and not (msg.get('body_text') or '').strip():
        msg['body_html_safe'] = Markup(sanitize_rich_html(msg.get('body_html')))
    else:
        msg['body_html_safe'] = None
    return render_template('donations/email_import_detail.html', msg=msg)


@donations_bp.route('/email-import/<int:message_id>/reparse', methods=['POST'])
@permission_required('manage_donations')
def email_import_reparse(message_id):
    mode = _parse_mode_from_request()
    try:
        gift = import_service.reparse_message(message_id, use_ai=mode)
        extras = (gift or {}).get('extras') or {}
        how = extras.get('parse_mode') or mode
        flash(
            f'Re-parsed ({_parse_mode_label(mode)}; engine={how}'
            + (', AI assisted' if extras.get('ai_used') else ', rules')
            + f'). Confidence ~{int(gift.get("confidence") or 0)}%.',
            'success',
        )
    except Exception as e:
        flash(str(e), 'error')
    return redirect(url_for('donations.email_import_detail', message_id=message_id))


@donations_bp.route('/email-import/paste', methods=['POST'])
@permission_required('manage_donations')
def email_import_paste():
    """Paste a payment notification — software detects format and parses."""
    subject = (request.form.get('subject') or '').strip()
    body = (request.form.get('body') or '').strip()
    from_address = (request.form.get('from_address') or '').strip()
    if not body:
        flash('Paste the email body to import.', 'error')
        return redirect(url_for('donations.email_import_queue'))
    try:
        mid = import_service.ingest_pasted_email(
            subject=subject,
            body=body,
            from_address=from_address,
            use_ai=None,  # software default
        )
        flash('Email parsed — review the gift and approve when ready.', 'success')
        log_change(session['user_id'], 'create', change_details=f'Pasted donation email #{mid}')
        return redirect(url_for('donations.email_import_detail', message_id=mid))
    except Exception as e:
        flash(str(e), 'error')
        return redirect(url_for('donations.email_import_queue'))


@donations_bp.route('/email-import/bulk-approve', methods=['POST'])
@permission_required('manage_donations')
def email_import_bulk_approve():
    ids = request.form.getlist('message_id')
    if not ids:
        flash('Select at least one gift to approve.', 'error')
        return redirect(url_for('donations.email_import_queue', status='inbox'))
    result = import_service.bulk_approve_messages(ids)
    flash(
        f"Approved {result.get('posted', 0)} donation(s)."
        + (f" Issues: {'; '.join((result.get('errors') or [])[:4])}" if result.get('errors') else ''),
        'success' if result.get('posted') else 'error',
    )
    log_change(
        session['user_id'], 'create',
        change_details=f"Bulk-approved {result.get('posted', 0)} email donations",
    )
    return redirect(url_for('donations.email_import_queue', status='inbox'))


def _redirect_after_queue_action(done_id: int, action_label: str):
    """
    After approve or deny: open the next gift if any, otherwise the inbox list.
    Keeps staff in a tight review loop.
    """
    next_id = import_service.first_inbox_message_id(exclude_id=done_id)
    if next_id:
        flash(f'{action_label} Opening next gift to review…', 'success')
        return redirect(url_for('donations.email_import_detail', message_id=next_id))
    flash(f'{action_label} No more gifts waiting — back to inbox.', 'success')
    return redirect(url_for('donations.email_import_queue', status='inbox'))


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
        log_change(session['user_id'], 'create', donation_id, change_details='Posted donation from email import')

        receipt_note = ''
        if request.form.get('send_receipt') == '1':
            from app.models.donation import get_donation_by_id
            donation = get_donation_by_id(donation_id)
            church = get_church_info()
            result = import_service.send_or_preview_receipt(donation or {}, church)
            receipt_note = f" Receipt: {result.get('status')} → {result.get('to') or 'n/a'}."
        return _redirect_after_queue_action(
            message_id,
            f'Approved as donation #{donation_id}.{receipt_note}',
        )
    except Exception as e:
        flash(str(e), 'error')
        return redirect(url_for('donations.email_import_detail', message_id=message_id))


@donations_bp.route('/email-import/<int:message_id>/dismiss', methods=['POST'])
@permission_required('manage_donations')
def email_import_dismiss(message_id):
    """Not a gift — skip it and move to the next real gift."""
    reason = (request.form.get('reason') or 'not_a_gift').strip()[:500]
    try:
        import_service.dismiss_message(message_id, reason=reason)
        log_change(
            session['user_id'], 'update',
            change_details=f'Dismissed donation email #{message_id} ({reason})',
        )
        return _redirect_after_queue_action(message_id, 'Skipped (not a gift).')
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
