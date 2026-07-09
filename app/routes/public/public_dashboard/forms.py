# MYVINECHURCH.ONLINE/app/routes/public/public_dashboard/forms.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/public_dashboard/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation and data cleaning for the Public Dashboard module.
# - The public dashboard is a read-only rich feed (no guest forms, no potluck, no comments.html on the homepage itself).
# - This file exists for full structural consistency with every other public feature (dreams, events, announcements, prophecies, etc.).
# - No validation functions are needed – kept minimal and clean so the modular layout remains identical across all sub-folders.
# - 100% rebuilt to match the exact style of events/forms.py, dreams/forms.py, etc.

from flask import flash
from app.utils.helpers import contains_censored_word


# No forms are used on the public dashboard feed itself.
# All guest comment / potluck / reply forms live in their individual feature folders (events, dreams, announcements, etc.).
# This file is intentionally empty (except for the standard header) to maintain 100% consistent project structure.

