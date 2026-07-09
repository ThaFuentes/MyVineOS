import pymysql
from app.models.db import get_db


def get_notes_for_setlist(setlist_id: int = None, template_id: int = None):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    if setlist_id:
        cur.execute("""
            SELECT n.*, CONCAT(u.first_name,' ',u.last_name) AS member_name, u.username
            FROM worship_member_notes n
            JOIN users u ON u.id = n.user_id
            WHERE n.setlist_id = %s
        """, (setlist_id,))
    elif template_id:
        cur.execute("""
            SELECT n.*, CONCAT(u.first_name,' ',u.last_name) AS member_name, u.username
            FROM worship_member_notes n
            JOIN users u ON u.id = n.user_id
            WHERE n.template_id = %s
        """, (template_id,))
    else:
        return []
    return cur.fetchall()


def save_member_note(user_id: int, note_text: str, created_by: int,
                     setlist_id: int = None, template_id: int = None):
    note_text = (note_text or '').strip()
    db = get_db()
    cur = db.cursor()
    if setlist_id:
        cur.execute("""
            INSERT INTO worship_member_notes (setlist_id, user_id, note_text, created_by)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE note_text = VALUES(note_text), created_by = VALUES(created_by)
        """, (setlist_id, user_id, note_text, created_by))
    elif template_id:
        cur.execute("""
            INSERT INTO worship_member_notes (template_id, user_id, note_text, created_by)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE note_text = VALUES(note_text), created_by = VALUES(created_by)
        """, (template_id, user_id, note_text, created_by))
    else:
        return
    db.commit()


def get_note_for_user(user_id: int, setlist_id: int = None, template_id: int = None):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    if setlist_id:
        cur.execute(
            "SELECT note_text FROM worship_member_notes WHERE setlist_id = %s AND user_id = %s",
            (setlist_id, user_id),
        )
    elif template_id:
        cur.execute(
            "SELECT note_text FROM worship_member_notes WHERE template_id = %s AND user_id = %s",
            (template_id, user_id),
        )
    else:
        return ''
    row = cur.fetchone()
    return (row.get('note_text') or '') if row else ''