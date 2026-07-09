# app/routes/emailer/queries.py
# Full path: MyVineChurch/app/routes/emailer/queries.py
# File name: queries.py
# Brief, detailed purpose: All database queries and operations for the Emailer module.
# - Pure data-access layer – no Flask routes, no templates, no flash messages.
# - Handles audit logging for all email sends (manual or bulk in the future).
# - Designed for easy growth – we can add bulk email logging, email templates, scheduled emails, etc. here without touching views.py.

from app.models.db import get_db
from app.models.log import log_change


# ----------------------------------------------------------------------
# Audit Logging
# ----------------------------------------------------------------------
def log_email_send(user_id, to_email, subject, success=True):
    """Log email send action with full details for audit trail."""
    details = f"Manual email sent to {to_email} – Subject: {subject}"
    if not success:
        details = f"FAILED: {details}"

    log_change(
        user_id=user_id,
        action='email',
        change_details=details
    )
    return True