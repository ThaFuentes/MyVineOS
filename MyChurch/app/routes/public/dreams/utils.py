# MYVINECHURCH.ONLINE/app/routes/public/dreams/utils.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/dreams/utils.py
# File name: utils.py
# Brief, detailed purpose: Feature-specific utility functions for the public Dreams & Visions section.
# - Exact same censor_public_content and format_public_datetime logic from the original shared public/utils.py
# - Tailored keys for dreams (title, description, notes, category) while preserving 100% of the old behavior
# - No functionality lost - all censoring, date formatting, and public safety checks remain identical

from app.utils.helpers import censor_text
from app.utils.time_utils import format_church


# ----------------------------------------------------------------------
# Public Helpers (Dreams & Visions specific)
# ----------------------------------------------------------------------
def censor_public_content(items):
    """Apply server-side censorship to a list of public dreams.
    Used by dreams listing and detail routes (exact same logic as the old shared public/utils.py)."""
    for item in items:
        for key in ['title', 'description', 'notes', 'category']:
            if key in item and item[key]:
                item[key] = censor_text(item[key])
    return items


def format_public_datetime(date_value):
    """Format datetime for public dreams pages using the church's timezone helper.
    Exact same behavior as the original public/utils.py."""
    if date_value:
        return format_church(date_value, '%B %d, %Y at %I:%M %p')
    return 'Unknown date'


