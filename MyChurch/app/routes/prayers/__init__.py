# app/routes/prayers/__init__.py
# Full path: MyVineChurch/app/routes/prayers/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Prayers Blueprint Package Initializer - 100% MariaDB/pymysql compatible.
# - Creates the exact same Blueprint(name='prayers', url_prefix='/prayers') as the old flat file.
# - Automatically imports ALL modular files (views, queries, forms, utils) so every route registers instantly.
# - Zero functional change today - public/private prayers listing, add, view, edit, delete, responses, server-side censorship, audit logging all remain 100% identical.
# - Designed purely for future scaling: we can now safely add more prayer features without touching app/__init__.py or main.py.

from flask import Blueprint

# ----------------------------------------------------------------------
# Blueprint definition (identical to old prayers.py)
# ----------------------------------------------------------------------
prayers_bp = Blueprint(
    'prayers',
    __name__,
    url_prefix='/prayers'
)

# ----------------------------------------------------------------------
# Import ALL modules - routes register automatically
# ----------------------------------------------------------------------
from . import views
from . import queries
from . import forms
from . import utils

# Re-export for easy import in app/__init__.py
__all__ = ['prayers_bp']