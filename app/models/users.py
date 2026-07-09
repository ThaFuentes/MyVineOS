# app/models/users.py
# Full path: WebChurchMan/app/models/users.py
# File name: users.py
# Brief, detailed purpose: Centralized user model and queries for the entire application.
#   Handles user lookups, profile updates, role management (approve/ban),
#   and complete family relationship lifecycle:
#     - Sending requests (spouse/parent/child/sibling)
#     - Pending incoming/outgoing lists
#     - Approval/rejection (mutual consent or admin override)
#     - Removal (by member or admin)
#     - Display logic with inverse relations for profile & directory views
#   All functions return dicts for template compatibility.
#   All write operations commit changes and log via log_change().
#   Includes owner_exists() for initial setup enforcement in app/__init__.py.
#   FIXED: All queries now use %s placeholders for MariaDB/PyMySQL compatibility.

import sqlite3
from typing import List, Dict, Optional
from werkzeug.security import generate_password_hash
from app.models.db import get_db
from app.models.log import log_change

# Inverse relation mapping – used to display correct label from perspective user's view
INVERSE_RELATIONS = {
    'spouse': 'spouse',
    'parent': 'child',
    'child': 'parent',
    'sibling': 'sibling',
    # Extendable in future: 'grandparent': 'grandchild', etc.
}

ALLOWED_RELATION_TYPES = list(INVERSE_RELATIONS.keys())


def owner_exists() -> bool:
    """
    Check if at least one user with role 'Owner' exists.
    Called by app/__init__.py to enforce initial owner registration.
    Returns True if an Owner exists, False otherwise.
    """
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT 1 FROM users WHERE role = 'Owner' LIMIT 1")
    return cur.fetchone() is not None


def _add_displayed_relation(relations: List[Dict], perspective_id: int) -> List[Dict]:
    """
    Helper: Add 'displayed_relation' key to each relationship from the perspective of user_id.
    For example: if perspective user is the 'parent', show 'child' to the relative.
    """
    for rel in relations:
        if rel['user_id'] == perspective_id:
            rel['displayed_relation'] = rel['relation_type']
        else:
            rel['displayed_relation'] = INVERSE_RELATIONS.get(rel['relation_type'], rel['relation_type'])
    return relations


# ----------------------------------------------------------------------
# Basic User Lookups
# ----------------------------------------------------------------------
def get_user_by_id(user_id: int) -> Optional[Dict]:
    import pymysql
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    return cur.fetchone()


def get_user_by_username(username: str) -> Optional[Dict]:
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    row = cur.fetchone()
    return dict(row) if row else None


def get_user_by_email(email: str) -> Optional[Dict]:
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    row = cur.fetchone()
    return dict(row) if row else None


def get_all_users(search_query: Optional[str] = None, exclude_roles: List[str] = None) -> List[Dict]:
    """
    Returns list of users, optionally filtered by search term.
    exclude_roles defaults to ['pending', 'banned'] for directory/public views.
    """
    db = get_db()
    cur = db.cursor()

    sql = "SELECT id, username, first_name, last_name, email, role, created_at FROM users"
    params = []

    if exclude_roles is None:
        exclude_roles = ['pending', 'banned']

    if exclude_roles:
        placeholders = ','.join(['%s'] * len(exclude_roles))
        sql += f" WHERE role NOT IN ({placeholders})"
        params.extend(exclude_roles)

    if search_query:
        like = f'%{search_query}%'
        sql += " AND (first_name LIKE %s OR last_name LIKE %s OR username LIKE %s OR email LIKE %s)"
        params.extend([like] * 4)

    sql += " ORDER BY last_name, first_name"
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


# ----------------------------------------------------------------------
# Profile & User Management
# ----------------------------------------------------------------------
def update_user_profile(
    user_id: int,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    address: Optional[str] = None,
    birthday: Optional[str] = None,
    show_birthday: Optional[int] = None,
    accepts_emails: Optional[int] = None,
    updated_by: Optional[int] = None
) -> None:
    """
    Update selected profile fields. Only provided fields are updated.
    Logs the action and commits changes.
    """
    db = get_db()
    cur = db.cursor()

    updates = []
    params = []

    field_map = {
        'first_name': first_name,
        'last_name': last_name,
        'email': email,
        'phone': phone,
        'address': address,
        'birthday': birthday,
        'show_birthday': show_birthday,
        'accepts_emails': accepts_emails
    }

    for col, val in field_map.items():
        if val is not None:
            updates.append(f"{col} = %s")
            params.append(val)

    if not updates:
        return

    sql = f"UPDATE users SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = %s"
    params.append(user_id)

    try:
        cur.execute(sql, params)
        db.commit()
        log_change(
            user_id=updated_by or user_id,
            action='update_profile',
            target_table='users',
            target_id=user_id,
            details="Updated profile fields"
        )
    except pymysql.IntegrityError as e:
        raise ValueError(f"Database conflict (likely duplicate email/username): {str(e)}")


def change_password(user_id: int, new_password: str, changed_by: Optional[int] = None) -> None:
    """
    Hash and update user password. Logs the action.
    """
    hashed = generate_password_hash(new_password)
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE users SET password = %s WHERE id = %s", (hashed, user_id))
    db.commit()
    log_change(
        user_id=changed_by or user_id,
        action='change_password',
        target_table='users',
        target_id=user_id,
        details="Password changed"
    )


def approve_user(user_id: int, approved_by: int, role: str = 'Member') -> None:
    """
    Approve a pending user and assign role (default 'Member').
    """
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        UPDATE users
        SET role = %s, needs_approval = 0, approved_by = %s, approved_at = CURRENT_TIMESTAMP
        WHERE id = %s AND role = 'pending'
    """, (role, approved_by, user_id))
    if cur.rowcount == 0:
        raise ValueError("User not found or already approved.")
    db.commit()
    log_change(approved_by, 'approve_user', target_table='users', target_id=user_id,
               details=f"Approved as {role}")


def ban_user(user_id: int, banned_by: int) -> None:
    """
    Ban a user (set role = 'banned').
    """
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE users SET role = 'banned' WHERE id = %s", (user_id,))
    db.commit()
    log_change(banned_by, 'ban_user', target_table='users', target_id=user_id)


def unban_user(user_id: int, unbanned_by: int, role: str = 'Member') -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE users SET role = %s WHERE id = %s AND role = 'banned'",
        (role, user_id),
    )
    if cur.rowcount == 0:
        raise ValueError('User is not banned.')
    db.commit()
    log_change(unbanned_by, 'unban_user', target_table='users', target_id=user_id,
               details=f'Restored role {role}')


def set_shadow_ban(user_id: int, shadow_banned: bool, actor_id: int) -> None:
    import pymysql
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    if shadow_banned:
        cur.execute(
            """
            UPDATE users
            SET is_shadow_banned = 1,
                shadow_banned_at = CURRENT_TIMESTAMP,
                shadow_banned_by = %s
            WHERE id = %s
            """,
            (actor_id, user_id),
        )
        action = 'shadow_ban_user'
        details = 'Account shadow banned — user can log in but only sees their own content; others cannot see theirs.'
    else:
        cur.execute(
            """
            UPDATE users
            SET is_shadow_banned = 0,
                shadow_banned_at = NULL,
                shadow_banned_by = NULL
            WHERE id = %s
            """,
            (user_id,),
        )
        action = 'unshadow_ban_user'
        details = 'Shadow ban removed.'
    db.commit()
    log_change(actor_id, action, target_table='users', target_id=user_id, details=details)


def set_account_login_lock(user_id: int, locked_until, actor_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        UPDATE users
        SET login_locked_until = %s, login_locked_by = %s
        WHERE id = %s
        """,
        (locked_until, actor_id, user_id),
    )
    db.commit()
    log_change(actor_id, 'account_login_lock', target_table='users', target_id=user_id,
               details=f'Login locked until {locked_until}')


def clear_account_login_lock(user_id: int, actor_id: int) -> None:
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        UPDATE users SET login_locked_until = NULL, login_locked_by = NULL
        WHERE id = %s
        """,
        (user_id,),
    )
    db.commit()
    log_change(actor_id, 'account_login_unlock', target_table='users', target_id=user_id,
               details='Account login lock cleared.')


# ----------------------------------------------------------------------
# Family Relationship Queries (Profile & Member Directory)
# ----------------------------------------------------------------------
def get_approved_family_members(user_id: int) -> List[Dict]:
    """
    Get all approved family members from user_id's perspective.
    Includes 'displayed_relation' (inverse if needed).
    """
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT
            CASE WHEN fr.user_id = %s THEN fr.relative_id ELSE fr.user_id END AS relative_id,
            u.first_name, u.last_name, u.email, u.username,
            fr.relation_type, fr.id AS relation_id
        FROM family_relations fr
        JOIN users u ON u.id = CASE WHEN fr.user_id = %s THEN fr.relative_id ELSE fr.user_id END
        WHERE (fr.user_id = %s OR fr.relative_id = %s) AND fr.status = 'approved'
        ORDER BY u.last_name, u.first_name
    """, (user_id, user_id, user_id, user_id))
    relations = [dict(row) for row in cur.fetchall()]
    return _add_displayed_relation(relations, user_id)


def get_family_count(user_id: int) -> int:
    """Quick count of approved family members for UI cards."""
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM family_relations
        WHERE (user_id = %s OR relative_id = %s) AND status = 'approved'
    """, (user_id, user_id))
    return cur.fetchone()['cnt']


def get_pending_incoming_requests(user_id: int) -> List[Dict]:
    """Pending requests where user_id is the receiver (needs approval)."""
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT fr.id AS relation_id, fr.user_id AS sender_id,
               fr.relation_type, u.first_name, u.last_name, u.email, u.username
        FROM family_relations fr
        JOIN users u ON u.id = fr.user_id
        WHERE fr.relative_id = %s AND fr.status = 'pending'
        ORDER BY fr.created_at DESC
    """, (user_id,))
    relations = [dict(row) for row in cur.fetchall()]
    return _add_displayed_relation(relations, user_id)


def get_pending_outgoing_requests(user_id: int) -> List[Dict]:
    """Pending requests sent by user_id (awaiting response)."""
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT fr.id AS relation_id, fr.relative_id AS receiver_id,
               fr.relation_type, u.first_name, u.last_name, u.email, u.username
        FROM family_relations fr
        JOIN users u ON u.id = fr.relative_id
        WHERE fr.user_id = %s AND fr.status = 'pending'
        ORDER BY fr.created_at DESC
    """, (user_id,))
    return [dict(row) for row in cur.fetchall()]


def search_potential_family_members(user_id: int, search_term: str = '') -> List[Dict]:
    """
    Search for users not already linked (approved or pending) to user_id.
    Used in family linking UI.
    """
    db = get_db()
    cur = db.cursor()
    like = f'%{search_term}%'
    cur.execute("""
        SELECT id, first_name, last_name, email, username
        FROM users
        WHERE id != %s
          AND (first_name LIKE %s OR last_name LIKE %s OR email LIKE %s OR username LIKE %s)
        ORDER BY last_name, first_name
        LIMIT 50
    """, (user_id, like, like, like, like))
    candidates = [dict(row) for row in cur.fetchall()]

    # Exclude already linked users
    linked_ids = set()
    for rel in get_approved_family_members(user_id):
        linked_ids.add(rel['relative_id'])
    for rel in get_pending_incoming_requests(user_id):
        linked_ids.add(rel['sender_id'])
    for rel in get_pending_outgoing_requests(user_id):
        linked_ids.add(rel['receiver_id'])

    return [c for c in candidates if c['id'] not in linked_ids]


# ----------------------------------------------------------------------
# Family Relationship Mutations
# ----------------------------------------------------------------------
def send_family_request(sender_id: int, receiver_id: int, relation_type: str) -> None:
    """
    Send a family relationship request.
    Clears any existing pending request in either direction first.
    """
    if sender_id == receiver_id:
        raise ValueError("Cannot request a relationship with yourself.")
    if relation_type not in ALLOWED_RELATION_TYPES:
        raise ValueError(f"Invalid relation type. Allowed: {', '.join(ALLOWED_RELATION_TYPES)}")

    db = get_db()
    cur = db.cursor()

    # Prevent duplicates / clean old requests
    cur.execute("""
        DELETE FROM family_relations
        WHERE (user_id = %s AND relative_id = %s)
           OR (user_id = %s AND relative_id = %s)
    """, (sender_id, receiver_id, receiver_id, sender_id))

    cur.execute("""
        INSERT INTO family_relations (user_id, relative_id, relation_type, status)
        VALUES (%s, %s, %s, 'pending')
    """, (sender_id, receiver_id, relation_type))

    db.commit()
    log_change(sender_id, 'send_family_request', target_table='family_relations',
               target_id=cur.lastrowid, details=f"Requested {relation_type} with user {receiver_id}")


def approve_family_request(request_id: int, approver_id: int) -> None:
    """
    Approve a pending family request (must be the receiver).
    """
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        UPDATE family_relations
        SET status = 'approved', responded_at = CURRENT_TIMESTAMP
        WHERE id = %s AND relative_id = %s AND status = 'pending'
    """, (request_id, approver_id))
    if cur.rowcount == 0:
        raise ValueError("Request not found, already processed, or not addressed to you.")
    db.commit()
    log_change(approver_id, 'approve_family_request', target_table='family_relations',
               target_id=request_id)


def reject_family_request(request_id: int, approver_id: int) -> None:
    """
    Reject a pending family request.
    """
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        UPDATE family_relations
        SET status = 'rejected', responded_at = CURRENT_TIMESTAMP
        WHERE id = %s AND relative_id = %s AND status = 'pending'
    """, (request_id, approver_id))
    if cur.rowcount == 0:
        raise ValueError("Request not found, already processed, or not addressed to you.")
    db.commit()
    log_change(approver_id, 'reject_family_request', target_table='family_relations',
               target_id=request_id)


def remove_family_relation(relation_id: int, actor_id: int) -> None:
    """
    Remove an approved family relation (by either party).
    """
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        DELETE FROM family_relations
        WHERE id = %s AND (user_id = %s OR relative_id = %s) AND status = 'approved'
    """, (relation_id, actor_id, actor_id))
    if cur.rowcount == 0:
        raise ValueError("Relation not found, not approved, or you are not part of it.")
    db.commit()
    log_change(actor_id, 'remove_family_relation', target_table='family_relations',
               target_id=relation_id)


# ----------------------------------------------------------------------
# Admin Override Functions (for Admin/Owner UI)
# ----------------------------------------------------------------------
def admin_approve_family_request(relation_id: int, admin_id: int) -> None:
    """
    Admin force-approve a family request (bypasses consent check).
    """
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        UPDATE family_relations
        SET status = 'approved', responded_at = CURRENT_TIMESTAMP, approved_by = %s
        WHERE id = %s
    """, (admin_id, relation_id))
    db.commit()
    log_change(admin_id, 'admin_approve_family', target_table='family_relations',
               target_id=relation_id)


def admin_force_remove_family_relation(relation_id: int, admin_id: int) -> None:
    """
    Admin force-remove any family relation.
    """
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM family_relations WHERE id = %s", (relation_id,))
    db.commit()
    log_change(admin_id, 'admin_remove_family', target_table='family_relations',
               target_id=relation_id)