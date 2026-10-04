# Notification bell (Facebook/Instagram style): reactions, comments, replies,
# follows, @mentions, Praying on prayers, DMs. One row per event, with unread
# repeats from the same person on the same thing folded together.
# Web push reuses app/utils/note_notify (DMs already push there).

from __future__ import annotations

import re
import threading

import pymysql
from flask import current_app, has_request_context, url_for

from app.models.db import get_db

TYPE_TEXT = {
    'reaction': 'reacted to your post',
    'praying': 'is praying for your request',
    'comment': 'commented on your post',
    'prayer_response': 'responded to your prayer request',
    'reply': 'replied to your comment',
    'follow': 'started following you',
    'mention': 'mentioned you',
    'dm': 'sent you a note',
}
TYPE_ICON = {
    'reaction': 'fa-heart',
    'praying': 'fa-hands-praying',
    'comment': 'fa-comment',
    'prayer_response': 'fa-hands-praying',
    'reply': 'fa-reply',
    'follow': 'fa-user-plus',
    'mention': 'fa-at',
    'dm': 'fa-envelope',
}
MENTION_RE = re.compile(r'(?<![\w@/])@([A-Za-z0-9_][A-Za-z0-9_.-]{1,39})')
MAX_MENTIONS = 10


def _cur():
    return get_db().cursor(pymysql.cursors.DictCursor)


def _safe_url(endpoint: str, **kwargs) -> str:
    try:
        return url_for(endpoint, **kwargs)
    except Exception:
        return ''


def content_url(kind: str, item_id: int | None, author_username: str | None = None) -> str:
    """Best page for a notification click."""
    kind = (kind or '').strip()
    if not item_id:
        return _safe_url('public.public_dashboard.public_community') or '/'
    mapping = {
        'prayer': ('prayers.view_prayer', 'prayer_id'),
        'event': ('events.view_event', 'event_id'),
        'sermon': ('sermons.view_sermon', 'sermon_id'),
        'announcement': ('announcements.view_announcement', 'ann_id'),
        'dream': ('dreams.view_dream', 'dream_id'),
        'prophecy': ('prophecies.view_prophecy', 'prophecy_id'),
        'photo': ('church.photo_view', 'photo_id'),
    }
    if kind in mapping:
        endpoint, arg = mapping[kind]
        return _safe_url(endpoint, **{arg: int(item_id)}) or '/'
    if author_username:
        return _safe_url('church.member_page', username=author_username) or '/'
    return _safe_url('public.public_dashboard.public_community') or '/'


def notify(user_id, notif_type: str, *, actor_id=None, target_kind: str | None = None,
           target_id=None, url: str = '', body: str = '', push: bool = True) -> int | None:
    """Create (or refresh) one notification. Never raises into the caller."""
    try:
        uid = int(user_id or 0)
        aid = int(actor_id) if actor_id else None
    except (TypeError, ValueError):
        return None
    if not uid or (aid and aid == uid):
        return None
    try:
        if aid:
            from app.models.social import blocked_either_way
            if blocked_either_way(uid, aid):
                return None
        from app.utils.helpers import censor_text
        body = censor_text((body or '').strip())[:280]
        db = get_db()
        cur = db.cursor()
        cur.execute(
            """
            SELECT id FROM notifications
            WHERE user_id=%s AND type=%s AND read_at IS NULL
              AND (actor_id <=> %s) AND (target_kind <=> %s) AND (target_id <=> %s)
            ORDER BY id DESC LIMIT 1
            """,
            (uid, notif_type, aid, target_kind, int(target_id) if target_id else None),
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE notifications SET created_at=NOW(), body=%s, url=%s WHERE id=%s",
                (body or None, (url or '')[:500] or None, int(row[0])),
            )
            db.commit()
            return int(row[0])
        cur.execute(
            """
            INSERT INTO notifications (user_id, actor_id, type, target_kind, target_id, url, body)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (uid, aid, notif_type[:32], target_kind, int(target_id) if target_id else None,
             (url or '')[:500] or None, body or None),
        )
        db.commit()
        new_id = int(cur.lastrowid)
    except Exception as exc:
        print(f'notify skipped: {exc}')
        try:
            get_db().rollback()
        except Exception:
            pass
        return None
    if push and notif_type != 'dm':  # DMs already push through note_notify
        _push_later(uid, notif_type, aid, url)
    return new_id


def _actor_name(actor_id) -> str:
    if not actor_id:
        return 'Someone'
    try:
        cur = _cur()
        cur.execute("SELECT username, first_name, last_name FROM users WHERE id=%s", (int(actor_id),))
        row = cur.fetchone() or {}
    except Exception:
        return 'Someone'
    name = f"{(row.get('first_name') or '').strip()} {(row.get('last_name') or '').strip()}".strip()
    return name or (row.get('username') or 'Someone')


def _push_later(user_id: int, notif_type: str, actor_id, url: str) -> None:
    """Web push to the person's devices in the background. Body text is never pushed."""
    try:
        cur = _cur()
        cur.execute("SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE user_id=%s", (int(user_id),))
        subs = list(cur.fetchall() or [])
    except Exception:
        return
    if not subs:
        return
    title = 'MyVine'
    blurb = f"{_actor_name(actor_id)} {TYPE_TEXT.get(notif_type, 'has something for you')}."
    href = url or '/'
    if href.startswith('/') and has_request_context():
        try:
            from flask import request
            href = request.host_url.rstrip('/') + href
        except Exception:
            pass
    app = current_app._get_current_object() if has_request_context() else None

    def _run():
        from app.utils.note_notify import _send_push
        if app is None:
            return
        with app.app_context():
            for sub in subs:
                try:
                    _send_push(sub, title, blurb, href, f'notif-{notif_type}')
                except Exception as exc:
                    print(f'notif push skipped: {exc}')

    try:
        threading.Thread(target=_run, daemon=True).start()
    except Exception as exc:
        print(f'notif push thread skipped: {exc}')


def notify_mentions(text: str, actor_id, *, target_kind: str, target_id, url: str = '',
                    skip_ids=None) -> int:
    """@username in a post or comment -> a 'mention' notification for that member."""
    names = []
    for m in MENTION_RE.finditer(text or ''):
        n = m.group(1).rstrip('.-').lower()
        if n and n not in names:
            names.append(n)
        if len(names) >= MAX_MENTIONS:
            break
    if not names:
        return 0
    skip = {int(i) for i in (skip_ids or []) if i}
    try:
        cur = _cur()
        cur.execute(
            f"SELECT id FROM users WHERE LOWER(username) IN ({','.join(['%s'] * len(names))})",
            names,
        )
        ids = [int(r['id']) for r in cur.fetchall() or []]
    except Exception:
        return 0
    if not url:
        _author, url = author_and_url(target_kind, target_id)
    sent = 0
    snippet = (text or '').strip()[:140]
    for uid in ids:
        if uid in skip:
            continue
        if notify(uid, 'mention', actor_id=actor_id, target_kind=target_kind, target_id=target_id,
                  url=url, body=snippet):
            sent += 1
    return sent


def unread_count(user_id) -> int:
    if not user_id:
        return 0
    try:
        cur = _cur()
        cur.execute(
            "SELECT COUNT(*) AS n FROM notifications WHERE user_id=%s AND read_at IS NULL",
            (int(user_id),),
        )
        return int((cur.fetchone() or {}).get('n') or 0)
    except Exception:
        return 0


def list_for(user_id, limit: int = 20) -> list[dict]:
    if not user_id:
        return []
    try:
        cur = _cur()
        cur.execute(
            """
            SELECT n.*, u.username AS actor_username, u.first_name, u.last_name, s.photo_path
            FROM notifications n
            LEFT JOIN users u ON u.id = n.actor_id
            LEFT JOIN member_spaces s ON s.user_id = n.actor_id
            WHERE n.user_id=%s
            ORDER BY n.created_at DESC, n.id DESC
            LIMIT %s
            """,
            (int(user_id), int(limit)),
        )
        rows = list(cur.fetchall() or [])
    except Exception as exc:
        print(f'notifications list: {exc}')
        return []
    from app.models.social import identity_url, when_label
    out = []
    for r in rows:
        name = f"{(r.get('first_name') or '').strip()} {(r.get('last_name') or '').strip()}".strip()
        name = name or (r.get('actor_username') or '') or ('A guest' if not r.get('actor_id') else 'Someone')
        out.append({
            'id': int(r['id']),
            'type': r.get('type') or '',
            'actor': name,
            'text': TYPE_TEXT.get(r.get('type') or '', 'has an update for you'),
            'icon': TYPE_ICON.get(r.get('type') or '', 'fa-bell'),
            'body': r.get('body') or '',
            'url': r.get('url') or '',
            'pic_url': identity_url(r.get('photo_path')) if r.get('photo_path') else '',
            'unread': r.get('read_at') is None,
            'when': when_label(r.get('created_at')),
        })
    return out


def mark_read(user_id, notif_id) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE notifications SET read_at=NOW() WHERE id=%s AND user_id=%s AND read_at IS NULL",
        (int(notif_id), int(user_id)),
    )
    db.commit()


def mark_all_read(user_id) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE notifications SET read_at=NOW() WHERE user_id=%s AND read_at IS NULL",
        (int(user_id),),
    )
    db.commit()


# ---------------------------------------------------------------------------
# Hooks used by reactions, comments, follows and posts
# ---------------------------------------------------------------------------

def author_and_url(kind: str, item_id) -> tuple[int | None, str]:
    """(author user id, click-through url) for a post, prayer, photo, etc."""
    kind = (kind or '').strip()
    author = None
    username = None
    try:
        if kind == 'photo':
            cur = _cur()
            cur.execute("SELECT owner_type, owner_id FROM page_photos WHERE id=%s", (int(item_id),))
            row = cur.fetchone() or {}
            if row.get('owner_type') == 'member':
                author = int(row.get('owner_id') or 0) or None
        else:
            from app.models.moderation import content_author_id
            author = content_author_id(kind, int(item_id))
        if author:
            cur = _cur()
            cur.execute("SELECT username FROM users WHERE id=%s", (int(author),))
            username = (cur.fetchone() or {}).get('username')
    except Exception as exc:
        print(f'notify author lookup: {exc}')
    return author, content_url(kind, item_id, username)


def notify_reaction(kind: str, item_id, actor_id, reaction: str) -> None:
    if not reaction:
        return
    author, url = author_and_url(kind, item_id)
    if not author:
        return
    ntype = 'praying' if reaction == 'pray' else 'reaction'
    label = {
        'like': 'Like', 'love': 'Love', 'pray': 'Praying', 'amen': 'Amen',
        'disagree': 'Disagree', 'sad': 'Sad', 'mad': 'Mad',
    }.get(reaction, reaction)
    notify(author, ntype, actor_id=actor_id, target_kind=kind, target_id=item_id, url=url, body=label)


def notify_comment(kind: str, parent_id, actor_id, text: str, *, table: str | None = None,
                   parent_comment_id=None, guest_name: str = '') -> None:
    """New comment/response: tell the post author, the person replied to, and @mentions."""
    author, url = author_and_url(kind, parent_id)
    snippet = (text or '').strip()[:140]
    if not actor_id and guest_name:
        snippet = f'{guest_name}: {snippet}'[:140]
    told = set()
    if author:
        ntype = 'prayer_response' if kind == 'prayer' else 'comment'
        if notify(author, ntype, actor_id=actor_id, target_kind=kind, target_id=parent_id, url=url, body=snippet):
            told.add(int(author))
    if parent_comment_id and table:
        try:
            from app.utils.comment_moderation import COMMENT_TYPES
            user_col = 'user_id'
            for cfg in COMMENT_TYPES.values():
                if cfg['table'] == table:
                    user_col = cfg['user_col']
                    break
            cur = _cur()
            cur.execute(f"SELECT {user_col} AS uid FROM {table} WHERE id=%s", (int(parent_comment_id),))
            replied_to = (cur.fetchone() or {}).get('uid')
            if replied_to and int(replied_to) not in told:
                if notify(replied_to, 'reply', actor_id=actor_id, target_kind=kind, target_id=parent_id,
                          url=url, body=snippet):
                    told.add(int(replied_to))
        except Exception as exc:
            print(f'notify reply: {exc}')
    if actor_id:
        notify_mentions(text, actor_id, target_kind=kind, target_id=parent_id, url=url, skip_ids=told)


def notify_follow(followed_id, follower_id) -> None:
    try:
        cur = _cur()
        cur.execute("SELECT username FROM users WHERE id=%s", (int(follower_id),))
        username = (cur.fetchone() or {}).get('username')
    except Exception:
        username = None
    url = _safe_url('church.member_page', username=username) if username else ''
    notify(followed_id, 'follow', actor_id=follower_id, target_kind='user', target_id=follower_id, url=url)
