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


def scan_mailbox(mailbox_id: int, limit: int = 40) -> dict:
    """
    Fetch recent messages and stage them for parsing.
    Returns {fetched, new, errors}.
    """
    cfg = get_mailbox_secret(mailbox_id)
    if not cfg:
        return {'fetched': 0, 'new': 0, 'errors': ['Mailbox not found']}
    if not cfg.get('enabled'):
        return {'fetched': 0, 'new': 0, 'errors': ['Mailbox disabled']}

    protocol = (cfg.get('protocol') or 'pop3').lower()
    try:
        if protocol == 'imap':
            result = _scan_imap(cfg, limit=limit)
        else:
            result = _scan_pop3(cfg, limit=limit)
        _mark_scan(mailbox_id, None)
        return result
    except Exception as e:
        _mark_scan(mailbox_id, str(e)[:480])
        return {'fetched': 0, 'new': 0, 'errors': [str(e)[:200]]}


def _mark_scan(mailbox_id: int, error: Optional[str]):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE donation_email_mailbox SET last_scan_at=%s, last_error=%s WHERE id=%s",
        (utc_now(), error, mailbox_id),
    )
    db.commit()


def _scan_pop3(cfg: dict, limit: int = 40) -> dict:
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
                    received_at=received,
                )
                fetched += 1
                if _count_messages() > before:
                    new += 1
            except Exception as e:
                errors.append(f'msg {i}: {e}'[:120])
        return {'fetched': fetched, 'new': new, 'errors': errors}
    finally:
        try:
            conn.quit()
        except Exception:
            pass


def _scan_imap(cfg: dict, limit: int = 40) -> dict:
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
                    received_at=received,
                )
                fetched += 1
                if _count_messages() > before:
                    new += 1
            except Exception as e:
                errors.append(str(e)[:120])
        return {'fetched': fetched, 'new': new, 'errors': errors}
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def _count_messages() -> int:
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM donation_email_messages")
    return int(cur.fetchone()[0])
