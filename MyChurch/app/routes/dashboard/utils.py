# app/routes/dashboard/utils.py
# Full path: MyVineChurch/app/routes/dashboard/utils.py
# File name: utils.py
# Brief, detailed purpose: Utility functions for the Dashboard module.
# - Prepares content lists with server-side censorship + church-local date/time formatting.
# - Keeps repeated formatting logic out of views.py (DRY).
# - 100% matches the original dashboard.py formatting behavior.
# - Ready for future growth (widget prep, quick stats, custom dashboard sections, etc.).

from app.utils.helpers import censor_text
from app.utils.time_utils import format_church
from datetime import datetime


# ----------------------------------------------------------------------
# Content Formatting Helpers
# ----------------------------------------------------------------------
def prepare_formatted_item(item, date_key='datetime'):
    """Add censored title and formatted date/time to a single content item."""
    if 'title' in item:
        item['title'] = censor_text(item['title'])

    if item.get(date_key):
        item['formatted_date'] = format_church(item[date_key], '%B %d, %Y')
        item['formatted_time'] = format_church(item[date_key], '%I:%M %p')
    else:
        item['formatted_date'] = 'Unknown'
        item['formatted_time'] = ''
    return item


def prepare_formatted_list(items, date_key='datetime'):
    """Apply formatting to an entire list of content items (prayers, dreams, etc.)."""
    for item in items:
        prepare_formatted_item(item, date_key)
    return items


def format_event_item(event):
    """Special formatting for events (event_date + optional event_time)."""
    event['title'] = censor_text(event['title'])
    event['formatted_date'] = event['event_date'].strftime('%A, %B %d, %Y')

    if event.get('event_time'):
        try:
            time_obj = datetime.strptime(event['event_time'], '%H:%M:%S').time()
            event['formatted_time'] = time_obj.strftime('%I:%M %p')
            event['formatted_full'] = f"{event['formatted_date']} at {event['formatted_time']}"
        except Exception:
            event['formatted_time'] = 'All Day'
            event['formatted_full'] = event['formatted_date']
    else:
        event['formatted_time'] = 'All Day'
        event['formatted_full'] = event['formatted_date']
    return event