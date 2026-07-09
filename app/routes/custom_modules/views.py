from flask import render_template, request, redirect, url_for, flash, session, abort
from app.utils.decorators import login_required
from app.models.log import log_change
from pymysql import IntegrityError

from . import custom_modules_bp
from .queries import (
    get_module_by_slug, get_records, get_record,
    create_record, update_record, delete_record,
)
from .permissions import can_view_module, can_manage_module
from .schemas import validate_record_data, MODULE_THEMES


@custom_modules_bp.route('/<slug>/')
def module_list(slug):
    module = get_module_by_slug(slug)
    if not module:
        flash('Module not found.', 'error')
        return redirect(url_for('dashboard.dashboard'))

    user_id = session.get('user_id')
    user_role = session.get('user_role')
    is_logged_in = bool(user_id)

    if not can_view_module(module, user_id, user_role, is_logged_in):
        if not is_logged_in:
            flash('Please log in to view this module.', 'error')
            return redirect(url_for('auth.login'))
        flash('You do not have permission to view this module.', 'error')
        return redirect(url_for('dashboard.dashboard'))

    records = get_records(module['id'])
    can_manage = can_manage_module(module, user_id, user_role)
    schema = module.get('schema') or {}

    return render_template(
        'custom_modules/list.html',
        module=module,
        records=records,
        schema=schema,
        can_manage=can_manage,
        themes=MODULE_THEMES,
    )


@custom_modules_bp.route('/<slug>/add', methods=['GET', 'POST'])
@login_required
def add_record(slug):
    module = get_module_by_slug(slug)
    if not module:
        abort(404)

    user_id = session['user_id']
    user_role = session.get('user_role')
    if not can_manage_module(module, user_id, user_role):
        flash('You do not have permission to add records here.', 'error')
        return redirect(url_for('custom_modules.module_list', slug=slug))

    schema = module.get('schema') or {}

    if request.method == 'POST':
        clean, err = validate_record_data(schema, request.form)
        if err:
            flash(err, 'error')
        else:
            title = clean.pop('_title', 'Untitled')
            try:
                rid = create_record(module['id'], title, clean, user_id)
                log_change(user_id, 'create', target_id=rid,
                           change_details=f'Added {schema.get("record_label", "record")} to module {module["name"]}')
                flash('Record added.', 'success')
                return redirect(url_for('custom_modules.module_list', slug=slug))
            except Exception:
                flash('Could not save record.', 'error')

    return render_template(
        'custom_modules/record_form.html',
        module=module,
        schema=schema,
        record=None,
        can_manage=True,
        form_action=url_for('custom_modules.add_record', slug=slug),
        themes=MODULE_THEMES,
    )


@custom_modules_bp.route('/<slug>/edit/<int:record_id>', methods=['GET', 'POST'])
@login_required
def edit_record(slug, record_id):
    module = get_module_by_slug(slug)
    if not module:
        abort(404)

    user_id = session['user_id']
    user_role = session.get('user_role')
    if not can_manage_module(module, user_id, user_role):
        flash('You do not have permission to edit records here.', 'error')
        return redirect(url_for('custom_modules.module_list', slug=slug))

    record = get_record(record_id, module['id'])
    if not record:
        flash('Record not found.', 'error')
        return redirect(url_for('custom_modules.module_list', slug=slug))

    schema = module.get('schema') or {}

    if request.method == 'POST':
        clean, err = validate_record_data(schema, request.form)
        if err:
            flash(err, 'error')
        else:
            title = clean.pop('_title', record.get('title', 'Untitled'))
            try:
                update_record(record_id, module['id'], title, clean, user_id)
                log_change(user_id, 'update', target_id=record_id,
                           change_details=f'Updated record in module {module["name"]}')
                flash('Record updated.', 'success')
                return redirect(url_for('custom_modules.module_list', slug=slug))
            except Exception:
                flash('Could not update record.', 'error')

    return render_template(
        'custom_modules/record_form.html',
        module=module,
        schema=schema,
        record=record,
        can_manage=True,
        form_action=url_for('custom_modules.edit_record', slug=slug, record_id=record_id),
        themes=MODULE_THEMES,
    )


@custom_modules_bp.route('/<slug>/delete/<int:record_id>', methods=['POST'])
@login_required
def delete_record_route(slug, record_id):
    module = get_module_by_slug(slug)
    if not module:
        abort(404)

    user_id = session['user_id']
    user_role = session.get('user_role')
    if not can_manage_module(module, user_id, user_role):
        flash('You do not have permission to delete records here.', 'error')
        return redirect(url_for('custom_modules.module_list', slug=slug))

    if delete_record(record_id, module['id']):
        log_change(user_id, 'delete', target_id=record_id,
                   change_details=f'Deleted record from module {module["name"]}')
        flash('Record deleted.', 'success')
    else:
        flash('Record not found.', 'error')

    return redirect(url_for('custom_modules.module_list', slug=slug))