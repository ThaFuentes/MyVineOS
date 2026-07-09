# app/models/pastoral/care.py
# Full path: WebChurchMan/app/models/pastoral/care.py
# File name: care.py
# Brief, detailed purpose:
#   All database operations related to the Pastoral Care module.
#   Handles confidential care requests for members (hospital visits, counseling,
#   prayer needs, bereavement, etc.), including:
#     - Requests CRUD (create, read, update, delete)
#     - Pastor/staff assignments (add/remove)
#     - Chronological private notes (team-only visibility)
#   All data is confidential - visibility enforced by pastoral_required decorator in routes.
#   Routes handle audit logging (log_change) and censorship checks separately.
#   Uses DictCursor for consistent dict results with human-readable names.
#   Parameterized queries for MariaDB / PyMySQL safety.

import pymysql
from app.models.db import get_db


# ----------------------------------------------------------------------
# Pastoral Care Requests - Core CRUD
# ----------------------------------------------------------------------
def fetch_care_requests(*, status=None, urgency=None):
    """
    Fetch all pastoral care requests, optionally filtered by status or urgency.

    Includes member name and comma-separated list of assigned pastors.

    Args:
        status (str, optional): Filter by status (open, assigned, in_progress, followed_up, closed)
        urgency (str, optional): Filter by urgency (low, normal, high, urgent)

    Returns:
        list[dict]: Care requests with member_name and assigned_pastors
    """
    if status == '':
        status = None
    if urgency == '':
        urgency = None
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    sql = """
        SELECT pcr.*,
               CONCAT(u.first_name, ' ', u.last_name) AS member_name,
               (SELECT GROUP_CONCAT(CONCAT(u2.first_name, ' ', u2.last_name) SEPARATOR ', ')
                FROM pastoral_care_assignments pca
                JOIN users u2 ON pca.pastor_id = u2.id
                WHERE pca.request_id = pcr.id) AS assigned_pastors
        FROM pastoral_care_requests pcr
        JOIN users u ON pcr.member_id = u.id
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
    """
    Fetch a single care request by ID, including member name.

    Args:
        request_id (int): ID of the care request

    Returns:
        dict or None: Request details + member_name
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT pcr.*,
               CONCAT(u.first_name, ' ', u.last_name) AS member_name
        FROM pastoral_care_requests pcr
        JOIN users u ON pcr.member_id = u.id
        WHERE pcr.id = %s
    """, (request_id,))

    return cur.fetchone()


def create_care_request(data, user_id):
    """
    Create a new pastoral care request.

    Args:
        data (dict): Must contain 'member_id', 'request_type', 'description';
                     optional: title, urgency, status
        user_id (int): ID of the submitting user (usually pastoral staff)

    Returns:
        int: Newly created request ID
    """
    db = get_db()
    cur = db.cursor()

    cur.execute("""
        INSERT INTO pastoral_care_requests (
            member_id, request_type, title, description,
            urgency, status, submitted_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        data['member_id'],
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

    Args:
        request_id (int): ID of request to update
        data (dict): Fields to change (request_type, title, description, urgency, status)
    """
    db = get_db()
    cur = db.cursor()

    sql = "UPDATE pastoral_care_requests SET "
    params = []
    updatable_fields = ['request_type', 'title', 'description', 'urgency', 'status']

    for field in updatable_fields:
        if field in data:
            sql += f"{field} = %s, "
            params.append(data[field])

    sql += "updated_at = NOW() WHERE id = %s"
    params.append(request_id)

    cur.execute(sql, params)
    db.commit()


def delete_care_request(request_id):
    """
    Permanently delete a care request (and cascade-dependent notes/assignments via DB constraints).

    Args:
        request_id (int): ID of request to delete
    """
    db = get_db()
    cur = db.cursor()

    cur.execute("DELETE FROM pastoral_care_requests WHERE id = %s", (request_id,))
    db.commit()


# ----------------------------------------------------------------------
# Pastoral Care Assignments (Pastor/Staff)
# ----------------------------------------------------------------------
def get_care_assignments(request_id):
    """
    Fetch all pastor/staff assignments for a care request.

    Args:
        request_id (int): Care request ID

    Returns:
        list[dict]: Assignments with pastor_name
    """
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
    """
    Assign a pastor/staff member to a care request.

    Args:
        request_id (int): Care request ID
        pastor_id (int): User ID of the assigned pastor/staff
        notes (str, optional): Optional assignment notes
        is_primary (int): 1 if primary pastor, 0 otherwise (default 0)
    """
    db = get_db()
    cur = db.cursor()

    cur.execute("""
        INSERT INTO pastoral_care_assignments (
            request_id, pastor_id, notes, is_primary
        ) VALUES (%s, %s, %s, %s)
    """, (request_id, pastor_id, notes, is_primary))

    db.commit()


def remove_care_assignment(assignment_id):
    """
    Remove a pastor/staff assignment from a care request.

    Args:
        assignment_id (int): ID of the assignment to remove
    """
    db = get_db()
    cur = db.cursor()

    cur.execute("DELETE FROM pastoral_care_assignments WHERE id = %s", (assignment_id,))
    db.commit()


# ----------------------------------------------------------------------
# Pastoral Care Notes (Confidential Timeline)
# ----------------------------------------------------------------------
def get_care_notes(request_id):
    """
    Fetch all chronological notes for a care request (most recent first).

    Args:
        request_id (int): Care request ID

    Returns:
        list[dict]: Notes with author_name and timestamps
    """
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
    """
    Add a confidential note to a care request (team-only visibility).

    Args:
        request_id (int): Care request ID
        user_id (int): ID of the pastoral team member adding the note
        note (str): The note content
        is_private (int): 1 for private/team-only (default), 0 if ever needed public
    """
    db = get_db()
    cur = db.cursor()

    cur.execute("""
        INSERT INTO pastoral_care_notes (
            request_id, user_id, note, is_private
        ) VALUES (%s, %s, %s, %s)
    """, (request_id, user_id, note, is_private))

    db.commit()