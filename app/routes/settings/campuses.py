# Multi-campus management (Settings).

from flask import render_template, request, redirect, url_for, flash, session

from . import settings_bp, has_section_permission, load_settings
from app.models import campuses as campus_model
from app.models.log import log_change
from app.models.db import get_db
import pymysql


@settings_bp.route('/campuses', methods=['GET', 'POST'])
def campuses():
    if not has_section_permission('general') and session.get('user_role') not in ('Admin', 'Owner'):
        flash('You do not have permission to manage campuses.', 'error')
        return redirect(url_for('settings.general'))

    if request.method == 'POST':
        action = request.form.get('action') or 'save_flags'
        try:
            if action == 'save_flags':
                campus_model.set_multi_campus_enabled(
                    request.form.get('multi_campus_enabled') == '1',
                    int(request.form.get('default_campus_id')) if request.form.get('default_campus_id') else None,
                    campus_all_view_admin_only=request.form.get('campus_all_view_admin_only') == '1',
                )
                flash('Multi-campus settings saved.', 'success')
                log_change(session['user_id'], 'update', change_details='Updated multi-campus settings')
            elif action == 'save_campus':
                cid = request.form.get('campus_id')
                campus_model.save_campus({
                    'code': request.form.get('code'),
                    'name': request.form.get('name'),
                    'short_name': request.form.get('short_name'),
                    'address': request.form.get('address'),
                    'city': request.form.get('city'),
                    'state': request.form.get('state'),
                    'postal_code': request.form.get('postal_code'),
                    'phone': request.form.get('phone'),
                    'email': request.form.get('email'),
                    'pastor_name': request.form.get('pastor_name'),
                    'timezone': request.form.get('timezone'),
                    'color': request.form.get('color') or '#22d3ee',
                    'is_primary': request.form.get('is_primary') == '1',
                    'is_active': request.form.get('is_active') != '0',
                    'sort_order': request.form.get('sort_order') or 0,
                    'notes': request.form.get('notes'),
                    'content_isolation': request.form.get('content_isolation') == '1',
                }, int(cid) if cid else None)
                flash('Campus saved.', 'success')
                log_change(session['user_id'], 'update', change_details=f"Saved campus {request.form.get('name')}")
            elif action == 'deactivate':
                campus_model.delete_campus(int(request.form.get('campus_id') or 0))
                flash('Campus deactivated.', 'success')
            elif action == 'assign_member':
                campus_model.add_user_to_campus(
                    int(request.form.get('user_id') or 0),
                    int(request.form.get('campus_id') or 0),
                    is_home=request.form.get('is_home') == '1',
                )
                flash('Member linked to campus.', 'success')
            elif action == 'remove_member':
                campus_model.remove_user_from_campus(
                    int(request.form.get('user_id') or 0),
                    int(request.form.get('campus_id') or 0),
                )
                flash('Member removed from campus.', 'success')
        except Exception as e:
            flash(str(e), 'error')
        return redirect(url_for('settings.campuses'))

    settings = load_settings()
    campuses_list = campus_model.list_campuses(active_only=False)
    members_by_campus = {c['id']: campus_model.list_campus_members(c['id']) for c in campuses_list}
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        """
        SELECT id, first_name, last_name, email FROM users
        WHERE COALESCE(needs_approval,0)=0
        ORDER BY last_name, first_name LIMIT 500
        """
    )
    people = list(cur.fetchall() or [])
    return render_template(
        'settings/campuses.html',
        settings=settings,
        campuses=campuses_list,
        members_by_campus=members_by_campus,
        people=people,
        multi_enabled=campus_model.multi_campus_enabled(),
        all_view_admin_only=campus_model.campus_all_view_admin_only(),
    )
