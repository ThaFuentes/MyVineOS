# app/routes/auth/__init__.py
# Full path: MyVineChurch/app/routes/auth/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Auth Blueprint Package Initializer – 100% MariaDB/pymysql compatible.
# • Creates the exact same Blueprint(name='auth') as the old flat file (no url_prefix).
# • Automatically imports ALL modular files so every route registers instantly.
# • 100% complete – views, queries, forms, and utils are all loaded and working.
# • Zero functional change today – login, logout, register, password reset, forgot username, root redirect, censorship, Owner creation, pending/banned checks all remain 100% identical.

from flask import Blueprint

# ----------------------------------------------------------------------
# Blueprint definition (identical to old auth.py)
# ----------------------------------------------------------------------
auth_bp = Blueprint('auth', __name__)

# ----------------------------------------------------------------------
# Import ALL modules – routes register automatically
# ----------------------------------------------------------------------
from . import views
from . import queries
from . import forms
from . import utils

# Re-export for easy import in app/__init__.py
__all__ = ['auth_bp']