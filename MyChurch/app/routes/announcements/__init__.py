# app/routes/announcements/__init__.py
# Full path: MyVineChurch/app/routes/announcements/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Announcements Blueprint Package Initializer
# - Creates the exact same Blueprint(name='announcements', url_prefix='/announcements')
# - Automatically imports all modular files so every route registers instantly
# - Zero functional change today - 100% compatible with your current main.py / app factory
# - Designed purely for future scaling (add api.py, tasks.py, admin.py later with zero breakage)

from flask import Blueprint

# ----------------------------------------------------------------------
# Blueprint (identical to the old flat file)
# ----------------------------------------------------------------------
announcements_bp = Blueprint(
    'announcements',
    __name__,
    url_prefix='/announcements'
)

# ----------------------------------------------------------------------
# Import all modules - routes register automatically when imported
# ----------------------------------------------------------------------
from . import views
from . import queries
from . import forms
from . import utils

# Optional: re-export for easy import in app/__init__.py or main.py
__all__ = ['announcements_bp']