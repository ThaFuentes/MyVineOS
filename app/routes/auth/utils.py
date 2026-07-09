# app/routes/auth/utils.py
# Full path: MyVineChurch/app/routes/auth/utils.py
# File name: utils.py
# Brief, detailed purpose: Utility functions and constants for the Auth module.
# • Generates secure random reset codes for password reset.
# • Keeps views.py, forms.py, and queries.py clean and focused.
# • 100% matches the original reset code logic from the flat auth.py.
# • Ready for future growth (add password strength checker, token expiration, email templates, etc.).

import random
import string


# ----------------------------------------------------------------------
# Reset Code Generator
# ----------------------------------------------------------------------
def generate_reset_code(length=10):
    """Generate a random numeric reset code (default 10 digits) for password reset."""
    return ''.join(random.choices(string.digits, k=length))