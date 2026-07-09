# app/routes/profile/__init__.py
# Full path: MyVineChurch/app/routes/profile/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Profile Blueprint Package Initializer – 100% MariaDB/pymysql compatible.
# - Creates the exact same Blueprint(name='profile', url_prefix='/profile') as the old flat file.
# - Automatically imports ALL modular files so every route registers instantly.
# - Zero functional change today – profile viewing/editing, family relationship management, privacy preferences, check-in PIN, censored word checks, audit logging all remain 100% identical.
# - Designed purely for future scaling: we can now safely add more profile features without touching app/__init__.py or main.py.

from flask import Blueprint

# ----------------------------------------------------------------------
# Blueprint definition (identical to old profile.py)
# ----------------------------------------------------------------------
profile_bp = Blueprint(
    'profile',
    __name__,
    url_prefix='/profile'
)

# ----------------------------------------------------------------------
# Import ALL modules – routes register automatically
# ----------------------------------------------------------------------
from . import views
from . import security
from . import queries
from . import forms
from . import utils

# Re-export for easy import in app/__init__.py
__all__ = ['profile_bp']