# In-app “new for you” on Feed and profile: notes, serving, follows, replies.

from __future__ import annotations

from datetime import datetime, timedelta

import pymysql
from flask import g, has_request_context, url_for

from app.models.db import get_db


def _cur():
    return get_db().cursor(pymysql.cursors.DictCursor)


def _parse(value):
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:19])
    except Exception:
        return None


def _seen_at(user_id: int) -> datetime | None:
    cur = _cur()
    try:
        cur.execute("SELECT seen_at FROM user_notice_state WHERE user_id = %s", (int(user_id),))
        row = cur.fetchone() or {}
        return _parse(row.get('seen_at'))
    except Exception:
        return None


def mark_notices_seen(user_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO user_notice_state (user_id, seen_at)
        VALUES (%s, UTC_TIMESTAMP())
        ON DUPLICATE KEY UPDATE seen_at = UTC_TIMESTAMP()
        """,
        (int(user_id),),
    )
    db.commit()
    if has_request_context():
        g.pop('_notice_bundle', None)


def _is_new(when, seen: datetime | None) -> bool:
    dt = _parse(when)
    if not dt:
        return True
    if seen is None:
        return True
    if dt.tzinfo and seen.tzinfo is None:
        seen = seen.replace(tzinfo=dt.tzinfo)
    elif seen.tzinfo and dt.tzinfo is None:
        dt = dt.replace(tzinfo=seen.tzinfo)
    return dt > seen


def _person(row: dict) -> str:
    name = f"{(row.get('first_name') or '').strip()} {(row.get('last_name') or '').strip()}".strip()
    return name or (row.get('username') or '').strip() or 'Someone'


def list_notices(user_id: int, limit: int = 12) -> list[dict]:
    uid = int(user_id)
    seen = _seen_at(uid)
    cutoff = datetime.utcnow() - timedelta(days=21)
    items: list[dict] = []

    try:
        from app.models.social import list_inbox, list_invites
        for row in list_inbox(uid) or []:
            if not row.get('unread'):
                continue
            when = row.get('updated_at')
            items.append({
                'kind': 'note',
                'title': 'New note',
                'body': row.get('preview') or (row.get('other_name') or 'A member wrote you'),
                'when': when,
                'url': url_for('church.messages_thread', thread_id=row['id']) if row.get('id') else url_for('church.messages'),
                'is_new': _is_new(when, seen),
            })
        for row in list_invites(uid) or []:
            when = row.get('updated_at')
            items.append({
                'kind': 'invite',
                'title': 'Note invite',
                'body': f"{row.get('host_name') or 'Someone'} invited you to {row.get('title') or 'a group note'}",
                'when': when,
                'url': url_for('church.messages'),
                'is_new': True,
            })
    except Exception as exc:
        print(f'notices notes: {exc}')

    try:
        from app.models.family_links import pending_incoming
        for row in pending_incoming(uid) or []:
            when = row.get('requested_at') or row.get('id')
            items.append({
                'kind': 'family',
                'title': 'Family request',
                'body': f"{row.get('name') or 'Someone'} wants you as {row.get('label') or 'family'}",
                'when': when,
                'url': row.get('page_url') or url_for('church.member_page', username=''),
                'is_new': True,
            })
    except Exception as exc:
        print(f'notices family: {exc}')

    try:
        from app.models.serving import my_serving
        for row in my_serving(uid, upcoming_only=True, limit=12) or []:
            if (row.get('status') or '') != 'pending':
                continue
            when = row.get('serve_date')
            title = row.get('event_title') or row.get('title') or 'an upcoming service'
            items.append({
                'kind': 'serving',
                'title': 'Serving ask',
                'body': f"{row.get('role_name') or 'A role'} · {title}",
                'when': when,
                'url': url_for('volunteers.my_schedule'),
                'is_new': True,
            })
    except Exception as exc:
        print(f'notices serving: {exc}')

    cur = _cur()
    try:
        cur.execute(
            """
            SELECT f.created_at, u.username, u.first_name, u.last_name
            FROM user_follows f
            JOIN users u ON u.id = f.follower_id
            WHERE f.followed_id = %s
            ORDER BY f.created_at DESC
            LIMIT 8
            """,
            (uid,),
        )
        for row in cur.fetchall() or []:
            when = row.get('created_at')
            if _parse(when) and _parse(when) < cutoff:
                continue
            un = (row.get('username') or '').strip()
            items.append({
                'kind': 'follow',
                'title': 'New follow',
                'body': f"{_person(row)} started following you",
                'when': when,
                'url': url_for('church.member_page', username=un) if un else url_for('church.people'),
                'is_new': _is_new(when, seen),
            })
    except Exception as exc:
        print(f'notices follows: {exc}')

    comment_specs = (
        (
            """
            SELECT c.created_at AS when_at, c.comment AS body, e.id AS parent_id, e.event_name AS title
            FROM event_comments c JOIN events e ON e.id = c.event_id
            WHERE COALESCE(e.created_by, e.updated_by) = %s AND COALESCE(c.user_id, 0) <> %s
            ORDER BY c.created_at DESC LIMIT 6
            """,
            'event', 'church.church_home',
        ),
        (
            """
            SELECT c.date_added AS when_at, c.prayer AS body, p.id AS parent_id, p.title
            FROM prayers_added c JOIN prayers p ON p.id = c.prayer_request_id
            WHERE COALESCE(p.user_id, p.created_by) = %s AND COALESCE(c.user_id, 0) <> %s
            ORDER BY c.date_added DESC LIMIT 6
            """,
            'prayer', 'church.church_home',
        ),
        (
            """
            SELECT c.date_added AS when_at, c.comment AS body, a.id AS parent_id, a.title
            FROM announcement_comments c JOIN announcements a ON a.id = c.announcement_id
            WHERE a.created_by = %s AND COALESCE(c.user_id, 0) <> %s
            ORDER BY c.date_added DESC LIMIT 6
            """,
            'reply', 'church.church_home',
        ),
        (
            """
            SELECT c.date_added AS when_at, c.comment AS body, p.id AS parent_id, p.caption AS title
            FROM page_photo_comments c
            JOIN page_photos p ON p.id = c.photo_id
            WHERE p.owner_type = 'member' AND p.owner_id = %s AND COALESCE(c.user_id, 0) <> %s
            ORDER BY c.date_added DESC LIMIT 6
            """,
            'photo', 'church.photo_view',
        ),
    )
    for sql, kind, _endpoint in comment_specs:
        try:
            cur.execute(sql, (uid, uid))
            for row in cur.fetchall() or []:
                when = row.get('when_at')
                if _parse(when) and _parse(when) < cutoff:
                    continue
                pid = row.get('parent_id')
                if kind == 'photo' and pid:
                    url = url_for('church.photo_view', photo_id=int(pid))
                else:
                    url = url_for('public.public_dashboard.public_community')
                snippet = (row.get('body') or '').strip()
                if len(snippet) > 90:
                    snippet = snippet[:88] + '…'
                items.append({
                    'kind': 'reply',
                    'title': 'New reply',
                    'body': snippet or (row.get('title') or 'Someone replied on your page'),
                    'when': when,
                    'url': url,
                    'is_new': _is_new(when, seen),
                })
        except Exception:
            continue

    def sort_key(item):
        dt = _parse(item.get('when')) or datetime.min
        if dt.tzinfo:
            dt = dt.replace(tzinfo=None)
        return dt

    items.sort(key=sort_key, reverse=True)
    return items[:limit]


def notice_bundle(user_id: int | None) -> dict:
    empty = {'count': 0, 'items': []}
    if not user_id:
        return empty
    if has_request_context() and isinstance(getattr(g, '_notice_bundle', None), dict):
        return g._notice_bundle
    try:
        items = list_notices(int(user_id))
    except Exception as exc:
        print(f'notice_bundle: {exc}')
        items = []
    bundle = {
        'count': sum(1 for i in items if i.get('is_new')),
        'items': items,
    }
    if has_request_context():
        g._notice_bundle = bundle
    return bundle
