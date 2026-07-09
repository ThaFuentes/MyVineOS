# MYVINECHURCH.ONLINE/app/routes/public/events/__init__.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/events/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Public Events sub-blueprint initializer.
# url_prefix='/events' under parent /public → /public/events
# Blueprint name 'public_events' → endpoints 'public.public_events.*'
# Clean structure, no more hyphen hacks or route stealing.

from flask import Blueprint

events_bp = Blueprint(
    'public_events',
    __name__,
    url_prefix='/events',
    template_folder='../../../templates/public/events',
    static_folder='../../../static'
)

# Import views/routes
from . import views

