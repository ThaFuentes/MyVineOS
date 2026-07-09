# MYVINECHURCH.ONLINE/app/routes/the_gathering/dashboard/utils.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/dashboard/utils.py
# File name: utils.py
# Brief, detailed purpose: Feature-specific utility functions for the main Gathering Place Manager Dashboard.
# - Provides manager-focused censorship (with flagging of censored content), datetime formatting, and safe truncation.
# - 100% rebuilt to match the exact clean, modular style of public/events/utils.py and public/dreams/utils.py
#   (detailed section comments, enhanced docstrings, consistent naming, no behavior changes).
# - All original functions (censor_for_manager, format_manager_datetime, safe_truncate) and their exact logic
#   are preserved 100% - only readability, documentation, and consistency with the public gold standard were updated.

from flask import url_for
from app.utils.helpers import censor_text
from app.utils.time_utils import format_church
import html


MANAGER_VIEW_ENDPOINTS = {
    'event': ('the_gathering.events.view_event', 'event_id'),
    'prayer': ('the_gathering.prayers.view_prayer', 'prayer_id'),
    'sermon': ('the_gathering.sermons.view_sermon', 'sermon_id'),
    'dream': ('the_gathering.dreams.view_dream', 'dream_id'),
    'prophecy': ('the_gathering.prophecies.view_prophecy', 'prophecy_id'),
    'announcement': ('the_gathering.announcements.view_announcement', 'announcement_id'),
}

MANAGER_COMMENTS_ENDPOINTS = {
    'event': ('the_gathering.events.event_comments', 'event_id'),
    'prayer': ('the_gathering.prayers.prayer_comments', 'prayer_id'),
    'sermon': ('the_gathering.sermons.sermon_comments', 'sermon_id'),
    'dream': ('the_gathering.dreams.dream_comments', 'dream_id'),
    'prophecy': ('the_gathering.prophecies.prophecy_comments', 'prophecy_id'),
    'announcement': ('the_gathering.announcements.announcement_comments', 'announcement_id'),
}

SECTION_DASHBOARD_ENDPOINTS = {
    'event': 'the_gathering.events.events_dashboard',
    'prayer': 'the_gathering.prayers.prayers_dashboard',
    'sermon': 'the_gathering.sermons.sermons_dashboard',
    'dream': 'the_gathering.dreams.dreams_dashboard',
    'prophecy': 'the_gathering.prophecies.prophecies_dashboard',
    'announcement': 'the_gathering.announcements.announcements_dashboard',
}


def manager_view_url(content_type, item_id):
    """URL to view/manage a content item in the Gathering Place Manager."""
    mapping = MANAGER_VIEW_ENDPOINTS.get(content_type)
    if not mapping or not item_id:
        return url_for('the_gathering.dashboard.dashboard')
    endpoint, param = mapping
    return url_for(endpoint, **{param: item_id})


def manager_comments_url(content_type, parent_id):
    """URL to moderate comments on a specific content item."""
    mapping = MANAGER_COMMENTS_ENDPOINTS.get(content_type)
    if not mapping or not parent_id:
        return url_for('the_gathering.dashboard.moderation_queue')
    endpoint, param = mapping
    return url_for(endpoint, **{param: parent_id})


def section_dashboard_url(content_type):
    """URL to the section listing dashboard."""
    endpoint = SECTION_DASHBOARD_ENDPOINTS.get(content_type)
    return url_for(endpoint) if endpoint else url_for('the_gathering.dashboard.dashboard')


# ----------------------------------------------------------------------
# Gathering Place Manager Helpers
# ----------------------------------------------------------------------
def censor_for_manager(items, fields=None):
    """Apply light censorship for internal manager views with flagging.

    Unlike public censorship, this version marks items that contained censored content
    (sets 'has_censored_content' flag) and stores both the original and censored versions
    (e.g. title_censored) for manager review and audit purposes.
    Used by the dashboard recent activity feed and any manager list views.
    """
    if fields is None:
        fields = ['title', 'name', 'comment_text']

    for item in items:
        item['has_censored_content'] = False
        for key in fields:
            if key in item and item[key]:
                original = str(item[key])
                censored = censor_text(original)
                if censored != original:
                    item['has_censored_content'] = True
                    item[f'{key}_censored'] = censored
    return items


def format_manager_datetime(date_value):
    """Format any datetime for manager dashboard display using the church's timezone helper.

    Uses a compact, readable format suitable for internal admin views (exact same behavior
    as the original version).
    """
    if date_value:
        return format_church(date_value, '%b %d, %Y - %I:%M %p')
    return 'Unknown date'


def safe_truncate(text, length=180):
    """Safely truncate text with HTML escaping to prevent template rendering issues.

    Used for previews on the dashboard recent activity feed and any long-text summaries.
    Exact same logic as original (escapes, truncates at word boundary, adds ellipsis).
    """
    if not text:
        return ''
    text = html.escape(str(text))
    if len(text) > length:
        return text[:length].rsplit(' ', 1)[0] + '...'
    return text


#print(" MYVINECHURCH.ONLINE the_gathering/dashboard/utils.py loaded successfully (public-style rebuilt)")