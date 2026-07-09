# MYVINECHURCH.ONLINE/app/routes/the_gathering/dashboard/__init__.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/dashboard/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Sub-blueprint initializer for the MAIN Gathering Place Manager Dashboard (overview, stats, recent activity).
# • Creates dashboard_bp with url_prefix='/dashboard' so the full URL is /the_gathering/dashboard (preserves original user-facing URL).
# • Template folder points to the correct location under templates/the_gathering/dashboard/.
# • Imports all supporting modules (views, queries, forms, utils) exactly like the public sub-blueprints and the parent the_gathering/__init__.py.
# • 100% rebuilt to match the clean, modular, nested blueprint pattern we perfected on the public side and in the parent the_gathering blueprint.
# • No functionality changed — only structure, readability, and consistency updated.

from flask import Blueprint

# ──────────────────────────────────────────────────────────────
# Main Dashboard Sub-Blueprint (for the Gathering Place Manager overview)
# ──────────────────────────────────────────────────────────────
dashboard_bp = Blueprint(
    'dashboard',
    __name__,
    url_prefix='/dashboard',
    template_folder='../../../templates/the_gathering',
    static_folder='../../../static'
)

# ──────────────────────────────────────────────────────────────
# Import all supporting modules for the main dashboard
# (These will be rebuilt one at a time next — exactly like public/ sub-modules)
# ──────────────────────────────────────────────────────────────
from . import queries
from . import forms
from . import utils
# Import view functions explicitly so all routes register on startup
from .views import dashboard, moderation_queue  # noqa: F401

print("✅ MYVINECHURCH.ONLINE the_gathering/dashboard sub-blueprint initialized successfully (main dashboard ready for registration)")