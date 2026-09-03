# MYVINECHURCH.ONLINE/app/routes/public/prophecies/queries.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/prophecies/queries.py
# File name: queries.py
# Brief, detailed purpose: Reusable database query functions specifically for the public Prophecies section.
# Returns ONLY public records (with creator_name via LEFT JOIN). Clean, efficient, and feature-specific - no generic table-name passing.
# 100% rebuilt to match the public/events/queries.py and public/dreams/queries.py gold standard - uses p.* so all columns are available to views and templates.

from app.models.db import get_db
import pymysql.cursors


def _user_join_expr(cols):
    if 'created_by' in cols and 'user_id' in cols:
        return "COALESCE(p.created_by, p.user_id)"
    if 'created_by' in cols:
        return "p.created_by"
    return "p.user_id"


def _approval_clause(cols):
    if 'is_approved' in cols:
        return " AND COALESCE(p.is_approved, 1) = 1"
    return ""


def get_public_prophecies(limit=None):
    """Public prophecies only. Tolerates older schemas missing created_by / is_approved."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cols = _prophecy_columns()
    join_on = _user_join_expr(cols)
    name_fallback = "p.contributor_name," if 'contributor_name' in cols else ""

    sql = f"""
        SELECT
            p.*,
            COALESCE(
                CONCAT(u.first_name, ' ', u.last_name),
                u.username,
                {name_fallback}
                'Anonymous'
            ) AS creator_name
        FROM prophecies p
        LEFT JOIN users u ON {join_on} = u.id
        WHERE p.visibility = 'public'
          {_approval_clause(cols)}
          AND COALESCE(p.moderation_hidden, 0) = 0
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


def _prophecy_columns():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'prophecies'
    """)
    names = set()
    for row in cur.fetchall() or []:
        if isinstance(row, dict):
            names.add(row.get('COLUMN_NAME') or row.get('column_name'))
        else:
            names.add(row[0])
    return {n for n in names if n}


def _ensure_prophecy_approval_column():
    """Guest submissions need is_approved; add if missing on older DBs."""
    try:
        cols = _prophecy_columns()
        if 'is_approved' in cols:
            return True
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "ALTER TABLE prophecies ADD COLUMN is_approved TINYINT(1) NOT NULL DEFAULT 1"
        )
        db.commit()
        return True
    except Exception as e:
        print(f'prophecies is_approved ensure: {e}')
        return False


def _approval_sql():
    if _ensure_prophecy_approval_column():
        return " AND COALESCE(p.is_approved, 1) = 1"
    return ""


def create_guest_prophecy(title, description, contributor_name, ip_address):
    """Visitor prophecy — public but not approved until staff reviews."""
    db = get_db()
    cur = db.cursor()
    try:
        if _ensure_prophecy_approval_column():
            cur.execute("""
                INSERT INTO prophecies
                (title, description, visibility, user_id, contributor_name, ip_address, is_approved, created_at, updated_at)
                VALUES (%s, %s, 'public', NULL, %s, %s, 0, UTC_TIMESTAMP(), UTC_TIMESTAMP())
            """, (title, description, contributor_name, ip_address))
        else:
            cur.execute("""
                INSERT INTO prophecies
                (title, description, visibility, user_id, contributor_name, ip_address, created_at, updated_at)
                VALUES (%s, %s, 'public', NULL, %s, %s, UTC_TIMESTAMP(), UTC_TIMESTAMP())
            """, (title, description, contributor_name, ip_address))
        db.commit()
        return cur.lastrowid
    except Exception:
        db.rollback()
        raise


def get_public_prophecy(prophecy_id):
    """Single public prophecy. Tolerates older schemas missing created_by / is_approved."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cols = _prophecy_columns()
    join_on = _user_join_expr(cols)
    name_fallback = "p.contributor_name," if 'contributor_name' in cols else ""

    cur.execute(f"""
        SELECT
            p.*,
            COALESCE(
                CONCAT(u.first_name, ' ', u.last_name),
                u.username,
                {name_fallback}
                'Anonymous'
            ) AS creator_name
        FROM prophecies p
        LEFT JOIN users u ON {join_on} = u.id
        WHERE p.id = %s
          AND p.visibility = 'public'
          {_approval_clause(cols)}
          AND COALESCE(p.moderation_hidden, 0) = 0
    """, (prophecy_id,))

    prophecy = cur.fetchone()
    cur.close()
    return prophecy


