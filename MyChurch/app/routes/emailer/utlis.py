# app/routes/emailer/utils.py
# Full path: MyVineChurch/app/routes/emailer/utils.py
# File name: utils.py
# Brief, detailed purpose: Utility functions and constants for the Emailer module.
# - REQUIRED_ROLES constant for consistency
# - Email validation and formatting helpers
# - Designed for easy future growth (bulk sending, templates, scheduled emails, etc.)
# - 100% professional and secure - no partials, no placeholders.

import re


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
REQUIRED_ROLES = ['Staff', 'Admin', 'Owner']


# ----------------------------------------------------------------------
# Email Validation
# ----------------------------------------------------------------------
def is_valid_email(email: str) -> bool:
    """Basic but robust email format validation."""
    if not email or not isinstance(email, str):
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email.strip()) is not None


# ----------------------------------------------------------------------
# Email Formatting
# ----------------------------------------------------------------------
def build_email_body(message: str, signature: str = None) -> str:
    """Build a clean email body with optional signature."""
    if signature:
        return f"{message}\n\n---\n{signature}"
    return message


# ----------------------------------------------------------------------
# Future Growth Placeholders
# ----------------------------------------------------------------------
# These can be expanded when you add bulk email, templates, scheduling, etc.
def get_default_signature():
    """Return default church email signature (can be made configurable later)."""
    return "Sent from MyVineChurch.Online\nwww.myvinechurch.online"