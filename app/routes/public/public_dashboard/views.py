# MYVINECHURCH.ONLINE/app/routes/public/public_dashboard/views.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/public_dashboard/views.py
# File name: views.py
# Brief, detailed purpose: Public Dashboard routes - rich social-media style feed on the home page (/ and /public).
# - Reuses ALL existing public queries with smart priority ordering (upcoming events first, newest sermons, recent announcements, dreams, prophecies, prayers).
# - Easy click-to-detail cards with recent comment previews (loaded via queries.py).
# - 100% rebuilt clean production version - identical structure to the working public/events/views.py gold standard.
# - All debug prints removed.

from datetime import date, datetime, timedelta

from flask import render_template, url_for, redirect, session, request

from app.utils.appearance import safe_url_for
from app.utils.helpers import censor_text
from app.utils.time_utils import format_church
from app.utils.welcome_page import render_welcome_page
from . import dashboard_bp
from .queries import FEED_TYPES, WHEN_FILTERS, get_public_dashboard_feed, parse_feed_datetime
from .utils import censor_public_content

TYPE_LABELS = {
    'event': 'Event',
    'prayer': 'Prayer',
    'sermon': 'Sermon',
    'announcement': 'Update',
    'dream': 'Dream',
    'prophecy': 'Prophecy',
}

DETAIL_ENDPOINTS = {
    'event': ('public.public_events.public_event_detail', 'event_id'),
    'sermon': ('public.public_sermons.public_sermon_detail', 'sermon_id'),
    'announcement': ('public.public_announcements.public_announcement_detail', 'ann_id'),
    'dream': ('public.public_dreams.public_dream_detail', 'dream_id'),
    'prophecy': ('public.public_prophecies.public_prophecy_detail', 'prophecy_id'),
    'prayer': ('public.public_prayers.public_prayer_detail', 'prayer_id'),
}


def _detail_url(item):
    spec = DETAIL_ENDPOINTS.get(item.get('type'))
    if not spec or not item.get('id'):
        return ''
    endpoint, arg = spec
    return safe_url_for(endpoint, '', **{arg: item['id']})


def _date_group(dt, today):
    if not dt:
        return 'Earlier'
    day = dt.date()
    if day == today:
        return 'Today'
    if day == today + timedelta(days=1):
        return 'Tomorrow'
    if today < day <= today + timedelta(days=7):
        return 'This week'
    if today - timedelta(days=7) <= day < today:
        return 'This week'
    if day > today:
        return 'Coming up'
    return 'Earlier'


def _build_public_feed(type_filter=None, when_filter=None, limit=40):
    """Prepare the community feed cards for rendering."""
    feed = get_public_dashboard_feed(
        limit=limit,
        type_filter=type_filter,
        when_filter=when_filter,
    )
    feed = censor_public_content(feed)
    today = date.today()

    for item in feed:
        item['title'] = censor_text(item.get('title') or item.get('event_name') or '')
        body = item.get('body') or item.get('description') or item.get('content') or ''
        item['body'] = censor_text(body) if body else ''
        item['type_label'] = TYPE_LABELS.get(item.get('type'), (item.get('type') or 'Post').title())

        dt = item.get('sort_dt') or parse_feed_datetime(
            item.get('datetime') or item.get('created_at') or item.get('date_posted')
            or item.get('uploaded_at') or item.get('event_date')
        )
        item['sort_dt'] = dt
        if dt:
            item['formatted_date'] = format_church(dt, '%B %d, %Y')
            item['formatted_time'] = format_church(dt, '%I:%M %p') if dt.time() != datetime.min.time() else ''
            item['group'] = _date_group(dt, today)
        else:
            item['formatted_date'] = ''
            item['formatted_time'] = ''
            item['group'] = 'Earlier'
        item['detail_url'] = _detail_url(item)

    return feed


@dashboard_bp.route('/')
def public_dashboard():
    """Guest home at /public/ - church overview, events, schedule, and sign-in."""
    if not session.get('user_id') or request.args.get('preview') == '1':
        return render_welcome_page()
    return redirect(url_for('public.public_dashboard.public_community'))


@dashboard_bp.route('/community')
def public_community():
    """Public church feed with type + date filters. Section pages stay available."""
    type_filter = (request.args.get('type') or '').strip().lower()
    if type_filter not in FEED_TYPES:
        type_filter = ''
    when_filter = (request.args.get('when') or 'all').strip().lower()
    if when_filter not in WHEN_FILTERS:
        when_filter = 'all'

    feed = _build_public_feed(type_filter=type_filter or None, when_filter=when_filter)
    compose_types = []
    if session.get('user_id'):
        try:
            from app.utils.compose import available_compose_types
            compose_types = available_compose_types()
        except Exception:
            compose_types = []
    def feed_href(kind='', when='all'):
        args = {}
        if kind:
            args['type'] = kind
        if when and when != 'all':
            args['when'] = when
        return safe_url_for('public.public_dashboard.public_community', '/public/community', **args)

    type_filters = [
        {'value': '', 'label': 'All', 'href': feed_href('', when_filter), 'active': type_filter == ''},
        {'value': 'event', 'label': 'Events', 'href': feed_href('event', when_filter), 'active': type_filter == 'event'},
        {'value': 'prayer', 'label': 'Prayers', 'href': feed_href('prayer', when_filter), 'active': type_filter == 'prayer'},
        {'value': 'sermon', 'label': 'Sermons', 'href': feed_href('sermon', when_filter), 'active': type_filter == 'sermon'},
        {'value': 'announcement', 'label': 'Updates', 'href': feed_href('announcement', when_filter), 'active': type_filter == 'announcement'},
        {'value': 'dream', 'label': 'Dreams', 'href': feed_href('dream', when_filter), 'active': type_filter == 'dream'},
        {'value': 'prophecy', 'label': 'Prophecies', 'href': feed_href('prophecy', when_filter), 'active': type_filter == 'prophecy'},
    ]
    when_filters = [
        {'value': key, 'label': label, 'href': feed_href(type_filter, key), 'active': when_filter == key}
        for key, label in (
            ('all', 'All dates'),
            ('upcoming', 'Upcoming'),
            ('week', 'This week'),
            ('month', 'This month'),
        )
    ]
    return render_template(
        'public/public_dashboard.html',
        feed=feed,
        compose_types=compose_types,
        feed_type=type_filter,
        feed_when=when_filter,
        feed_type_filters=type_filters,
        feed_when_filters=when_filters,
    )


# print(" MYVINECHURCH.ONLINE public/public_dashboard/views.py loaded successfully (production-clean + gold standard applied)")