# Persist parsed gifts, manage import queue, receipts dry-run.

from __future__ import annotations

import json
import re
from typing import Optional

import pymysql
from flask import session

from app.models.db import get_db
from app.utils.field_crypto import encrypt, decrypt
from app.utils.time_utils import now_church, utc_now
from app.donations_import.parsers import parse_payment_email, ParsedGift
from app.donations_import.fixtures import all_fixtures


def _parse_email_list(raw) -> list[str]:
    """Split comma/semicolon/newline list into lowercase emails."""
    if not raw:
        return []
    text = str(raw).replace(';', '\n').replace(',', '\n')
    out = []
    for line in text.splitlines():
        e = line.strip().lower()
        if e and '@' in e:
            out.append(e)
    # unique preserve order
    seen = set()
    uniq = []
    for e in out:
        if e not in seen:
            seen.add(e)
            uniq.append(e)
    return uniq


def get_receipt_settings() -> dict:
    ensure_import_settings_columns()
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    try:
        cur.execute(
            """
            SELECT donation_receipt_mode, donation_email_auto_import, donation_email_auto_post,
                   donation_receipt_test_email, email_send_donation_receipts,
                   donation_email_import_enabled, donation_email_auto_post_min_conf,
                   donation_email_auto_receipt, donation_receipt_policy,
                   donation_receipt_email_list, donation_receipt_staff_notify,
                   donation_email_parse_mode
            FROM settings WHERE id = 1
            """
        )
        row = cur.fetchone() or {}
    except Exception:
        cur.execute(
            """
            SELECT donation_receipt_mode, donation_email_auto_import, donation_email_auto_post,
                   donation_receipt_test_email, email_send_donation_receipts
            FROM settings WHERE id = 1
            """
        )
        row = cur.fetchone() or {}
    min_conf = row.get('donation_email_auto_post_min_conf')
    try:
        min_conf = int(min_conf) if min_conf is not None else 90
    except (TypeError, ValueError):
        min_conf = 90
    min_conf = max(50, min(99, min_conf))
    enabled = row.get('donation_email_import_enabled')
    if enabled is None:
        enabled = 1
    policy = (row.get('donation_receipt_policy') or 'all').strip().lower()
    if policy not in ('all', 'allowlist', 'denylist', 'none'):
        policy = 'all'
    parse_mode = (row.get('donation_email_parse_mode') or 'auto').strip().lower()
    if parse_mode not in ('rules', 'auto', 'ai'):
        parse_mode = 'auto'
    ai_ok = False
    try:
        from app.utils.ai_assist_parse import ai_configured
        ai_ok = bool(ai_configured())
    except Exception:
        ai_ok = False
    return {
        'receipt_mode': (row.get('donation_receipt_mode') or 'test').lower(),
        'auto_import': bool(row.get('donation_email_auto_import')),
        'auto_post': bool(row.get('donation_email_auto_post')),
        'auto_post_min_confidence': min_conf,
        'auto_receipt': bool(row.get('donation_email_auto_receipt')),
        'receipt_policy': policy,
        'receipt_email_list': (row.get('donation_receipt_email_list') or '').strip(),
        'receipt_email_list_parsed': _parse_email_list(row.get('donation_receipt_email_list')),
        'staff_notify': (row.get('donation_receipt_staff_notify') or '').strip(),
        'import_enabled': bool(enabled),
        'test_email': (row.get('donation_receipt_test_email') or '').strip(),
        'send_receipts_enabled': bool(row.get('email_send_donation_receipts', 1)),
        'parse_mode': parse_mode,
        'ai_configured': ai_ok,
    }


def ensure_import_settings_columns():
    """Add optional settings columns used by the import inbox."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        """
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'settings'
        """
    )
    have = {r['COLUMN_NAME'] for r in (cur.fetchall() or [])}
    adds = {
        'donation_email_import_enabled': "TINYINT(1) NOT NULL DEFAULT 1",
        'donation_email_auto_post_min_conf': "INT NOT NULL DEFAULT 90",
        'donation_email_auto_receipt': "TINYINT(1) NOT NULL DEFAULT 0",
        'donation_receipt_policy': "VARCHAR(24) NOT NULL DEFAULT 'all'",
        'donation_receipt_email_list': "MEDIUMTEXT NULL",
        'donation_receipt_staff_notify': "VARCHAR(500) NULL",
        'donation_email_parse_mode': "VARCHAR(16) NOT NULL DEFAULT 'auto'",
    }
    cur2 = db.cursor()
    for col, defn in adds.items():
        if col not in have:
            try:
                cur2.execute(f"ALTER TABLE settings ADD COLUMN {col} {defn}")
            except Exception as e:
                print(f'donation import settings col {col}: {e}')
    db.commit()


def save_receipt_settings(data: dict):
    ensure_import_settings_columns()
    db = get_db()
    cur = db.cursor()
    mode = (data.get('receipt_mode') or 'test').lower()
    if mode not in ('test', 'live', 'off'):
        mode = 'test'
    try:
        min_conf = int(data.get('auto_post_min_confidence') or 90)
    except (TypeError, ValueError):
        min_conf = 90
    min_conf = max(50, min(99, min_conf))
    policy = (data.get('receipt_policy') or 'all').strip().lower()
    if policy not in ('all', 'allowlist', 'denylist', 'none'):
        policy = 'all'
    # Normalize list for storage
    list_raw = (data.get('receipt_email_list') or '').strip()
    if list_raw:
        list_raw = '\n'.join(_parse_email_list(list_raw))
    staff = (data.get('staff_notify') or '').strip() or None
    parse_mode = (data.get('parse_mode') or 'auto').strip().lower()
    if parse_mode not in ('rules', 'auto', 'ai'):
        parse_mode = 'auto'
    cur.execute(
        """
        UPDATE settings SET
            donation_receipt_mode = %s,
            donation_email_auto_import = %s,
            donation_email_auto_post = %s,
            donation_receipt_test_email = %s,
            donation_email_import_enabled = %s,
            donation_email_auto_post_min_conf = %s,
            donation_email_auto_receipt = %s,
            donation_receipt_policy = %s,
            donation_receipt_email_list = %s,
            donation_receipt_staff_notify = %s,
            donation_email_parse_mode = %s
        WHERE id = 1
        """,
        (
            mode,
            1 if data.get('auto_import') else 0,
            1 if data.get('auto_post') else 0,
            (data.get('test_email') or '').strip() or None,
            1 if data.get('import_enabled', True) else 0,
            min_conf,
            1 if data.get('auto_receipt') else 0,
            policy,
            list_raw or None,
            staff,
            parse_mode,
        ),
    )
    db.commit()


def configured_parse_mode() -> str:
    """rules | auto | ai — from Settings on the Email gifts page."""
    mode = (get_receipt_settings().get('parse_mode') or 'auto').strip().lower()
    if mode not in ('rules', 'auto', 'ai'):
        return 'auto'
    return mode


def donor_matches_receipt_policy(donor_email: str, settings: dict | None = None) -> tuple[bool, str]:
    """
    Whether this donor should get a receipt under current policy.
    Returns (should_send, reason).
    """
    settings = settings or get_receipt_settings()
    policy = (settings.get('receipt_policy') or 'all').lower()
    email = (donor_email or '').strip().lower()
    allow = set(settings.get('receipt_email_list_parsed') or _parse_email_list(settings.get('receipt_email_list')))

    if policy == 'none':
        return False, 'policy_none'
    if not email or '@' not in email:
        return False, 'no_donor_email'
    if policy == 'all':
        return True, 'all'
    if policy == 'allowlist':
        if email in allow:
            return True, 'allowlist'
        return False, 'not_on_allowlist'
    if policy == 'denylist':
        if email in allow:
            return False, 'on_denylist'
        return True, 'not_denied'
    return True, 'default'


def list_mailboxes():
    """
    Any Settings → Email account that has POP3/IMAP incoming configured.
    No separate donations mailbox setup — donations only *uses* these accounts.
    """
    try:
        from app.routes.settings import ensure_email_account_role_columns
        ensure_email_account_role_columns()
    except Exception:
        pass
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    try:
        cur.execute(
            """
            SELECT id, name AS label, incoming_protocol AS protocol,
                   incoming_server AS host, incoming_port AS port,
                   incoming_username, incoming_password, incoming_encryption,
                   last_scan_at, last_error
            FROM email_accounts
            WHERE incoming_server IS NOT NULL
              AND TRIM(incoming_server) <> ''
              AND incoming_protocol IS NOT NULL
              AND TRIM(incoming_protocol) <> ''
            ORDER BY name ASC
            """
        )
        rows = cur.fetchall() or []
    except Exception as e:
        print(f'list_mailboxes email_accounts: {e}')
        return []

    out = []
    for r in rows:
        host = (r.get('host') or '').strip()
        if not host:
            continue
        r['enabled'] = True
        r['protocol'] = (r.get('protocol') or 'POP3').lower()
        r['has_password'] = bool(r.get('incoming_password'))
        r.pop('incoming_password', None)
        r.pop('incoming_username', None)
        out.append(r)
    return out


def get_mailbox_secret(mailbox_id: int) -> Optional[dict]:
    """
    POP3/IMAP connection from a Settings → Email account.
    Shape for mailbox scanner: host, port, username, password, protocol, use_ssl, label, enabled.
    """
    try:
        from app.routes.settings import ensure_email_account_role_columns
        ensure_email_account_role_columns()
    except Exception:
        pass
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM email_accounts WHERE id = %s", (mailbox_id,))
    row = cur.fetchone()
    if not row:
        return None

    host = (row.get('incoming_server') or '').strip()
    if not host:
        return None

    user = decrypt(row.get('incoming_username') or '') or decrypt(row.get('outgoing_username') or '')
    password = decrypt(row.get('incoming_password') or '') or decrypt(row.get('outgoing_password') or '')
    protocol = (row.get('incoming_protocol') or 'POP3').strip().lower()
    if protocol not in ('pop3', 'imap'):
        protocol = 'pop3'
    enc = (row.get('incoming_encryption') or 'SSL').upper()
    use_ssl = enc in ('SSL', 'TLS', 'STARTTLS') or True
    port = row.get('incoming_port')
    try:
        port = int(port) if port else (993 if protocol == 'imap' else 995)
    except (TypeError, ValueError):
        port = 993 if protocol == 'imap' else 995

    return {
        'id': row['id'],
        'label': row.get('name') or 'Email account',
        'protocol': protocol,
        'host': host,
        'port': port,
        'username': user,
        'password': password,
        'use_ssl': 1 if use_ssl else 0,
        'enabled': 1,
        'last_scan_at': row.get('last_scan_at'),
        'last_error': row.get('last_error'),
    }


def upsert_message(
    *,
    mailbox_id: int | None,
    uid: str,
    subject: str,
    from_address: str,
    body_text: str,
    body_html: str = '',
    message_id_header: str = '',
    received_at=None,
    is_fixture: bool = False,
    use_ai: str | bool | None = None,
) -> int:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    # Existing?
    cur.execute(
        """
        SELECT id FROM donation_email_messages
        WHERE IFNULL(mailbox_id,0) = IFNULL(%s,0) AND message_uid = %s
        """,
        (mailbox_id, uid),
    )
    existing = cur.fetchone()
    if existing:
        return int(existing['id'])

    # Mode from Check emails form, or automation default
    if use_ai is None:
        use_ai = configured_parse_mode()
    gift = parse_payment_email(subject, body_text or body_html, from_address, use_ai=use_ai)
    parse_status = _status_for_gift(gift)
    # If this gift was already posted as a donation, mark linked (skip re-post)
    existing_don = _find_existing_donation(gift)
    donation_id = existing_don
    if existing_don:
        parse_status = 'already_recorded'
    err_detail = None
    if parse_status == 'skipped':
        err_detail = 'No gift amount found — auto-skipped (not a payment email)'
    extras = gift.extras or {}
    if extras.get('ai_error'):
        err_detail = (err_detail + '; ' if err_detail else '') + str(extras.get('ai_error'))[:400]
    cur2 = db.cursor()
    cur2.execute(
        """
        INSERT INTO donation_email_messages
            (mailbox_id, message_uid, message_id_header, subject, from_address, received_at,
             body_text, body_html, processor, parse_status, parse_confidence, parsed_json,
             donation_id, is_fixture, error_detail)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            mailbox_id,
            uid,
            message_id_header or None,
            subject[:500] if subject else None,
            from_address[:255] if from_address else None,
            received_at,
            body_text,
            body_html or None,
            gift.processor,
            parse_status,
            gift.confidence,
            json.dumps(gift.to_dict()),
            donation_id,
            1 if is_fixture else 0,
            err_detail,
        ),
    )
    db.commit()
    new_id = int(cur2.lastrowid)
    # Optional auto-post (high confidence only) — never for already_recorded / skipped
    if parse_status in ('parsed', 'needs_review') and not donation_id:
        _maybe_auto_post(new_id, gift)
    return new_id


# Terminal / hidden statuses — not shown in the main “Needs you” queue
_HIDDEN_STATUSES = frozenset({
    'posted', 'already_recorded', 'skipped', 'dismissed', 'not_a_gift',
})


def _status_for_gift(gift: ParsedGift) -> str:
    """
    Classify parse result for the queue.
    - skipped: no gift amount found (marketing, bounce, etc.) — hide from main inbox
    - parsed: clear gift ready to approve
    - needs_review: amount found but fields/confidence are weak
    """
    try:
        amount = float(gift.amount or 0)
    except (TypeError, ValueError):
        amount = 0.0
    try:
        conf = float(gift.confidence or 0)
    except (TypeError, ValueError):
        conf = 0.0
    if amount <= 0:
        return 'skipped'
    if conf >= 55:
        return 'parsed'
    return 'needs_review'


def reclassify_non_gifts() -> int:
    """
    Mark queued rows with no amount as skipped so they leave “Needs you”.
    Safe to call on every inbox load (only updates when needed).
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        """
        SELECT id, parsed_json, parse_status FROM donation_email_messages
        WHERE donation_id IS NULL
          AND IFNULL(parse_status,'') NOT IN ('posted','already_recorded','skipped','dismissed','not_a_gift')
        LIMIT 500
        """
    )
    rows = cur.fetchall() or []
    updated = 0
    cur2 = db.cursor()
    for row in rows:
        try:
            parsed = json.loads(row.get('parsed_json') or '{}')
        except json.JSONDecodeError:
            parsed = {}
        try:
            amount = float(parsed.get('amount') or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount > 0:
            continue
        cur2.execute(
            """
            UPDATE donation_email_messages
            SET parse_status = 'skipped',
                error_detail = COALESCE(NULLIF(error_detail,''), 'No gift amount found — not a payment email')
            WHERE id = %s AND donation_id IS NULL
            """,
            (row['id'],),
        )
        updated += 1
    if updated:
        db.commit()
    return updated


def dismiss_message(message_id: int, reason: str = 'not_a_gift') -> None:
    """Staff deny / skip — hide from main queue (still available under Manually check)."""
    db = get_db()
    cur = db.cursor()
    detail = (reason or 'not_a_gift').strip()[:500]
    cur.execute(
        """
        UPDATE donation_email_messages
        SET parse_status = 'dismissed', error_detail = %s
        WHERE id = %s AND donation_id IS NULL
        """,
        (detail, message_id),
    )
    if cur.rowcount == 0:
        raise ValueError('Message not found or already saved as a donation.')
    db.commit()


def first_inbox_message_id(exclude_id: int | None = None) -> int | None:
    """Next gift that still needs staff action (FIFO)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    sql = """
        SELECT id FROM donation_email_messages
        WHERE donation_id IS NULL
          AND IFNULL(parse_status,'') NOT IN ('posted','already_recorded','skipped','dismissed','not_a_gift')
    """
    params: list = []
    if exclude_id:
        sql += " AND id <> %s"
        params.append(int(exclude_id))
    sql += " ORDER BY created_at ASC, id ASC LIMIT 1"
    cur.execute(sql, params)
    row = cur.fetchone()
    return int(row['id']) if row else None


def _find_existing_donation(gift: ParsedGift) -> int | None:
    """If processor+external_id or confirmation already on a donation, return that id."""
    processor = (gift.processor or 'email').lower()
    external_id = (gift.external_id or gift.confirmation_number or '').strip()[:128]
    if not external_id:
        return None
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "SELECT id FROM donations WHERE processor = %s AND external_id = %s LIMIT 1",
        (processor, external_id),
    )
    row = cur.fetchone()
    if row:
        return int(row['id'])
    if gift.confirmation_number:
        cur.execute(
            "SELECT id FROM donations WHERE confirmation_number = %s LIMIT 1",
            (gift.confirmation_number[:120],),
        )
        row = cur.fetchone()
        if row:
            return int(row['id'])
    return None


def _maybe_auto_post(message_id: int, gift: ParsedGift) -> int | None:
    """
    When staff trust the pipeline: auto-create donation if confidence is high enough.
    Optionally send receipts per receipt_mode + allow/deny lists.
    """
    settings = get_receipt_settings()
    if not settings.get('auto_post'):
        return None
    min_c = int(settings.get('auto_post_min_confidence') or 90)
    if gift.amount <= 0 or float(gift.confidence or 0) < min_c:
        return None
    try:
        donation_id = post_message_as_donation(message_id)
        if donation_id and settings.get('auto_receipt'):
            _auto_send_receipt_for_donation(donation_id)
        return donation_id
    except Exception as e:
        print(f'auto_post message {message_id}: {e}')
        return None


def _auto_send_receipt_for_donation(donation_id: int) -> dict | None:
    """Apply receipt mode + allow/deny policy after trusted auto-post."""
    try:
        from app.models.donation import get_donation_by_id
        donation = get_donation_by_id(donation_id)
        if not donation:
            return None
        settings = get_receipt_settings()
        # Staff-only notify (always, if configured) — separate from donor receipt
        staff = (settings.get('staff_notify') or '').strip()
        if staff:
            _notify_staff_of_auto_gift(donation, staff)

        ok, reason = donor_matches_receipt_policy(donation.get('donor_email') or '', settings)
        if not ok:
            _set_receipt_status(donation_id, f'skipped_{reason}'[:24])
            return {'status': 'skipped', 'reason': reason}

        # Reuse existing receipt sender (respects test/live/off)
        try:
            from app.routes.donations.utils import get_church_info
            church = get_church_info() or {}
        except Exception:
            church = {}
        return send_or_preview_receipt(donation, church)
    except Exception as e:
        print(f'auto receipt donation {donation_id}: {e}')
        return None


def _notify_staff_of_auto_gift(donation: dict, staff_raw: str):
    """Optional: email church staff when a gift was auto-approved."""
    from app.utils.emailer import send_email
    recipients = _parse_email_list(staff_raw)
    if not recipients:
        return
    body = (
        f"Auto-approved email gift\n\n"
        f"Donation #{donation.get('id')}\n"
        f"Donor: {donation.get('name')}\n"
        f"Email: {donation.get('donor_email') or '—'}\n"
        f"Amount: ${float(donation.get('amount') or 0):,.2f}\n"
        f"Date: {donation.get('date')}\n"
        f"Method: {donation.get('method')}\n"
        f"Confirmation: {donation.get('confirmation_number') or '—'}\n"
    )
    subject = f"[Auto gift] ${float(donation.get('amount') or 0):,.2f} — {donation.get('name') or 'Donor'}"
    for to in recipients:
        try:
            send_email(to, subject, body)
        except Exception as e:
            print(f'staff notify {to}: {e}')


def load_fixtures(force: bool = False) -> int:
    """Insert mock provider emails into the queue (no SMTP) for parser/receipt testing."""
    count = 0
    for fx in all_fixtures():
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute(
            "SELECT id FROM donation_email_messages WHERE message_uid = %s AND is_fixture = 1",
            (fx['uid'],),
        )
        if cur.fetchone() and not force:
            continue
        if force:
            cur.execute("DELETE FROM donation_email_messages WHERE message_uid = %s AND is_fixture = 1", (fx['uid'],))
            db.commit()
        upsert_message(
            mailbox_id=None,
            uid=fx['uid'],
            subject=fx['subject'],
            from_address=fx['from_address'],
            body_text=fx['body_text'],
            is_fixture=True,
            received_at=utc_now(),
            use_ai='rules',
        )
        count += 1
    return count


def send_sample_payment_emails(to_email: str | None = None) -> dict:
    """
    Email realistic sample gift notices (Stripe, PayPal, Cash App, Venmo, ACH, …)
    via Settings → Email SMTP.

    Requires an explicit To address — never defaults to admin, mailbox username,
    or any account on file (avoids flooding real inboxes with test mail).
    """
    from app.utils.emailer import send_email

    to_email = (to_email or '').strip()
    if not to_email or '@' not in to_email:
        raise ValueError(
            'Enter a destination email for samples. '
            'Nothing is sent by default to admin or your real mailboxes.'
        )

    sent = 0
    errors = []
    for fx in all_fixtures():
        subject = f"[TEST GIFT · {fx.get('processor', 'gift')}] {fx['subject']}"
        body = (
            f"(Church Portal test sample — parse practice only)\n"
            f"Simulated provider From: {fx.get('from_address') or 'payments@example.com'}\n"
            f"Processor tag: {fx.get('processor') or 'unknown'}\n\n"
            f"{fx['body_text']}\n"
        )
        try:
            send_email(to_email, subject, body)
            sent += 1
        except Exception as e:
            errors.append(f"{fx.get('uid')}: {e}")
    return {'to': to_email, 'sent': sent, 'errors': errors, 'total': len(all_fixtures())}


def revalidate_open_parses(use_ai: str = 'rules', limit: int = 80) -> dict:
    """
    Re-run rules (default) on open queue rows so false gifts (cPanel/IP amounts)
    move to skipped without requiring a full mailbox re-download.
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        """
        SELECT id FROM donation_email_messages
        WHERE donation_id IS NULL
          AND IFNULL(parse_status,'') NOT IN ('posted','already_recorded','dismissed')
        ORDER BY id ASC
        LIMIT %s
        """,
        (int(limit),),
    )
    ids = [int(r['id']) for r in (cur.fetchall() or [])]
    fixed = 0
    skipped = 0
    for mid in ids:
        try:
            gift = reparse_message(mid, use_ai=use_ai)
            fixed += 1
            if float(gift.get('amount') or 0) <= 0:
                skipped += 1
        except Exception:
            continue
    return {'reparsed': fixed, 'now_skipped': skipped}


def list_messages(status: str | None = None, limit: int = 100):
    """
    status filters:
      - inbox / new / unposted — real gifts needing staff (excludes skipped/dismissed)
      - ready — clear parses ready to approve
      - needs_review — amount found but unclear fields
      - manual / skipped — auto-skipped or staff-dismissed (not payment emails)
      - posted / already_recorded — saved gifts
      - all — everything
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    sql = "SELECT * FROM donation_email_messages"
    params: list = []
    st = (status or 'inbox').strip().lower()
    hidden = "('posted','already_recorded','skipped','dismissed','not_a_gift')"
    if st in ('inbox', 'new', 'unposted', 'queue'):
        sql += (
            f" WHERE donation_id IS NULL AND IFNULL(parse_status,'') NOT IN {hidden}"
        )
    elif st in ('manual', 'skipped', 'other', 'not_gifts'):
        sql += (
            " WHERE donation_id IS NULL"
            " AND parse_status IN ('skipped','dismissed','not_a_gift')"
        )
    elif st in ('all',):
        pass
    elif st == 'posted':
        sql += " WHERE donation_id IS NOT NULL OR parse_status IN ('posted','already_recorded')"
    elif st == 'ready':
        sql += " WHERE donation_id IS NULL AND parse_status = 'parsed'"
    elif st == 'needs_review':
        sql += " WHERE donation_id IS NULL AND parse_status = 'needs_review'"
    else:
        sql += " WHERE parse_status = %s"
        params.append(st)
    # Inbox: oldest first so “next email” is natural; other tabs newest first
    if st in ('inbox', 'new', 'unposted', 'queue', 'ready', 'needs_review'):
        sql += " ORDER BY created_at ASC, id ASC LIMIT %s"
    else:
        sql += " ORDER BY created_at DESC, id DESC LIMIT %s"
    params.append(int(limit))
    cur.execute(sql, params)
    rows = cur.fetchall() or []
    for r in rows:
        try:
            r['parsed'] = json.loads(r.get('parsed_json') or '{}')
        except json.JSONDecodeError:
            r['parsed'] = {}
        r['donor_match'] = resolve_donor_match(r.get('parsed') or {})
        r['member_match'] = match_member_for_parsed(r.get('parsed') or {})
    return rows


def queue_counts() -> dict:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    hidden = "('posted','already_recorded','skipped','dismissed','not_a_gift')"
    cur.execute(
        f"""
        SELECT
          SUM(CASE WHEN donation_id IS NULL
                    AND IFNULL(parse_status,'') NOT IN {hidden}
                   THEN 1 ELSE 0 END) AS inbox,
          SUM(CASE WHEN parse_status = 'needs_review' AND donation_id IS NULL THEN 1 ELSE 0 END) AS needs_review,
          SUM(CASE WHEN parse_status = 'parsed' AND donation_id IS NULL THEN 1 ELSE 0 END) AS ready,
          SUM(CASE WHEN donation_id IS NOT NULL OR parse_status IN ('posted','already_recorded')
                   THEN 1 ELSE 0 END) AS posted,
          SUM(CASE WHEN donation_id IS NULL
                    AND parse_status IN ('skipped','dismissed','not_a_gift')
                   THEN 1 ELSE 0 END) AS manual
        FROM donation_email_messages
        """
    )
    row = cur.fetchone() or {}
    return {
        'inbox': int(row.get('inbox') or 0),
        'needs_review': int(row.get('needs_review') or 0),
        'ready': int(row.get('ready') or 0),
        'posted': int(row.get('posted') or 0),
        'manual': int(row.get('manual') or 0),
    }


def _normalize_phone(raw: str | None) -> str:
    """Digits-only phone; strip leading US 1 for 11-digit numbers."""
    digits = re.sub(r'\D+', '', str(raw or ''))
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    return digits


def _user_display_name(row: dict) -> str:
    name = ' '.join(
        x for x in [(row.get('first_name') or '').strip(), (row.get('last_name') or '').strip()] if x
    )
    return name or (row.get('username') or row.get('email') or 'Member')


def match_member_for_parsed(parsed: dict) -> dict | None:
    """
    Link to a registered member by donor email or phone when possible.
    Returns None when no member account is found (guest path).
    """
    match = resolve_donor_match(parsed)
    if match.get('kind') == 'member' and match.get('user_id'):
        return {
            'user_id': match['user_id'],
            'name': match.get('name'),
            'email': match.get('email'),
            'phone': match.get('phone') or '',
            'match_by': match.get('match_by'),
        }
    return None


def resolve_donor_match(parsed: dict | None) -> dict:
    """
    Simple on-file check after parse:
      1) Registered member by email
      2) Registered member by phone
      3) Prior donation row by email / phone (guest history)
      4) New guest otherwise

    Always returns a dict with kind, donor_type, and labels for the review UI.
    """
    parsed = parsed or {}
    email = (parsed.get('donor_email') or '').strip().lower()
    phone_raw = (parsed.get('donor_phone') or parsed.get('phone') or '').strip()
    phone = _normalize_phone(phone_raw)
    name_hint = (parsed.get('donor_name') or '').strip()

    result = {
        'kind': 'new_guest',
        'donor_type': 'guest',
        'user_id': None,
        'name': name_hint or 'Online Donor',
        'email': email or '',
        'phone': phone_raw or '',
        'match_by': None,
        'prior_donation_count': 0,
        'label': 'New guest — no member or prior gift on file',
    }

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    # 1) Member by email
    if email and '@' in email:
        try:
            cur.execute(
                """
                SELECT id, username, email, first_name, last_name, phone
                FROM users
                WHERE LOWER(TRIM(email)) = %s
                LIMIT 1
                """,
                (email,),
            )
            row = cur.fetchone()
            if row:
                result.update({
                    'kind': 'member',
                    'donor_type': 'member',
                    'user_id': int(row['id']),
                    'name': _user_display_name(row),
                    'email': (row.get('email') or email).strip(),
                    'phone': (row.get('phone') or phone_raw or '').strip(),
                    'match_by': 'member_email',
                    'label': f"Registered member · {_user_display_name(row)}",
                })
                return result
        except Exception:
            pass

    # 2) Member by phone (digits match)
    if phone and len(phone) >= 7:
        try:
            cur.execute(
                """
                SELECT id, username, email, first_name, last_name, phone
                FROM users
                WHERE phone IS NOT NULL AND TRIM(phone) != ''
                LIMIT 400
                """
            )
            for row in cur.fetchall() or []:
                if _normalize_phone(row.get('phone')) == phone:
                    result.update({
                        'kind': 'member',
                        'donor_type': 'member',
                        'user_id': int(row['id']),
                        'name': _user_display_name(row),
                        'email': (row.get('email') or email or '').strip(),
                        'phone': (row.get('phone') or phone_raw or '').strip(),
                        'match_by': 'member_phone',
                        'label': f"Registered member (phone) · {_user_display_name(row)}",
                    })
                    return result
        except Exception:
            pass

    # 3) Prior donation records (guest or any) by email / phone
    prior = None
    prior_count = 0
    try:
        if email and '@' in email:
            cur.execute(
                """
                SELECT id, name, user_id, donor_email, donor_phone, donor_type
                FROM donations
                WHERE LOWER(TRIM(IFNULL(donor_email,''))) = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (email,),
            )
            prior = cur.fetchone()
            cur.execute(
                """
                SELECT COUNT(*) AS cnt FROM donations
                WHERE LOWER(TRIM(IFNULL(donor_email,''))) = %s
                """,
                (email,),
            )
            prior_count = int((cur.fetchone() or {}).get('cnt') or 0)
            if prior:
                result['match_by'] = 'prior_email'
        if not prior and phone and len(phone) >= 7:
            cur.execute(
                """
                SELECT id, name, user_id, donor_email, donor_phone, donor_type
                FROM donations
                WHERE donor_phone IS NOT NULL AND TRIM(donor_phone) != ''
                ORDER BY id DESC
                LIMIT 300
                """
            )
            for row in cur.fetchall() or []:
                if _normalize_phone(row.get('donor_phone')) == phone:
                    prior = row
                    result['match_by'] = 'prior_phone'
                    break
            if prior:
                cur.execute(
                    """
                    SELECT id, donor_phone FROM donations
                    WHERE donor_phone IS NOT NULL AND TRIM(donor_phone) != ''
                    ORDER BY id DESC
                    LIMIT 500
                    """
                )
                prior_count = sum(
                    1 for r in (cur.fetchall() or [])
                    if _normalize_phone(r.get('donor_phone')) == phone
                )
    except Exception:
        prior = None

    if prior:
        # If a prior gift was already linked to a member, prefer that
        uid = prior.get('user_id')
        if uid:
            try:
                cur.execute(
                    """
                    SELECT id, username, email, first_name, last_name, phone
                    FROM users WHERE id = %s LIMIT 1
                    """,
                    (int(uid),),
                )
                urow = cur.fetchone()
                if urow:
                    result.update({
                        'kind': 'member',
                        'donor_type': 'member',
                        'user_id': int(urow['id']),
                        'name': _user_display_name(urow),
                        'email': (urow.get('email') or prior.get('donor_email') or email or '').strip(),
                        'phone': (urow.get('phone') or prior.get('donor_phone') or phone_raw or '').strip(),
                        'match_by': 'prior_linked_member',
                        'prior_donation_count': prior_count or 1,
                        'label': f"Registered member (from prior gifts) · {_user_display_name(urow)}",
                    })
                    return result
            except Exception:
                pass

        pname = (prior.get('name') or name_hint or 'Online Donor').strip()
        result.update({
            'kind': 'prior_guest',
            'donor_type': 'guest',
            'user_id': None,
            'name': pname,
            'email': (prior.get('donor_email') or email or '').strip(),
            'phone': (prior.get('donor_phone') or phone_raw or '').strip(),
            'prior_donation_count': prior_count or 1,
            'label': (
                f"Prior guest on file · {pname}"
                + (f" · {prior_count} earlier gift(s)" if prior_count else "")
            ),
        })
        return result

    return result


def get_message(message_id: int):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM donation_email_messages WHERE id = %s", (message_id,))
    row = cur.fetchone()
    if not row:
        return None
    try:
        row['parsed'] = json.loads(row.get('parsed_json') or '{}')
    except json.JSONDecodeError:
        row['parsed'] = {}
    row['donor_match'] = resolve_donor_match(row.get('parsed') or {})
    row['member_match'] = match_member_for_parsed(row.get('parsed') or {})
    return row


def reparse_message(message_id: int, use_ai: str | bool | None = None) -> dict:
    msg = get_message(message_id)
    if not msg:
        raise ValueError('Message not found')
    if use_ai is None:
        use_ai = configured_parse_mode()
    gift = parse_payment_email(
        msg.get('subject') or '',
        msg.get('body_text') or msg.get('body_html') or '',
        msg.get('from_address') or '',
        use_ai=use_ai,
    )
    existing_don = msg.get('donation_id') or _find_existing_donation(gift)
    if msg.get('donation_id'):
        parse_status = 'posted'
    elif existing_don:
        parse_status = 'already_recorded'
    else:
        parse_status = _status_for_gift(gift)
    db = get_db()
    cur = db.cursor()
    err_detail = None
    extras = gift.extras or {}
    if extras.get('ai_error'):
        err_detail = str(extras.get('ai_error'))[:500]
    cur.execute(
        """
        UPDATE donation_email_messages
        SET processor=%s, parse_status=%s, parse_confidence=%s, parsed_json=%s,
            error_detail=%s, donation_id=COALESCE(donation_id, %s)
        WHERE id=%s
        """,
        (
            gift.processor,
            parse_status,
            gift.confidence,
            json.dumps(gift.to_dict()),
            err_detail,
            existing_don,
            message_id,
        ),
    )
    db.commit()
    return gift.to_dict()


def bulk_approve_messages(message_ids: list[int]) -> dict:
    """Staff approve several ready gifts into donation records."""
    posted = 0
    errors = []
    for mid in message_ids or []:
        try:
            post_message_as_donation(int(mid))
            posted += 1
        except Exception as e:
            errors.append(f'#{mid}: {e}')
    return {'posted': posted, 'errors': errors}


def ingest_pasted_email(
    *,
    subject: str,
    body: str,
    from_address: str = '',
    use_ai: str | bool | None = None,
) -> int:
    """Create a queue row from a manually pasted payment email (software parses)."""
    import hashlib
    subject = (subject or '').strip() or '(no subject)'
    body = (body or '').strip()
    if not body:
        raise ValueError('Email body is required.')
    digest = hashlib.sha256(
        f'{subject}|{from_address}|{body[:2000]}'.encode('utf-8', errors='replace')
    ).hexdigest()[:24]
    uid = f'paste-{digest}'
    if use_ai is None:
        use_ai = configured_parse_mode()
    gift = parse_payment_email(subject, body, from_address, use_ai=use_ai)
    existing_don = _find_existing_donation(gift)
    parse_status = 'already_recorded' if existing_don else _status_for_gift(gift)
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "SELECT id FROM donation_email_messages WHERE message_uid = %s AND mailbox_id IS NULL",
        (uid,),
    )
    existing = cur.fetchone()
    if existing:
        reparse_message(int(existing['id']), use_ai=use_ai)
        return int(existing['id'])
    cur2 = db.cursor()
    cur2.execute(
        """
        INSERT INTO donation_email_messages
            (mailbox_id, message_uid, subject, from_address, received_at,
             body_text, processor, parse_status, parse_confidence, parsed_json,
             donation_id, is_fixture)
        VALUES (NULL,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0)
        """,
        (
            uid,
            subject[:500],
            (from_address or '')[:255] or None,
            utc_now(),
            body,
            gift.processor,
            parse_status,
            gift.confidence,
            json.dumps(gift.to_dict()),
            existing_don,
        ),
    )
    db.commit()
    mid = int(cur2.lastrowid)
    if parse_status != 'already_recorded':
        _maybe_auto_post(mid, gift)
    return mid


def post_message_as_donation(message_id: int, overrides: dict | None = None) -> int:
    """Create a donation from a parsed email message (idempotent on processor+external_id)."""
    msg = get_message(message_id)
    if not msg:
        raise ValueError('Message not found')
    if msg.get('donation_id'):
        return int(msg['donation_id'])

    parsed = dict(msg.get('parsed') or {})
    overrides = overrides or {}
    parsed.update({k: v for k, v in overrides.items() if v not in (None, '')})

    amount = float(parsed.get('amount') or 0)
    if amount <= 0:
        raise ValueError('Amount missing or zero — review the parse first.')

    processor = (parsed.get('processor') or msg.get('processor') or 'email').lower()
    external_id = (parsed.get('external_id') or parsed.get('confirmation_number') or f'msg-{message_id}')[:128]

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "SELECT id FROM donations WHERE processor = %s AND external_id = %s LIMIT 1",
        (processor, external_id),
    )
    existing = cur.fetchone()
    if existing:
        cur2 = db.cursor()
        cur2.execute(
            "UPDATE donation_email_messages SET donation_id=%s, parse_status='posted' WHERE id=%s",
            (existing['id'], message_id),
        )
        db.commit()
        return int(existing['id'])

    # Match member account or prior guest gifts by email/phone on file
    donor = resolve_donor_match(parsed)
    donor_type = donor.get('donor_type') or 'guest'
    donor_name = (
        donor.get('name')
        or parsed.get('donor_name')
        or 'Online Donor'
    )
    user_id = donor.get('user_id')
    donor_email = (
        (parsed.get('donor_email') or '').strip()
        or (donor.get('email') or '').strip()
    )
    donor_phone = (
        (parsed.get('donor_phone') or parsed.get('phone') or '').strip()
        or (donor.get('phone') or '').strip()
    )
    method = (parsed.get('method') or processor.title() or 'Online').strip()

    # Note on the donation for audit trail
    notes = (parsed.get('notes') or '').strip()
    match_note = ''
    if donor.get('kind') == 'member':
        match_note = f"Linked to member #{user_id} via {donor.get('match_by') or 'match'}."
    elif donor.get('kind') == 'prior_guest':
        match_note = (
            f"Matched prior guest on file ({donor.get('match_by') or 'email/phone'}"
            f"; {donor.get('prior_donation_count') or 0} earlier gift(s))."
        )
    else:
        match_note = 'New guest donor (no member/email/phone match on file).'
    if match_note:
        notes = f'{notes} {match_note}'.strip() if notes else match_note

    # Never post known non-gift / bounce garbage into the books
    bad_name = (donor_name or '').lower()
    if any(
        x in bad_name
        for x in (
            'mail delivery software',
            'mailer-daemon',
            'mail delivery system',
            'undelivered mail',
            'postmaster',
            'online donor',
        )
    ) and amount and processor in ('unknown', 'email', ''):
        if 'online donor' not in bad_name or processor in ('unknown', 'email', ''):
            if any(x in bad_name for x in ('mail delivery', 'mailer-daemon', 'postmaster', 'undelivered')):
                raise ValueError(
                    'This looks like a bounce/system email, not a gift. '
                    'Skip it under Email gifts instead of approving.'
                )

    gift_date = parsed.get('date') or now_church().strftime('%Y-%m-%d')
    donation_id = _insert_donation_extended(
        name=donor_name,
        amount=amount,
        date=gift_date,
        method=method,
        notes=notes,
        confirmation_number=parsed.get('confirmation_number') or external_id,
        donor_email=donor_email,
        donor_phone=donor_phone,
        donor_type=donor_type,
        user_id=user_id,
        source='email_import',
        processor=processor,
        external_id=external_id,
        currency=parsed.get('currency') or 'USD',
        fund_label=parsed.get('fund_label') or '',
        is_recurring=1 if parsed.get('is_recurring') else 0,
        import_message_id=message_id,
        receipt_status='pending',
    )

    cur2 = db.cursor()
    cur2.execute(
        "UPDATE donation_email_messages SET donation_id=%s, parse_status='posted' WHERE id=%s",
        (donation_id, message_id),
    )
    db.commit()

    # Double-entry: Debit Cash / Credit Tithes & Offerings
    try:
        from app.models.accounting import post_donation_income
        from flask import session as flask_session
        post_donation_income(
            int(donation_id),
            amount,
            gift_date,
            memo=f"Email gift · {donor_name} · {method}"[:500],
            created_by=flask_session.get('user_id'),
        )
    except Exception as e:
        print(f'email gift accounting post failed #{donation_id}: {e}')

    if parsed.get('is_recurring'):
        _ensure_recurring_from_parsed(parsed, donation_id)

    return donation_id


def _insert_donation_extended(**kwargs) -> int:
    """Insert using extended columns when available; fall back to classic add_donation."""
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute(
            """
            INSERT INTO donations
                (name, amount, date, method, notes, confirmation_number, goods_services_provided,
                 user_id, donor_email, donor_phone, donor_type, external_id, source, processor,
                 currency, receipt_status, import_message_id, fund_label, is_recurring)
            VALUES (%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                kwargs['name'],
                kwargs['amount'],
                kwargs['date'],
                kwargs['method'],
                kwargs.get('notes') or '',
                kwargs.get('confirmation_number') or '',
                kwargs.get('user_id'),
                kwargs.get('donor_email') or '',
                kwargs.get('donor_phone') or '',
                kwargs.get('donor_type') or 'guest',
                kwargs.get('external_id'),
                kwargs.get('source') or 'email_import',
                kwargs.get('processor'),
                kwargs.get('currency') or 'USD',
                kwargs.get('receipt_status') or 'pending',
                kwargs.get('import_message_id'),
                kwargs.get('fund_label') or None,
                kwargs.get('is_recurring') or 0,
            ),
        )
        db.commit()
        return cur.lastrowid
    except Exception:
        from app.models.donation import add_donation
        return add_donation(
            name=kwargs['name'],
            amount=kwargs['amount'],
            date=kwargs['date'],
            method=kwargs['method'],
            notes=kwargs.get('notes') or '',
            confirmation_number=kwargs.get('confirmation_number') or '',
            donor_email=kwargs.get('donor_email') or '',
            donor_phone=kwargs.get('donor_phone') or '',
            donor_type=kwargs.get('donor_type') or 'guest',
            user_id=kwargs.get('user_id'),
        )


def _ensure_recurring_from_parsed(parsed: dict, donation_id: int):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            """
            INSERT INTO donation_recurring
                (donor_name, donor_email, amount, currency, frequency, processor,
                 external_subscription_id, method, status, start_date, notes)
            VALUES (%s,%s,%s,%s,'monthly',%s,%s,%s,'active',%s,%s)
            """,
            (
                parsed.get('donor_name') or 'Online Donor',
                parsed.get('donor_email') or None,
                float(parsed.get('amount') or 0),
                parsed.get('currency') or 'USD',
                parsed.get('processor'),
                parsed.get('external_id'),
                parsed.get('method'),
                parsed.get('date') or now_church().strftime('%Y-%m-%d'),
                f'Auto-created from donation #{donation_id}',
            ),
        )
        rid = cur.lastrowid
        cur.execute("UPDATE donations SET recurring_id=%s WHERE id=%s", (rid, donation_id))
        db.commit()
    except Exception:
        db.rollback()


def send_or_preview_receipt(donation: dict, church_info: dict, *, respect_policy: bool = True) -> dict:
    """
    Send receipt according to donation_receipt_mode:
      - off: do nothing
      - test: send only to test address (never donor)
      - live: send to donor if enabled + optional allow/deny list
    Returns {status, to, preview_body}
    """
    from app.utils.emailer import send_email

    settings = get_receipt_settings()
    mode = settings['receipt_mode']
    church = church_info.get('church_name') or 'Church'
    body = f"""Thank you for your generous gift to {church}.

Donor: {donation.get('name', 'Donor')}
Amount: ${float(donation.get('amount', 0)):,.2f}
Date: {donation.get('date')}
Method: {donation.get('method', 'N/A')}
Confirmation #: {donation.get('confirmation_number') or 'N/A'}
Processor: {donation.get('processor') or 'N/A'}
Fund: {donation.get('fund_label') or 'General'}

{church_info.get('tax_status') or ''}

This message serves as acknowledgment of your donation. Please retain for your records.
"""
    subject = f"Donation receipt - {church}"
    donor_email = (donation.get('donor_email') or '').strip()

    if mode == 'off' or not settings['send_receipts_enabled']:
        _set_receipt_status(donation.get('id'), 'skipped')
        return {'status': 'skipped', 'to': None, 'preview_body': body, 'subject': subject}

    if mode == 'test':
        to = settings['test_email'] or None
        if not to:
            _set_receipt_status(donation.get('id'), 'test_pending')
            return {
                'status': 'test_pending',
                'to': None,
                'preview_body': body,
                'subject': f"[TEST] {subject}",
                'message': 'Set a test email under Donations → Email Import settings.',
            }
        try:
            send_email(to, f"[TEST] {subject}", body)
            _set_receipt_status(donation.get('id'), 'test_sent')
            return {'status': 'test_sent', 'to': to, 'preview_body': body, 'subject': f"[TEST] {subject}"}
        except Exception as e:
            return {'status': 'error', 'to': to, 'preview_body': body, 'error': str(e)[:200]}

    # live — allowlist / denylist / none
    if respect_policy:
        ok, reason = donor_matches_receipt_policy(donor_email, settings)
        if not ok:
            _set_receipt_status(donation.get('id'), 'skipped')
            return {
                'status': 'skipped',
                'to': None,
                'preview_body': body,
                'subject': subject,
                'reason': reason,
                'message': f'Receipt not sent ({reason.replace("_", " ")}).',
            }

    if not donor_email:
        _set_receipt_status(donation.get('id'), 'no_email')
        return {'status': 'no_email', 'to': None, 'preview_body': body, 'subject': subject}
    try:
        send_email(donor_email, subject, body)
        _set_receipt_status(donation.get('id'), 'sent')
        return {'status': 'sent', 'to': donor_email, 'preview_body': body, 'subject': subject}
    except Exception as e:
        _set_receipt_status(donation.get('id'), 'error')
        return {'status': 'error', 'to': donor_email, 'preview_body': body, 'error': str(e)[:200]}


def _set_receipt_status(donation_id, status: str):
    if not donation_id:
        return
    try:
        db = get_db()
        cur = db.cursor()
        if status in ('sent', 'test_sent'):
            cur.execute(
                "UPDATE donations SET receipt_status=%s, receipt_sent_at=%s WHERE id=%s",
                (status, utc_now(), donation_id),
            )
        else:
            cur.execute(
                "UPDATE donations SET receipt_status=%s WHERE id=%s",
                (status, donation_id),
            )
        db.commit()
    except Exception:
        pass


def enterprise_report(year: int | None = None) -> dict:
    """High-level giving analytics for leadership / AI Insights."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    y = year or now_church().year
    report = {'year': y}

    try:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt, COALESCE(SUM(amount),0) AS total
            FROM donations
            WHERE YEAR(STR_TO_DATE(date, '%%Y-%%m-%%d')) = %s OR YEAR(date) = %s
            """,
            (y, y),
        )
        row = cur.fetchone() or {}
        report['gift_count'] = int(row.get('cnt') or 0)
        report['total_amount'] = float(row.get('total') or 0)
    except Exception:
        report['gift_count'] = 0
        report['total_amount'] = 0.0

    try:
        cur.execute(
            """
            SELECT COALESCE(processor, method, 'unknown') AS channel,
                   COUNT(*) AS cnt, COALESCE(SUM(amount),0) AS total
            FROM donations
            WHERE YEAR(STR_TO_DATE(date, '%%Y-%%m-%%d')) = %s OR YEAR(date) = %s
            GROUP BY channel
            ORDER BY total DESC
            """,
            (y, y),
        )
        report['by_channel'] = cur.fetchall() or []
    except Exception:
        report['by_channel'] = []

    try:
        cur.execute(
            """
            SELECT COALESCE(source, 'manual') AS source,
                   COUNT(*) AS cnt, COALESCE(SUM(amount),0) AS total
            FROM donations
            GROUP BY source
            """
        )
        report['by_source'] = cur.fetchall() or []
    except Exception:
        report['by_source'] = []

    try:
        cur.execute(
            """
            SELECT receipt_status, COUNT(*) AS cnt
            FROM donations
            GROUP BY receipt_status
            """
        )
        report['receipt_pipeline'] = cur.fetchall() or []
    except Exception:
        report['receipt_pipeline'] = []

    try:
        cur.execute(
            """
            SELECT parse_status, COUNT(*) AS cnt
            FROM donation_email_messages
            GROUP BY parse_status
            """
        )
        report['email_import_queue'] = cur.fetchall() or []
    except Exception:
        report['email_import_queue'] = []

    try:
        cur.execute(
            """
            SELECT status, COUNT(*) AS cnt, COALESCE(SUM(amount),0) AS monthly_run_rate
            FROM donation_recurring
            GROUP BY status
            """
        )
        report['recurring'] = cur.fetchall() or []
    except Exception:
        report['recurring'] = []

    return report
