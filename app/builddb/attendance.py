# myvinechurchonline/app/builddb/attendance.py
# Full path: WebChurchMan/app/builddb/attendance.py
# File name: attendance.py
# Brief, detailed purpose: Creates the attendance table for MariaDB.
# Tracks individual member check-ins for church services/events.
# Core fields: user_id, service_date (DATE for weekly services), check_in/check_out timestamps.
# Optional group_id for group check-ins (e.g., youth group attendance).
# notes TEXT for manual comments.html.
# checked_in_by for staff manual check-in.
# UNIQUE constraint prevents duplicate check-in for same user on same date.
# Searchable via members directory (per member history) and groups (group attendance reports).
# Safe schema evolution: adds missing columns via INFORMATION_SCHEMA.COLUMNS.
# Isolated module - called from builddb.py during DB initialization.
# All user/group FKs use UNSIGNED INT to match users.id/groups.id and fix errno 150.
# FULL REBUILD: Removed unnecessary import (check_password_hash belongs in routes, not migration).
# No Werkzeug imports - pure schema creation.

def create_tables(cursor):
    """
    Creates/updates the attendance table.
    Designed for both fresh DB creation and safe migration of existing databases.
    """

    # ----- ATTENDANCE TABLE -----
    # Simple daily check-in for services; extendable for events via future event_attendance table if needed.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id              INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
            user_id         INT UNSIGNED NOT NULL,
            group_id        INT UNSIGNED NULL,                 -- Optional group context (e.g., youth group service)
            service_date    DATE NOT NULL,                     -- Date of the service/event
            check_in        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            check_out       TIMESTAMP NULL,
            notes           TEXT,
            checked_in_by   INT UNSIGNED NULL,                 -- Staff who manually checked in (if not self)
            FOREIGN KEY (user_id)       REFERENCES users(id)   ON DELETE CASCADE,
            FOREIGN KEY (group_id)      REFERENCES groups(id)  ON DELETE SET NULL,
            FOREIGN KEY (checked_in_by) REFERENCES users(id)   ON DELETE SET NULL,
            UNIQUE (user_id, service_date)                     -- One check-in per user per day
        ) ENGINE=InnoDB;
    """)

    # Safe column additions for schema evolution
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance'
    """)
    existing_columns = [row[0] for row in cursor.fetchall()]

    columns_to_add = {
        'group_id':        "INT UNSIGNED NULL",
        'service_date':    "DATE NOT NULL",
        'check_in':        "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        'check_out':       "TIMESTAMP NULL",
        'notes':           "TEXT",
        'checked_in_by':   "INT UNSIGNED NULL"
    }

    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_columns:
            print(f"Migration: Adding missing column '{col_name}' to attendance table.")
            cursor.execute(f"ALTER TABLE attendance ADD COLUMN {col_name} {col_def}")

    # Indexes for common queries (try/except for migration safety)
    try:
        cursor.execute("CREATE INDEX idx_attendance_user_date ON attendance(user_id, service_date)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_attendance_group_date ON attendance(group_id, service_date)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_attendance_date ON attendance(service_date DESC)")
    except: pass
    try:
        cursor.execute("CREATE INDEX idx_attendance_check_in ON attendance(check_in DESC)")
    except: pass

