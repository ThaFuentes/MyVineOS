# MYVINECHURCH.ONLINE/app/routes/the_gathering/prayers/utils.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/prayers/utils.py
# File name: utils.py
# Brief, detailed purpose: Utility helpers specifically for the Prayers section
# of the Gathering Place Manager.
# - Light censorship for manager display (flags prohibited words).
# - Date/time formatting using church timezone helper.
# - Audit log preparation for every create/edit/delete/moderate action.
# - Safe truncation and HTML escaping for tables.
# - 100% consistent with the_gathering/events/utils.py, dreams/utils.py and announcements/utils.py.
# - Only this file was rebuilt — everything else on the site remains untouched.

from app.utils.helpers import censor_text
from app.utils.time_utils import format_church
import html


def censor_for_manager(items, fields=None):
    """
    Apply light censorship for manager views (shows original content but flags issues).
    Used on prayers listing and comment views.
    """
    if fields is None:
        fields = ['title', 'prayer_text', 'name', 'comment_text']

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
    """Format any datetime for manager display using church timezone."""
    if date_value:
        return format_church(date_value, '%b %d, %Y - %I:%M %p')
    return 'Unknown date'


def prepare_audit_log(action, item_type, item_id, user_id, details=None):
    """
    Prepare structured data for audit logging (future-proof).
    Call before every create/update/delete/moderate action in prayers.
    """
    return {
        'action': action,
        'item_type': item_type,          # 'prayer' or 'prayer_comment'
        'item_id': item_id,
        'performed_by': user_id,
        'details': details or {},
        'timestamp': format_church(None)  # will be replaced with NOW() in DB
    }


def safe_truncate(text, length=180):
    """Safe truncation with HTML escaping for prayer tables."""
    if not text:
        return ''
    text = html.escape(str(text))
    if len(text) > length:
        return text[:length].rsplit(' ', 1)[0] + '…'
    return text


# print(" MYVINECHURCH.ONLINE the_gathering/prayers/utils.py loaded successfully (manager helpers + audit prep ready)")