# app/routes/groups/views.py
# Full path: MyVineChurch/app/routes/groups/views.py
# File name: views.py
# Brief, detailed purpose: All route handlers (controllers) for the Groups blueprint.
# - Every single function name and endpoint from the original groups.py is preserved exactly.
# - All database work moved to queries.py
# - All form validation + censorship moved to forms.py
# - All helpers moved to utils.py
# - 100% original behavior preserved + improved edit experience (full permission checkboxes + member management)

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from app.utils.decorators import login_required, role_required, permission_required
from app.utils.permissions import user_has_permission
from app.models.db import get_db
from app.models.log import log_change
from pymysql import IntegrityError
from pymysql.cursors import DictCursor
import json

# Package-relative blueprint
from . import groups_bp

# Import from our modular files (no renaming)
from .queries import (
    get_groups_list,
    search_groups,
    create_group,
    update_group,
    delete_group as delete_group_record,
    assign_user_to_group,
    remove_user_from_group,
    update_user_role_in_group,
    is_group_leader,
    lookup_user_by_username_or_email,
    search_users_for_group_assignment,
)
from .forms import validate_create_group_form, validate_edit_group_form
from .utils import (
    KNOWN_PERMISSIONS,
    is_global_manager,
    normalize_group_role,
    can_assign_group_manager_role,
    group_role_label,
    build_group_permissions_context,
    resolve_group_permissions,
)
from .gathering_place import (
    is_gathering_place_group_id,
    is_gathering_place_group_name,
    can_manage_group_members,
    can_edit_group_record,
)


def _render_group_form(template, **extra):
    """Render create/edit group with full permission editor context."""
    db = get_db()
    cur = db.cursor(DictCursor)
    user_id = session.get('user_id')
    user_role = session.get('user_role')
    current = extra.pop('current_permissions', None)
    if current is None:
        current = extra.get('group', {}).get('permissions')
        if isinstance(current, str):
            try:
                current = json.loads(current or '[]')
            except (TypeError, json.JSONDecodeError):
                current = []
        current = current or []
    ctx = build_group_permissions_context(cur, user_id, user_role, current)
    return render_template(template, **extra, **ctx)


def _can_admin_permission_groups() -> bool:
    """Permission Groups admin UI is not for random members."""
    return user_has_permission('manage_groups')


# ----------------------------------------------------------------------
# List Groups (permission admin only — not open to all members)
# ----------------------------------------------------------------------
@groups_bp.route('/')
@login_required
@permission_required('manage_groups')
def list_groups():
    is_logged_in = 'user_id' in session
    role = session.get('user_role', 'Member') if is_logged_in else 'Guest'
    user_id = session.get('user_id')

    groups = get_groups_list(is_logged_in=is_logged_in, role=role, user_id=user_id)

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
@login_required
@permission_required('manage_groups')
def search_groups_route():
    query = request.args.get('q', '').strip()
    visibility_filter = request.args.get('visibility', 'all')

    is_logged_in = 'user_id' in session
    role = session.get('user_role', 'Member') if is_logged_in else 'Guest'
    user_id = session.get('user_id')

    groups = search_groups(
        query=query,
        visibility_filter=visibility_filter,
        is_logged_in=is_logged_in,
        role=role,
        user_id=user_id
    )

    return jsonify(groups)


# ----------------------------------------------------------------------
# Create Group (manage_groups / Staff+)
# ----------------------------------------------------------------------
@groups_bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('manage_groups')
def create_group():
    user_id = session['user_id']
    user_role = session.get('user_role')

    if request.method == 'POST':
        clean_data = validate_create_group_form(request.form)
        if not clean_data:
            return _render_group_form(
                'groups/create.html',
                current_permissions=request.form.getlist('permissions'),
            )

        db = get_db()
        cur = db.cursor(DictCursor)
        resolved = resolve_group_permissions(
            cur, user_id, user_role, [], clean_data['permissions']
        )
        permissions_json = json.dumps(resolved)

        try:
            group_id = create_group(
                name=clean_data['name'],
                description=clean_data['description'],
                visibility=clean_data['visibility'],
                permissions=permissions_json,
                user_id=user_id
            )
            log_change(
                user_id, 'create',
                change_details=f'Created group "{clean_data["name"]}" with permissions {permissions_json}',
            )
            flash('Group created successfully.', 'success')
            return redirect(url_for('groups.list_groups'))
        except IntegrityError:
            flash('A group with this name already exists.', 'error')
            return _render_group_form(
                'groups/create.html',
                current_permissions=resolved,
            )

    return _render_group_form('groups/create.html', current_permissions=[])


# ----------------------------------------------------------------------
# Edit Group (global OR group leader) - IMPROVED
# ----------------------------------------------------------------------
@groups_bp.route('/edit/<int:group_id>', methods=['GET', 'POST'])
@login_required
def edit_group(group_id):
    user_id = session['user_id']
    user_role = session.get('user_role')
    global_manager = is_global_manager()
    # Permission matrix editing: manage_groups (or Staff+).
    # Group leaders may still manage members of their own group only.
    can_admin = _can_admin_permission_groups()
    can_lead = (
        can_edit_group_record(group_id, user_id, user_role)
        or can_manage_group_members(group_id, user_id, user_role)
    )
    if not (can_admin or can_lead):
        flash('You do not have permission to view or manage this group.', 'error')
        return redirect(url_for('dashboard.dashboard'))

    db = get_db()
    cur = db.cursor(DictCursor)
    cur.execute("SELECT * FROM groups WHERE id = %s", (group_id,))
    group = cur.fetchone()

    if not group:
        flash('Group not found.', 'error')
        return redirect(url_for('groups.list_groups'))

    # Populate extra fields for template
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

    group['is_gathering_place_group'] = is_gathering_place_group_id(group_id)
    group['can_manage_members'] = global_manager or can_manage_group_members(group_id, user_id, user_role)
    group['can_edit'] = global_manager or can_edit_group_record(group_id, user_id, user_role)
    group['can_manage'] = group['can_manage_members'] or group['can_edit']
    group['can_change_roles'] = can_assign_group_manager_role()

    # Current permissions as list for checkboxes
    try:
        current_permissions = json.loads(group.get('permissions') or '[]')
    except (TypeError, json.JSONDecodeError):
        current_permissions = []
    if not isinstance(current_permissions, list):
        current_permissions = []

    if request.method == 'POST':
        if not group['can_edit']:
            flash('You do not have permission to edit this group\'s settings.', 'error')
            return redirect(url_for('groups.edit_group', group_id=group_id))

        clean_data = validate_edit_group_form(request.form)
        if not clean_data:
            return _render_group_form(
                'groups/edit.html',
                group=group,
                current_permissions=request.form.getlist('permissions') or current_permissions,
            )

        resolved = resolve_group_permissions(
            cur, user_id, user_role, current_permissions, clean_data['permissions']
        )
        permissions_json = json.dumps(resolved)

        try:
            update_group(
                group_id=group_id,
                name=clean_data['name'],
                description=clean_data['description'],
                visibility=clean_data['visibility'],
                permissions=permissions_json,
                user_id=user_id
            )
            log_change(user_id, 'update', target_id=group_id,
                       change_details=f'Updated group "{clean_data["name"]}" permissions')
            flash('Group updated successfully.', 'success')
            return redirect(url_for('groups.edit_group', group_id=group_id))
        except IntegrityError:
            flash('A group with this name already exists.', 'error')
            return _render_group_form(
                'groups/edit.html',
                group=group,
                current_permissions=resolved,
            )

    return _render_group_form(
        'groups/edit.html',
        group=group,
        current_permissions=current_permissions,
    )


# ----------------------------------------------------------------------
# Delete Group (Admin/Owner only)
# ----------------------------------------------------------------------
@groups_bp.route('/delete/<int:group_id>', methods=['POST'])
@login_required
@permission_required('manage_groups')
@role_required(['Admin', 'Owner'])
def delete_group(group_id):
    if is_gathering_place_group_id(group_id):
        flash('The Gathering Place Managers group is protected and cannot be deleted.', 'error')
        return redirect(url_for('groups.list_groups'))
    try:
        delete_group_record(group_id)
        log_change(session['user_id'], 'delete', target_id=group_id, change_details=f'Deleted group ID {group_id}')
        flash('Group deleted.', 'success')
    except Exception:
        flash('Group not found or could not be deleted.', 'error')

    return redirect(url_for('groups.list_groups'))


# ----------------------------------------------------------------------
# Live user search for add-member UI on edit page
# ----------------------------------------------------------------------
@groups_bp.route('/search_users')
@login_required
def search_users():
    query = request.args.get('q', '').strip()
    group_id = request.args.get('group_id', type=int)
    user_id = session['user_id']
    user_role = session.get('user_role')

    if not group_id:
        return jsonify([])

    if not can_manage_group_members(group_id, user_id, user_role):
        return jsonify({'error': 'Permission denied'}), 403

    users = search_users_for_group_assignment(group_id, query)
    return jsonify(users)


# ----------------------------------------------------------------------
# Assign User to Group (global OR group leader)
# ----------------------------------------------------------------------
@groups_bp.route('/<int:group_id>/assign', methods=['POST'])
@login_required
def assign_user(group_id):
    user_id = session['user_id']
    user_role = session.get('user_role')
    if not can_manage_group_members(group_id, user_id, user_role):
        flash('You do not have permission to assign users to this group.', 'error')
        return redirect(url_for('groups.list_groups'))

    target_user_id = request.form.get('user_id', type=int)
    identifier = request.form.get('username_or_email', '').strip()
    role_in_group = normalize_group_role(request.form.get('role_in_group', 'member'))
    if role_in_group == 'leader' and not can_assign_group_manager_role():
        flash('Only site Owner, Admin, or Staff can assign the Group Manager role.', 'error')
        return redirect(request.referrer or url_for('groups.edit_group', group_id=group_id))

    if not target_user_id and identifier:
        target_user = lookup_user_by_username_or_email(identifier)
        if not target_user:
            flash('User not found. Enter an exact username or email.', 'error')
            return redirect(request.referrer or url_for('groups.edit_group', group_id=group_id))
        target_user_id = target_user['id']

    if not target_user_id:
        flash('Select a user to add, or enter a username or email.', 'error')
        return redirect(request.referrer or url_for('groups.edit_group', group_id=group_id))

    try:
        assign_user_to_group(group_id, target_user_id, role_in_group, user_id)
        log_change(user_id, 'create',
                   change_details=f'Assigned user {target_user_id} to group {group_id} as {role_in_group}')
        flash(f'User assigned as {group_role_label(role_in_group)}.', 'success')
    except IntegrityError:
        flash('User is already in this group.', 'error')

    return redirect(request.referrer or url_for('groups.edit_group', group_id=group_id))


# ----------------------------------------------------------------------
# Remove User from Group (global OR group leader)
# ----------------------------------------------------------------------
@groups_bp.route('/<int:group_id>/remove/<int:user_id>', methods=['POST'])
@login_required
def remove_user(group_id, user_id):
    if not can_manage_group_members(group_id, session['user_id'], session.get('user_role')):
        flash('You do not have permission to remove users from this group.', 'error')
        return redirect(request.referrer or url_for('groups.list_groups'))

    try:
        if remove_user_from_group(group_id, user_id):
            log_change(session['user_id'], 'delete', change_details=f'Removed user {user_id} from group {group_id}')
            flash('User removed from group.', 'success')
        else:
            flash('User was not in this group.', 'info')
    except Exception:
        flash('Could not remove user from group.', 'error')

    return redirect(request.referrer or url_for('groups.edit_group', group_id=group_id))


# ----------------------------------------------------------------------
# Update User's Role in Group (global OR group leader)
# ----------------------------------------------------------------------
@groups_bp.route('/<int:group_id>/update_role/<int:user_id>', methods=['POST'])
@login_required
def update_role(group_id, user_id):
    if not can_manage_group_members(group_id, session['user_id'], session.get('user_role')):
        flash('You do not have permission to change roles in this group.', 'error')
        return redirect(url_for('groups.list_groups'))

    if not can_assign_group_manager_role():
        flash('Only site Owner, Admin, or Staff can change in-group roles.', 'error')
        return redirect(request.referrer or url_for('groups.edit_group', group_id=group_id))

    new_role = normalize_group_role(request.form.get('role_in_group', 'member'))

    try:
        if update_user_role_in_group(group_id, user_id, new_role):
            log_change(session['user_id'], 'update', change_details=f'Changed role of user {user_id} in group {group_id} to {new_role}')
            flash(f'Role updated to {group_role_label(new_role)}.', 'success')
        else:
            flash('No changes made.', 'info')
    except Exception:
        flash('Could not update role.', 'error')

    return redirect(request.referrer or url_for('groups.edit_group', group_id=group_id))