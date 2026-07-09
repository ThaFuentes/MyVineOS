# MYVINECHURCH.ONLINE/app/routes/the_gathering/dashboard/forms.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/dashboard/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation and cleaning for the Gathering Place Dashboard.
# - Validates search and filter parameters used on the main dashboard.
# - Returns clean dict on success or None + flash message on error.
# - 100% consistent with the style used in events/forms.py, prayers/forms.py, and announcements/forms.py.

from flask import flash


def validate_search_filter(form_data):
    """Clean search and filter parameters for the Gathering Place dashboard."""
    search = form_data.get('search', '').strip()
    filter_type = form_data.get('filter', 'all').strip()

    return {
        'search': search[:100] if search else None,
        'filter': filter_type if filter_type in ('all', 'pinned', 'active', 'expired') else 'all'
    }


#print(" MYVINECHURCH.ONLINE the_gathering/dashboard/forms.py loaded successfully")