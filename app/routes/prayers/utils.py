# app/routes/prayers/utils.py
# Full path: MyVineChurch/app/routes/prayers/utils.py
# File name: utils.py
# Brief, detailed purpose: Utility functions and constants for the Prayers module.
# • REQUIRED_ROLES and ADMIN_ROLES constants
# • Simple helpers for role checks (keeps views.py clean)
# • Designed for easy future growth (email notifications, response moderation, etc.)
# • 100% consistent with the rest of the application

from flask import session


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
REQUIRED_ROLES = ['Staff', 'Admin', 'Owner']
ADMIN_ROLES = ['Admin', 'Owner']


# ----------------------------------------------------------------------
# Permission Helpers
# ----------------------------------------------------------------------
def is_admin_or_owner():
    """True if current user is Admin or Owner."""
    return session.get('user_role') in ADMIN_ROLES


def is_staff_plus():
    """True if current user is Staff, Admin, or Owner."""
    return session.get('user_role') in REQUIRED_ROLES


# ----------------------------------------------------------------------
# Future Growth Placeholders
# ----------------------------------------------------------------------
# These can be expanded when you add more prayer features (notifications, moderation, etc.)
def get_default_visibility():
    """Default visibility for new prayer requests (public focus)."""
    return 'public'