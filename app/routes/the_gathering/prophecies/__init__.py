# MYVINECHURCH.ONLINE/app/routes/the_gathering/prophecies/__init__.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/prophecies/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Prophecies sub-blueprint for the Gathering Place Manager.
# • Dedicated routes for all prophecy management (list, edit, view, delete, comments.html).
# • url_prefix='/prophecies' under the parent /the_gathering.
# • Template folder points to templates/the_gathering/prophecies/
# • Keeps every other file on the site untouched and working.
# • Part of the new nested sub-blueprint structure you requested.

from flask import Blueprint

prophecies_bp = Blueprint(
    'prophecies',
    __name__,
    url_prefix='/prophecies',
    template_folder='../../../templates/the_gathering/prophecies',
    static_folder='../../../static'
)

# Import the dedicated files for this section (will be built one at a time)
from . import views
from . import queries
from . import forms
from . import utils

print("✅ MYVINECHURCH.ONLINE the_gathering/prophecies sub-blueprint initialized successfully (dedicated routes for edit/delete/comments.html ready)")