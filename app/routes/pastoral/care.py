# app/routes/pastoral/care.py
# Full path: WebChurchMan/app/routes/pastoral/care.py
# File name: care.py
# Brief, detailed purpose: Blueprint and routes for the Pastoral Care module.
#   Handles confidential care requests (hospital visits, counseling, prayer needs, bereavement, etc.),
#   assignment to pastors/staff, and private chronological notes.
#   All routes require pastoral_required() decorator -> only Pastoral Group members can access.
#   Enforces confidentiality: notes are private by default, only visible to pastoral team.
#   Audit-logged actions (create/update/assign/note).
#   Uses centralized models.pastoral functions for DB access.
#   FIXED: Removed circular import (from .. import pastoral_bp) -> uses relative import from .

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, abort
from . import pastoral_required  # Relative import from __init__.py in same folder
from app.models.pastoral.care import (
    fetch_care_requests,
    get_care_request_by_id, create_care_request, update_care_request, delete_care_request,
    get_care_assignments, add_care_assignment, remove_care_assignment,
    get_care_notes, add_care_note,
)
from app.models.pastoral.shared import get_pastoral_team_members, get_active_members_for_care
from app.models.log import log_change
from app.utils.helpers import contains_censored_word

care_bp = Blueprint('care', __name__, url_prefix='/care')

# ----------------------------------------------------------------------
# List all care requests (pastoral team view)
# ----------------------------------------------------------------------
@care_bp.route('/')
@pastoral_required()
def care_dashboard():
    status = request.args.get('status') or None
    urgency = request.args.get('urgency') or None

    care_requests = fetch_care_requests(status=status, urgency=urgency)

    return render_template(
        'pastoral/care/care_dashboard.html',
        requests=care_requests,
        page_title="Pastoral Care Dashboard",
        active_status=status,
        active_urgency=urgency
    )

# ----------------------------------------------------------------------
# View single care request detail (with assignments & notes)
# ----------------------------------------------------------------------
@care_bp.route('/<int:request_id>')
@pastoral_required()
def care_request_detail(request_id):
    request_data = get_care_request_by_id(request_id)
    if not request_data:
        flash("Care request not found.", "error")
        return redirect(url_for('pastoral.care.care_dashboard'))

    assignments = get_care_assignments(request_id)
    notes = get_care_notes(request_id)

    return render_template(
        'pastoral/care/care_request_detail.html',
        request=request_data,
        assignments=assignments,
        notes=notes,
        pastoral_team=get_pastoral_team_members(),
        page_title=f"Care Request - {request_data['title'] or request_data['request_type']}"
    )

# ----------------------------------------------------------------------
# Create new care request
# ----------------------------------------------------------------------
@care_bp.route('/new', methods=['GET', 'POST'])
@pastoral_required()
def care_new():
    if request.method == 'POST':
        data = {
            'member_id': request.form.get('member_id'),
            'request_type': request.form.get('request_type'),
            'title': request.form.get('title', '').strip(),
            'description': request.form.get('description', '').strip(),
            'urgency': request.form.get('urgency', 'normal'),
            'status': 'open'
        }

        if not data['member_id'] or not data['request_type'] or not data['description']:
            flash("Member, type, and description are required.", "error")
            return render_template(
                'pastoral/care/care_new.html',
                members=get_active_members_for_care(),
                page_title="New Pastoral Care Request",
            )

        if contains_censored_word(data['title'] + " " + data['description']):
            flash("Prohibited content detected.", "error")
            return render_template(
                'pastoral/care/care_new.html',
                members=get_active_members_for_care(),
                page_title="New Pastoral Care Request",
            )

        request_id = create_care_request(data, session['user_id'])
        log_change(session['user_id'], 'create', request_id, data['title'] or data['request_type'],
                   "Created pastoral care request")

        flash("Care request created successfully.", "success")
        return redirect(url_for('pastoral.care.care_request_detail', request_id=request_id))

    return render_template(
        'pastoral/care/care_new.html',
        members=get_active_members_for_care(),
        page_title="New Pastoral Care Request",
    )

# ----------------------------------------------------------------------
# Update care request (status, urgency, description, etc.)
# ----------------------------------------------------------------------
@care_bp.route('/<int:request_id>/edit', methods=['POST'])
@pastoral_required()
def care_edit(request_id):
    data = {}
    for field in ['title', 'description', 'urgency', 'status']:
        if field in request.form:
            data[field] = request.form[field].strip()

    if not data:
        flash("No changes submitted.", "warning")
        return redirect(url_for('pastoral.care.care_request_detail', request_id=request_id))

    if 'description' in data or 'title' in data:
        text = (data.get('title', '') + " " + data.get('description', ''))
        if contains_censored_word(text):
            flash("Prohibited content detected.", "error")
            return redirect(request.referrer or url_for('pastoral.care.care_dashboard'))

    update_care_request(request_id, data)
    log_change(session['user_id'], 'update', request_id, data.get('title'), "Updated pastoral care request")

    flash("Care request updated.", "success")
    return redirect(url_for('pastoral.care.care_request_detail', request_id=request_id))

# ----------------------------------------------------------------------
# Assign pastor/staff to request
# ----------------------------------------------------------------------
@care_bp.route('/<int:request_id>/assign', methods=['POST'])
@pastoral_required()
def care_assign(request_id):
    pastor_id = request.form.get('pastor_id')
    notes = request.form.get('notes', '').strip()
    is_primary = 1 if request.form.get('is_primary') else 0

    if not pastor_id:
        flash("Please select a pastor/staff member.", "error")
        return redirect(url_for('pastoral.care.care_request_detail', request_id=request_id))

    add_care_assignment(request_id, pastor_id, notes, is_primary)
    log_change(session['user_id'], 'assign', request_id, f"Assigned to user {pastor_id}",
               "Assigned pastoral care request")

    update_care_request(request_id, {'status': 'assigned'})

    flash("Pastor/staff assigned successfully.", "success")
    return redirect(url_for('pastoral.care.care_request_detail', request_id=request_id))

# ----------------------------------------------------------------------
# Remove assignment
# ----------------------------------------------------------------------
@care_bp.route('/assignment/<int:assignment_id>/remove', methods=['POST'])
@pastoral_required()
def care_remove_assignment(assignment_id):
    remove_care_assignment(assignment_id)
    log_change(session['user_id'], 'delete', assignment_id, None, "Removed pastoral care assignment")
    flash("Assignment removed.", "success")
    return redirect(request.referrer or url_for('pastoral.care.care_dashboard'))

# ----------------------------------------------------------------------
# Add confidential note to request
# ----------------------------------------------------------------------
@care_bp.route('/<int:request_id>/note', methods=['POST'])
@pastoral_required()
def care_add_note(request_id):
    note = request.form.get('note', '').strip()
    is_private = 1 if request.form.get('is_private') else 0

    if not note:
        flash("Note cannot be empty.", "error")
        return redirect(url_for('pastoral.care.care_request_detail', request_id=request_id))

    if contains_censored_word(note):
        flash("Prohibited content detected.", "error")
        return redirect(url_for('pastoral.care.care_request_detail', request_id=request_id))

    add_care_note(request_id, session['user_id'], note, is_private)
    log_change(session['user_id'], 'create', request_id, "Added note", "Added pastoral care note")

    flash("Note added successfully.", "success")
    return redirect(url_for('pastoral.care.care_request_detail', request_id=request_id))

# ----------------------------------------------------------------------
# Delete entire care request (admin/owner only - add role check later if needed)
# ----------------------------------------------------------------------
@care_bp.route('/<int:request_id>/delete', methods=['POST'])
@pastoral_required()
def care_delete(request_id):
    delete_care_request(request_id)
    log_change(session['user_id'], 'delete', request_id, None, "Deleted pastoral care request")
    flash("Care request permanently deleted.", "success")
    return redirect(url_for('pastoral.care.care_dashboard'))