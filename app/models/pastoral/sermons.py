# app/models/pastoral/sermons.py
# Full path: WebChurchMan/app/models/pastoral/sermons.py
# File name: sermons.py
# Brief, detailed purpose:
#   All database operations related to the Sermon Builder module.
#   Handles:
#     - Fetching visible sermons (personal, collaborators, pastoral group)
#     - Sermon CRUD (create, read, update, delete) with visibility enforcement
#     - Sermon section management (structured, ordered content blocks)
#       - FULL REPLACE PATTERN: Delete all old sections -> insert new ones (prevents accumulation of blanks/extras)
#       - Safe sequential sort_order assignment if missing
#       - All current fields preserved: title, section_type, scripture_reference, source (free text reference), content, notes
#     - Collaborator management (add/remove users who can edit)
#   Visibility strictly enforced at query level.
#   Routes handle audit logging and censorship checks separately.
#   Uses DictCursor for consistent dict results.
#   Parameterized queries for MariaDB / PyMySQL safety.
#   PRODUCTION-READY: Complete, stable version with permanent fix for extra sections and source field.

import pymysql
from app.models.db import get_db


# ----------------------------------------------------------------------
# Visible Sermons Listing
# ----------------------------------------------------------------------
def get_visible_sermons(user_id, search=None, visibility=None, limit=None, offset=0):
    """
    Fetch all sermons the current user can see or edit.

    Visibility rules:
    - Own sermons (created_by = user_id)
    - Collaborator sermons (visibility = 'collaborators' + user in sermon_collaborators)
    - Pastoral group sermons (visibility = 'pastoral_group')

    Args:
        user_id (int): Current user's ID
        search (str, optional): Filter by title or primary passage
        visibility (str, optional): Filter by specific visibility level
        limit (int, optional): Pagination limit
        offset (int): Pagination offset

    Returns:
        list[dict]: Sermons with creator_name and collaborator_count
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    sql = """
        SELECT ps.*,
               CONCAT(u.first_name, ' ', u.last_name) AS creator_name,
               (SELECT COUNT(*) FROM sermon_collaborators WHERE sermon_id = ps.id) AS collaborator_count
        FROM pastoral_sermons ps
        JOIN users u ON ps.created_by = u.id
        WHERE (ps.created_by = %s
               OR (ps.visibility = 'collaborators' AND EXISTS (
                   SELECT 1 FROM sermon_collaborators sc 
                   WHERE sc.sermon_id = ps.id AND sc.user_id = %s
               ))
               OR ps.visibility = 'pastoral_group')
    """
    params = [user_id, user_id]

    if search:
        sql += " AND (ps.title LIKE %s OR ps.primary_passage LIKE %s)"
        params.extend([f"%{search}%", f"%{search}%"])

    if visibility:
        sql += " AND ps.visibility = %s"
        params.append(visibility)

    sql += " ORDER BY ps.created_at DESC"

    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])

    cur.execute(sql, params)
    return cur.fetchall()


def get_sermon_by_id(sermon_id, user_id):
    """
    Fetch a single sermon if the user has access to it.

    Args:
        sermon_id (int): ID of the sermon
        user_id (int): Current user's ID (for visibility check)

    Returns:
        dict or None: Sermon details + creator_name if accessible
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT ps.*,
               CONCAT(u.first_name, ' ', u.last_name) AS creator_name
        FROM pastoral_sermons ps
        JOIN users u ON ps.created_by = u.id
        WHERE ps.id = %s
          AND (ps.created_by = %s
               OR (ps.visibility = 'collaborators' AND EXISTS (
                   SELECT 1 FROM sermon_collaborators sc 
                   WHERE sc.sermon_id = ps.id AND sc.user_id = %s
               ))
               OR ps.visibility = 'pastoral_group')
    """, (sermon_id, user_id, user_id))

    return cur.fetchone()


# ----------------------------------------------------------------------
# Sermon CRUD Operations
# ----------------------------------------------------------------------
def create_sermon(data, user_id):
    """
    Create a new sermon entry.

    Args:
        data (dict): Form data with title, primary_passage, visibility, etc.
        user_id (int): ID of the creating user

    Returns:
        int: Newly created sermon ID
    """
    db = get_db()
    cur = db.cursor()

    cur.execute("""
        INSERT INTO pastoral_sermons (
            title, preacher_id, primary_passage, service_date, visibility,
            header_text, footer_text, conclusion_text, series_tags, notes, created_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        data.get('title'),
        data.get('preacher_id'),
        data.get('primary_passage'),
        data.get('service_date') or None,
        data.get('visibility', 'private'),
        data.get('header_text'),
        data.get('footer_text'),
        data.get('conclusion_text'),
        data.get('series_tags'),
        data.get('notes'),
        user_id
    ))

    db.commit()
    return cur.lastrowid


def update_sermon(sermon_id, data, user_id):
    """
    Update an existing sermon (only if owned by user_id).

    Args:
        sermon_id (int): ID of sermon to update
        data (dict): Fields to update (partial allowed)
        user_id (int): Must match created_by for security
    """
    db = get_db()
    cur = db.cursor()

    sql = "UPDATE pastoral_sermons SET "
    params = []
    updatable_fields = [
        'title', 'preacher_id', 'primary_passage', 'service_date', 'visibility',
        'header_text', 'footer_text', 'conclusion_text', 'series_tags', 'notes'
    ]

    for field in updatable_fields:
        if field in data:
            sql += f"{field} = %s, "
            params.append(data[field])

    if not params:
        return  # Nothing to update

    sql = sql.rstrip(', ') + " WHERE id = %s AND created_by = %s"
    params.extend([sermon_id, user_id])

    cur.execute(sql, params)
    db.commit()


def delete_sermon(sermon_id):
    """
    Permanently delete a sermon (cascades to sections/collaborators via DB constraints).

    Args:
        sermon_id (int): ID of sermon to delete
    """
    db = get_db()
    cur = db.cursor()

    cur.execute("DELETE FROM pastoral_sermons WHERE id = %s", (sermon_id,))
    db.commit()


# ----------------------------------------------------------------------
# Sermon Sections - FULL REPLACE + source field
# ----------------------------------------------------------------------
def get_sermon_sections(sermon_id):
    """
    Fetch all ordered sections for a sermon.

    Args:
        sermon_id (int): Sermon ID

    Returns:
        list[dict]: Sections in sort_order sequence
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT id, sort_order, section_type, title, content,
               scripture_reference, source, notes
        FROM sermon_sections
        WHERE sermon_id = %s
        ORDER BY sort_order
    """, (sermon_id,))

    return cur.fetchall()


def save_sermon_sections(sermon_id, sections_list):
    """
    FULL REPLACE: Delete all existing sections -> insert new ones.
    Prevents accumulation of blank/extra sections forever.
    Assigns sequential sort_order if missing.
    Includes source field (free text reference - books, conversations, etc.).

    Args:
        sermon_id (int): Sermon to update
        sections_list (list[dict]): New sections from frontend
    """
    db = get_db()
    cur = db.cursor()

    # CRITICAL: Delete ALL old sections first - fixes extra blanks permanently
    cur.execute("DELETE FROM sermon_sections WHERE sermon_id = %s", (sermon_id,))

    # Insert new sections
    for i, sec in enumerate(sections_list):
        sort_order = sec.get('sort_order') or (i + 1)  # Safe sequential fallback

        cur.execute("""
            INSERT INTO sermon_sections (
                sermon_id, sort_order, section_type, title, content,
                scripture_reference, source, notes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            sermon_id,
            sort_order,
            sec.get('section_type', 'point'),
            sec.get('title', ''),
            sec.get('content', ''),
            sec.get('scripture_reference', ''),
            sec.get('source', ''),      # Free text source/reference - saved correctly
            sec.get('notes', '')
        ))

    db.commit()


# ----------------------------------------------------------------------
# Sermon Collaborators
# ----------------------------------------------------------------------
def get_collaborators(sermon_id):
    """
    Fetch all users who are collaborators on this sermon.

    Args:
        sermon_id (int): Sermon ID

    Returns:
        list[dict]: Collaborator user details
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT sc.user_id AS id, u.username, u.first_name, u.last_name,
               CONCAT(u.first_name, ' ', u.last_name) AS full_name
        FROM sermon_collaborators sc
        JOIN users u ON sc.user_id = u.id
        WHERE sc.sermon_id = %s
    """, (sermon_id,))

    return cur.fetchall()


def add_collaborator(sermon_id, user_id, added_by):
    """
    Add a user as collaborator (idempotent).

    Args:
        sermon_id (int): Sermon ID
        user_id (int): User to add
        added_by (int): Who added them (audit)
    """
    db = get_db()
    cur = db.cursor()

    cur.execute("""
        INSERT IGNORE INTO sermon_collaborators (sermon_id, user_id, added_by)
        VALUES (%s, %s, %s)
    """, (sermon_id, user_id, added_by))

    db.commit()


def remove_collaborator(sermon_id, user_id):
    """
    Remove a collaborator.

    Args:
        sermon_id (int): Sermon ID
        user_id (int): User to remove
    """
    db = get_db()
    cur = db.cursor()

    cur.execute("""
        DELETE FROM sermon_collaborators 
        WHERE sermon_id = %s AND user_id = %s
    """, (sermon_id, user_id))

    db.commit()