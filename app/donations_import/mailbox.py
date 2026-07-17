# POP3 / IMAP fetch for giving-notification mailboxes.

from __future__ import annotations

import email
import imaplib
import poplib
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Optional

from app.donations_import.service import get_mailbox_secret, upsert_message
from app.models.db import get_db
from app.utils.time_utils import utc_now
import pymysql


def _decode_header_value(raw) -> str:
    if not raw:
        return ''
    parts = decode_header(raw)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or 'utf-8', errors='replace'))
        else:
            out.append(text)
    return ''.join(out)


def _body_from_message(msg) -> tuple[str, str]:
    text, html = '', ''
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get('Content-Disposition') or '')
            if 'attachment' in disp:
                continue
            try:
                payload = part.get_payload(decode=True) or b''
                charset = part.get_content_charset() or 'utf-8'
                decoded = payload.decode(charset, errors='replace')
            except Exception:
                continue
            if ctype == 'text/plain' and not text:
                text = decoded
            elif ctype == 'text/html' and not html:
                html = decoded
    else:
        try:
            payload = msg.get_payload(decode=True) or b''
            charset = msg.get_content_charset() or 'utf-8'
            decoded = payload.decode(charset, errors='replace')
            if msg.get_content_type() == 'text/html':
                html = decoded
            else:
                text = decoded
        except Exception:
            text = str(msg.get_payload() or '')
    return text, html


def scan_mailbox(mailbox_id: int, limit: int = 40, use_ai: str | bool | None = None) -> dict:
    """
    Fetch recent messages from POP3/IMAP, parse each with the chosen mode,
    and stage gifts for human review (or auto-post if enabled).
    Returns {fetched, new, errors, mailbox_id, label, parse_mode}.
    """
    cfg = get_mailbox_secret(mailbox_id)
    if not cfg:
        return {'fetched': 0, 'new': 0, 'errors': ['Mailbox not found'], 'mailbox_id': mailbox_id}
    if not cfg.get('enabled'):
        return {
            'fetched': 0, 'new': 0, 'errors': ['Mailbox disabled'],
            'mailbox_id': mailbox_id, 'label': cfg.get('label'),
        }

    protocol = (cfg.get('protocol') or 'pop3').lower()
    try:
        if protocol == 'imap':
            result = _scan_imap(cfg, limit=limit, use_ai=use_ai)
        else:
            result = _scan_pop3(cfg, limit=limit, use_ai=use_ai)
        _mark_scan(mailbox_id, None)
        result['mailbox_id'] = mailbox_id
        result['label'] = cfg.get('label') or f'Mailbox #{mailbox_id}'
        result['parse_mode'] = use_ai
        return result
    except Exception as e:
        _mark_scan(mailbox_id, str(e)[:480])
        return {
            'fetched': 0, 'new': 0, 'errors': [str(e)[:200]],
            'mailbox_id': mailbox_id, 'label': cfg.get('label'),
            'parse_mode': use_ai,
        }


def scan_all_enabled_mailboxes(limit: int = 50, use_ai: str | bool | None = None) -> dict:
    """
    Check every enabled POP3/IMAP giving mailbox.
    Primary staff action: choose software vs AI → fetch → parse → review queue.
    """
    from app.donations_import.service import list_mailboxes

    mailboxes = [m for m in (list_mailboxes() or []) if m.get('enabled')]
    if not mailboxes:
        return {
            'fetched': 0, 'new': 0,
            'errors': [
                'No POP3/IMAP account found. Add incoming mail under Settings → Email '
                '(protocol + server), then click Check emails here.'
            ],
            'mailboxes': 0, 'scanned': 0, 'parse_mode': use_ai,
        }

    total_fetched = total_new = 0
    errors = []
    scanned = 0
    for mb in mailboxes:
        result = scan_mailbox(int(mb['id']), limit=limit, use_ai=use_ai)
        scanned += 1
        total_fetched += int(result.get('fetched') or 0)
        total_new += int(result.get('new') or 0)
        for err in (result.get('errors') or []):
            label = result.get('label') or mb.get('label') or mb['id']
            errors.append(f"{label}: {err}")
    return {
        'fetched': total_fetched,
        'new': total_new,
        'errors': errors,
        'mailboxes': len(mailboxes),
        'scanned': scanned,
        'parse_mode': use_ai,
    }


def run_scheduled_mailbox_scans() -> dict:
    """Background / cron: only when auto-scan is enabled (uses saved automation parse mode)."""
    from app.donations_import.service import get_receipt_settings
    settings = get_receipt_settings()
    if not settings.get('import_enabled', True) or not settings.get('auto_import'):
        return {'skipped': True, 'fetched': 0, 'new': 0}
    return scan_all_enabled_mailboxes(limit=40, use_ai=None)


def _mark_scan(mailbox_id: int, error: Optional[str]):
    """Record scan time/error on shared email_accounts (giving inbox role)."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            "UPDATE email_accounts SET last_scan_at=%s, last_error=%s WHERE id=%s",
            (utc_now(), error, mailbox_id),
        )
        db.commit()
        return
    except Exception:
        db.rollback()
    try:
        cur.execute(
            "UPDATE donation_email_mailbox SET last_scan_at=%s, last_error=%s WHERE id=%s",
            (utc_now(), error, mailbox_id),
        )
        db.commit()
    except Exception:
        db.rollback()


def _scan_pop3(cfg: dict, limit: int = 40, use_ai: str | bool | None = None) -> dict:
    host = cfg['host']
    port = int(cfg.get('port') or 995)
    user = cfg['username']
    password = cfg.get('password') or ''
    use_ssl = bool(cfg.get('use_ssl', 1))

    if use_ssl:
        conn = poplib.POP3_SSL(host, port, timeout=45)
    else:
        conn = poplib.POP3(host, port, timeout=45)
    try:
        conn.user(user)
        conn.pass_(password)
        count, _ = conn.stat()
        start = max(1, count - limit + 1)
        fetched = new = 0
        errors = []
        for i in range(start, count + 1):
            try:
                resp, lines, octets = conn.retr(i)
                raw = b'\n'.join(lines)
                msg = email.message_from_bytes(raw)
                subject = _decode_header_value(msg.get('Subject'))
                from_addr = _decode_header_value(msg.get('From'))
                mid = (msg.get('Message-ID') or f'pop-{i}').strip()
                text, html = _body_from_message(msg)
                received = None
                if msg.get('Date'):
                    try:
                        received = parsedate_to_datetime(msg.get('Date'))
                    except Exception:
                        received = None
                before = _count_messages()
                upsert_message(
                    mailbox_id=cfg['id'],
                    uid=mid or f'pop-{cfg["id"]}-{i}',
                    subject=subject,
                    from_address=from_addr,
                    body_text=text or html,
                    body_html=html,
                    message_id_header=mid,
                    received_at=_naive_received(received),
                    use_ai=use_ai,
                )
                fetched += 1
                if _count_messages() > before:
                    new += 1
            except Exception as e:
                errors.append(_fmt_scan_error(i, e))
        return {'fetched': fetched, 'new': new, 'errors': errors}
    finally:
        try:
            conn.quit()
        except Exception:
            pass


def _scan_imap(cfg: dict, limit: int = 40, use_ai: str | bool | None = None) -> dict:
    host = cfg['host']
    port = int(cfg.get('port') or 993)
    user = cfg['username']
    password = cfg.get('password') or ''
    use_ssl = bool(cfg.get('use_ssl', 1))

    if use_ssl:
        conn = imaplib.IMAP4_SSL(host, port)
    else:
        conn = imaplib.IMAP4(host, port)
    try:
        conn.login(user, password)
        conn.select('INBOX')
        typ, data = conn.search(None, 'ALL')
        ids = data[0].split() if data and data[0] else []
        ids = ids[-limit:]
        fetched = new = 0
        errors = []
        for num in ids:
            try:
                typ, msg_data = conn.fetch(num, '(RFC822)')
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)
                subject = _decode_header_value(msg.get('Subject'))
                from_addr = _decode_header_value(msg.get('From'))
                mid = (msg.get('Message-ID') or f'imap-{num.decode()}').strip()
                text, html = _body_from_message(msg)
                received = None
                if msg.get('Date'):
                    try:
                        received = parsedate_to_datetime(msg.get('Date'))
                    except Exception:
                        received = None
                before = _count_messages()
                upsert_message(
                    mailbox_id=cfg['id'],
                    uid=mid or f'imap-{cfg["id"]}-{num.decode()}',
                    subject=subject,
                    from_address=from_addr,
                    body_text=text or html,
                    body_html=html,
                    message_id_header=mid,
                    received_at=_naive_received(received),
                    use_ai=use_ai,
                )
                fetched += 1
                if _count_messages() > before:
                    new += 1
            except Exception as e:
                raw_num = num.decode() if isinstance(num, (bytes, bytearray)) else num
                errors.append(_fmt_scan_error(raw_num, e))
        return {'fetched': fetched, 'new': new, 'errors': errors}
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def _count_messages() -> int:
    """Row count for new-message detection. get_db() uses DictCursor — never index by [0]."""
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) AS cnt FROM donation_email_messages")
    row = cur.fetchone()
    if row is None:
        return 0
    if isinstance(row, dict):
        return int(row.get('cnt') or 0)
    return int(row[0])


def _naive_received(received):
    """MariaDB TIMESTAMP insert is happier with naive datetimes."""
    if received is None:
        return None
    try:
        if getattr(received, 'tzinfo', None) is not None:
            return received.replace(tzinfo=None)
    except Exception:
        pass
    return received


def _fmt_scan_error(msg_ref, exc: BaseException) -> str:
    """Human-readable per-message error (avoid bare KeyError(0) → '0')."""
    name = type(exc).__name__
    detail = str(exc).strip()
    if not detail:
        detail = repr(exc)
    # KeyError(0) stringifies as "0" — expand it
    if name == 'KeyError' and detail in ('0', '1', "'0'"):
        detail = f'{detail} (internal row access — fixed if you still see this after update)'
    text = f'message #{msg_ref}: {name}: {detail}'
    return text[:180]
