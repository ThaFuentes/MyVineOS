# app/routes/bills/__init__.py
# Full path: MyVineChurch/app/routes/bills/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Bills blueprint package initializer.
# Creates the bills blueprint and registers all route groups from the split modules.
# This is the file imported by the app factory (app/__init__.py still does importlib.import_module('app.routes.bills')).

from flask import Blueprint

bills_bp = Blueprint('bills', __name__, url_prefix='/bills')

# Register route groups from the split files in this package
from .dashboard import register_dashboard_routes
from .view import register_view_routes
from .management import register_management_routes
from .assign import register_assign_routes
from .delete import register_delete_routes
from .payment import register_payment_routes
from .reminder import register_reminder_routes

register_dashboard_routes(bills_bp)
register_view_routes(bills_bp)
register_management_routes(bills_bp)
register_assign_routes(bills_bp)
register_delete_routes(bills_bp)
register_payment_routes(bills_bp)
register_reminder_routes(bills_bp)