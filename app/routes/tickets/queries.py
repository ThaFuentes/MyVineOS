# MYVINECHURCH.ONLINE/app/routes/tickets/queries.py
# Full path: MYVINECHURCH.ONLINE/app/routes/tickets/queries.py
# File name: queries.py
# Brief, detailed purpose: All database operations (SELECT, INSERT, UPDATE, DELETE) for the **Ticket Manager** blueprint ONLY (routes/tickets/).
# MariaDB/PyMySQL ready (%s placeholders). Every query from original tickets.py extracted here.
# This file is now 100% isolated to administrative ticket management (ticket_managers group + Admins/Owner).
# • All user-facing queries (get_user_tickets, get_open_user_ticket_count, create_ticket for guests) have been removed.
# • Only manager-specific queries remain: full queue, comments.html, status/priority/assignment updates, group management, notifications.
# • All timestamps (created_at/updated_at/date_added) expect UTC values. Behavior 100% identical for managers.

import pymysql.cursors
import json
from app.models.db import get_db


def user_has_manage_tickets_group_permission(user_id):
    """Return True if user belongs to any group with 'manage_tickets' permission (DB part only)."""
    if not user_id:
        return False
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT g.permissions
        FROM groups g
        JOIN user_groups ug ON g.id = ug.group_id
        WHERE ug.user_id = %s
    """, (user_id,))
    rows = cur.fetchall()

    for row in rows:
        try:
            perms = json.loads(row['permissions'] or '[]')
            if 'manage_tickets' in perms:
                return True
        except (json.JSONDecodeError, TypeError):
            continue
    return False


def get_staff_emails():
    """Return list of staff/admin/owner emails who accept emails (Ticket Manager use)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT email FROM users WHERE role IN ('Staff', 'Admin', 'Owner') AND accepts_emails = 1")
    return [row['email'] for row in cur.fetchall() if row.get('email')]


def get_creator_email(ticket):
    """Get creator email (handles registered user or guest contact_email)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    if ticket.get('created_by'):
        cur.execute("SELECT email FROM users WHERE id = %s", (ticket['created_by'],))
        row = cur.fetchone()
        return row['email'] if row and row.get('email') else None
    return ticket.get('contact_email')


def get_all_tickets():
    """Get ALL tickets for manager dashboard with priority sorting."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT t.*, c.name AS category_name, 
               u.username AS creator_name, a.username AS assignee_name
        FROM tickets t
        JOIN ticket_categories c ON t.category_id = c.id
        LEFT JOIN users u ON t.created_by = u.id
        LEFT JOIN users a ON t.assigned_to = a.id
        ORDER BY 
            CASE t.priority 
                WHEN 'urgent' THEN 1 
                WHEN 'high' THEN 2 
                WHEN 'medium' THEN 3 
                WHEN 'low' THEN 4 
                ELSE 5 
            END ASC,
            t.created_at ASC
    """)
    return cur.fetchall()


def get_open_ticket_count():
    """Count ALL open tickets (for manager dashboard)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT COUNT(*) AS cnt FROM tickets WHERE status NOT IN ('resolved', 'closed')")
    row = cur.fetchone()
    return row['cnt'] if row else 0


def get_staff_list():
    """Get staff list for assignment dropdown (Ticket Manager only)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT id, username FROM users WHERE role IN ('Staff', 'Admin', 'Owner') ORDER BY username")
    return cur.fetchall()


def get_ticket(ticket_id):
    """Get single ticket by ID (for view_ticket - manager only)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT t.*, c.name AS category_name,
               u.username AS creator_name, a.username AS assignee_name
        FROM tickets t
        JOIN ticket_categories c ON t.category_id = c.id
        LEFT JOIN users u ON t.created_by = u.id
        LEFT JOIN users a ON t.assigned_to = a.id
        WHERE t.id = %s
    """, (ticket_id,))
    return cur.fetchone()


def get_ticket_comments(ticket_id):
    """Get all comments.html for a ticket (manager view)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT tc.*, u.username
        FROM ticket_comments tc
        JOIN users u ON tc.user_id = u.id
        WHERE tc.ticket_id = %s
        ORDER BY tc.date_added ASC
    """, (ticket_id,))
    return cur.fetchall()


def get_ticket_categories():
    """Get ALL ticket categories for manager forms (full list - no guest filter)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT id, name, default_priority 
        FROM ticket_categories 
        ORDER BY sort_order, name
    """)
    return cur.fetchall()


def get_ticket_for_notification(ticket_id):
    """Get ticket + category for email notifications (Ticket Manager only)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT t.*, c.name AS category_name
        FROM tickets t
        JOIN ticket_categories c ON t.category_id = c.id
        WHERE t.id = %s
    """, (ticket_id,))
    return cur.fetchone()


def add_ticket_comment(ticket_id, user_id, comment, notify_creator=False, date_added=None):
    """Insert new comment (Ticket Manager only)."""
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO ticket_comments (ticket_id, user_id, comment, notify_creator, date_added)
        VALUES (%s, %s, %s, %s, %s)
    """, (ticket_id, user_id, comment, 1 if notify_creator else 0, date_added))
    db.commit()


def update_ticket_status(ticket_id, new_status, updated_at):
    """Update status and timestamp (Ticket Manager only)."""
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE tickets SET status = %s, updated_at = %s WHERE id = %s",
                (new_status, updated_at, ticket_id))
    db.commit()


def assign_ticket(ticket_id, assigned_to, updated_at):
    """Assign ticket to staff member (Ticket Manager only)."""
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE tickets SET assigned_to = %s, updated_at = %s WHERE id = %s",
                (assigned_to, updated_at, ticket_id))
    db.commit()


def update_ticket_priority(ticket_id, new_priority, updated_at):
    """Update priority and timestamp (Ticket Manager only)."""
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE tickets SET priority = %s, updated_at = %s WHERE id = %s",
                (new_priority, updated_at, ticket_id))
    db.commit()


def get_ticket_title(ticket_id):
    """Get title only (used before delete - Ticket Manager only)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT title FROM tickets WHERE id = %s", (ticket_id,))
    row = cur.fetchone()
    return row['title'] if row else None


def delete_ticket(ticket_id):
    """Permanently delete ticket (Ticket Manager only)."""
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM tickets WHERE id = %s", (ticket_id,))
    db.commit()


# ----------------------------------------------------------------------
# Ticket Managers Group (Admin/Owner only)
# ----------------------------------------------------------------------
def get_ticket_manager_user_ids():
    """Return list of user_ids currently in ticket_managers table."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT user_id FROM ticket_managers")
    return [row['user_id'] for row in cur.fetchall()]


def add_to_ticket_managers(user_id):
    """Add user to ticket_managers (IGNORE if already present)."""
    db = get_db()
    cur = db.cursor()
    cur.execute("INSERT OR IGNORE INTO ticket_managers (user_id) VALUES (%s)", (user_id,))
    db.commit()


def remove_from_ticket_managers(user_id):
    """Remove user from ticket_managers."""
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM ticket_managers WHERE user_id = %s", (user_id,))
    db.commit()


def get_all_users():
    """Get all users for manage-group page (Admin/Owner only)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT id, username, first_name, last_name, role FROM users ORDER BY username")
    return cur.fetchall()


