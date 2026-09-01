# app/routes/profile/queries.py
# Full path: MyVineChurch/app/routes/profile/queries.py
# File name: queries.py
# Brief, detailed purpose: All database queries and operations for the Profile module.
# - Pure data-access layer - no Flask routes, no templates, no flash messages.
# - Every SELECT/INSERT/UPDATE/DELETE from the original profile.py is now here.
# - 100% original behavior preserved (profile load, family requests, search, suggested users, approve/reject/remove).
# - 100% MariaDB/pymysql compatible (%s placeholders, DictCursor).

import pymysql
from app.models.db import get_db


# ----------------------------------------------------------------------
# Profile Load
# ----------------------------------------------------------------------
def get_user_profile(user_id):
    """Return full user profile data including new privacy preferences."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    return cur.fetchone()


# ----------------------------------------------------------------------
# Family Management
# ----------------------------------------------------------------------
def get_pending_incoming_requests(user_id):
    """Return pending family requests sent TO this user."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute('''
        SELECT fr.id, CONCAT(u.first_name, ' ', u.last_name) AS name, fr.relation_type
        FROM family_relations fr
        JOIN users u ON fr.user_id = u.id
        WHERE fr.relative_id = %s AND fr.status = 'pending'
        ORDER BY fr.requested_at DESC
    ''', (user_id,))
    return cur.fetchall()


def get_approved_family(user_id):
    """Return all approved family relationships (both directions)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute('''
        SELECT fr.id,
               CASE
                 WHEN fr.user_id = %s THEN CONCAT(u2.first_name, ' ', u2.last_name)
                 ELSE CONCAT(u1.first_name, ' ', u1.last_name)
               END AS name,
               fr.relation_type
        FROM family_relations fr
        LEFT JOIN users u1 ON fr.user_id = u1.id
        LEFT JOIN users u2 ON fr.relative_id = u2.id
        WHERE fr.status = 'approved' AND %s IN (fr.user_id, fr.relative_id)
        ORDER BY name
    ''', (user_id, user_id))
    return cur.fetchall()


def get_suggested_family(user_id):
    """Return suggested family members (same last name, no existing relation, respects allow_family_search)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute('''
        SELECT u.id, u.first_name, u.last_name
        FROM users u
        WHERE LOWER(u.last_name) = LOWER((SELECT last_name FROM users WHERE id = %s))
          AND u.id != %s
          AND u.allow_family_search = 1
          AND u.id NOT IN (
              SELECT relative_id FROM family_relations WHERE user_id = %s AND status IN ('pending', 'approved')
              UNION
              SELECT user_id FROM family_relations WHERE relative_id = %s AND status IN ('pending', 'approved')
          )
        ORDER BY u.first_name
    ''', (user_id, user_id, user_id, user_id))
    return cur.fetchall()


def search_family_members(user_id, search_query):
    """Search for potential family members (respects allow_family_search)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    like_param = f'%{search_query}%'
    cur.execute('''
        SELECT id, first_name, last_name
        FROM users
        WHERE (LOWER(first_name) LIKE %s OR LOWER(last_name) LIKE %s OR LOWER(email) LIKE %s)
          AND id != %s
          AND allow_family_search = 1
          AND id NOT IN (
              SELECT relative_id FROM family_relations WHERE user_id = %s AND status IN ('pending', 'approved')
              UNION
              SELECT user_id FROM family_relations WHERE relative_id = %s AND status IN ('pending', 'approved')
          )
    ''', (like_param, like_param, like_param, user_id, user_id, user_id))
    return cur.fetchall()


# ----------------------------------------------------------------------
# Family Request Actions
# ----------------------------------------------------------------------
def create_family_request(user_id, relative_id, relation_type):
    """Create a new pending family request."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute('''
            INSERT INTO family_relations (user_id, relative_id, relation_type, status)
            VALUES (%s, %s, %s, 'pending')
        ''', (user_id, relative_id, relation_type))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def approve_family_request(fr_id, user_id):
    """Approve a pending family request."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute('''
            UPDATE family_relations
            SET status = 'approved', responded_at = CURRENT_TIMESTAMP, approved_by = %s
            WHERE id = %s AND relative_id = %s AND status = 'pending'
        ''', (user_id, fr_id, user_id))
        db.commit()
        return cur.rowcount > 0
    except Exception:
        db.rollback()
        raise


def reject_family_request(fr_id, user_id):
    """Reject a pending family request."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute('''
            UPDATE family_relations
            SET status = 'rejected', responded_at = CURRENT_TIMESTAMP
            WHERE id = %s AND relative_id = %s AND status = 'pending'
        ''', (fr_id, user_id))
        db.commit()
        return cur.rowcount > 0
    except Exception:
        db.rollback()
        raise


def remove_family_relationship(fr_id, user_id):
    """Remove an approved family relationship."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute('''
            DELETE FROM family_relations
            WHERE id = %s AND status = 'approved'
              AND (user_id = %s OR relative_id = %s)
        ''', (fr_id, user_id, user_id))
        db.commit()
        return cur.rowcount > 0
    except Exception:
        db.rollback()
        raise


# ----------------------------------------------------------------------
# Profile Update
# ----------------------------------------------------------------------
def update_user_profile(user_id, data):
    """Update user profile including new privacy preferences and optional PIN."""
    db = get_db()
    cur = db.cursor()
    # Normalize birthday for MySQL DATE (empty string is invalid)
    birthday = data.get('birthday') or None
    if isinstance(birthday, str) and not birthday.strip():
        birthday = None
    try:
        cur.execute('''
            UPDATE users
            SET first_name = %s, last_name = %s, email = %s, phone = %s, address = %s,
                birthday = %s, show_birthday = %s,
                allow_proxy_checkin = %s, allow_group_add = %s, allow_family_search = %s,
                checkin_pin = %s
            WHERE id = %s
        ''', (data['first_name'], data['last_name'], data['email'], data['phone'],
              data['address'], birthday, data['show_birthday'],
              data['allow_proxy_checkin'], data['allow_group_add'], data['allow_family_search'],
              data.get('checkin_pin'), user_id))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def update_user_password(user_id, new_hashed_password):
    """Update user password hash. Ensures column can store modern Werkzeug hashes."""
    db = get_db()
    cur = db.cursor()
    try:
        # Some older DBs used VARCHAR(64)/VARCHAR(128) which truncates scrypt/pbkdf2 hashes
        try:
            cur.execute("SHOW COLUMNS FROM users LIKE 'password'")
            col = cur.fetchone()
            col_type = ''
            if col:
                # tuple or dict
                col_type = (col[1] if not isinstance(col, dict) else col.get('Type') or '').lower()
            if col_type.startswith('varchar') and 'text' not in col_type:
                cur.execute("ALTER TABLE users MODIFY COLUMN password TEXT NOT NULL")
        except Exception:
            pass

        cur.execute('UPDATE users SET password = %s WHERE id = %s', (new_hashed_password, user_id))
        if cur.rowcount < 0:
            pass
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise