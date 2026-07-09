# MYVINECHURCH.ONLINE/app/routes/public/public_dashboard/utils.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/public_dashboard/utils.py
# File name: utils.py
# Brief, detailed purpose: Feature-specific utility functions for the Public Dashboard (rich social-media style feed).
# • Exact same censor_public_content and format_public_datetime logic from the original shared public/utils.py
# • Tailored keys for the mixed feed items (title, body, content, event_name, location, description, notes, etc.)
# • No functionality lost – all censoring and date formatting remain identical for the homepage feed.
# • 100% rebuilt to match the exact style of public/events/utils.py and public/dreams/utils.py gold standard.

from app.utils.helpers import censor_text
from app.utils.time_utils import format_church


# ----------------------------------------------------------------------
# Public Helpers (Dashboard specific)
# ----------------------------------------------------------------------
def censor_public_content(items):
    """Apply server-side censorship to the rich public dashboard feed items.
    Handles mixed content types (announcements, events, sermons, prayers, dreams, prophecies)."""
    for item in items:
        for key in ['title', 'body', 'content', 'event_name', 'location', 'description', 'notes']:
            if key in item and item[key]:
                item[key] = censor_text(item[key])
    return items


def format_public_datetime(date_value):
    """Format datetime for the public dashboard feed using the church's timezone helper.
    Exact same behavior as the original public/utils.py and Events gold standard."""
    if date_value:
        return format_church(date_value, '%B %d, %Y at %I:%M %p')
    return 'Unknown date'


