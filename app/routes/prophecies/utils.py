# app/routes/prophecies/utils.py
# Full path: MyVineChurch/app/routes/prophecies/utils.py
# File name: utils.py
# Brief, detailed purpose: Utility functions and constants for the Prophecies module.
# - REQUIRED_ROLES and ADMIN_ROLES constants
# - Simple role check helpers (keeps views.py clean)
# - 100% matches the original prophecies.py constants and permission logic.

from flask import session


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
REQUIRED_ROLES = ['Admin', 'Owner']
ADMIN_ROLES = ['Admin', 'Owner']


# ----------------------------------------------------------------------
# Permission Helpers
# ----------------------------------------------------------------------
def is_admin_or_owner():
    """True if current user is Admin or Owner."""
    return session.get('user_role') in ADMIN_ROLES


def is_staff_plus():
    """True if current user is Staff, Admin, or Owner (for future expansion)."""
    return session.get('user_role') in REQUIRED_ROLES