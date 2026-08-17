# Quick-compose posts from Home / Community Feed.

from flask import Blueprint, request, redirect, url_for, flash, session

from app.utils.decorators import login_required
from app.utils.compose import create_from_compose

compose_bp = Blueprint('compose', __name__, url_prefix='/compose')


@compose_bp.route('/', methods=['POST'])
@login_required
def compose_create():
    nxt = (request.form.get('next') or '').strip()
    ok, dest = create_from_compose(request.form)
    if dest:
        return redirect(dest)
    if nxt and nxt.startswith('/'):
        return redirect(nxt)
    return redirect(url_for('dashboard.dashboard'))
