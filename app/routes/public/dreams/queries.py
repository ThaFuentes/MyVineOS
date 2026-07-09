# MYVINECHURCH.ONLINE/app/routes/public/dreams/queries.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/dreams/queries.py
# File name: queries.py
# Brief, detailed purpose: Reusable database query functions specifically for the public Dreams & Visions section.
# Returns ONLY public + approved records (with creator_name via LEFT JOIN).
# 100% rebuilt to match the public/events/queries.py gold standard - uses d.* so all columns are available to views and templates.

from app.models.db import get_db
import pymysql.cursors


def get_public_dreams(limit=None):
    """
    Retrieve publicly visible and approved dreams for the main public dreams listing page.
    Ordered by most recent first. Supports optional limit for previews (dashboard).
    Uses d.* + creator_name exactly as the Events gold standard.
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    sql = """
        SELECT 
            d.*,
            COALESCE(
                CONCAT(u.first_name, ' ', u.last_name),
                u.username,
                d.contributor_name,
                'Anonymous'
            ) AS creator_name
        FROM dreams d
        LEFT JOIN users u ON COALESCE(d.created_by, d.user_id) = u.id
        WHERE d.visibility = 'public'
          AND COALESCE(d.is_approved, 1) = 1   -- legacy dreams without is_approved still show
        ORDER BY d.date_posted DESC
    """

    if limit is not None:
        sql += " LIMIT %s"
        cur.execute(sql, (int(limit),))
    else:
        cur.execute(sql)

    dreams = cur.fetchall()
    cur.close()
    return dreams


def get_public_dream(dream_id):
    """
    Retrieve a single public + approved dream by ID for the detail page (view_dream.html).
    Includes creator_name and all fields needed for the template.
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT 
            d.*,
            COALESCE(
                CONCAT(u.first_name, ' ', u.last_name),
                u.username,
                d.contributor_name,
                'Anonymous'
            ) AS creator_name
        FROM dreams d
        LEFT JOIN users u ON COALESCE(d.created_by, d.user_id) = u.id
        WHERE d.id = %s 
          AND d.visibility = 'public'
          AND COALESCE(d.is_approved, 1) = 1
    """, (dream_id,))

    dream = cur.fetchone()
    cur.close()
    return dream


