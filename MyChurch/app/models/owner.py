# myvinechurchonline/app/models/owner.py
# Full path: myvinechurchonline/app/models/owner.py
# File name: owner.py
# Brief, detailed purpose: Provides a simple utility to check whether an Owner account exists.
# Aligned for MariaDB: Uses 'total' alias to handle DictCursor results and %s placeholders.

from app.models.db import get_db


def owner_exists() -> bool:
    """
    Check if at least one user with the role 'Owner' exists in the database.
    Returns False if the users table does not exist or if no owner is found.
    """
    db = get_db()
    # Ensure we use the cursor from the connection
    cur = db.cursor()
    try:
        # We use 'AS total' so the dictionary key is predictable across all environments
        cur.execute("SELECT COUNT(*) AS total FROM users WHERE role = %s", ('Owner',))
        row = cur.fetchone()

        # In DictCursor, row looks like {'total': 1}
        # In standard cursor, it would look like (1,)
        # This logic handles the dictionary returned by your MariaDB setup
        if row and 'total' in row:
            return row['total'] > 0
        return False

    except Exception as e:
        # During debugging, you can uncomment the line below to see table-missing errors:
        # print(f"DEBUG: owner_exists check failed: {e}")
        return False


if __name__ == "__main__":
    print("This module is intended for use within the Flask app. Run via main.py for testing.")