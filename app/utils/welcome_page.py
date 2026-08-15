# app/utils/welcome_page.py
# Shared guest welcome page renderer used by /public/ and /index.

from datetime import date, datetime

from flask import g, render_template

from app.routes.auth.queries import get_welcome_overview
from app.utils.appearance import appearance_context, safe_url_for
from app.utils.time_utils import format_church


def _coerce_event_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], '%Y-%m-%d')
        except ValueError:
            return None
    return None


def render_welcome_page():
    """Render the guest welcome overview with church info, events, and schedule."""
    overview = get_welcome_overview()
    for event in overview['upcoming_events']:
        dt = _coerce_event_date(event.get('event_date'))
        if dt:
            event['formatted_date'] = format_church(dt, '%B %d, %Y')
            if event.get('event_time'):
                event['formatted_time'] = str(event['event_time'])[:5]
            else:
                event['formatted_time'] = ''
        else:
            event['formatted_date'] = 'Date TBD'
            event['formatted_time'] = ''
    look = appearance_context(getattr(g, 'settings', None) or {}, include_welcome_links=True)
    look['welcome_feed_url'] = safe_url_for(
        'public.public_dashboard.public_community',
        '/public/community',
    )
    look['welcome_feed_preview'] = []
    try:
        from app.routes.public.public_dashboard.queries import get_public_dashboard_feed
        preview = get_public_dashboard_feed(limit=3)
        type_labels = {
            'event': 'Event', 'prayer': 'Prayer', 'sermon': 'Sermon',
            'announcement': 'Update', 'dream': 'Dream', 'prophecy': 'Prophecy',
        }
        detail = {
            'event': ('public.public_events.public_event_detail', 'event_id'),
            'sermon': ('public.public_sermons.public_sermon_detail', 'sermon_id'),
            'announcement': ('public.public_announcements.public_announcement_detail', 'ann_id'),
            'dream': ('public.public_dreams.public_dream_detail', 'dream_id'),
            'prophecy': ('public.public_prophecies.public_prophecy_detail', 'prophecy_id'),
            'prayer': ('public.public_prayers.public_prayer_detail', 'prayer_id'),
        }
        for item in preview:
            kind = item.get('type')
            item['type_label'] = type_labels.get(kind, 'Post')
            dt = item.get('sort_dt')
            item['formatted_date'] = format_church(dt, '%B %d, %Y') if dt else ''
            spec = detail.get(kind)
            item['detail_url'] = (
                safe_url_for(spec[0], '', **{spec[1]: item['id']})
                if spec and item.get('id') else ''
            )
        look['welcome_feed_preview'] = preview
    except Exception:
        look['welcome_feed_preview'] = []
    for event in overview['upcoming_events']:
        event['detail_url'] = safe_url_for(
            'public.public_events.public_event_detail',
            '',
            event_id=event.get('id'),
        ) if event.get('id') else ''
    look['welcome_events_url'] = safe_url_for(
        'public.public_events.public_events',
        '/public/events/',
    )
    return render_template(
        'auth/index.html',
        upcoming_events=overview['upcoming_events'],
        upcoming_services=overview['upcoming_services'],
        **look,
    )