# app/routes/tickets.py
# Full path: myvinechurchonline/app/routes/tickets.py
# File name: tickets.py
# Brief, detailed purpose: Blueprint for church support ticket / helpdesk system – FULL REBUILD FOR MARIADB.
#          - Permission: Owners/Admins have full access.
#            Additional access via general groups system: any group with "manage_tickets" in permissions JSON grants full management.
#          - /tickets/ (function named tickets → endpoint 'tickets.tickets') → ALL logged-in users see ONLY their own tickets (tickets_dashboard.html).
#          - /tickets/manage (endpoint 'manager_dashboard') → Owners/Admins OR users in a group with "manage_tickets" permission see ALL tickets (ticket_manager.html).
#          - /tickets/manage-group (endpoint 'manage_group') → Admin/Owner only: manage membership in Ticket Managers group (ticket_manager.html).
#          - /tickets/submit → Public guest submission (allowed categories) + private member submission.
#          - /tickets/<id> (endpoint 'view_ticket') → Detail view (members see own for read/comment; group sees any for full management).
#          - Emails: new → staff group; member comment → staff; manager comment → creator (if checked); manager updates → creator; close → creator special.
#          - Censored word check on title/description/comments.html
#          - All significant actions audit-logged
#          - FULL REBUILD: Group management moved to Tickets module (correct base template).
#            Permission uses general groups system + Owner/Admin override.
#            Template names match actual files. MariaDB/PyMySQL ready (%s placeholders).
# TIMEZONE INTEGRATION: Timestamps (created_at, updated_at, date_added) formatted in church local time via format_church().
#   All existing functionality preserved exactly – only display formatting updated.

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.utils.decorators import login_required, role_required
from app.utils.helpers import contains_censored_word
from app.models.db import get_db
from app.models.log import log_change
from app.utils.emailer import send_email
from app.utils.time_utils import format_church  # For church local time display
from datetime import datetime
import json
import pymysql  # ← ADDED: Required for pymysql.cursors.DictCursor

tickets_bp = Blueprint('tickets', __name__, url_prefix='/tickets')


# ----------------------------------------------------------------------
# Permission Check – general groups + Owner/Admin override
# ----------------------------------------------------------------------
def can_manage_tickets(user_id):
    """Return True if user is Owner/Admin OR belongs to any group with 'manage_tickets' permission."""
    if session.get('user_role') in ['Owner', 'Admin']:
        return True

    db = get_db()
    cur = db.cursor()
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


# ----------------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------------
def get_staff_emails(db):
    cur = db.cursor()
    cur.execute("SELECT email FROM users WHERE role IN ('Staff', 'Admin', 'Owner') AND accepts_emails = 1")
    return [row['email'] for row in cur.fetchall() if row['email']]


def get_creator_email(db, ticket):
    if ticket['created_by']:
        cur = db.cursor()
        cur.execute("SELECT email FROM users WHERE id = %s", (ticket['created_by'],))
        row = cur.fetchone()
        return row['email'] if row and row['email'] else None
    return ticket['contact_email']


def send_ticket_notification(db, ticket, subject, body, notify_staff=False, notify_creator=False, always_creator=False):
    staff_emails = get_staff_emails(db) if notify_staff else []
    creator_email = get_creator_email(db, ticket) if (notify_creator or always_creator) else None

    emails = set()
    if staff_emails:
        emails.update(staff_emails)
    if creator_email:
        emails.add(creator_email)

    if not emails:
        return

    full_body = body + f"\n\nView ticket: https://myvinechurch.online/tickets/{ticket['id']}"

    for email in emails:
        send_email(email, subject, full_body)


# ----------------------------------------------------------------------
# Member view – "Tickets" tab (root URL – only own tickets)
# ----------------------------------------------------------------------
@tickets_bp.route('/')
def tickets():
    if not session.get('user_id'):
        flash('Please log in to view your tickets.', 'error')
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT t.*, c.name AS category_name
        FROM tickets t
        JOIN ticket_categories c ON t.category_id = c.id
        WHERE t.created_by = %s
        ORDER BY t.updated_at DESC
    """, (user_id,))
    tickets_list = cur.fetchall()

    # Format timestamps in church local time
    for t in tickets_list:
        if t['created_at']:
            t['formatted_created'] = format_church(t['created_at'], '%B %d, %Y at %I:%M %p')
        else:
            t['formatted_created'] = 'Unknown'
        if t['updated_at']:
            t['formatted_updated'] = format_church(t['updated_at'], '%B %d, %Y at %I:%M %p')
        else:
            t['formatted_updated'] = 'Never'

    cur.execute("SELECT COUNT(*) AS cnt FROM tickets WHERE created_by = %s AND status NOT IN ('resolved', 'closed')", (user_id,))
    row = cur.fetchone()
    open_count = row['cnt'] if row else 0

    log_change(user_id, 'view', change_details='Viewed own tickets list')

    return render_template('tickets/tickets_dashboard.html',
                           tickets=tickets_list,
                           open_count=open_count,
                           can_manage=can_manage_tickets(user_id))


# ----------------------------------------------------------------------
# Manager view – "Ticket Manager" (Owners/Admins OR group permission – all tickets)
# ----------------------------------------------------------------------
@tickets_bp.route('/manage', endpoint='manager_dashboard')
@login_required
def manager_dashboard():
    user_id = session['user_id']
    if not can_manage_tickets(user_id):
        flash('You do not have permission to access ticket management.', 'error')
        return redirect(url_for('tickets.tickets'))

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
    tickets_list = cur.fetchall()

    # Format timestamps in church local time
    for t in tickets_list:
        if t['created_at']:
            t['formatted_created'] = format_church(t['created_at'], '%B %d, %Y at %I:%M %p')
        else:
            t['formatted_created'] = 'Unknown'
        if t['updated_at']:
            t['formatted_updated'] = format_church(t['updated_at'], '%B %d, %Y at %I:%M %p')
        else:
            t['formatted_updated'] = 'Never'

    cur.execute("SELECT COUNT(*) AS cnt FROM tickets WHERE status NOT IN ('resolved', 'closed')")
    row = cur.fetchone()
    open_count = row['cnt'] if row else 0

    cur.execute("SELECT id, username FROM users WHERE role IN ('Staff', 'Admin', 'Owner') ORDER BY username")
    staff = cur.fetchall()

    log_change(user_id, 'view', change_details='Viewed ticket manager dashboard_tgp')

    return render_template('tickets/ticket_manager.html',
                           tickets=tickets_list,
                           open_count=open_count,
                           staff=staff,
                           can_manage=True)


# ----------------------------------------------------------------------
# Manage Ticket Managers Group – Admin/Owner only
# ----------------------------------------------------------------------
@tickets_bp.route('/manage-group', methods=['GET', 'POST'], endpoint='manage_group')
@login_required
@role_required(['Admin', 'Owner'])
def manage_group():
    """Admin/Owner page to add/remove users from the dedicated ticket_managers group."""
    db = get_db()
    cur = db.cursor()

    # Fetch all users
    cur.execute("SELECT id, username, first_name, last_name, role FROM users ORDER BY username")
    all_users = cur.fetchall()

    # Fetch current manager user_ids
    cur.execute("SELECT user_id FROM ticket_managers")
    manager_ids = [row['user_id'] for row in cur.fetchall()]

    if request.method == 'POST':
        action = request.form.get('action')
        user_id = request.form.get('user_id')

        if action == 'add':
            cur.execute("INSERT OR IGNORE INTO ticket_managers (user_id) VALUES (%s)", (user_id,))
        elif action == 'remove':
            cur.execute("DELETE FROM ticket_managers WHERE user_id = %s", (user_id,))

        db.commit()
        flash('Ticket Managers group updated.', 'success')
        return redirect(url_for('tickets.manage_group'))

    return render_template('tickets/ticket_manager.html',
                           all_users=all_users,
                           manager_ids=manager_ids)


# ----------------------------------------------------------------------
# Submit Ticket – public guest + private member
# ----------------------------------------------------------------------
@tickets_bp.route('/submit', methods=['GET', 'POST'], endpoint='submit_ticket')
def submit_ticket():
    db = get_db()
    cur = db.cursor()

    is_logged_in = 'user_id' in session
    user_id = session.get('user_id')

    if is_logged_in:
        cur.execute("SELECT id, name, default_priority FROM ticket_categories ORDER BY sort_order, name")
    else:
        cur.execute("SELECT id, name, default_priority FROM ticket_categories WHERE allow_guest_creation = 1 ORDER BY sort_order, name")
    categories = cur.fetchall()

    if not categories and not is_logged_in:
        flash('Guest submissions are currently disabled.', 'error')
        return redirect(url_for('public.public_dashboard'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category_id = request.form.get('category_id')
        priority = request.form.get('priority', 'medium')

        contact_name = request.form.get('contact_name', '').strip() if not is_logged_in else None
        contact_email = request.form.get('contact_email', '').strip() if not is_logged_in else None

        if not title or not description or not category_id:
            flash('Title, description, and category are required.', 'error')
            return render_template('tickets/submit_ticket.html', categories=categories, is_logged_in=is_logged_in)

        if not is_logged_in and (not contact_name or not contact_email):
            flash('Name and email are required for guest submissions.', 'error')
            return render_template('tickets/submit_ticket.html', categories=categories, is_logged_in=is_logged_in)

        if contains_censored_word(f"{title} {description}"):
            flash('Entry contains a prohibited word or phrase.', 'error')
            return render_template('tickets/submit_ticket.html', categories=categories, is_logged_in=is_logged_in)

        ip_address = request.remote_addr if not is_logged_in else None

        created_at_utc = utc_now()  # UTC for created_at

        cur = db.cursor()
        cur.execute("""
            INSERT INTO tickets (title, description, category_id, priority, status, created_by,
                                 contact_name, contact_email, ip_address, created_at)
            VALUES (%s, %s, %s, %s, 'open', %s, %s, %s, %s, %s)
        """, (title, description, category_id, priority,
              user_id if is_logged_in else None,
              contact_name, contact_email, ip_address, created_at_utc))
        db.commit()
        ticket_id = cur.lastrowid

        cur.execute("""
            SELECT t.*, c.name AS category_name
            FROM tickets t
            JOIN ticket_categories c ON t.category_id = c.id
            WHERE t.id = %s
        """, (ticket_id,))
        ticket = cur.fetchone()

        subject = f"New Support Ticket #{ticket_id}: {title}"
        body = f"""
A new ticket has been submitted.

Title: {title}
Category: {ticket['category_name']}
Priority: {priority.capitalize()}
Submitted by: {contact_name or session.get('username', 'Member')}

Description:
{description}
        """
        send_ticket_notification(db, ticket, subject, body, notify_staff=True)

        log_change(user_id if is_logged_in else None, 'create', ticket_id, title,
                   'Guest ticket submitted' if not is_logged_in else 'Ticket created')

        flash('Ticket submitted successfully! We will respond soon.', 'success')
        return redirect(url_for('tickets.tickets') if is_logged_in else url_for('public.public_dashboard'))

    return render_template('tickets/submit_ticket.html', categories=categories, is_logged_in=is_logged_in)


# ----------------------------------------------------------------------
# View / Manage Individual Ticket
# ----------------------------------------------------------------------
@tickets_bp.route('/<int:ticket_id>', methods=['GET', 'POST'], endpoint='view_ticket')
@login_required
def view_ticket(ticket_id):
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
    ticket = cur.fetchone()
    if not ticket:
        flash('Ticket not found.', 'error')
        return redirect(url_for('tickets.tickets'))

    if ticket['created_by'] != session['user_id'] and not can_manage_tickets(session['user_id']):
        flash('Access denied.', 'error')
        return redirect(url_for('tickets.tickets'))

    can_manage = can_manage_tickets(session['user_id'])

    # Format ticket timestamps in church local time
    if ticket['created_at']:
        ticket['formatted_created'] = format_church(ticket['created_at'], '%B %d, %Y at %I:%M %p')
    else:
        ticket['formatted_created'] = 'Unknown'
    if ticket['updated_at']:
        ticket['formatted_updated'] = format_church(ticket['updated_at'], '%B %d, %Y at %I:%M %p')
    else:
        ticket['formatted_updated'] = 'Never'

    cur.execute("""
        SELECT tc.*, u.username
        FROM ticket_comments tc
        JOIN users u ON tc.user_id = u.id
        WHERE tc.ticket_id = %s
        ORDER BY tc.date_added ASC
    """, (ticket_id,))
    comments = cur.fetchall()

    # Format comment timestamps in church local time
    for c in comments:
        if c['date_added']:
            c['formatted_date'] = format_church(c['date_added'], '%B %d, %Y at %I:%M %p')
        else:
            c['formatted_date'] = 'Unknown'

    cur.execute("SELECT id, username FROM users WHERE role IN ('Staff', 'Admin', 'Owner') ORDER BY username")
    staff = cur.fetchall()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'comment':
            comment = request.form.get('comment', '').strip()
            notify_creator = 'notify_creator' in request.form and can_manage

            if not comment:
                flash('Comment cannot be empty.', 'error')
            elif contains_censored_word(comment):
                flash('Comment contains a prohibited word.', 'error')
            else:
                comment_time_utc = utc_now()  # UTC for date_added

                cur.execute("""
                    INSERT INTO ticket_comments (ticket_id, user_id, comment, notify_creator, date_added)
                    VALUES (%s, %s, %s, %s, %s)
                """, (ticket_id, session['user_id'], comment, 1 if notify_creator else 0, comment_time_utc))
                db.commit()

                if can_manage and notify_creator:
                    subject = f"Update on Ticket #{ticket_id}: {ticket['title']}"
                    body = f"Staff member {session['username']} added a comment:\n\n{comment}"
                    send_ticket_notification(db, ticket, subject, body, notify_creator=True)
                elif not can_manage:
                    subject = f"Member comment on Ticket #{ticket_id}: {ticket['title']}"
                    body = f"Member {session['username']} added a comment:\n\n{comment}"
                    send_ticket_notification(db, ticket, subject, body, notify_staff=True)

                log_change(session['user_id'], 'comment', ticket_id, change_details='Added comment')
                flash('Comment added.', 'success')

        elif action in ['status', 'assign', 'priority'] and can_manage:
            updated = False
            message = ""

            update_time_utc = utc_now()  # UTC for updated_at

            if action == 'status':
                new_status = request.form.get('status')
                if new_status in ['open', 'in_progress', 'resolved', 'closed']:
                    old_status = ticket['status']
                    cur.execute("UPDATE tickets SET status = %s, updated_at = %s WHERE id = %s", (new_status, update_time_utc, ticket_id))
                    db.commit()
                    ticket['status'] = new_status
                    updated = True
                    message = f"Status changed to {new_status.replace('_', ' ').title()}"
                    log_change(session['user_id'], 'update', ticket_id, change_details=f'Status {old_status} → {new_status}')

                    if new_status in ['resolved', 'closed']:
                        subject = f"Ticket #{ticket_id} {new_status.capitalize()}: {ticket['title']}"
                        body = f"Your ticket has been {new_status}. Thank you!"
                        send_ticket_notification(db, ticket, subject, body, always_creator=True)

            elif action == 'assign':
                assigned_to = request.form.get('assigned_to') or None
                cur.execute("UPDATE tickets SET assigned_to = %s, updated_at = %s WHERE id = %s", (assigned_to, update_time_utc, ticket_id))
                db.commit()
                assignee = 'unassigned' if not assigned_to else next((s['username'] for s in staff if str(s['id']) == assigned_to), 'unknown')
                updated = True
                message = f"Assigned to {assignee}"
                log_change(session['user_id'], 'assign', ticket_id, change_details=f'Assigned to {assignee}')

            elif action == 'priority':
                new_pri = request.form.get('priority')
                if new_pri in ['low', 'medium', 'high', 'urgent']:
                    cur.execute("UPDATE tickets SET priority = %s, updated_at = %s WHERE id = %s", (new_pri, update_time_utc, ticket_id))
                    db.commit()
                    ticket['priority'] = new_pri
                    updated = True
                    message = f"Priority changed to {new_pri.capitalize()}"
                    log_change(session['user_id'], 'update', ticket_id, change_details=f'Priority → {new_pri}')

            if updated and ticket['status'] not in ['resolved', 'closed']:
                subject = f"Update on Ticket #{ticket_id}: {ticket['title']}"
                body = f"Staff has updated your ticket:\n{message}"
                send_ticket_notification(db, ticket, subject, body, notify_creator=True)

            flash('Ticket updated.', 'success')

        return redirect(url_for('tickets.view_ticket', ticket_id=ticket_id))

    log_change(session['user_id'], 'view', ticket_id, change_details=f"Viewed ticket #{ticket_id}")

    return render_template('tickets/view_ticket.html',
                           ticket=ticket,
                           comments=comments,
                           staff=staff,
                           can_manage=can_manage)


# ----------------------------------------------------------------------
# Delete Ticket – Admin/Owner only
# ----------------------------------------------------------------------
@tickets_bp.route('/delete/<int:ticket_id>', methods=['POST'], endpoint='delete_ticket')
@login_required
@role_required(['Admin', 'Owner'])
def delete_ticket(ticket_id):
    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT title FROM tickets WHERE id = %s", (ticket_id,))
    row = cur.fetchone()
    if not row:
        flash('Ticket not found.', 'error')
        return redirect(url_for('tickets.tickets'))

    cur.execute("DELETE FROM tickets WHERE id = %s", (ticket_id,))
    db.commit()

    log_change(session['user_id'], 'delete', ticket_id, row['title'], 'Deleted ticket')
    flash('Ticket deleted permanently.', 'success')
    return redirect(url_for('tickets.tickets'))