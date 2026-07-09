# MYVINECHURCH.ONLINE/app/routes/the_gathering/prayers/__init__.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/prayers/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Prayers sub-blueprint for the Gathering Place Manager.
# • Dedicated routes for all prayer management (list, edit, view, delete, responses, comments.html).
# • url_prefix='/prayers' under the parent /the_gathering.
# • Template folder points to templates/the_gathering/prayers/
# • Keeps every other file on the site untouched and working.
# • Part of the new nested sub-blueprint structure you requested.

from flask import Blueprint

prayers_bp = Blueprint(
    'prayers',
    __name__,
    url_prefix='/prayers',
    template_folder='../../../templates/the_gathering/prayers',
    static_folder='../../../static'
)

# Import the dedicated files for this section (will be built one at a time)
from . import views
from . import queries
from . import forms
from . import utils

# print("✅ MYVINECHURCH.ONLINE the_gathering/prayers sub-blueprint initialized successfully (dedicated routes for edit/delete/responses/comments.html ready)")