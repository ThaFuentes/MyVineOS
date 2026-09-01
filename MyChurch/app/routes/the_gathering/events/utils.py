# MYVINECHURCH.ONLINE/app/routes/the_gathering/events/utils.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/events/utils.py
# File name: utils.py
# Brief, detailed purpose: Utility helpers specifically for the Events section
# of the Gathering Place Manager.
# - Light censorship for manager display (flags prohibited words).
# - Date/time formatting using church timezone helper.
# - 100% consistent with the_gathering/dreams/utils.py and announcements/utils.py.
# - Only this file was rebuilt - everything else on the site remains untouched.

from app.utils.helpers import censor_text
from app.utils.time_utils import format_church
import html


def censor_for_manager(items, fields=None):
    """
    Apply light censorship for manager views (shows original content but flags issues).
    Used on events listing, potluck, and comment views.
    """
    if fields is None:
        fields = ['event_name', 'description', 'name', 'comment_text', 'notes']

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
    """Format any datetime for manager dashboard display using the church's timezone helper."""
    if date_value:
        return format_church(date_value, '%b %d, %Y - %I:%M %p')
    return 'Unknown date'


def safe_truncate(text, length=180):
    """Safely truncate text with HTML escaping."""
    if not text:
        return ''
    text = html.escape(str(text))
    if len(text) > length:
        return text[:length].rsplit(' ', 1)[0] + '...'
    return text


# print(" MYVINECHURCH.ONLINE the_gathering/events/utils.py loaded successfully (manager helpers ready)")