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
from .queries import FEED_TYPES, WHEN_FILTERS, _matches_when, get_public_dashboard_feed, parse_feed_datetime
from .utils import censor_public_content

TYPE_LABELS = {
    'event': 'Event',
    'prayer': 'Prayer',
    'sermon': 'Sermon',
    'announcement': 'Update',
    'dream': 'Dream',
    'prophecy': 'Prophecy',
    'post': 'Post',
    'quote': 'Quote',
    'verse': 'Verse',
    'image': 'Photo',
    'blog': 'Blog',
    'book': 'Book',
}
WALL_FEED_TYPES = ('post', 'quote', 'verse', 'image', 'blog', 'book')

DETAIL_ENDPOINTS = {
    'event': ('public.public_events.public_event_detail', 'event_id'),
    'sermon': ('public.public_sermons.public_sermon_detail', 'sermon_id'),
    'announcement': ('public.public_announcements.public_announcement_detail', 'ann_id'),
    'dream': ('public.public_dreams.public_dream_detail', 'dream_id'),
    'prophecy': ('public.public_prophecies.public_prophecy_detail', 'prophecy_id'),
    'prayer': ('public.public_prayers.public_prayer_detail', 'prayer_id'),
}


def _detail_url(item, member_view=False):
    if member_view and item.get('type') == 'prayer' and item.get('visibility') == 'private':
        return safe_url_for('prayers.view_prayer', '', prayer_id=item.get('id'))
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


def _build_public_feed(type_filter=None, when_filter=None, limit=40, include_members=False):
    """Prepare the community feed cards for rendering."""
    from app.models import social as social_model
    from app.models import church_community as cc
    from flask import url_for

    want_modules = not type_filter or type_filter not in WALL_FEED_TYPES
    want_posts = not type_filter or type_filter in WALL_FEED_TYPES or type_filter == 'post'
    feed = []
    if want_modules:
        feed = get_public_dashboard_feed(
            limit=limit,
            type_filter=type_filter if type_filter not in WALL_FEED_TYPES else None,
            when_filter=when_filter,
            include_members=include_members,
        ) or []
    if want_posts:
        viewer_id = session.get('user_id') if include_members else None
        for row in social_model.list_recent_wall_posts(viewer_id=viewer_id, limit=limit):
            kind = row.get('kind') or 'post'
            if type_filter in WALL_FEED_TYPES and type_filter != 'post' and kind != type_filter:
                continue
            feed.append({
                'id': row.get('id'),
                'type': kind,
                'title': row.get('title') or 'Post',
                'body': row.get('body') or '',
                'image_url': row.get('image_url') or '',
                'url': row.get('url') or '',
                'link_title': row.get('link_title') or '',
                'link_image': row.get('link_image') or '',
                'link_desc': row.get('link_desc') or '',
                'user_id': row.get('user_id'),
                'author_id': row.get('user_id'),
                'username': row.get('username') or '',
                'creator_name': row.get('display_name') or row.get('username') or '',
                'author_url': row.get('author_url') or '',
                'campus_id': int(row.get('primary_campus_id') or 0),
                'visibility': row.get('visibility') or 'public',
                'shadowed': bool(row.get('shadowed')),
                'allow_comments': row.get('allow_comments', True),
                'allow_share': row.get('allow_share', True),
                'share_of': row.get('share_of'),
                'datetime': row.get('created_at'),
                'sort_dt': parse_feed_datetime(row.get('created_at')),
                'comments': [],
            })
    feed = censor_public_content(feed)
    seen = set()
    unique = []
    for item in feed:
        key = (item.get('type'), item.get('id'))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    feed = unique
    today = date.today()
    feed = [item for item in feed if _matches_when(item, when_filter, today)]

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
        item['detail_url'] = _detail_url(item, member_view=include_members)
        if not item.get('author_url') and item.get('username'):
            try:
                item['author_url'] = url_for('church.member_page', username=item['username'])
            except Exception:
                item['author_url'] = ''

    viewer_id = session.get('user_id') if include_members else None
    feed = cc.visible_items(feed, viewer_id, surface='feed')
    if viewer_id:
        feed = cc.attach_feed_rank(feed, viewer_id=viewer_id)
    try:
        from app.models.post_social import attach_social
        feed = attach_social(feed, viewer_id)
    except Exception as exc:
        print(f'feed social: {exc}')
    try:
        from app.models.moderation import flag_wall_moderation
        feed = flag_wall_moderation(feed)
    except Exception:
        pass
    return feed[:limit]


@dashboard_bp.route('/')
def public_dashboard():
    """Home is the church profile. Keep welcome preview for settings (?preview=1)."""
    if request.args.get('preview') == '1':
        return render_welcome_page()
    return redirect(url_for('church.church_home'))


@dashboard_bp.route('/community')
def public_community():
    """Public church feed with type + date filters. Section pages stay available."""
    type_filter = (request.args.get('type') or '').strip().lower()
    if type_filter not in FEED_TYPES:
        type_filter = ''
    when_filter = (request.args.get('when') or 'all').strip().lower()
    if when_filter not in WHEN_FILTERS:
        when_filter = 'all'

    feed = _build_public_feed(
        type_filter=type_filter or None,
        when_filter=when_filter,
        include_members=bool(session.get('user_id')),
    )
    compose_types = []
    if session.get('user_id'):
        try:
            from flask import current_app
            if 'compose.compose_create' in current_app.view_functions:
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
        {'value': 'post', 'label': 'Posts', 'href': feed_href('post', when_filter), 'active': type_filter == 'post'},
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
    from app.models import church_community as cc
    from app.models import social as social_model

    viewer_id = session.get('user_id')
    space = cc.get_member_space(viewer_id) if viewer_id else None
    church_context = cc.church_context_for_user(viewer_id)
    campus_id = int((church_context or {}).get('campus_id') or 0)
    campus = cc.resolve_campus(campus_id=campus_id, user_id=viewer_id) if campus_id else None
    is_org = cc.single_church_install() or not campus_id
    return render_template(
        'public/public_dashboard.html',
        feed=feed,
        compose_types=compose_types,
        feed_type=type_filter,
        feed_when=when_filter,
        feed_type_filters=type_filters,
        feed_when_filters=when_filters,
        viewer_space=space,
        church_context=church_context,
        upcoming_service=(church_context or {}).get('upcoming_service') or cc.scheduler_upcoming(),
        contact=cc.profile_contact(campus),
        campus=campus or {},
        is_org=is_org,
        church_name=cc.church_name(),
        branch_name=(church_context or {}).get('branch_name') or '',
        branches=cc.branch_directory() if is_org else [],
        worship=social_model.worship_lineup(campus_id or None),
        following=social_model.following_preview(viewer_id, viewer_id=viewer_id, limit=8) if viewer_id else [],
        rail_updates=cc.church_wall(include_members=bool(viewer_id), limit=8, campus_id=campus_id if not is_org else 0),
    )


# print(" MYVINECHURCH.ONLINE public/public_dashboard/views.py loaded successfully (production-clean + gold standard applied)")