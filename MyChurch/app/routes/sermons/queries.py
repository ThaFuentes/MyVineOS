# app/routes/sermons/queries.py
# Full path: WebChurchMan/app/routes/sermons/queries.py
# File name: queries.py
# Brief, detailed purpose: All database operations (SELECT, INSERT, UPDATE, DELETE) for the sermons blueprint.
# MariaDB/PyMySQL ready (%s placeholders). Every query from original sermons.py extracted here.
# All timestamps expect UTC values. Behavior 100% identical.

import pymysql.cursors
from app.models.db import get_db


def get_visible_sermons(user_id=None):
    """
    Fetch sermons based on visibility rules.
    - Guests (user_id=None): public only
    - Logged-in: public + private + own personal
    Returns list of sermon dicts (with uploader username joined).
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    if user_id:
        cur.execute("""
            SELECT s.id, s.title, s.notes, s.details, s.sermon_file,
                   s.external_link, s.uploaded_at, s.visibility,
                   u.username AS uploader, s.uploaded_by
            FROM sermons s
            LEFT JOIN users u ON s.uploaded_by = u.id
            WHERE s.visibility IN ('public', 'private')
               OR (s.visibility = 'personal' AND s.uploaded_by = %s)
            ORDER BY s.uploaded_at DESC
        """, (user_id,))
    else:
        cur.execute("""
            SELECT s.id, s.title, s.notes, s.details, s.sermon_file,
                   s.external_link, s.uploaded_at, s.visibility,
                   u.username AS uploader, s.uploaded_by
            FROM sermons s
            LEFT JOIN users u ON s.uploaded_by = u.id
            WHERE s.visibility = 'public'
            ORDER BY s.uploaded_at DESC
        """)

    return cur.fetchall()


def get_sermon_by_id(sermon_id):
    """Fetch single sermon by ID (for edit/delete/view checks)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT * FROM sermons WHERE id = %s
    """, (sermon_id,))
    return cur.fetchone()


def get_sermon_comments(sermon_id):
    """Fetch all comments.html for a sermon (with commenter username)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT sc.id, sc.user_id, sc.comment, sc.date_added,
               u.username AS commenter_username
        FROM sermon_comments sc
        LEFT JOIN users u ON sc.user_id = u.id
        WHERE sc.sermon_id = %s
        ORDER BY sc.date_added ASC
    """, (sermon_id,))
    return cur.fetchall()


def get_comment_owner(comment_id):
    """Get user_id of comment owner (for edit/delete authorization)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT user_id FROM sermon_comments WHERE id = %s", (comment_id,))
    row = cur.fetchone()
    return row['user_id'] if row else None


def create_sermon(title, notes_filename, details, sermon_filename, external_link, visibility, uploaded_by):
    """Insert new sermon and return its ID."""
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO sermons
        (title, notes, details, sermon_file, external_link, visibility, uploaded_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (title, notes_filename, details, sermon_filename, external_link or None, visibility, uploaded_by))
    db.commit()
    return cur.lastrowid


def update_sermon(sermon_id, title, details, external_link, visibility, notes_filename=None, sermon_filename=None):
    """Update sermon fields (only changed files are passed)."""
    db = get_db()
    cur = db.cursor()

    updates = ["title = %s", "details = %s", "external_link = %s", "visibility = %s"]
    params = [title, details, external_link or None, visibility]

    if notes_filename is not None:
        updates.append("notes = %s")
        params.append(notes_filename)

    if sermon_filename is not None:
        updates.append("sermon_file = %s")
        params.append(sermon_filename)

    params.append(sermon_id)
    sql = f"UPDATE sermons SET {', '.join(updates)} WHERE id = %s"

    cur.execute(sql, params)
    db.commit()


def delete_sermon(sermon_id):
    """Delete sermon record (files removed in views)."""
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM sermons WHERE id = %s", (sermon_id,))
    db.commit()


def create_sermon_comment(sermon_id, user_id, comment):
    """Add new comment."""
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO sermon_comments (sermon_id, user_id, comment)
        VALUES (%s, %s, %s)
    """, (sermon_id, user_id, comment))
    db.commit()


def update_sermon_comment(comment_id, new_comment):
    """Update existing comment text."""
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE sermon_comments SET comment = %s WHERE id = %s",
                (new_comment, comment_id))
    db.commit()


def delete_sermon_comment(comment_id):
    """Delete a comment."""
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM sermon_comments WHERE id = %s", (comment_id,))
    db.commit()


def get_sermon_file_owner(filename):
    """Find sermon that owns this file (for secure serving + visibility check)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT visibility, uploaded_by FROM sermons 
        WHERE notes = %s OR sermon_file = %s
    """, (filename, filename))
    return cur.fetchone()