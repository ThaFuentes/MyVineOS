# app/models/log.py
# Full path: myvinechurchonline/app/models/log.py
# File name: log.py
# Brief, detailed purpose:
#   Centralizes audit logging for the entire application in MariaDB.
#   Provides a single, ultra-robust log_change() function used throughout the app.
#   - Accepts ANY combination of old/new/legacy parameter names without error.
#   - Standard columns: user_id, action, target_id (item_id), target_username (item_title), change_details (details/description)
#   - FULL REBUILD: maximum backward + forward compatibility, clean, type-hinted, documented.
#   - Errors printed but NEVER crash the app.
#   - Uses server-side UTC_TIMESTAMP() for perfect consistency.
#   - Added explicit rollback() in except for safety (even though single INSERT).

from app.models.db import get_db
from typing import Optional


def log_change(
    user_id: int,
    action: str,
    # Preferred modern parameters
    item_id: Optional[int] = None,
    item_title: Optional[str] = None,
    details: Optional[str] = None,
    # Explicit alias for any code still using 'description'
    description: Optional[str] = None,
    # Legacy parameter names (kept for 100% compatibility)
    target_id: Optional[int] = None,
    target_username: Optional[str] = None,
    target_table: Optional[str] = None,
    change_details: Optional[str] = None,
    **kwargs,
) -> None:
    """
    Record a significant user action in the change_records table.

    Fully backward and forward compatible - accepts every parameter name ever used:
        - Preferred: item_id, item_title, details
        - Alias: description -> maps to details
        - Legacy: target_id -> item_id, target_username -> item_title, change_details -> details

    The function resolves to the correct column values regardless of which name is used.
    Silently skips if user_id is falsy (anonymous actions).
    """
    if not user_id:
        return  # Skip anonymous actions

    # Resolve item_id (prefer modern -> legacy)
    resolved_item_id = item_id if item_id is not None else target_id

    # Resolve item_title/username
    resolved_item_title = item_title if item_title is not None else target_username

    # Resolve details (prefer details -> description -> change_details)
    resolved_details = details
    if resolved_details is None:
        resolved_details = description
    if resolved_details is None:
        resolved_details = change_details

    if target_table:
        prefix = f"[{target_table}]"
        if resolved_details:
            resolved_details = f"{prefix} {resolved_details}"
        elif not resolved_item_title:
            resolved_item_title = target_table

    db = get_db()
    cur = db.cursor()

    try:
        cur.execute("""
            INSERT INTO change_records 
            (user_id, action, target_id, target_username, change_details, timestamp)
            VALUES (%s, %s, %s, %s, %s, UTC_TIMESTAMP())
        """, (
            user_id,
            action,
            resolved_item_id,
            resolved_item_title or '',
            resolved_details or ''
        ))
        db.commit()
    except Exception as e:
        # Logging must never break the application
        db.rollback()  # Safety rollback even for single statement
        print(f"[AUDIT LOG ERROR] Failed to record change: {e}")
        print(f"    user_id={user_id} | action={action} | "
              f"item_id={resolved_item_id} | item_title={resolved_item_title} | "
              f"details={resolved_details}")


# Direct execution guard
if __name__ == "__main__":
    print("log.py - Audit logging module")
    print("Fully compatible with all existing calls (item_id, target_id, details, description, change_details, etc.).")
    print("Ready for use within the Flask application.")