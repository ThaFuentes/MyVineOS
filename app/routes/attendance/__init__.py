# app/routes/attendance/__init__.py
# Full path: MyVineChurch/app/routes/attendance/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Attendance Blueprint Package Initializer – 100% MariaDB/pymysql compatible.
# • Creates the exact same Blueprint(name='attendance', url_prefix='/attendance') as the old flat file.
# • Automatically imports all modular files so every route registers instantly.
# • Zero functional change today – kiosk, self-checkin, dashboard, day details, live search, token security, UTC time handling all remain 100% identical.
# • Designed purely for future scaling: we can now safely split into views.py, queries.py, forms.py, utils.py (and later api.py, tasks.py, etc.) without touching main.py or app/__init__.py.

from flask import Blueprint

# ----------------------------------------------------------------------
# Blueprint definition (identical to old attendance.py)
# ----------------------------------------------------------------------
attendance_bp = Blueprint(
    'attendance',
    __name__,
    url_prefix='/attendance'
)

# ----------------------------------------------------------------------
# Import route modules (they will define all the @attendance_bp.route handlers)
# ----------------------------------------------------------------------
# We do ONE file at a time per your instructions → next we will build views.py
from . import views
# from . import queries
# from . import forms
# from . import utils

# Optional: re-export for easy import in app/__init__.py
__all__ = ['attendance_bp']