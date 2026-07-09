# MYVINECHURCH.ONLINE/app/routes/the_gathering/sermons/__init__.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/sermons/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Sermons sub-blueprint for the Gathering Place Manager.
# • Dedicated routes for all sermon management (list, edit, view, delete, sections, comments.html).
# • url_prefix='/sermons' under the parent /the_gathering.
# • Template folder points to templates/the_gathering/sermons/
# • Keeps every other file on the site untouched and working.
# • Part of the new nested sub-blueprint structure you requested.

from flask import Blueprint

sermons_bp = Blueprint(
    'sermons',
    __name__,
    url_prefix='/sermons',
    template_folder='../../../templates/the_gathering/sermons',
    static_folder='../../../static'
)

# Import the dedicated files for this section (will be built one at a time)
from . import views
from . import queries
from . import forms
from . import utils

# print("✅ MYVINECHURCH.ONLINE the_gathering/sermons sub-blueprint initialized successfully (dedicated routes for edit/delete/sections/comments.html ready)")