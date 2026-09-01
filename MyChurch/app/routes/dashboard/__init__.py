# app/routes/dashboard/__init__.py
# Full path: MyVineChurch/app/routes/dashboard/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Dashboard Blueprint Package Initializer - 100% MariaDB/pymysql compatible.
# - Creates the exact same Blueprint(name='dashboard') as the old flat file (no url_prefix).
# - Automatically imports all modular files so every route registers instantly.
# - Zero functional change today - public/private dashboard, birthdays, prayers, dreams, prophecies, sermons, announcements, events, widgets, timezone-aware formatting, censorship all remain 100% identical.
# - Designed purely for future scaling.

from flask import Blueprint

# ----------------------------------------------------------------------
# Blueprint definition (identical to old dashboard.py)
# ----------------------------------------------------------------------
dashboard_bp = Blueprint('dashboard', __name__)

# ----------------------------------------------------------------------
# Import route modules (they will define all the @dashboard_bp.route handlers)
# ----------------------------------------------------------------------
# We do ONE file at a time per your instructions -> next we will build views.py
from . import views
# from . import queries
# from . import forms
# from . import utils

# Optional: re-export for easy import in app/__init__.py
__all__ = ['dashboard_bp']