# Persist parsed gifts, manage import queue, receipts dry-run.

from __future__ import annotations

import json
from typing import Optional

import pymysql
from flask import session

from app.models.db import get_db
from app.utils.field_crypto import encrypt, decrypt
from app.utils.time_utils import now_church, utc_now
from app.donations_import.parsers import parse_payment_email, ParsedGift
from app.donations_import.fixtures import all_fixtures


def get_receipt_settings() -> dict:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        """
        SELECT donation_receipt_mode, donation_email_auto_import, donation_email_auto_post,
               donation_receipt_test_email, email_send_donation_receipts
        FROM settings WHERE id = 1
        """
    )
    row = cur.fetchone() or {}
    return {
        'receipt_mode': (row.get('donation_receipt_mode') or 'test').lower(),  # test | live | off
        'auto_import': bool(row.get('donation_email_auto_import')),
        'auto_post': bool(row.get('donation_email_auto_post')),
        'test_email': (row.get('donation_receipt_test_email') or '').strip(),
        'send_receipts_enabled': bool(row.get('email_send_donation_receipts', 1)),
    }


def save_receipt_settings(data: dict):
    db = get_db()
    cur = db.cursor()
    mode = (data.get('receipt_mode') or 'test').lower()
    if mode not in ('test', 'live', 'off'):
        mode = 'test'
    cur.execute(
        """
        UPDATE settings SET
            donation_receipt_mode = %s,
            donation_email_auto_import = %s,
            donation_email_auto_post = %s,
            donation_receipt_test_email = %s
        WHERE id = 1
        """,
        (
            mode,
            1 if data.get('auto_import') else 0,
            1 if data.get('auto_post') else 0,
            (data.get('test_email') or '').strip() or None,
        ),
    )
    db.commit()


def list_mailboxes():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM donation_email_mailbox ORDER BY id")
    rows = cur.fetchall() or []
    for r in rows:
        r['has_password'] = bool(r.get('password_enc'))
        r.pop('password_enc', None)
    return rows


def save_mailbox(data: dict, mailbox_id: int | None = None):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    pwd = (data.get('password') or '').strip()
    enc = encrypt(pwd) if pwd else None
    fields = (
        (data.get('label') or 'Giving inbox').strip(),
        (data.get('protocol') or 'pop3').lower(),
        (data.get('host') or '').strip(),
        int(data.get('port') or 995),
        (data.get('username') or '').strip(),
        1 if data.get('use_ssl') else 0,
        1 if data.get('enabled') else 0,
    )
    if mailbox_id:
        if enc:
            cur.execute(
                """
                UPDATE donation_email_mailbox
                SET label=%s, protocol=%s, host=%s, port=%s, username=%s,
                    password_enc=%s, use_ssl=%s, enabled=%s
                WHERE id=%s
                """,
                (*fields[:5], enc, fields[5], fields[6], mailbox_id),
            )
        else:
            cur.execute(
                """
                UPDATE donation_email_mailbox
                SET label=%s, protocol=%s, host=%s, port=%s, username=%s,
                    use_ssl=%s, enabled=%s
                WHERE id=%s
                """,
                (*fields, mailbox_id),
            )
        db.commit()
        return mailbox_id
    cur.execute(
        """
        INSERT INTO donation_email_mailbox
            (label, protocol, host, port, username, password_enc, use_ssl, enabled)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (*fields[:5], enc, fields[5], fields[6]),
    )
    db.commit()
    return cur.lastrowid


def get_mailbox_secret(mailbox_id: int) -> Optional[dict]:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM donation_email_mailbox WHERE id = %s", (mailbox_id,))
    row = cur.fetchone()
    if not row:
        return None
    row['password'] = decrypt(row.get('password_enc') or '') if row.get('password_enc') else ''
    return row


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

    # Mailbox ingest: rules first; AI only if weak (auto). Avoids AI cost on every scan.
    gift = parse_payment_email(
        subject, body_text or body_html, from_address, use_ai='auto'
    )
    cur2 = db.cursor()
    cur2.execute(
        """
        INSERT INTO donation_email_messages
            (mailbox_id, message_uid, message_id_header, subject, from_address, received_at,
             body_text, body_html, processor, parse_status, parse_confidence, parsed_json, is_fixture)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
            'parsed' if gift.amount > 0 else 'needs_review',
            gift.confidence,
            json.dumps(gift.to_dict()),
            1 if is_fixture else 0,
        ),
    )
    db.commit()
    return cur2.lastrowid


def load_fixtures(force: bool = False) -> int:
    """Insert mock provider emails for parser/receipt testing."""
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
        )
        count += 1
    return count


def list_messages(status: str | None = None, limit: int = 100):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    sql = "SELECT * FROM donation_email_messages"
    params = []
    if status:
        sql += " WHERE parse_status = %s"
        params.append(status)
    sql += " ORDER BY created_at DESC LIMIT %s"
    params.append(int(limit))
    cur.execute(sql, params)
    rows = cur.fetchall() or []
    for r in rows:
        try:
            r['parsed'] = json.loads(r.get('parsed_json') or '{}')
        except json.JSONDecodeError:
            r['parsed'] = {}
    return rows


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
    return row


def reparse_message(message_id: int, use_ai: str | bool = 'auto') -> dict:
    msg = get_message(message_id)
    if not msg:
        raise ValueError('Message not found')
    gift = parse_payment_email(
        msg.get('subject') or '',
        msg.get('body_text') or msg.get('body_html') or '',
        msg.get('from_address') or '',
        use_ai=use_ai,
    )
    db = get_db()
    cur = db.cursor()
    err_detail = None
    extras = gift.extras or {}
    if extras.get('ai_error'):
        err_detail = str(extras.get('ai_error'))[:500]
    cur.execute(
        """
        UPDATE donation_email_messages
        SET processor=%s, parse_status=%s, parse_confidence=%s, parsed_json=%s, error_detail=%s
        WHERE id=%s
        """,
        (
            gift.processor,
            'parsed' if gift.amount > 0 else 'needs_review',
            gift.confidence,
            json.dumps(gift.to_dict()),
            err_detail,
            message_id,
        ),
    )
    db.commit()
    return gift.to_dict()


def ingest_pasted_email(
    *,
    subject: str,
    body: str,
    from_address: str = '',
    use_ai: str | bool = 'auto',
) -> int:
    """Create a queue row from a manually pasted payment email."""
    import hashlib
    subject = (subject or '').strip() or '(no subject)'
    body = (body or '').strip()
    if not body:
        raise ValueError('Email body is required.')
    digest = hashlib.sha256(
        f'{subject}|{from_address}|{body[:2000]}'.encode('utf-8', errors='replace')
    ).hexdigest()[:24]
    uid = f'paste-{digest}'
    gift = parse_payment_email(subject, body, from_address, use_ai=use_ai)
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "SELECT id FROM donation_email_messages WHERE message_uid = %s AND mailbox_id IS NULL",
        (uid,),
    )
    existing = cur.fetchone()
    if existing:
        # Re-parse existing paste with requested mode
        reparse_message(int(existing['id']), use_ai=use_ai)
        return int(existing['id'])
    cur2 = db.cursor()
    cur2.execute(
        """
        INSERT INTO donation_email_messages
            (mailbox_id, message_uid, subject, from_address, received_at,
             body_text, processor, parse_status, parse_confidence, parsed_json, is_fixture)
        VALUES (NULL,%s,%s,%s,%s,%s,%s,%s,%s,%s,0)
        """,
        (
            uid,
            subject[:500],
            (from_address or '')[:255] or None,
            utc_now(),
            body,
            gift.processor,
            'parsed' if gift.amount > 0 else 'needs_review',
            gift.confidence,
            json.dumps(gift.to_dict()),
        ),
    )
    db.commit()
    return cur2.lastrowid


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

    from app.models.donation import add_donation

    # Extended insert if columns exist
    donation_id = _insert_donation_extended(
        name=parsed.get('donor_name') or 'Online Donor',
        amount=amount,
        date=parsed.get('date') or now_church().strftime('%Y-%m-%d'),
        method=parsed.get('method') or processor.title(),
        notes=parsed.get('notes') or '',
        confirmation_number=parsed.get('confirmation_number') or external_id,
        donor_email=parsed.get('donor_email') or '',
        donor_type='guest',
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
            VALUES (%s,%s,%s,%s,%s,%s,0,NULL,%s,'',%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                kwargs['name'],
                kwargs['amount'],
                kwargs['date'],
                kwargs['method'],
                kwargs.get('notes') or '',
                kwargs.get('confirmation_number') or '',
                kwargs.get('donor_email') or '',
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
            donor_type=kwargs.get('donor_type') or 'guest',
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


def send_or_preview_receipt(donation: dict, church_info: dict) -> dict:
    """
    Send receipt according to donation_receipt_mode:
      - off: do nothing
      - test: send only to test email (never donor)
      - live: send to donor if enabled
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
        ok = False
        try:
            send_email(to, f"[TEST] {subject}", body)
            ok = True
        except Exception as e:
            return {'status': 'error', 'to': to, 'preview_body': body, 'error': str(e)[:200]}
        if ok:
            _set_receipt_status(donation.get('id'), 'test_sent')
        return {'status': 'test_sent', 'to': to, 'preview_body': body, 'subject': f"[TEST] {subject}"}

    # live
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
