# app/routes/events/__init__.py
# Full path: MyVineChurch/app/routes/events/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Events blueprint package initializer.
# Creates the events blueprint and registers all route groups from the split modules.
# This is the file imported by the app factory (app/__init__.py still does importlib.import_module('app.routes.events')).

from flask import Blueprint

events_bp = Blueprint('events', __name__, url_prefix='/events')

# Register route groups from the split files in this package
from .events_dashboard import register_dashboard_routes
from .event_detail import register_detail_routes
from .event_contributions import register_contributions_routes
from .event_management import register_management_routes
from .event_email import register_email_routes

register_dashboard_routes(events_bp)
register_detail_routes(events_bp)
register_contributions_routes(events_bp)
register_management_routes(events_bp)
register_email_routes(events_bp)