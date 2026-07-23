# MYVINECHURCH.ONLINE/app/routes/public/prophecies/queries.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/prophecies/queries.py
# File name: queries.py
# Brief, detailed purpose: Reusable database query functions specifically for the public Prophecies section.
# Returns ONLY public records (with creator_name via LEFT JOIN). Clean, efficient, and feature-specific - no generic table-name passing.
# 100% rebuilt to match the public/events/queries.py and public/dreams/queries.py gold standard - uses p.* so all columns are available to views and templates.

from app.models.db import get_db
import pymysql.cursors


def get_public_prophecies(limit=None):
    """
    Retrieve publicly visible prophecies for the main public prophecies listing page.
    Ordered by most recent first. Supports optional limit for previews (dashboard).
    Uses p.* + creator_name exactly as the Events/Dreams gold standard.
    """
    _ensure_prophecy_approval_column()
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    sql = """
        SELECT 
            p.*,
            COALESCE(
                CONCAT(u.first_name, ' ', u.last_name),
                u.username,
                p.contributor_name,
                'Anonymous'
            ) AS creator_name
        FROM prophecies p
        LEFT JOIN users u ON COALESCE(p.created_by, p.user_id) = u.id
        WHERE p.visibility = 'public'
          AND COALESCE(p.is_approved, 1) = 1
        ORDER BY p.created_at DESC
    """

    if limit is not None:
        sql += " LIMIT %s"
        cur.execute(sql, (int(limit),))
    else:
        cur.execute(sql)

    prophecies = cur.fetchall()
    cur.close()
    return prophecies


def _ensure_prophecy_approval_column():
    """Guest submissions need is_approved; add if missing on older DBs."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'prophecies'
              AND COLUMN_NAME = 'is_approved'
        """)
        n = cur.fetchone()[0]
        if not n:
            cur.execute(
                "ALTER TABLE prophecies ADD COLUMN is_approved TINYINT(1) DEFAULT 1"
            )
            db.commit()
    except Exception as e:
        print(f'prophecies is_approved ensure: {e}')


def create_guest_prophecy(title, description, contributor_name, ip_address):
    """Visitor prophecy — public but not approved until staff reviews."""
    _ensure_prophecy_approval_column()
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO prophecies
            (title, description, visibility, user_id, contributor_name, ip_address, is_approved, created_at, updated_at)
            VALUES (%s, %s, 'public', NULL, %s, %s, 0, UTC_TIMESTAMP(), UTC_TIMESTAMP())
        """, (title, description, contributor_name, ip_address))
        db.commit()
        return cur.lastrowid
    except Exception:
        db.rollback()
        raise


def get_public_prophecy(prophecy_id):
    """
    Retrieve a single public prophecy by ID for the detail page (view_prophecy.html).
    Includes creator_name and all fields needed for the template.
    """
    _ensure_prophecy_approval_column()
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT 
            p.*,
            COALESCE(
                CONCAT(u.first_name, ' ', u.last_name),
                u.username,
                p.contributor_name,
                'Anonymous'
            ) AS creator_name
        FROM prophecies p
        LEFT JOIN users u ON COALESCE(p.created_by, p.user_id) = u.id
        WHERE p.id = %s 
          AND p.visibility = 'public'
          AND COALESCE(p.is_approved, 1) = 1
    """, (prophecy_id,))

    prophecy = cur.fetchone()
    cur.close()
    return prophecy


