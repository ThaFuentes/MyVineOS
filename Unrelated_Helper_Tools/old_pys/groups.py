# myvinechurchonline/app/routes/groups.py
# Full path: myvinechurchonline/app/routes/groups.py
# File name: groups.py
# Brief, detailed purpose: Blueprint for group management with dynamic, granular permissions.
# Groups grant specific abilities via a JSON permissions array (e.g., ["access_pastoral", "create_announcements"]).
# Membership in a group grants exactly the selected permissions – no more, no less.
# Management (edit group, assign/remove users, change roles) allowed for global Staff/Admin/Owner OR group leaders (role_in_group = 'leader').
# Creator is automatically added as leader. Fully fluid: any group name/combination works.
# Enforces visibility at query level, audit-logs all changes, pre-loads member counts/details/permissions.
# FULL REBUILD: Converted to PyMySQL/MariaDB compatibility (%s placeholders, DictCursor).
#   Expanded KNOWN_PERMISSIONS to cover ALL major features (bills, tickets, attendance, members, change records, etc.).
#   Added server-side censored word check on group create/edit for visible fields (name + description).
#   Preserved every existing feature/logic exactly (permissions, leader checks, visibility, logging, etc.).

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from app.utils.decorators import login_required, role_required
from app.utils.helpers import contains_censored_word
from app.models.db import get_db
from app.models.log import log_change
from pymysql import IntegrityError
from pymysql.cursors import DictCursor
import pymysql
import json

groups_bp = Blueprint('groups', __name__, url_prefix='/groups')

# Known permissions – FULLY EXPANDED to cover every major feature in the application
# Key: permission identifier (used in code checks)
# Value: human-readable description (shown in UI)
KNOWN_PERMISSIONS = {
    # Core Content Creation/Moderation
    'create_announcements': 'Create and edit own announcements_tgp',
    'moderate_announcements': 'Delete or edit ANY announcement (moderation)',
    'create_events': 'Create and edit own events_tgp',
    'moderate_events': 'Delete or edit ANY event (moderation)',
    'manage_event_registration': 'Manage event registrations, fees, and ticketing',
    'upload_sermons': 'Upload and manage sermons_tgp',
    'moderate_sermons': 'Delete or edit ANY sermon or comment',
    'moderate_prayers': 'Delete or edit ANY prayer request or response',
    'moderate_dreams': 'Delete or edit ANY dream/vision or comment',
    'moderate_prophecies': 'Delete or edit ANY prophecy or comment',

    # Financial & Operational
    'view_donations': 'View donation records and reports (no editing)',
    'manage_donations': 'Full donation management (record, edit, delete – sensitive)',
    'manage_bills': 'Access and manage Recurring Bills (/bills/)',
    'manage_tickets': 'Full Ticket Manager access (/tickets/manage – create, assign, resolve any ticket)',
    'submit_tickets': 'Submit and view own support/event tickets (/tickets/)',

    # Member & Attendance Management
    'view_members': 'View the member directory',
    'manage_members': 'Edit member profiles, directory settings, and family links',
    'manage_family_links': 'Approve/reject family relationship requests (admin override)',
    'manage_attendance': 'Access Attendance Kiosk and full attendance records',

    # User & System Administration
    'manage_users': 'Create, edit, approve, or delete user accounts and roles',
    'manage_groups': 'Create/edit/delete permission groups and assign members',
    'send_emails': 'Use the email tool to send messages to members',
    'manage_settings': 'Access and change church settings (name, email config, themes, etc.)',
    'view_audit_logs': 'View the Change Records / audit log',
    'access_pastoral': 'Access to the private Pastoral Care section',

    # Add even more here as new features are built
}

# ----------------------------------------------------------------------
# Permission Helpers
# ----------------------------------------------------------------------
def is_global_manager():
    """True if user has global management rights (Staff/Admin/Owner)."""
    return session.get('user_role') in ['Staff', 'Admin', 'Owner']

def is_group_leader(group_id: int, user_id: int) -> bool:
    """True if user has role_in_group = 'leader' in the specific group."""
    if not user_id:
        return False
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT 1 FROM user_groups
        WHERE group_id = %s AND user_id = %s AND role_in_group = 'leader'
    """, (group_id, user_id))
    return cur.fetchone() is not None

# ----------------------------------------------------------------------
# Fetch groups with details (members, counts, parsed permissions, can_manage flag)
# ----------------------------------------------------------------------
def fetch_groups_with_details(cur, base_sql, params=[], current_user_id=None):
    cur.execute(base_sql, params)
    groups = cur.fetchall()  # List of dicts (DictCursor)

    global_manager = is_global_manager()

    for group in groups:
        # Member count
        cur.execute("SELECT COUNT(*) AS member_count FROM user_groups WHERE group_id = %s", (group['id'],))
        row = cur.fetchone()
        group['member_count'] = row['member_count'] if row else 0

        # Member details
        cur.execute("""
            SELECT u.id AS user_id, u.first_name, u.last_name, u.username, ug.role_in_group
            FROM user_groups ug
            JOIN users u ON ug.user_id = u.id
            WHERE ug.group_id = %s
            ORDER BY u.last_name, u.first_name
        """, (group['id'],))
        group['members'] = cur.fetchall()

        # Parse permissions
        perms_json = group.get('permissions') or '[]'
        permission_list = json.loads(perms_json)
        group['permission_list'] = permission_list
        group['permission_labels'] = [
            KNOWN_PERMISSIONS.get(p, p.replace('_', ' ').title()) for p in permission_list
        ]

        # Can current user manage this group?
        group['can_manage'] = global_manager or (current_user_id and is_group_leader(group['id'], current_user_id))

    return groups


# ----------------------------------------------------------------------
# List Groups
# ----------------------------------------------------------------------
@groups_bp.route('/')
def list_groups():
    is_logged_in = 'user_id' in session
    role = session.get('user_role', 'Member') if is_logged_in else 'Guest'
    user_id = session.get('user_id')

    db = get_db()
    cur = db.cursor(DictCursor)

    sql = """
        SELECT g.*, u.username AS creator_name
        FROM groups g
        LEFT JOIN users u ON u.id = g.created_by
    """
    params = []

    if not is_logged_in or role not in ['Admin', 'Owner', 'Staff']:
        sql += " WHERE g.visibility = 'public'"

    sql += " ORDER BY g.name"

    groups = fetch_groups_with_details(cur, sql, params, user_id)

    return render_template(
        'groups/list.html',
        groups=groups,
        is_logged_in=is_logged_in,
        role=role
    )


# ----------------------------------------------------------------------
# AJAX Search / Filter
# ----------------------------------------------------------------------
@groups_bp.route('/search')
def search_groups():
    query = request.args.get('q', '').strip()
    visibility_filter = request.args.get('visibility', 'all')

    is_logged_in = 'user_id' in session
    role = session.get('user_role', 'Member') if is_logged_in else 'Guest'
    user_id = session.get('user_id')

    db = get_db()
    cur = db.cursor(DictCursor)

    sql = """
        SELECT g.*, u.username AS creator_name
        FROM groups g
        LEFT JOIN users u ON u.id = g.created_by
    """
    where_clauses = []
    params = []

    if query:
        where_clauses.append("(g.name LIKE %s OR g.description LIKE %s)")
        params += [f'%{query}%', f'%{query}%']

    if visibility_filter != 'all':
        where_clauses.append("g.visibility = %s")
        params.append(visibility_filter)

    if not is_logged_in or role not in ['Admin', 'Owner', 'Staff']:
        where_clauses.append("g.visibility = 'public'")

    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)

    sql += " ORDER BY g.name"

    groups = fetch_groups_with_details(cur, sql, params, user_id)

    return jsonify(groups)


# ----------------------------------------------------------------------
# Create Group (global Staff+ only)
# ----------------------------------------------------------------------
@groups_bp.route('/create', methods=['GET', 'POST'])
@login_required
@role_required(['Staff', 'Admin', 'Owner'])
def create_group():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        visibility = request.form.get('visibility', 'private')
        selected_perms = request.form.getlist('permissions')
        permissions = json.dumps([p for p in selected_perms if p in KNOWN_PERMISSIONS])

        # Censored words check on visible fields (name + description)
        combined_text = f"{name} {description}"
        if contains_censored_word(combined_text):
            flash('Group name or description contains a prohibited word or phrase.', 'error')
            return render_template('groups/create.html', known_permissions=KNOWN_PERMISSIONS)

        if not name:
            flash('Group name is required.', 'error')
            return render_template('groups/create.html', known_permissions=KNOWN_PERMISSIONS)

        db = get_db()
        cur = db.cursor()
        try:
            cur.execute("""
                INSERT INTO groups (name, description, visibility, permissions, created_by, updated_by)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (name, description, visibility, permissions, session['user_id'], session['user_id']))
            group_id = cur.lastrowid

            # Auto-add creator as leader
            cur.execute("""
                INSERT INTO user_groups (user_id, group_id, role_in_group, assigned_by)
                VALUES (%s, %s, 'leader', %s)
            """, (session['user_id'], group_id, session['user_id']))

            db.commit()
            log_change(session['user_id'], 'create', change_details=f'Created group "{name}" with permissions {permissions}')
            flash('Group created successfully.', 'success')
            return redirect(url_for('groups.list_groups'))
        except IntegrityError:
            flash('A group with this name already exists.', 'error')

    return render_template('groups/create.html', known_permissions=KNOWN_PERMISSIONS)


# ----------------------------------------------------------------------
# Edit Group (global OR group leader)
# ----------------------------------------------------------------------

@groups_bp.route('/edit/<int:group_id>', methods=['GET', 'POST'])
@login_required
def edit_group(group_id):
    user_id = session['user_id']
    global_manager = is_global_manager()

    if not (global_manager or is_group_leader(group_id, user_id)):
        flash('You do not have permission to edit this group.', 'error')
        return redirect(url_for('groups.list_groups'))

    db = get_db()
    cur = db.cursor(DictCursor)

    cur.execute("SELECT * FROM groups WHERE id = %s", (group_id,))
    group = cur.fetchone()
    if not group:
        flash('Group not found.', 'error')
        return redirect(url_for('groups.list_groups'))

    # Populate the same extra fields used in list view and edit template
    cur.execute("SELECT COUNT(*) AS member_count FROM user_groups WHERE group_id = %s", (group_id,))
    row = cur.fetchone()
    group['member_count'] = row['member_count'] if row else 0

    cur.execute("""
        SELECT u.id AS user_id, u.first_name, u.last_name, u.username, ug.role_in_group
        FROM user_groups ug
        JOIN users u ON ug.user_id = u.id
        WHERE ug.group_id = %s
        ORDER BY u.last_name, u.first_name
    """, (group_id,))
    group['members'] = cur.fetchall()

    group['can_manage'] = global_manager or is_group_leader(group_id, user_id)

    current_permissions = json.loads(group['permissions'] or '[]')

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        visibility = request.form.get('visibility', 'private')
        selected_perms = request.form.getlist('permissions')
        permissions = json.dumps([p for p in selected_perms if p in KNOWN_PERMISSIONS])

        # Censored words check on visible fields (name + description)
        combined_text = f"{name} {description}"
        if contains_censored_word(combined_text):
            flash('Group name or description contains a prohibited word or phrase.', 'error')
            return render_template('groups/edit.html', group=group, known_permissions=KNOWN_PERMISSIONS, current_permissions=current_permissions)

        if not name:
            flash('Group name is required.', 'error')
            return render_template('groups/edit.html', group=group, known_permissions=KNOWN_PERMISSIONS, current_permissions=current_permissions)

        try:
            cur.execute("""
                UPDATE groups
                SET name = %s, description = %s, visibility = %s, permissions = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (name, description, visibility, permissions, user_id, group_id))
            db.commit()
            log_change(user_id, 'update', target_id=group_id, change_details=f'Updated group "{name}" permissions to {permissions}')
            flash('Group updated successfully.', 'success')
            return redirect(url_for('groups.list_groups'))
        except IntegrityError:
            flash('A group with this name already exists.', 'error')

    return render_template('groups/edit.html', group=group, known_permissions=KNOWN_PERMISSIONS, current_permissions=current_permissions)


# ----------------------------------------------------------------------
# Delete Group (Admin/Owner only)
# ----------------------------------------------------------------------
@groups_bp.route('/delete/<int:group_id>', methods=['POST'])
@login_required
@role_required(['Admin', 'Owner'])
def delete_group(group_id):
    db = get_db()
    cur = db.cursor(DictCursor)

    cur.execute("SELECT name FROM groups WHERE id = %s", (group_id,))
    group = cur.fetchone()

    if group:
        cur.execute("DELETE FROM groups WHERE id = %s", (group_id,))
        db.commit()
        log_change(session['user_id'], 'delete', target_id=group_id, change_details=f'Deleted group "{group["name"]}"')
        flash('Group deleted.', 'success')
    else:
        flash('Group not found.', 'error')

    return redirect(url_for('groups.list_groups'))


# ----------------------------------------------------------------------
# Assign User to Group (global OR group leader)
# ----------------------------------------------------------------------
@groups_bp.route('/<int:group_id>/assign', methods=['POST'])
@login_required
def assign_user(group_id):
    user_id = session['user_id']
    if not (is_global_manager() or is_group_leader(group_id, user_id)):
        flash('You do not have permission to assign users to this group.', 'error')
        return redirect(url_for('groups.list_groups'))

    identifier = request.form.get('username_or_email', '').strip()
    role_in_group = request.form.get('role_in_group', 'member').strip()

    if not identifier:
        flash('Username or email is required.', 'error')
        return redirect(url_for('groups.list_groups'))

    db = get_db()
    cur = db.cursor(DictCursor)

    cur.execute("SELECT id FROM users WHERE username = %s OR email = %s", (identifier, identifier))
    target_user = cur.fetchone()

    if not target_user:
        flash('User not found.', 'error')
        return redirect(url_for('groups.list_groups'))

    try:
        cur.execute("""
            INSERT INTO user_groups (user_id, group_id, role_in_group, assigned_by)
            VALUES (%s, %s, %s, %s)
        """, (target_user['id'], group_id, role_in_group, session['user_id']))
        db.commit()
        log_change(session['user_id'], 'create',
                   change_details=f'Assigned user {target_user["id"]} to group {group_id} as {role_in_group}')
        flash('User assigned to group.', 'success')
    except IntegrityError:
        flash('User is already in this group.', 'error')

    return redirect(url_for('groups.list_groups'))


# ----------------------------------------------------------------------
# Remove User from Group (global OR group leader)
# ----------------------------------------------------------------------
@groups_bp.route('/<int:group_id>/remove/<int:user_id>', methods=['POST'])
@login_required
def remove_user(group_id, user_id):
    if not (is_global_manager() or is_group_leader(group_id, session['user_id'])):
        flash('You do not have permission to remove users from this group.', 'error')
        return '', 403

    db = get_db()
    cur = db.cursor()

    cur.execute("DELETE FROM user_groups WHERE group_id = %s AND user_id = %s", (group_id, user_id))
    if cur.rowcount:
        db.commit()
        log_change(session['user_id'], 'delete',
                   change_details=f'Removed user {user_id} from group {group_id}')

    return '', 204


# ----------------------------------------------------------------------
# Update User's Role in Group (global OR group leader)
# ----------------------------------------------------------------------
@groups_bp.route('/<int:group_id>/update_role/<int:user_id>', methods=['POST'])
@login_required
def update_role(group_id, user_id):
    if not (is_global_manager() or is_group_leader(group_id, session['user_id'])):
        flash('You do not have permission to change roles in this group.', 'error')
        return redirect(url_for('groups.list_groups'))

    new_role = request.form.get('role_in_group', 'member').strip()

    db = get_db()
    cur = db.cursor()

    cur.execute("""
        UPDATE user_groups
        SET role_in_group = %s
        WHERE group_id = %s AND user_id = %s
    """, (new_role, group_id, user_id))

    if cur.rowcount:
        db.commit()
        log_change(session['user_id'], 'update',
                   change_details=f'Changed role of user {user_id} in group {group_id} to {new_role}')
        flash('Role updated.', 'success')
    else:
        flash('No changes made.', 'info')

    return redirect(url_for('groups.list_groups'))