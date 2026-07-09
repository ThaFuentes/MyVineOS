# MYVINECHURCH.ONLINE/app/routes/public/public_dashboard/views.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/public_dashboard/views.py
# File name: views.py
# Brief, detailed purpose: Public Dashboard routes – rich social-media style feed on the home page (/ and /public).
# • Reuses ALL existing public queries with smart priority ordering (upcoming events first, newest sermons, recent announcements, dreams, prophecies, prayers).
# • Easy click-to-detail cards with recent comment previews (loaded via queries.py).
# • 100% rebuilt clean production version - identical structure to the working public/events/views.py gold standard.
# • All debug prints removed.

from flask import render_template, url_for, redirect, session
from app.utils.welcome_page import render_welcome_page
from . import dashboard_bp
from .queries import get_public_dashboard_feed
from .utils import censor_public_content

from app.utils.helpers import censor_text
from app.utils.time_utils import format_church
from datetime import datetime


def _build_public_feed():
    """Prepare the community feed cards for rendering."""
    feed = get_public_dashboard_feed()

    # Censor the entire feed (main content only — comments are censored in queries.py)
    feed = censor_public_content(feed)

    for item in feed:
        # Main title handling
        item['title'] = censor_text(item.get('title') or item.get('event_name') or '')

        # Body/description/content censoring
        if item.get('body'):
            item['body'] = censor_text(item['body'])
        elif item.get('description'):
            item['body'] = censor_text(item['description'])
        elif item.get('content'):
            item['body'] = censor_text(item['content'])

        # Safe date handling for mixed content types
        dt = item.get('datetime') or item.get('created_at') or item.get('date_posted') or item.get('uploaded_at') or item.get('event_date')
        if isinstance(dt, str):
            try:
                if ' ' in dt:
                    dt = datetime.strptime(dt[:19], '%Y-%m-%d %H:%M:%S')
                else:
                    dt = datetime.strptime(dt[:10], '%Y-%m-%d')
            except:
                dt = None

        if dt:
            item['formatted_date'] = format_church(dt, '%B %d, %Y')
            item['formatted_time'] = format_church(dt, '%I:%M %p')
        else:
            item['formatted_date'] = 'Unknown'
            item['formatted_time'] = ''

        # Direct link to the correct public detail page (using the fixed nested blueprint endpoints)
        item_type = item.get('type')
        if item_type == 'event':
            item['detail_url'] = url_for('public.public_events.public_event_detail', event_id=item['id'])
        elif item_type == 'sermon':
            item['detail_url'] = url_for('public.public_sermons.public_sermon_detail', sermon_id=item['id'])
        elif item_type == 'announcement':
            item['detail_url'] = url_for('public.public_announcements.public_announcement_detail', ann_id=item['id'])
        elif item_type == 'dream':
            item['detail_url'] = url_for('public.public_dreams.public_dream_detail', dream_id=item['id'])
        elif item_type == 'prophecy':
            item['detail_url'] = url_for('public.public_prophecies.public_prophecy_detail', prophecy_id=item['id'])
        elif item_type == 'prayer':
            item['detail_url'] = url_for('public.public_prayers.public_prayer_detail', prayer_id=item['id'])
        else:
            item['detail_url'] = '#'

    return feed


@dashboard_bp.route('/')
def public_dashboard():
    """Guest home at /public/ — church overview, events, schedule, and sign-in."""
    if not session.get('user_id'):
        return render_welcome_page()
    return redirect(url_for('public.public_dashboard.public_community'))


@dashboard_bp.route('/community')
def public_community():
    """Rich public community feed with smart priority ordering + latest comment previews."""
    feed = _build_public_feed()
    return render_template('public/public_dashboard.html', feed=feed)


# print("✅ MYVINECHURCH.ONLINE public/public_dashboard/views.py loaded successfully (production-clean + gold standard applied)")