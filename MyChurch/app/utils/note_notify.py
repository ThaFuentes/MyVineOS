# Push + optional email for Notes. Never puts the note body in email or push.

from __future__ import annotations

import json
import os
from pathlib import Path

from flask import current_app, has_request_context, url_for

_KEY_PATH = Path(__file__).resolve().parent.parent.parent / 'vapid.json'


def _b64url(raw: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


def vapid_keys() -> dict:
    if _KEY_PATH.exists():
        try:
            data = json.loads(_KEY_PATH.read_text())
            if data.get('public') and data.get('private_pem'):
                return data
        except Exception:
            pass
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization

    key = ec.generate_private_key(ec.SECP256R1())
    priv_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    data = {'public': _b64url(pub), 'private_pem': priv_pem}
    try:
        _KEY_PATH.write_text(json.dumps(data))
        os.chmod(_KEY_PATH, 0o600)
    except Exception as exc:
        print(f'vapid key write skipped: {exc}')
    return data


def vapid_public() -> str:
    return vapid_keys().get('public') or ''


def note_url(thread_id: int) -> str:
    try:
        from app.utils.email_notifications import external_url
        return external_url('church.messages_thread', thread_id=int(thread_id))
    except Exception:
        if has_request_context():
            return url_for('church.messages_thread', thread_id=int(thread_id), _external=True)
        return f'/church/messages/{int(thread_id)}'


def save_subscription(user_id: int, endpoint: str, p256dh: str, auth: str) -> bool:
    from app.models.db import get_db

    endpoint = (endpoint or '').strip()[:700]
    p256dh = (p256dh or '').strip()[:255]
    auth = (auth or '').strip()[:128]
    if not (endpoint.startswith('https://') and p256dh and auth):
        return False
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE user_id=VALUES(user_id), p256dh=VALUES(p256dh), auth=VALUES(auth)
        """,
        (int(user_id), endpoint, p256dh, auth),
    )
    db.commit()
    return True


def drop_subscription(endpoint: str) -> None:
    from app.models.db import get_db

    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM push_subscriptions WHERE endpoint=%s", ((endpoint or '').strip()[:700],))
    db.commit()


def _send_push(sub: dict, title: str, body: str, url: str, tag: str) -> None:
    keys = vapid_keys()
    payload = json.dumps({'title': title, 'body': body, 'url': url, 'tag': tag})
    try:
        from pywebpush import webpush, WebPushException
    except Exception:
        return
    try:
        webpush(
            subscription_info={
                'endpoint': sub['endpoint'],
                'keys': {'p256dh': sub['p256dh'], 'auth': sub['auth']},
            },
            data=payload,
            vapid_private_key=keys['private_pem'],
            vapid_claims={'sub': 'mailto:notes@myvineos.local'},
        )
    except Exception as exc:
        gone = False
        try:
            from pywebpush import WebPushException
            if isinstance(exc, WebPushException) and getattr(exc, 'response', None) is not None:
                gone = exc.response.status_code in (404, 410)
        except Exception:
            gone = '410' in str(exc) or '404' in str(exc)
        if gone:
            drop_subscription(sub['endpoint'])
        else:
            print(f'note push skipped: {exc}')


def notify_note_reply(thread: dict, sender_id: int, sender_name: str) -> None:
    """Alert other members. Body of the note is never included."""
    from app.models.db import get_db
    import pymysql

    tid = int(thread.get('id') or 0)
    if not tid:
        return
    kind = (thread.get('thread_kind') or 'direct').strip()
    title = (thread.get('title') or '').strip() or 'Notes'
    if kind == 'open':
        label = title
        blurb = f'{sender_name} wrote in the open note “{title}”.'
    elif kind == 'group':
        label = title
        blurb = f'{sender_name} wrote in the group note “{title}”.'
    elif kind == 'church':
        label = 'Church office'
        blurb = f'{sender_name} left a church-office note.'
    else:
        label = sender_name
        blurb = f'{sender_name} left you a note.'
    href = note_url(tid)
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    recipients: list[dict] = []
    if kind in ('group', 'open'):
        cur.execute(
            """
            SELECT m.user_id, m.notify_push, m.notify_email, u.email, u.accepts_emails, u.accepts_note_emails
            FROM dm_members m
            JOIN users u ON u.id = m.user_id
            WHERE m.thread_id=%s AND m.status='member' AND m.user_id != %s
            """,
            (tid, int(sender_id)),
        )
        recipients = list(cur.fetchall() or [])
    else:
        others = []
        if kind == 'church':
            starter = int(thread.get('starter_id') or thread.get('user_low') or 0)
            if int(sender_id) == starter:
                cur.execute(
                    """
                    SELECT u.id AS user_id, u.email, u.accepts_emails, u.accepts_note_emails
                    FROM users u
                    WHERE u.role IN ('Owner', 'Admin') AND u.id != %s
                    """,
                    (int(sender_id),),
                )
                others = list(cur.fetchall() or [])
            elif starter:
                cur.execute(
                    """
                    SELECT u.id AS user_id, u.email, u.accepts_emails, u.accepts_note_emails
                    FROM users u WHERE u.id=%s
                    """,
                    (starter,),
                )
                others = list(cur.fetchall() or [])
        else:
            other = thread.get('user_high') if int(thread.get('user_low') or 0) == int(sender_id) else thread.get('user_low')
            if other:
                cur.execute(
                    """
                    SELECT u.id AS user_id, u.email, u.accepts_emails, u.accepts_note_emails
                    FROM users u WHERE u.id=%s
                    """,
                    (int(other),),
                )
                others = list(cur.fetchall() or [])
        for row in others:
            row['notify_push'] = 1
            row['notify_email'] = int(row.get('accepts_note_emails') or 0)
            recipients.append(row)

    seen = set()
    for row in recipients:
        uid = int(row.get('user_id') or 0)
        if not uid or uid in seen:
            continue
        seen.add(uid)
        if row.get('notify_push', 1):
            cur.execute(
                "SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE user_id=%s",
                (uid,),
            )
            for sub in cur.fetchall() or []:
                _send_push(sub, label, blurb, href, f'note-{tid}')
        want_email = bool(row.get('notify_email') or row.get('accepts_note_emails'))
        if want_email and row.get('accepts_emails', 1) and row.get('email'):
            try:
                from app.utils.email_notifications import _safe_send
                _safe_send(
                    row['email'],
                    f'A note in {label}',
                    f"{blurb}\n\nOpen Notes to read it (the note itself is never emailed):\n{href}\n",
                    'note_reply',
                )
            except Exception as exc:
                print(f'note email skipped: {exc}')
