# Permission Groups product UI is permanently removed.
# No Blueprint. No /groups routes. /groups must 404.
#
# Remaining modules are libraries only:
#   utils.py           — KNOWN_PERMISSIONS catalog (imported by Access / help)
#   gathering_place.py — Gathering Place access check
#   queries.py / forms.py — kept for any legacy internal imports

__all__ = []
