# MYVINECHURCH.ONLINE/app/routes/the_gathering/events/__init__.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/events/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Events sub-blueprint for the Gathering Place Manager.
# - Dedicated routes for all event management (list, edit, view, delete, potluck, comments.html).
# - url_prefix='/events' under the parent /the_gathering.
# - Template folder points to templates/the_gathering/events/
# - Keeps every other file on the site untouched and working.
# - Part of the new nested sub-blueprint structure you requested.

from flask import Blueprint

events_bp = Blueprint(
    'events',
    __name__,
    url_prefix='/events',
    template_folder='../../../templates/the_gathering/events',
    static_folder='../../../static'
)

# Import the dedicated files for this section (will be built one at a time)
from . import views
from . import queries
from . import forms
from . import utils

# print(" MYVINECHURCH.ONLINE the_gathering/events sub-blueprint initialized successfully (dedicated routes for edit/delete/potluck/comments.html ready)")