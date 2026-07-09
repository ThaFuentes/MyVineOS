# MYVINECHURCH.ONLINE/app/routes/public/__init__.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Main public blueprint package initializer.
# public_bp now has url_prefix='/public' so all community features live cleanly under /public/dreams, /public/events, etc.
# Registers the sub-blueprints (public_dashboard for the feed at /public/, plus public_dreams etc.).
# Sub bps use names like 'public_dreams' so full endpoints are 'public.public_dreams.public_dreams' (unambiguous).
# Private bps (short names at /dreams etc.) are registered earlier but paths no longer collide.

from flask import Blueprint, flash, redirect, url_for

# ──────────────────────────────────────────────────────────────
# Main public blueprint (url_prefix='/public' for clean public community area)
# ──────────────────────────────────────────────────────────────
public_bp = Blueprint(
    'public',
    __name__,
    url_prefix='/public',
    template_folder='../templates/public',
    static_folder='../static'
)

# ──────────────────────────────────────────────────────────────
# Register all public feature sub-blueprints
# (Each sub-module defines its own bp in its __init__.py)
# ──────────────────────────────────────────────────────────────

# Public Dashboard (homepage feed) – becomes /public/ and /public/public
from .public_dashboard import dashboard_bp
public_bp.register_blueprint(dashboard_bp)

# Announcements → /public/announcements
from .announcements import announcements_bp
public_bp.register_blueprint(announcements_bp)

# Dreams & Visions → /public/dreams
from .dreams import dreams_bp
public_bp.register_blueprint(dreams_bp)

# Events (potluck, signups, comments) → /public/events
from .events import events_bp
public_bp.register_blueprint(events_bp)

# Prayers → /public/prayers
from .prayers import prayers_bp
public_bp.register_blueprint(prayers_bp)

# Prophecies → /public/prophecies
from .prophecies import prophecies_bp
public_bp.register_blueprint(prophecies_bp)

# Sermons → /public/sermons
from .sermons import sermons_bp
public_bp.register_blueprint(sermons_bp)

# print(" public routes initialized under /public/ with clean nested endpoints (public.public_xxx.*)")

# ----------------------------------------------------------------------
# Donate (online giving public page)
# Currently a minimal implementation so url_for('public.donate') and the nav tab work without 404/BuildError.
# The tab is only shown when settings.online_donations_enabled is truthy.
# TODO: Create templates/public/donate.html + proper query of online donation options (see settings/online_giving.py load_online_options).
# ----------------------------------------------------------------------
@public_bp.route('/donate')
def donate():
    """Public-facing donate / online giving landing."""
    # For now, send users to the rich public community feed (where they can see announcements etc.)
    # and give a helpful flash. Future: dedicated page listing Stripe/PayPal/Venmo/QR options from DB.
    flash('Thank you for supporting the ministry! Online giving options and links are available from our team or will appear here soon.', 'info')
    return redirect(url_for('public.public_dashboard.public_dashboard'))
