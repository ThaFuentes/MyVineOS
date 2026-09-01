# MYVINECHURCH.ONLINE/app/routes/public/public_dashboard/__init__.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/public_dashboard/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Public Dashboard sub-blueprint initializer (rich feed on the public homepage).
# Registered under public parent (url_prefix='/public'), so this sub's '/' route serves /public/
# (the main guest landing page / public community hub feed).
# 'public_dashboard' bp name -> endpoint 'public.public_dashboard.public_dashboard'
# Uses dedicated public templates.

from flask import Blueprint

dashboard_bp = Blueprint(
    'public_dashboard',
    __name__,
    # No url_prefix on this sub-bp. When registered under public_bp (url_prefix="/public"),
    # its @dashboard_bp.route("/") becomes the public homepage at exactly /public/
    # (the main guest + community feed entry point).
    template_folder='../../templates/public',
    static_folder='../../static'
)

# Import views/routes (next file we will rebuild)
from . import views

