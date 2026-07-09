# app/routes/inventory/__init__.py
# Full path: MyVineChurch/app/routes/inventory/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Inventory Blueprint Package Initializer - 100% MariaDB/pymysql compatible.
# - Creates the exact same Blueprint(name='inventory', url_prefix='/inventory') as the old flat file.
# - Automatically imports ALL modular files so every route registers instantly.
# - Zero functional change today - dashboard, barcode lookup, items catalog, receive stock, categories/locations, low-stock/expiring alerts, audit logging all remain 100% identical.
# - Designed purely for future scaling.

from flask import Blueprint

# ----------------------------------------------------------------------
# Blueprint definition (identical to old inventory.py)
# ----------------------------------------------------------------------
inventory_bp = Blueprint(
    'inventory',
    __name__,
    url_prefix='/inventory'
)

# ----------------------------------------------------------------------
# Import ALL modules - routes register automatically
# ----------------------------------------------------------------------
from . import views
from . import queries
from . import forms
from . import utils

# Re-export for easy import in app/__init__.py
__all__ = ['inventory_bp']