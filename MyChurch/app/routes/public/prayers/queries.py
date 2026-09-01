# MYVINECHURCH.ONLINE/app/routes/public/prayers/queries.py
# Database queries for the public Prayers section.

from app.models.db import get_db
import pymysql.cursors

_APPROVED_FILTER = "COALESCE(p.status, 'approved') = 'approved'"


def get_public_prayers():
    """Approved public prayers only - guest submissions stay hidden until reviewed."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute(f"""
        SELECT 
            p.id,
            p.title,
            p.description,
            p.date_posted,
            COALESCE(u.username, p.contributor_name, 'Anonymous') AS creator_name
        FROM prayers p
        LEFT JOIN users u ON COALESCE(p.created_by, p.user_id) = u.id
        WHERE p.visibility = 'public'
          AND {_APPROVED_FILTER}
        ORDER BY p.date_posted DESC
    """)
    prayers = cur.fetchall()
    cur.close()
    return prayers


def get_public_prayer(prayer_id):
    """Single approved public prayer for the detail page."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute(f"""
        SELECT 
            p.*,
            COALESCE(u.username, p.contributor_name, 'Anonymous') AS creator_name
        FROM prayers p
        LEFT JOIN users u ON COALESCE(p.created_by, p.user_id) = u.id
        WHERE p.id = %s 
          AND p.visibility = 'public'
          AND {_APPROVED_FILTER}
    """, (prayer_id,))

    prayer = cur.fetchone()
    cur.close()
    return prayer


def create_guest_prayer_request(title, description, contributor_name, ip_address):
    """Queue a visitor prayer request for staff review before it goes public."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO prayers
            (title, description, visibility, user_id, contributor_name, ip_address, status, date_posted)
            VALUES (%s, %s, 'public', NULL, %s, %s, 'pending', UTC_TIMESTAMP())
        """, (title, description, contributor_name, ip_address))
        db.commit()
        return cur.lastrowid
    except Exception:
        db.rollback()
        raise