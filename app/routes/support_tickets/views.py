# MYVINECHURCH.ONLINE/app/routes/support_tickets/views.py
# 100% REBUILT + HEAVY DEBUGGER
# Watch the console when you visit /support-tickets/ to see exactly where it fails

from flask import render_template, request, redirect, url_for, flash, session
from app.utils.decorators import login_required
from app.models.log import log_change
from app.utils.time_utils import utc_now

from . import support_tickets_bp
from .queries import (
    get_user_tickets, get_open_user_ticket_count,
    create_ticket, get_user_ticket, get_ticket_comments,
    add_ticket_comment, get_ticket_categories
)
from .forms import validate_ticket_submission, validate_ticket_comment
from .utils import send_new_ticket_notification_to_staff

print("🚀 [DEBUG] support_tickets/views.py LOADED SUCCESSFULLY")


# ----------------------------------------------------------------------
# Member Dashboard – "My Tickets"
# ----------------------------------------------------------------------
@support_tickets_bp.route('/', endpoint='dashboard')
@login_required
def dashboard():
    print("\n" + "=" * 70)
    print("🔍 [DEBUG] ENTERED /support-tickets/ DASHBOARD")
    print(f"🔍 [DEBUG] Session user_id: {session.get('user_id')}")
    print(f"🔍 [DEBUG] Session role: {session.get('user_role')}")

    user_id = session['user_id']
    print(f"🔍 [DEBUG] Getting tickets for user_id = {user_id}")

    try:
        tickets = get_user_tickets(user_id)
        print(f"🔍 [DEBUG] Got {len(tickets)} tickets")
    except Exception as e:
        print(f"❌ [DEBUG] ERROR in get_user_tickets: {e}")
        tickets = []

    try:
        open_count = get_open_user_ticket_count(user_id)
        print(f"🔍 [DEBUG] Open ticket count: {open_count}")
    except Exception as e:
        print(f"❌ [DEBUG] ERROR in get_open_user_ticket_count: {e}")
        open_count = 0

    log_change(user_id, 'view', change_details='Viewed personal support ticket portal')
    print("🔍 [DEBUG] Rendering support_tickets/dashboard.html")
    print("=" * 70 + "\n")

    return render_template('support_tickets/dashboard.html',
                           tickets=tickets,
                           open_count=open_count)


# ----------------------------------------------------------------------
# Submit New Support Ticket
# ----------------------------------------------------------------------
@support_tickets_bp.route('/submit', methods=['GET', 'POST'], endpoint='submit_ticket')
@login_required
def submit_ticket():
    print("\n" + "=" * 70)
    print("🔍 [DEBUG] ENTERED /support-tickets/submit")
    user_id = session['user_id']
    print(f"🔍 [DEBUG] user_id = {user_id}")

    if request.method == 'POST':
        print("🔍 [DEBUG] POST request received")
        is_valid, errors, cleaned = validate_ticket_submission(request.form)
        print(f"🔍 [DEBUG] Validation result: is_valid={is_valid}, errors={errors}")

        if not is_valid:
            for err in errors:
                flash(err, 'error')
            categories = get_ticket_categories()
            return render_template('support_tickets/submit_ticket.html',
                                   categories=categories,
                                   form_data=cleaned)
        else:
            created_at = utc_now()
            ticket_id = create_ticket(
                user_id,
                cleaned['title'],
                cleaned['description'],
                cleaned['category_id'],
                cleaned['priority'],
                created_at
            )
#             print(f"✅ [DEBUG] Ticket created with ID: {ticket_id}")

            try:
                send_new_ticket_notification_to_staff(
                    ticket_id, cleaned['title'], 'General', cleaned['priority']
                )
#                 print("✅ [DEBUG] Staff notification sent")
                except Exception as e:
    #                 print(f"⚠️ [DEBUG] Staff notification failed: {e}")
    
                log_change(user_id, 'create', ticket_id, change_details='Submitted new support ticket')
            flash('Your support ticket has been submitted successfully!', 'success')
            return redirect(url_for('support_tickets.view_ticket', ticket_id=ticket_id))

    categories = get_ticket_categories()
    print(f"🔍 [DEBUG] Rendering submit_ticket.html with {len(categories)} categories")
    print("=" * 70 + "\n")
    return render_template('support_tickets/submit_ticket.html', categories=categories)


# ----------------------------------------------------------------------
# View Single Ticket + Add Comment
# ----------------------------------------------------------------------
@support_tickets_bp.route('/<int:ticket_id>', methods=['GET', 'POST'], endpoint='view_ticket')
@login_required
def view_ticket(ticket_id):
    print(f"\n🔍 [DEBUG] ENTERED /support-tickets/{ticket_id}")
    user_id = session['user_id']
    print(f"🔍 [DEBUG] user_id = {user_id}, ticket_id = {ticket_id}")

    ticket = get_user_ticket(ticket_id, user_id)
    if not ticket:
        print("❌ [DEBUG] Ticket not found or permission denied")
        flash('Ticket not found or you do not have permission to view it.', 'error')
        return redirect(url_for('support_tickets.dashboard'))

#     print(f"✅ [DEBUG] Ticket found: {ticket.get('title')}")
    comments = get_ticket_comments(ticket_id)
    print(f"🔍 [DEBUG] Loaded {len(comments)} comments")

    if request.method == 'POST':
        print("🔍 [DEBUG] POST request on view_ticket")
        is_valid, errors, cleaned = validate_ticket_comment(request.form)
        if not is_valid:
            for err in errors:
                flash(err, 'error')
        else:
            created_at = utc_now()
            add_ticket_comment(ticket_id, user_id, cleaned['comment'], created_at)
            log_change(user_id, 'comment', ticket_id, change_details='Added comment to own ticket')
            flash('Your comment has been added.', 'success')
            return redirect(url_for('support_tickets.view_ticket', ticket_id=ticket_id))

    return render_template('support_tickets/view_ticket.html',
                           ticket=ticket,
                           comments=comments)


# print("✅ [DEBUG] support_tickets/views.py FULLY LOADED - All routes registered")