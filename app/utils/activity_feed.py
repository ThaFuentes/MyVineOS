# Build a member activity feed from existing module lists.

from flask import url_for


def _item(kind, title, when, url, author='', body=''):
    return {
        'type': kind,
        'title': title or 'Untitled',
        'when': when,
        'url': url,
        'author': author or '',
        'body': body or '',
    }


def build_member_feed(prayers, dreams, prophecies, sermons, announcements, events):
    feed = []
    for row in prayers or []:
        feed.append(_item(
            'prayer',
            row.get('title'),
            row.get('datetime') or row.get('date_posted'),
            url_for('prayers.view_prayer', prayer_id=row['id']),
            row.get('poster_username') or '',
        ))
    for row in dreams or []:
        feed.append(_item(
            'dream',
            row.get('title'),
            row.get('datetime') or row.get('date_posted'),
            url_for('dreams.view_dream', dream_id=row['id']),
            row.get('poster_username') or '',
        ))
    for row in prophecies or []:
        feed.append(_item(
            'prophecy',
            row.get('title'),
            row.get('datetime') or row.get('created_at'),
            url_for('prophecies.view_prophecy', prophecy_id=row['id']),
            row.get('poster_username') or '',
        ))
    for row in sermons or []:
        feed.append(_item(
            'sermon',
            row.get('title'),
            row.get('datetime') or row.get('uploaded_at'),
            url_for('sermons.view_sermon', sermon_id=row['id']),
            row.get('poster_username') or '',
        ))
    for row in announcements or []:
        feed.append(_item(
            'announcement',
            row.get('title'),
            row.get('datetime') or row.get('created_at'),
            url_for('announcements.view_announcement', ann_id=row['id']),
            row.get('poster_username') or '',
        ))
    for row in events or []:
        feed.append(_item(
            'event',
            row.get('title') or row.get('event_name'),
            row.get('event_date') or row.get('datetime'),
            url_for('events.view_event', event_id=row['id']),
            '',
        ))
    feed.sort(key=lambda x: str(x.get('when') or ''), reverse=True)
    return feed[:24]
