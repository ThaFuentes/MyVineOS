# MYVINECHURCH.ONLINE/app/routes/tickets/views.py
# Full path: MYVINECHURCH.ONLINE/app/routes/tickets/views.py
# File name: views.py
# Brief, detailed purpose: All the route functions (the @route decorators) for the **Ticket Manager** blueprint ONLY.
# - FIXED: RecursionError when deleting a ticket.
#   The view function was named `delete_ticket` and it was also importing `delete_ticket` from queries.py → Python name shadowing caused infinite recursion.
#   Now the queries function is imported with an alias so it can never call itself.
# - Manage Ticket Managers Group route and link have been completely removed (you confirmed you do not want it — use /groups/ instead).
# - Everything else (dashboard, view ticket, status/priority/assign, comments.html, email notifications) is untouched and working.

from flask import render_template, request, redirect, url_for, flash, session
from app.utils.decorators import login_required, role_required
from app.models.log import log_change
from app.utils.time_utils import format_church, utc_now

from . import tickets_bp
from .queries import (
    get_all_tickets, get_open_ticket_count, get_staff_list,
    get_ticket, get_ticket_comments,
    add_ticket_comment, update_ticket_status, assign_ticket,
    update_ticket_priority, get_ticket_title,
    delete_ticket as delete_ticket_from_db   # ← ALIAS to prevent recursion
)
from .forms import (
    validate_ticket_comment, validate_status_update,
    validate_priority_update
)
from .utils import can_manage_tickets, send_ticket_notification


# ----------------------------------------------------------------------
# Root for /tickets -> manager dashboard
# ----------------------------------------------------------------------
@tickets_bp.route('/')
@login_required
def tickets_root():
    return redirect(url_for('tickets.manager_dashboard'))


# ----------------------------------------------------------------------
# Manager view – "Ticket Manager" (Owners/Admins OR ticket_managers group – all tickets)
# ----------------------------------------------------------------------
@tickets_bp.route('/manage', endpoint='manager_dashboard')
@login_required
def manager_dashboard():
    user_id = session['user_id']
    if not can_manage_tickets(user_id):
        flash('You do not have permission to access ticket management.', 'error')
        return redirect(url_for('tickets.manager_dashboard'))

    tickets_list = get_all_tickets()

    for t in tickets_list:
        if t['created_at']:
            t['formatted_created'] = format_church(t['created_at'], '%B %d, %Y at %I:%M %p')
        else:
            t['formatted_created'] = 'Unknown'
        if t['updated_at']:
            t['formatted_updated'] = format_church(t['updated_at'], '%B %d, %Y at %I:%M %p')
        else:
            t['formatted_updated'] = 'Never'

    open_count = get_open_ticket_count()
    staff = get_staff_list()

    log_change(user_id, 'view', change_details='Viewed ticket manager dashboard')

    return render_template('tickets/ticket_manager.html',
                           tickets=tickets_list,
                           open_count=open_count,
                           staff=staff,
                           can_manage=True)


# ----------------------------------------------------------------------
# View / Manage Individual Ticket (Ticket Manager only)
# ----------------------------------------------------------------------
@tickets_bp.route('/<int:ticket_id>', methods=['GET', 'POST'], endpoint='view_ticket')
@login_required
def view_ticket(ticket_id):
    ticket = get_ticket(ticket_id)
    if not ticket:
        flash('Ticket not found.', 'error')
        return redirect(url_for('tickets.manager_dashboard'))

    user_id = session['user_id']
    if not can_manage_tickets(user_id):
        flash('Access denied.', 'error')
        return redirect(url_for('tickets.manager_dashboard'))

    # Format ticket timestamps
    if ticket['created_at']:
        ticket['formatted_created'] = format_church(ticket['created_at'], '%B %d, %Y at %I:%M %p')
    else:
        ticket['formatted_created'] = 'Unknown'
    if ticket['updated_at']:
        ticket['formatted_updated'] = format_church(ticket['updated_at'], '%B %d, %Y at %I:%M %p')
    else:
        ticket['formatted_updated'] = 'Never'

    comments = get_ticket_comments(ticket_id)

    for c in comments:
        if c['date_added']:
            c['formatted_date'] = format_church(c['date_added'], '%B %d, %Y at %I:%M %p')
        else:
            c['formatted_date'] = 'Unknown'

    staff = get_staff_list()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'comment':
            is_valid, errors, cleaned = validate_ticket_comment(request.form, can_manage=True)
            if not is_valid:
                for err in errors:
                    flash(err, 'error')
            else:
                comment_time_utc = utc_now()
                add_ticket_comment(
                    ticket_id,
                    user_id,
                    cleaned['comment'],
                    cleaned['notify_creator'],
                    comment_time_utc
                )

                if cleaned['notify_creator']:
                    subject = f"Update on Ticket #{ticket_id}: {ticket['title']}"
                    body = f"Staff member {session.get('username', 'Manager')} added a comment:\n\n{cleaned['comment']}"
                    send_ticket_notification(ticket, subject, body, notify_creator=True)

                log_change(user_id, 'comment', ticket_id, change_details='Added comment')
                flash('Comment added.', 'success')

        elif action in ['status', 'assign', 'priority']:
            updated = False
            message = ""
            update_time_utc = utc_now()

            if action == 'status':
                is_valid, err = validate_status_update(request.form)
                if not is_valid:
                    flash(err, 'error')
                else:
                    new_status = request.form.get('status')
                    old_status = ticket['status']
                    update_ticket_status(ticket_id, new_status, update_time_utc)
                    ticket['status'] = new_status
                    updated = True
                    message = f"Status changed to {new_status.replace('_', ' ').title()}"
                    log_change(user_id, 'update', ticket_id,
                               change_details=f'Status {old_status} → {new_status}')

                    if new_status in ['resolved', 'closed']:
                        subject = f"Ticket #{ticket_id} {new_status.capitalize()}: {ticket['title']}"
                        body = f"Your ticket has been {new_status}. Thank you!"
                        send_ticket_notification(ticket, subject, body, always_creator=True)

            elif action == 'assign':
                assigned_to = request.form.get('assigned_to') or None
                assign_ticket(ticket_id, assigned_to, update_time_utc)
                assignee = 'unassigned' if not assigned_to else next(
                    (s['username'] for s in staff if str(s['id']) == assigned_to), 'unknown'
                )
                updated = True
                message = f"Assigned to {assignee}"
                log_change(user_id, 'assign', ticket_id,
                           change_details=f'Assigned to {assignee}')

            elif action == 'priority':
                is_valid, err = validate_priority_update(request.form)
                if not is_valid:
                    flash(err, 'error')
                else:
                    new_pri = request.form.get('priority')
                    update_ticket_priority(ticket_id, new_pri, update_time_utc)
                    ticket['priority'] = new_pri
                    updated = True
                    message = f"Priority changed to {new_pri.capitalize()}"
                    log_change(user_id, 'update', ticket_id,
                               change_details=f'Priority → {new_pri}')

            if updated and ticket['status'] not in ['resolved', 'closed']:
                subject = f"Update on Ticket #{ticket_id}: {ticket['title']}"
                body = f"Staff has updated your ticket:\n{message}"
                send_ticket_notification(ticket, subject, body, notify_creator=True)

            if updated:
                flash('Ticket updated.', 'success')

        return redirect(url_for('tickets.view_ticket', ticket_id=ticket_id))

    log_change(user_id, 'view', ticket_id, change_details=f"Viewed ticket #{ticket_id}")

    return render_template('tickets/view_ticket.html',
                           ticket=ticket,
                           comments=comments,
                           staff=staff,
                           can_manage=True)


# ----------------------------------------------------------------------
# Delete Ticket – Admin/Owner only
# ----------------------------------------------------------------------
@tickets_bp.route('/delete/<int:ticket_id>', methods=['POST'], endpoint='delete_ticket')
@login_required
@role_required(['Admin', 'Owner'])
def delete_ticket(ticket_id):
    title = get_ticket_title(ticket_id)
    if not title:
        flash('Ticket not found.', 'error')
        return redirect(url_for('tickets.manager_dashboard'))

    # FIXED: Use the aliased import so we do NOT call ourselves recursively
    delete_ticket_from_db(ticket_id)

    log_change(session['user_id'], 'delete', ticket_id, title, 'Deleted ticket')
    flash('Ticket deleted permanently.', 'success')
    return redirect(url_for('tickets.manager_dashboard'))


