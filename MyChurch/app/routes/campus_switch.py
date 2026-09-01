# Lightweight campus switcher (session scope) — not under settings auth.

from flask import Blueprint, request, redirect, session, url_for, flash

from app.models import campuses as campus_model
from app.utils.decorators import login_required

campus_switch_bp = Blueprint('campus_switch', __name__)


@campus_switch_bp.route('/campus/switch', methods=['POST'])
@login_required
def switch():
    if not campus_model.multi_campus_enabled():
        flash('Multi-campus is not enabled.', 'error')
        return redirect(request.referrer or url_for('dashboard.dashboard'))

    choice = (request.form.get('campus_id') or '').strip()
    uid = session.get('user_id')

    if choice in ('all', '', '0'):
        if campus_model.campus_all_view_admin_only() and not campus_model.user_is_org_admin(uid):
            flash(
                '“All campuses” is limited to Admins. Isolated branches stay private.',
                'error',
            )
            return redirect(request.referrer or url_for('dashboard.dashboard'))
        campus_model.set_session_campus(None, view_all=True)
        flash('Viewing all campuses (isolated branches still hidden if you are not a member).', 'info')
    else:
        try:
            cid = int(choice)
        except ValueError:
            flash('Invalid campus.', 'error')
            return redirect(request.referrer or url_for('dashboard.dashboard'))
        c = campus_model.get_campus(cid)
        if not c or not c.get('is_active'):
            flash('Campus not found.', 'error')
            return redirect(request.referrer or url_for('dashboard.dashboard'))
        if c.get('content_isolation') and not campus_model.user_can_access_campus(uid, cid):
            flash(
                f'{c.get("short_name") or c.get("name")} keeps its content private to that branch. '
                'Ask an Admin to link you if you serve there.',
                'error',
            )
            return redirect(request.referrer or url_for('dashboard.dashboard'))
        campus_model.set_session_campus(cid, view_all=False)
        iso = ' · private to this branch' if c.get('content_isolation') else ''
        flash(f'Campus: {c.get("short_name") or c.get("name")}{iso}', 'success')

    return redirect(request.referrer or url_for('dashboard.dashboard'))
