# MYVINECHURCH.ONLINE/app/routes/public/announcements/__init__.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/announcements/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Public Announcements sub-blueprint initializer.
# url_prefix='/announcements' under parent public_bp (/public) -> /public/announcements
# Uses 'public_announcements' name -> full endpoints public.public_announcements.* for reliable url_for.

from flask import Blueprint

announcements_bp = Blueprint(
    'public_announcements',
    __name__,
    url_prefix='/announcements',
    template_folder='../../../templates/public/announcements',
    static_folder='../../../static'
)

# Import views/routes (next file we will rebuild)
from . import views

