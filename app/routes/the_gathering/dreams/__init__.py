# MYVINECHURCH.ONLINE/app/routes/the_gathering/dreams/__init__.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/dreams/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Dreams sub-blueprint for the Gathering Place Manager.
# • Dedicated routes for all dream/vision management (list, edit, view, delete, comments.html).
# • url_prefix='/dreams' under the parent /the_gathering.
# • Template folder points to templates/the_gathering/dreams/
# • Keeps every other file on the site untouched and working.
# • Part of the new nested sub-blueprint structure you requested.

from flask import Blueprint

dreams_bp = Blueprint(
    'dreams',
    __name__,
    url_prefix='/dreams',
    template_folder='../../../templates/the_gathering/dreams',
    static_folder='../../../static'
)

# Import the dedicated files for this section (will be built one at a time)
from . import views
from . import queries
from . import forms
from . import utils

# print("✅ MYVINECHURCH.ONLINE the_gathering/dreams sub-blueprint initialized successfully (dedicated routes for edit/delete/comments.html ready)")