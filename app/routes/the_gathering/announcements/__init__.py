# MYVINECHURCH.ONLINE/app/routes/the_gathering/announcements/__init__.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/announcements/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Announcements sub-blueprint for the Gathering Place Manager.
# - Dedicated routes for all announcement management (list, edit, view, delete, comments.html).
# - url_prefix='/announcements' under the parent /the_gathering.
# - Template folder points to templates/the_gathering/announcements/
# - Keeps every other file on the site untouched and working.
# - Part of the new nested sub-blueprint structure you requested.

from flask import Blueprint

announcements_bp = Blueprint(
    'announcements',
    __name__,
    url_prefix='/announcements',
    template_folder='../../../templates/the_gathering/announcements',
    static_folder='../../../static'
)

# Import the dedicated files for this section (will be built one at a time)
from . import views
from . import queries
from . import forms
from . import utils

# print(" MYVINECHURCH.ONLINE the_gathering/announcements sub-blueprint initialized successfully (dedicated routes for edit/delete/comments.html ready)")