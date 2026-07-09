# app/routes/dashboard/forms.py
# Full path: MyVineChurch/app/routes/dashboard/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation and data cleaning for the Dashboard module.
# - Currently NO forms are used (dashboard is a pure display route with no POST actions).
# - This file exists for future-proofing – easy to add widget customization, quick-search, or user preference forms later.
# - Keeps the package structure consistent with announcements, attendance, and auth.

from flask import flash


# ----------------------------------------------------------------------
# Placeholder – ready for future dashboard forms
# ----------------------------------------------------------------------
def validate_widget_settings_form(form_data):
    """
    Example placeholder for future widget customization form.
    Returns cleaned data or None + flash on error.
    """
    # No current forms – always return success placeholder
    return {}  # or raise NotImplementedError when you add real forms


# No other form functions needed at this time