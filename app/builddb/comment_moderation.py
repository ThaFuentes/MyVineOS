# app/builddb/comment_moderation.py
# Adds moderation columns to all public comment tables and prayers_added responses.


MODERATION_COLUMNS = {
    'shadowed': 'TINYINT(1) DEFAULT 0',
    'shadow_ip': 'VARCHAR(45) NULL',
    'shadow_user_id': 'INT UNSIGNED NULL',
    'moderated': 'TINYINT(1) DEFAULT 1',
    'moderated_by': 'INT UNSIGNED NULL',
    'moderated_at': 'TIMESTAMP NULL',
    'edited_by_moderator': 'TINYINT(1) DEFAULT 0',
    'moderator_edited_at': 'TIMESTAMP NULL',
}

COMMENT_TABLES = (
    'event_comments',
    'sermon_comments',
    'dream_comments',
    'prophecy_comments',
    'announcement_comments',
    'prayers_added',
)


def _table_exists(cursor, table_name):
    cursor.execute("""
        SELECT 1 FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
    """, (table_name,))
    return cursor.fetchone() is not None


def _migrate_table(cursor, table_name):
    if not _table_exists(cursor, table_name):
        print(f"  Skipping {table_name} (table not created yet)")
        return

    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
    """, (table_name,))
    existing = {row[0] for row in cursor.fetchall()}

    for col, definition in MODERATION_COLUMNS.items():
        if col not in existing:
            print(f"  Migration: Adding '{col}' to {table_name}")
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} {definition}")

    try:
        cursor.execute(f"CREATE INDEX idx_{table_name}_shadowed ON {table_name}(shadowed)")
    except Exception:
        pass


def create_tables(cursor):
    """Add moderation columns to every comment/response table."""
    print("comment_moderation.py: migrating comment tables...")
    for table in COMMENT_TABLES:
        _migrate_table(cursor, table)
    print("comment_moderation.py migration complete.")