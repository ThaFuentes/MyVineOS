# app/routes/members/queries.py
# Full path: MyVineChurch/app/routes/members/queries.py
# File name: queries.py
# Brief, detailed purpose: All database queries and operations for the Members module.
# - Pure data-access layer – no Flask routes, no templates, no flash messages.
# - Every SELECT/INSERT/UPDATE/DELETE from the original members.py is now here.
# - 100% original behavior preserved (directory with family relations, add/edit, delete, export, email roster, group assignment, role checks).
# - 100% MariaDB/pymysql compatible (%s placeholders, DictCursor).

import pymysql
from app.models.db import get_db


# ----------------------------------------------------------------------
# Directory
# ----------------------------------------------------------------------
def get_members_directory(search_term=''):
    """Return all members with family relations for expandable rows."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    sql = """
        SELECT id, first_name, last_name, email, phone, address, username, role,
               accepts_emails, birthday, show_birthday,
               COALESCE(email_verified, 0) AS email_verified,
               COALESCE(is_shadow_banned, 0) AS is_shadow_banned,
               login_locked_until, shadow_banned_at
        FROM users
    """
    params = []

    if search_term:
        like_param = f'%{search_term}%'
        sql += """ WHERE first_name LIKE %s OR last_name LIKE %s OR email LIKE %s
                   OR phone LIKE %s OR address LIKE %s OR username LIKE %s"""
        params = [like_param] * 6

    sql += " ORDER BY last_name, first_name"
    cur.execute(sql, params)
    members = cur.fetchall()

    for member in members:
        cur.execute("""
            SELECT u.id, u.first_name, u.last_name, fr.relation_type
            FROM family_relations fr
            JOIN users u ON (fr.relative_id = u.id AND fr.user_id = %s)
                 OR (fr.user_id = u.id AND fr.relative_id = %s)
            WHERE (fr.user_id = %s OR fr.relative_id = %s)
              AND fr.status = 'approved'
            ORDER BY u.last_name, u.first_name
        """, (member['id'], member['id'], member['id'], member['id']))
        member['family_members'] = cur.fetchall()

    return members


# ----------------------------------------------------------------------
# Add/Edit Member
# ----------------------------------------------------------------------
def create_member(data):
    """Insert new member and return new id."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""INSERT INTO users
                       (username, password, first_name, last_name, email, phone, address,
                        birthday, show_birthday, role, accepts_emails, created_by)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (data['username'], data['password'], data['first_name'], data['last_name'],
                     data['email'], data['phone'], data['address'], data['birthday'],
                     data['show_birthday'], data['role'], data['accepts_emails'], data['created_by']))
        db.commit()
        return cur.lastrowid
    except Exception:
        db.rollback()
        raise


def update_member(member_id, data):
    """Update existing member."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""UPDATE users SET
                       first_name=%s, last_name=%s, email=%s, phone=%s, address=%s,
                       birthday=%s, show_birthday=%s, role=%s, accepts_emails=%s
                       WHERE id=%s""",
                    (data['first_name'], data['last_name'], data['email'], data['phone'],
                     data['address'], data['birthday'], data['show_birthday'],
                     data['role'], data['accepts_emails'], member_id))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def get_member_by_id(member_id):
    """Return single member or None."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM users WHERE id = %s", (member_id,))
    return cur.fetchone()


def get_member_for_export():
    """Return all members for DOCX export."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT first_name, last_name, phone, email, address, role, username,
               accepts_emails, birthday, show_birthday
        FROM users ORDER BY last_name, first_name
    """)
    return cur.fetchall()


# ----------------------------------------------------------------------
# Delete Member
# ----------------------------------------------------------------------
def _reassign_or_null_user_refs(cur, member_id: int, reassign_to: int | None):
    """
    Clear or reassign foreign-key references so DELETE FROM users can succeed.
    RESTRICT / NOT NULL columns are reassigned to reassign_to (usually the actor or an Owner).
    """
    uid = int(member_id)
    # Prefer a real user id for NOT NULL columns
    fallback = reassign_to
    if not fallback:
        cur.execute("SELECT id FROM users WHERE role = 'Owner' AND id != %s LIMIT 1", (uid,))
        row = cur.fetchone()
        if row:
            fallback = row[0] if not isinstance(row, dict) else row['id']
    if not fallback:
        cur.execute("SELECT id FROM users WHERE id != %s ORDER BY id LIMIT 1", (uid,))
        row = cur.fetchone()
        if row:
            fallback = row[0] if not isinstance(row, dict) else row['id']

    # Rows that only exist as membership/session data — safe to delete
    for sql in (
        "DELETE FROM user_groups WHERE user_id = %s",
        "DELETE FROM user_widgets WHERE user_id = %s",
        "DELETE FROM user_help_pins WHERE user_id = %s",
        "DELETE FROM member_roles WHERE user_id = %s",
        "DELETE FROM ticket_managers WHERE user_id = %s",
        "DELETE FROM pastoral_group_members WHERE user_id = %s",
        "DELETE FROM sermon_collaborators WHERE user_id = %s",
        "DELETE FROM family_relations WHERE user_id = %s OR relative_id = %s",
        "DELETE FROM attendance WHERE user_id = %s",
        "DELETE FROM kiosk_sessions WHERE created_by = %s",
        "DELETE FROM recurring_bill_assignments WHERE user_id = %s",
        "DELETE FROM worship_default_assignments WHERE user_id = %s",
        "DELETE FROM worship_setlist_assignments WHERE user_id = %s",
        "DELETE FROM worship_template_assignments WHERE user_id = %s",
        "DELETE FROM worship_weekly_template_assignments WHERE user_id = %s",
        "DELETE FROM service_plan_assignments WHERE user_id = %s",
        "DELETE FROM service_template_assignments WHERE user_id = %s",
        "DELETE FROM pastoral_care_assignments WHERE pastor_id = %s",
        "DELETE FROM pastoral_care_notes WHERE user_id = %s",
        "DELETE FROM pastoral_care_requests WHERE member_id = %s",
        "DELETE FROM sermon_edits WHERE user_id = %s",
        "DELETE FROM worship_member_notes WHERE user_id = %s",
    ):
        try:
            # family_relations needs two binds
            if sql.count('%s') == 2:
                cur.execute(sql, (uid, uid))
            else:
                cur.execute(sql, (uid,))
        except Exception:
            pass  # table may not exist on older DBs

    # RESTRICT / NOT NULL: reassign ownership so delete can proceed
    if fallback:
        for sql in (
            "UPDATE inventory_transactions SET user_id = %s WHERE user_id = %s",
            "UPDATE sermons SET uploaded_by = %s WHERE uploaded_by = %s",
            "UPDATE pastoral_sermons SET created_by = %s WHERE created_by = %s",
            "UPDATE tickets SET created_by = %s WHERE created_by = %s",
            "UPDATE service_plans SET created_by = %s WHERE created_by = %s",
            "UPDATE service_templates SET created_by = %s WHERE created_by = %s",
        ):
            try:
                cur.execute(sql, (fallback, uid))
            except Exception:
                pass

    # Nullable audit / author fields — SET NULL when possible
    for table, col in (
        ('donations', 'user_id'),
        ('inventory_transactions', 'user_id'),
        ('sermons', 'uploaded_by'),
        ('sermons', 'created_by'),
        ('sermons', 'updated_by'),
        ('announcements', 'user_id'),
        ('announcements', 'created_by'),
        ('announcements', 'updated_by'),
        ('dreams', 'user_id'),
        ('prayers', 'user_id'),
        ('prophecies', 'user_id'),
        ('events', 'created_by'),
        ('change_records', 'user_id'),
        ('tickets', 'assigned_to'),
        ('users', 'approved_by'),
        ('users', 'created_by'),
        ('user_groups', 'assigned_by'),
    ):
        try:
            cur.execute(f"UPDATE {table} SET {col} = NULL WHERE {col} = %s", (uid,))
        except Exception:
            # NOT NULL column — try reassign
            if fallback:
                try:
                    cur.execute(
                        f"UPDATE {table} SET {col} = %s WHERE {col} = %s",
                        (fallback, uid),
                    )
                except Exception:
                    pass


def delete_member(member_id, reassign_to: int | None = None):
    """
    Permanently delete a user after clearing FK blockers.
    reassign_to: user id that inherits NOT NULL ownership (actor or Owner).
    """
    db = get_db()
    cur = db.cursor()
    try:
        _reassign_or_null_user_refs(cur, member_id, reassign_to)
        cur.execute('DELETE FROM users WHERE id = %s', (member_id,))
        if cur.rowcount < 1:
            db.rollback()
            raise ValueError('User not found or already deleted.')
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


# ----------------------------------------------------------------------
# Groups Assignment
# ----------------------------------------------------------------------
def assign_groups_to_member(user_id, group_ids, assigned_by):
    """Replace all group assignments for a member."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM user_groups WHERE user_id = %s", (user_id,))
        for gid in group_ids:
            cur.execute("""INSERT INTO user_groups (user_id, group_id, role_in_group, assigned_by)
                           VALUES (%s, %s, 'member', %s)""",
                        (user_id, gid, assigned_by))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


# ----------------------------------------------------------------------
# Email Roster
# ----------------------------------------------------------------------
def get_email_roster():
    """Active members who accept church emails (for roster listing / member broadcasts)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT email, first_name, last_name, phone, role
        FROM users
        WHERE accepts_emails = 1
          AND role NOT IN ('pending', 'banned')
          AND email IS NOT NULL AND TRIM(email) != ''
        ORDER BY last_name, first_name
    """)
    return cur.fetchall()


def build_roster_text(members: list) -> str:
    """Plain-text roster block for email bodies."""
    if not members:
        return ''
    lines = ['--- Church Member Roster ---', f'Total: {len(members)} members', '']
    for m in members:
        phone = m.get('phone') or 'Not provided'
        role = m.get('role') or 'Member'
        lines.append(f"{m.get('first_name', '')} {m.get('last_name', '')} - {phone} - {m.get('email', '')} - {role}")
    return '\n'.join(lines)