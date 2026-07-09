# app/routes/donations/__init__.py
# Full path: MyVineChurch/app/routes/donations/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Donations Blueprint Package Initializer – 100% MariaDB/pymysql compatible.
# - Creates the exact same Blueprint(name='donations', url_prefix='/donations') as the old flat file.
# - Automatically imports ALL modular files (views, queries, forms, utils) so every route registers instantly.
# - Zero functional change today – dashboard, add/edit/delete, view all, reports, DOCX exports, censored word checks, church local time, audit logging, member selector, etc. all remain 100% identical.
# - Fully modularized for future scaling – add new routes, API endpoints, or reports without ever touching this file again.

from flask import Blueprint

# ----------------------------------------------------------------------
# Blueprint definition (identical to old donations.py)
# ----------------------------------------------------------------------
donations_bp = Blueprint(
    'donations',
    __name__,
    url_prefix='/donations'
)

# ----------------------------------------------------------------------
# Import ALL modules – routes register automatically
# ----------------------------------------------------------------------
from . import views
from . import queries
from . import forms
from . import utils

# Re-export for easy import in app/__init__.py
__all__ = ['donations_bp']