# app/routes/groups/__init__.py
# Full path: MyVineChurch/app/routes/groups/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Groups Blueprint Package Initializer - 100% MariaDB/pymysql compatible.
# - Creates the exact same Blueprint(name='groups', url_prefix='/groups') as the old flat file.
# - Automatically imports ALL modular files (views, queries, forms, utils) so every route registers instantly.
# - Zero functional change today - group management, granular permissions (JSON array), leader checks, visibility enforcement, censored word checks on name/description, audit logging, fetch_groups_with_details, KNOWN_PERMISSIONS, assign/remove/update role all remain 100% identical.
# - Designed purely for future scaling: we can now safely add more group features without touching app/__init__.py or main.py.

from flask import Blueprint

# ----------------------------------------------------------------------
# Blueprint definition (identical to old groups.py)
# ----------------------------------------------------------------------
groups_bp = Blueprint(
    'groups',
    __name__,
    url_prefix='/groups'
)

# ----------------------------------------------------------------------
# Import ALL modules - routes register automatically
# ----------------------------------------------------------------------
from . import views
from . import queries
from . import forms
from . import utils
from .utils import group_role_label, GROUP_ROLES


@groups_bp.app_context_processor
def inject_group_role_helpers():
    return {
        'group_role_label': group_role_label,
        'GROUP_ROLES': GROUP_ROLES,
    }

# Re-export for easy import in app/__init__.py
__all__ = ['groups_bp']