from flask import render_template, request, redirect, url_for, flash, session, abort
from app.utils.decorators import login_required
from app.models.log import log_change
from pymysql import IntegrityError

from . import custom_modules_bp
from .queries import (
    get_module_by_slug, get_records, get_record,
    create_record, update_record, delete_record,
    update_module_settings, ensure_settings_column, default_bus_settings,
)
from .permissions import can_view_module, can_manage_module
from .schemas import validate_record_data, enrich_schema_for_module, MODULE_THEMES


def _is_bus(module: dict) -> bool:
    return (module.get('type_key') or '') == 'bus_routes' or bool(
        (module.get('schema') or {}).get('bus_module')
    )


@custom_modules_bp.route('/<slug>/')
def module_list(slug):
    ensure_settings_column()
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
    schema = enrich_schema_for_module(module.get('schema') or {}, module)

    return render_template(
        'custom_modules/list.html',
        module=module,
        records=records,
        schema=schema,
        can_manage=can_manage,
        themes=MODULE_THEMES,
        is_bus=_is_bus(module),
        bus_settings=module.get('settings') if _is_bus(module) else None,
    )


@custom_modules_bp.route('/<slug>/settings', methods=['GET', 'POST'])
@login_required
def module_settings(slug):
    """Bus (and future) module owner settings: locations, approved routes, radius."""
    ensure_settings_column()
    module = get_module_by_slug(slug)
    if not module:
        abort(404)

    user_id = session['user_id']
    user_role = session.get('user_role')
    if not can_manage_module(module, user_id, user_role):
        flash('Only bus managers / group owners can edit bus settings.', 'error')
        return redirect(url_for('custom_modules.module_list', slug=slug))

    if not _is_bus(module):
        flash('Settings for this app type are not available yet.', 'info')
        return redirect(url_for('custom_modules.module_list', slug=slug))

    settings = module.get('settings') or default_bus_settings()

    if request.method == 'POST':
        bus_start = (request.form.get('bus_start_location') or '').strip()[:500]
        church = (request.form.get('church_location') or '').strip()[:500]
        try:
            max_radius = float(request.form.get('max_radius_miles') or 25)
        except (TypeError, ValueError):
            max_radius = 25.0
        if max_radius < 1:
            max_radius = 1.0
        if max_radius > 200:
            max_radius = 200.0

        # Parse approved routes from repeated form fields
        names = request.form.getlist('route_name')
        maxes = request.form.getlist('route_max_miles')
        notes_list = request.form.getlist('route_notes')
        approved = []
        seen = set()
        for i, name in enumerate(names):
            name = (name or '').strip()[:120]
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            raw_max = maxes[i] if i < len(maxes) else ''
            try:
                rmax = float(raw_max) if str(raw_max).strip() != '' else None
            except (TypeError, ValueError):
                rmax = None
            if rmax is not None:
                if rmax < 1:
                    rmax = 1.0
                if rmax > max_radius:
                    rmax = max_radius
            note = (notes_list[i] if i < len(notes_list) else '') or ''
            approved.append({
                'name': name,
                'max_miles': rmax,
                'notes': note.strip()[:500],
            })

        if not bus_start or not church:
            flash('Set both the bus starting location and the church location.', 'error')
        elif not approved:
            flash('Add at least one approved route (the corridors you are willing to run).', 'error')
        else:
            new_settings = {
                'bus_start_location': bus_start,
                'church_location': church,
                'max_radius_miles': max_radius,
                'approved_routes': approved,
            }
            try:
                update_module_settings(module['id'], new_settings, user_id)
                log_change(
                    user_id,
                    'update',
                    target_id=module['id'],
                    change_details=f'Updated bus settings for {module["name"]} ({len(approved)} routes, max {max_radius} mi)',
                )
                flash('Bus settings saved. Stops must stay inside your routes and radius.', 'success')
                return redirect(url_for('custom_modules.module_list', slug=slug))
            except Exception as e:
                flash(f'Could not save settings: {e}', 'error')

        settings = {
            'bus_start_location': bus_start,
            'church_location': church,
            'max_radius_miles': max_radius,
            'approved_routes': approved,
        }

    return render_template(
        'custom_modules/bus_settings.html',
        module=module,
        settings=settings,
        can_manage=True,
        schema=module.get('schema') or {},
        themes=MODULE_THEMES,
    )


@custom_modules_bp.route('/<slug>/add', methods=['GET', 'POST'])
@login_required
def add_record(slug):
    ensure_settings_column()
    module = get_module_by_slug(slug)
    if not module:
        abort(404)

    user_id = session['user_id']
    user_role = session.get('user_role')
    if not can_manage_module(module, user_id, user_role):
        flash('You do not have permission to add records here.', 'error')
        return redirect(url_for('custom_modules.module_list', slug=slug))

    schema = enrich_schema_for_module(module.get('schema') or {}, module)

    if _is_bus(module):
        st = module.get('settings') or {}
        if not st.get('church_location') or not st.get('bus_start_location') or not st.get('approved_routes'):
            flash(
                'Set the bus start location, church location, and approved routes before adding stops.',
                'error',
            )
            return redirect(url_for('custom_modules.module_settings', slug=slug))

    if request.method == 'POST':
        clean, err = validate_record_data(schema, request.form, module=module)
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
        is_bus=_is_bus(module),
        bus_settings=module.get('settings') if _is_bus(module) else None,
    )


@custom_modules_bp.route('/<slug>/edit/<int:record_id>', methods=['GET', 'POST'])
@login_required
def edit_record(slug, record_id):
    ensure_settings_column()
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

    schema = enrich_schema_for_module(module.get('schema') or {}, module)

    if request.method == 'POST':
        clean, err = validate_record_data(schema, request.form, module=module)
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
        is_bus=_is_bus(module),
        bus_settings=module.get('settings') if _is_bus(module) else None,
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