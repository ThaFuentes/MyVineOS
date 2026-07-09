# app/routes/members/__init__.py
# Full path: MyVineChurch/app/routes/members/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Members Blueprint Package Initializer – 100% MariaDB/pymysql compatible.
# • Creates the exact same Blueprint(name='members', url_prefix='/members') as the old flat file.
# • Automatically imports ALL modular files (views, queries, forms, utils) so every route registers instantly.
# • Zero functional change today – member directory, add/edit member, delete, export DOCX, email roster, family relations, group assignment, censored word checks, audit logging all remain 100% identical.
# • Designed purely for future scaling: we can now safely add more member features without touching app/__init__.py or main.py.

from flask import Blueprint

# ----------------------------------------------------------------------
# Blueprint definition (identical to old members.py)
# ----------------------------------------------------------------------
members_bp = Blueprint(
    'members',
    __name__,
    url_prefix='/members'
)

# ----------------------------------------------------------------------
# Import ALL modules – routes register automatically
# ----------------------------------------------------------------------
from . import views
from . import queries
from . import forms
from . import utils

# Re-export for easy import in app/__init__.py
__all__ = ['members_bp']