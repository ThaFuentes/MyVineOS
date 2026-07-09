# Central access control for The Gathering Place Manager.

from functools import wraps
from flask import session, redirect, url_for, flash
from app.routes.groups.gathering_place import can_access_gathering_place


def user_can_access_gathering_place() -> bool:
    return can_access_gathering_place(
        session.get('user_id'),
        session.get('user_role'),
    )


def gathering_place_required(f):
    """Must be Owner or a member of the Gathering Place Managers group."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access the Gathering Place Manager.', 'error')
            return redirect(url_for('auth.login'))

        if user_can_access_gathering_place():
            return f(*args, **kwargs)

        flash(
            'The Gathering Place Manager requires membership in the '
            '"Gathering Place Managers" group. Contact the church Owner.',
            'error',
        )
        return redirect(url_for('dashboard.dashboard'))

    return decorated_function