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
    if choice in ('all', '', '0'):
        campus_model.set_session_campus(None, view_all=True)
        flash('Viewing all campuses.', 'info')
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
        campus_model.set_session_campus(cid, view_all=False)
        flash(f'Campus: {c.get("short_name") or c.get("name")}', 'success')

    return redirect(request.referrer or url_for('dashboard.dashboard'))
