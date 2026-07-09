# MYVINECHURCH.ONLINE/app/routes/support_tickets/queries.py
# FIXED for your actual database schema (created_by + no is_active)

import pymysql.cursors
from app.models.db import get_db

print("🚀 [DEBUG] support_tickets/queries.py (FIXED VERSION) LOADED")

def get_user_tickets(user_id):
    print(f"🔍 [DEBUG] get_user_tickets called for user_id={user_id}")
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT t.*, 
               tc.name AS category_name,
               DATE_FORMAT(t.created_at, '%%b %%d, %%Y') AS formatted_created,
               DATE_FORMAT(t.updated_at, '%%b %%d, %%Y') AS formatted_updated
        FROM tickets t
        LEFT JOIN ticket_categories tc ON t.category_id = tc.id
        WHERE t.created_by = %s
        ORDER BY t.updated_at DESC
    """, (user_id,))
    result = cur.fetchall()
    print(f"🔍 [DEBUG] get_user_tickets returned {len(result)} rows")
    return result


def get_open_user_ticket_count(user_id):
    print(f"🔍 [DEBUG] get_open_user_ticket_count called for user_id={user_id}")
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM tickets 
        WHERE created_by = %s AND status IN ('open', 'in_progress')
    """, (user_id,))
    result = cur.fetchone()[0]
    print(f"🔍 [DEBUG] get_open_user_ticket_count = {result}")
    return result


def create_ticket(user_id, title, description, category_id, priority, created_at):
    print(f"🔍 [DEBUG] create_ticket called")
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO tickets 
        (created_by, title, description, category_id, priority, status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, 'open', %s, %s)
    """, (user_id, title, description, category_id, priority, created_at, created_at))
    db.commit()
    new_id = cur.lastrowid
#     print(f"✅ [DEBUG] create_ticket created ID {new_id}")
    return new_id


def get_user_ticket(ticket_id, user_id):
    print(f"🔍 [DEBUG] get_user_ticket called for ticket_id={ticket_id}, user_id={user_id}")
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT t.*, 
               tc.name AS category_name,
               u.username AS creator_name
        FROM tickets t
        LEFT JOIN ticket_categories tc ON t.category_id = tc.id
        LEFT JOIN users u ON t.created_by = u.id
        WHERE t.id = %s AND t.created_by = %s
    """, (ticket_id, user_id))
    result = cur.fetchone()
    print(f"🔍 [DEBUG] get_user_ticket result: {result is not None}")
    return result


def get_ticket_comments(ticket_id):
    print(f"🔍 [DEBUG] get_ticket_comments called for ticket_id={ticket_id}")
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT tc.*, u.username 
        FROM ticket_comments tc
        JOIN users u ON tc.user_id = u.id
        WHERE tc.ticket_id = %s
        ORDER BY tc.date_added ASC
    """, (ticket_id,))
    result = cur.fetchall()
    print(f"🔍 [DEBUG] get_ticket_comments returned {len(result)} comments")
    return result


def add_ticket_comment(ticket_id, user_id, comment, created_at):
    print(f"🔍 [DEBUG] add_ticket_comment called")
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO ticket_comments (ticket_id, user_id, comment, date_added)
        VALUES (%s, %s, %s, %s)
    """, (ticket_id, user_id, comment, created_at))
    cur.execute("UPDATE tickets SET updated_at = %s WHERE id = %s", (created_at, ticket_id))
    db.commit()
#     print("✅ [DEBUG] add_ticket_comment done")


def get_ticket_categories():
    print("🔍 [DEBUG] get_ticket_categories called")
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    # FIXED: removed is_active filter (column doesn't exist)
    cur.execute("SELECT id, name FROM ticket_categories ORDER BY sort_order")
    result = cur.fetchall()
    print(f"🔍 [DEBUG] get_ticket_categories returned {len(result)} categories")
    return result


def get_staff_emails():
    print("🔍 [DEBUG] get_staff_emails called")
    db = get_db()
    cur = db.cursor()
    emails = set()

    try:
        cur.execute("""
            SELECT DISTINCT u.email
            FROM users u
            JOIN user_groups ug ON u.id = ug.user_id
            JOIN groups g ON ug.group_id = g.id
            WHERE LOWER(g.name) = 'ticket_managers'
              AND u.email IS NOT NULL AND u.email != ''
        """)
        for row in cur.fetchall():
            if row[0]:
                emails.add(row[0].strip())
    except Exception as e:
#         print(f"⚠️ [DEBUG] Error getting ticket_managers emails: {e}")

    try:
        cur.execute("""
            SELECT email FROM users 
            WHERE role IN ('admin', 'owner')
              AND email IS NOT NULL AND email != ''
        """)
        for row in cur.fetchall():
            if row[0]:
                emails.add(row[0].strip())
    except Exception as e:
#         print(f"⚠️ [DEBUG] Error getting admin/owner emails: {e}")

    cur.close()
    return list(emails)


def get_ticket_title(ticket_id):
    print(f"🔍 [DEBUG] get_ticket_title called for {ticket_id}")
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT title FROM tickets WHERE id = %s", (ticket_id,))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else f"Ticket #{ticket_id}"


# print("✅ [DEBUG] support_tickets/queries.py (FIXED) FULLY LOADED")