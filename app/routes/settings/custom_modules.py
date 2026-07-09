from flask import render_template, request, redirect, url_for, flash, session
from pymysql import IntegrityError

from . import settings_bp, has_section_permission
from app.models.log import log_change
from app.utils.helpers import contains_censored_word
from app.routes.custom_modules.queries import (
    get_module_types, get_all_modules, get_module_by_id,
    create_module, update_module, delete_module, get_groups_for_select,
    create_permission_group_for_module,
)
from app.routes.custom_modules.schemas import (
    MODULE_THEMES, normalize_slug, validate_slug,
)


def _parse_module_form(form):
    type_key = form.get('type_key', '').strip()
    name = form.get('name', '').strip()
    slug = normalize_slug(form.get('slug') or name)
    description = form.get('description', '').strip()
    theme = form.get('theme', 'ocean').strip()
    visibility = form.get('visibility', 'members').strip()
    group_id = form.get('group_id', type=int) or None
    manage_group_id = form.get('manage_group_id', type=int) or None
    show_on_dashboard = form.get('show_on_dashboard') == 'on'
    is_enabled = form.get('is_enabled') == 'on'
    create_group = form.get('create_group') == 'on'

    if not type_key or not name:
        flash('Module type and name are required.', 'error')
        return None
    if contains_censored_word(f'{name} {description}'):
        flash('Name or description contains a prohibited word.', 'error')
        return None
    if not validate_slug(slug):
        flash('URL slug must be 2-64 lowercase letters, numbers, and hyphens.', 'error')
        return None
    if theme not in MODULE_THEMES:
        theme = 'ocean'
    if visibility not in ('public', 'members', 'group'):
        visibility = 'members'
    if visibility == 'group' and not group_id and not create_group:
        flash('Select an access group, or check "Create a permission group" below.', 'error')
        return None

    return {
        'type_key': type_key,
        'name': name,
        'slug': slug,
        'description': description,
        'theme': theme,
        'visibility': visibility,
        'group_id': group_id if visibility == 'group' else None,
        'manage_group_id': manage_group_id,
        'show_on_dashboard': show_on_dashboard,
        'is_enabled': is_enabled,
        'create_group': create_group,
    }


@settings_bp.route('/custom-modules')
def custom_modules_list():
    if session.get('user_role') not in ('Owner', 'Admin'):
        flash('Only Owner or Admin can manage custom modules.', 'error')
        return redirect(url_for('settings.general'))

    modules = get_all_modules(include_disabled=True)
    types = get_module_types()
    return render_template(
        'settings/custom_modules.html',
        modules=modules,
        types=types,
        themes=MODULE_THEMES,
    )


@settings_bp.route('/custom-modules/create', methods=['GET', 'POST'])
def custom_modules_create():
    if session.get('user_role') not in ('Owner', 'Admin'):
        flash('Only Owner or Admin can create custom modules.', 'error')
        return redirect(url_for('settings.general'))

    types = get_module_types()
    groups = get_groups_for_select()

    if request.method == 'POST':
        data = _parse_module_form(request.form)
        if data:
            try:
                if data.get('create_group'):
                    gid = create_permission_group_for_module(
                        data['name'], data['slug'], data.get('description', ''), session['user_id'],
                    )
                    data['visibility'] = 'group'
                    data['group_id'] = gid
                    data['manage_group_id'] = data.get('manage_group_id') or gid

                mid = create_module(data, session['user_id'])
                log_change(session['user_id'], 'create', target_id=mid,
                           change_details=f'Created custom module "{data["name"]}"')
                msg = f'App "{data["name"]}" installed - visit /modules/{data["slug"]}/'
                if data.get('create_group') and data.get('group_id'):
                    msg += f' A permission group was created - add members at Groups -> Edit.'
                flash(msg, 'success')
                if data.get('group_id'):
                    return redirect(url_for('groups.edit_group', group_id=data['group_id']))
                return redirect(url_for('settings.custom_modules_list'))
            except IntegrityError:
                flash('That URL slug is already in use.', 'error')

    return render_template(
        'settings/custom_modules_form.html',
        module=None,
        types=types,
        groups=groups,
        themes=MODULE_THEMES,
    )


@settings_bp.route('/custom-modules/edit/<int:module_id>', methods=['GET', 'POST'])
def custom_modules_edit(module_id):
    if session.get('user_role') not in ('Owner', 'Admin'):
        flash('Only Owner or Admin can edit custom modules.', 'error')
        return redirect(url_for('settings.general'))

    module = get_module_by_id(module_id)
    if not module:
        flash('Module not found.', 'error')
        return redirect(url_for('settings.custom_modules_list'))

    types = get_module_types()
    groups = get_groups_for_select()

    if request.method == 'POST':
        data = _parse_module_form(request.form)
        if data:
            try:
                update_module(module_id, data, session['user_id'])
                log_change(session['user_id'], 'update', target_id=module_id,
                           change_details=f'Updated custom module "{data["name"]}"')
                flash('Module updated.', 'success')
                return redirect(url_for('settings.custom_modules_list'))
            except IntegrityError:
                flash('That URL slug is already in use.', 'error')

    return render_template(
        'settings/custom_modules_form.html',
        module=module,
        types=types,
        groups=groups,
        themes=MODULE_THEMES,
    )


@settings_bp.route('/custom-modules/delete/<int:module_id>', methods=['POST'])
def custom_modules_delete(module_id):
    if session.get('user_role') not in ('Owner', 'Admin'):
        flash('Only Owner or Admin can delete custom modules.', 'error')
        return redirect(url_for('settings.general'))

    module = get_module_by_id(module_id)
    if module and delete_module(module_id):
        log_change(session['user_id'], 'delete', target_id=module_id,
                   change_details=f'Deleted custom module "{module.get("name")}"')
        flash('Module deleted.', 'success')
    else:
        flash('Module not found.', 'error')

    return redirect(url_for('settings.custom_modules_list'))