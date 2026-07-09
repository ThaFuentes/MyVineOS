from functools import wraps
from flask import Blueprint, flash, redirect, session, url_for
from app.utils.decorators import login_required
from app.models.worship.shared import can_view_worship

worship_bp = Blueprint('worship', __name__, url_prefix='/worship', template_folder='../../templates/worship')


def worship_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not can_view_worship():
            flash('The Worship Team area is for team members and church leaders.', 'error')
            return redirect(url_for('dashboard.dashboard'))
        return view_func(*args, **kwargs)
    return wrapper


from . import views  # noqa: E402, F401