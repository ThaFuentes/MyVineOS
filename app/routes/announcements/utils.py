# app/routes/announcements/utils.py
# Full path: MyVineChurch/app/routes/announcements/utils.py
# File name: utils.py
# Brief, detailed purpose: Utility functions and constants for the Announcements module.
# • REQUIRED_ROLES constant
# • censor_text() – server-side censorship
# • build_email_body() – keeps email logic clean
# • is_comment_owner() – critical for secure comment management (only owner OR moderate_announcements can edit/delete)
# • 100% professional, secure, and consistent with the rest of the application.

from app.utils.helpers import contains_censored_word
from app.models.db import get_db
import pymysql


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
REQUIRED_ROLES = ['Staff', 'Admin', 'Owner']


# ----------------------------------------------------------------------
# Text Processing
# ----------------------------------------------------------------------
def censor_text(text):
    """Apply server-side censorship to any text (title, content, comments.html).
    Currently passes through clean text (input validation already happened).
    Easy to upgrade later with word-masking or replacement logic.
    """
    if not text:
        return ''
    return text   # placeholder – ready for real censor logic when needed


# ----------------------------------------------------------------------
# Email Helpers
# ----------------------------------------------------------------------
def build_email_body(message, title, content):
    """Build clean email body for the /email/<ann_id> feature."""
    return f"{message}\n\n--- Announcement ---\nTitle: {title}\n\n{content}"


# ----------------------------------------------------------------------
# Comment Security Helper
# ----------------------------------------------------------------------
def is_comment_owner(comment_id: int, user_id: int) -> bool:
    """Return True if the user is the owner of this specific comment.
    Used to enforce that only the comment owner (or moderate_announcements permission) can edit/delete.
    """
    if not user_id:
        return False
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT user_id FROM announcement_comments WHERE id = %s", (comment_id,))
    row = cur.fetchone()
    return row is not None and row['user_id'] == user_id