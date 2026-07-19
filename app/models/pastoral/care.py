# app/models/pastoral/care.py
# Full path: WebChurchMan/app/models/pastoral/care.py
# File name: care.py
# Brief, detailed purpose:
#   All database operations related to the Pastoral Care module.
#   Handles confidential care requests for members AND non-members
#   (hospital visits, counseling, prayer needs, bereavement, etc.), including:
#     - Requests CRUD (create, read, update, delete)
#     - Pastor/staff assignments (add/remove)
#     - Chronological private notes (team-only visibility)
#   All data is confidential - visibility enforced by pastoral_required decorator in routes.
#   Routes handle audit logging (log_change) and censorship checks separately.
#   Uses DictCursor for consistent dict results with human-readable names.
#   Parameterized queries for MariaDB / PyMySQL safety.

import pymysql
from app.models.db import get_db


def ensure_care_non_member_columns():
    """
    Migrate pastoral_care_requests so non-members can be cared for:
      - member_id nullable
      - person_name / person_phone / person_email for guests/visitors
    Safe to call repeatedly.
    """
    db = get_db()
    cur = db.cursor()
    # Nullable member_id (drop NOT NULL if still present)
    try:
        cur.execute("""
            SELECT IS_NULLABLE, COLUMN_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'pastoral_care_requests'
              AND COLUMN_NAME = 'member_id'
        """)
        row = cur.fetchone()
        if row:
            is_nullable = row[0] if not isinstance(row, dict) else row.get('IS_NULLABLE')
            if str(is_nullable).upper() == 'NO':
                cur.execute("""
                    ALTER TABLE pastoral_care_requests
                    MODIFY COLUMN member_id INT UNSIGNED NULL
                """)
                db.commit()
    except Exception as exc:
        print(f'care migration member_id nullable: {exc}')
        try:
            db.rollback()
        except Exception:
            pass

    for col, coldef in (
        ('person_name', 'VARCHAR(160) NULL'),
        ('person_phone', 'VARCHAR(40) NULL'),
        ('person_email', 'VARCHAR(160) NULL'),
    ):
        try:
            cur.execute("""
                SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'pastoral_care_requests'
                  AND COLUMN_NAME = %s
            """, (col,))
            if not cur.fetchone():
                cur.execute(f'ALTER TABLE pastoral_care_requests ADD COLUMN {col} {coldef}')
                db.commit()
        except Exception as exc:
            print(f'care migration {col}: {exc}')
            try:
                db.rollback()
            except Exception:
                pass


def _person_display_sql():
    """COALESCE expression: member full name, else free-text person_name, else 'Unknown'."""
    return """
        COALESCE(
            NULLIF(TRIM(CONCAT(IFNULL(u.first_name, ''), ' ', IFNULL(u.last_name, ''))), ''),
            NULLIF(TRIM(pcr.person_name), ''),
            'Unknown person'
        )
    """


# ----------------------------------------------------------------------
# Pastoral Care Requests - Core CRUD
# ----------------------------------------------------------------------
def fetch_care_requests(*, status=None, urgency=None):
    """
    Fetch all pastoral care requests, optionally filtered by status or urgency.

    Includes person display name (member or non-member) and assigned pastors.
    """
    ensure_care_non_member_columns()
    if status == '':
        status = None
    if urgency == '':
        urgency = None
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    display = _person_display_sql()
    sql = f"""
        SELECT pcr.*,
               {display} AS member_name,
               {display} AS person_display,
               CASE WHEN pcr.member_id IS NULL THEN 0 ELSE 1 END AS is_member,
               (SELECT GROUP_CONCAT(CONCAT(u2.first_name, ' ', u2.last_name) SEPARATOR ', ')
                FROM pastoral_care_assignments pca
                JOIN users u2 ON pca.pastor_id = u2.id
                WHERE pca.request_id = pcr.id) AS assigned_pastors
        FROM pastoral_care_requests pcr
        LEFT JOIN users u ON pcr.member_id = u.id
    """
    params = []
    where_clauses = []

    if status:
        where_clauses.append("pcr.status = %s")
        params.append(status)

    if urgency:
        where_clauses.append("pcr.urgency = %s")
        params.append(urgency)

    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)

    sql += " ORDER BY pcr.created_at DESC"

    cur.execute(sql, params)
    return cur.fetchall()


# Backward-compatible alias (old callers); keyword-only - avoids positional arg bugs
get_care_requests = fetch_care_requests


def get_care_request_by_id(request_id):
    """Fetch a single care request by ID, including person display name."""
    ensure_care_non_member_columns()
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    display = _person_display_sql()
    cur.execute(f"""
        SELECT pcr.*,
               {display} AS member_name,
               {display} AS person_display,
               CASE WHEN pcr.member_id IS NULL THEN 0 ELSE 1 END AS is_member,
               u.email AS member_email,
               u.phone AS member_phone
        FROM pastoral_care_requests pcr
        LEFT JOIN users u ON pcr.member_id = u.id
        WHERE pcr.id = %s
    """, (request_id,))

    return cur.fetchone()


def create_care_request(data, user_id):
    """
    Create a new pastoral care request for a member or non-member.

    Args:
        data (dict): Must contain 'request_type', 'description';
                     either member_id OR person_name (non-member);
                     optional: title, urgency, status, person_phone, person_email
        user_id (int): ID of the submitting user (usually pastoral staff)

    Returns:
        int: Newly created request ID
    """
    ensure_care_non_member_columns()
    db = get_db()
    cur = db.cursor()

    member_id = data.get('member_id')
    if member_id in ('', 'None', None, 0, '0'):
        member_id = None
    else:
        try:
            member_id = int(member_id)
        except (TypeError, ValueError):
            member_id = None

    person_name = (data.get('person_name') or '').strip() or None
    person_phone = (data.get('person_phone') or '').strip() or None
    person_email = (data.get('person_email') or '').strip() or None

    if not member_id and not person_name:
        raise ValueError('Select a member or enter a non-member name.')

    # If member is selected, clear free-text person fields (name comes from users)
    if member_id:
        person_name = person_name  # optional nickname/alias still allowed
        # keep optional contact overrides empty unless provided

    cur.execute("""
        INSERT INTO pastoral_care_requests (
            member_id, person_name, person_phone, person_email,
            request_type, title, description,
            urgency, status, submitted_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        member_id,
        person_name,
        person_phone,
        person_email,
        data['request_type'],
        data.get('title'),
        data['description'],
        data.get('urgency', 'normal'),
        data.get('status', 'open'),
        user_id
    ))

    db.commit()
    return cur.lastrowid


def update_care_request(request_id, data):
    """
    Update fields on an existing care request (partial update allowed).
    Only keys present in data are written — never wipes unspecified columns.
    """
    ensure_care_non_member_columns()
    db = get_db()
    cur = db.cursor()

    sql = "UPDATE pastoral_care_requests SET "
    params = []
    updatable_fields = [
        'request_type', 'title', 'description', 'urgency', 'status',
        'member_id', 'person_name', 'person_phone', 'person_email',
    ]

    for field in updatable_fields:
        if field in data:
            val = data[field]
            if field == 'member_id' and val in ('', 'None', 0, '0'):
                val = None
            if field in ('person_name', 'person_phone', 'person_email') and isinstance(val, str):
                val = val.strip() or None
            sql += f"{field} = %s, "
            params.append(val)

    if not params:
        return

    sql += "updated_at = NOW() WHERE id = %s"
    params.append(request_id)

    cur.execute(sql, params)
    db.commit()


def delete_care_request(request_id):
    """
    Permanently delete a care request (and cascade-dependent notes/assignments via DB constraints).
    """
    db = get_db()
    cur = db.cursor()

    cur.execute("DELETE FROM pastoral_care_requests WHERE id = %s", (request_id,))
    db.commit()


# ----------------------------------------------------------------------
# Pastoral Care Assignments (Pastor/Staff)
# ----------------------------------------------------------------------
def get_care_assignments(request_id):
    """Fetch all pastor/staff assignments for a care request."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT pca.*,
               CONCAT(u.first_name, ' ', u.last_name) AS pastor_name
        FROM pastoral_care_assignments pca
        JOIN users u ON pca.pastor_id = u.id
        WHERE pca.request_id = %s
    """, (request_id,))

    return cur.fetchall()


def add_care_assignment(request_id, pastor_id, notes=None, is_primary=0):
    """Assign a pastor/staff member to a care request."""
    db = get_db()
    cur = db.cursor()

    cur.execute("""
        INSERT INTO pastoral_care_assignments (
            request_id, pastor_id, notes, is_primary
        ) VALUES (%s, %s, %s, %s)
    """, (request_id, pastor_id, notes, is_primary))

    db.commit()


def remove_care_assignment(assignment_id):
    """Remove a pastor/staff assignment from a care request."""
    db = get_db()
    cur = db.cursor()

    cur.execute("DELETE FROM pastoral_care_assignments WHERE id = %s", (assignment_id,))
    db.commit()


# ----------------------------------------------------------------------
# Pastoral Care Notes (Confidential Timeline)
# ----------------------------------------------------------------------
def get_care_notes(request_id):
    """Fetch all chronological notes for a care request (most recent first)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT pcn.*,
               CONCAT(u.first_name, ' ', u.last_name) AS author_name
        FROM pastoral_care_notes pcn
        JOIN users u ON pcn.user_id = u.id
        WHERE pcn.request_id = %s
        ORDER BY pcn.created_at DESC
    """, (request_id,))

    return cur.fetchall()


def add_care_note(request_id, user_id, note, is_private=1):
    """Add a confidential note to a care request (team-only visibility)."""
    db = get_db()
    cur = db.cursor()

    cur.execute("""
        INSERT INTO pastoral_care_notes (
            request_id, user_id, note, is_private
        ) VALUES (%s, %s, %s, %s)
    """, (request_id, user_id, note, is_private))

    db.commit()
