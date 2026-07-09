# app/routes/profile/utils.py
# Full path: MyVineChurch/app/routes/profile/utils.py
# File name: utils.py
# Brief, detailed purpose: Utility functions and constants for the Profile module.
# • REQUIRED_ROLES constant
# • current_user_id() helper for logging and ownership
# • PIN hashing and validation helper
# • 100% matches the original profile.py helpers and logic. No renaming of anything.

from flask import session
from werkzeug.security import generate_password_hash


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
REQUIRED_ROLES = ['Staff', 'Admin', 'Owner']


# ----------------------------------------------------------------------
# User Helpers
# ----------------------------------------------------------------------
def current_user_id():
    """Return current logged-in user ID for logging and ownership."""
    return session.get('user_id')


# ----------------------------------------------------------------------
# PIN Helpers
# ----------------------------------------------------------------------
def hash_checkin_pin(pin: str):
    """Hash the check-in PIN if provided. Returns None if empty."""
    if not pin or not pin.strip():
        return None
    return generate_password_hash(pin.strip())


def is_valid_checkin_pin(pin: str) -> bool:
    """Validate PIN is 4-6 digits or empty."""
    if not pin or not pin.strip():
        return True
    pin = pin.strip()
    return pin.isdigit() and 4 <= len(pin) <= 6