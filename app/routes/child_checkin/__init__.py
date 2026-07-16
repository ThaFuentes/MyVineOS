# Child Check-In System — kiosk, secure pickup, classrooms, labels.

from flask import Blueprint

child_checkin_bp = Blueprint(
    'child_checkin',
    __name__,
    url_prefix='/child-checkin',
)

from . import views  # noqa: E402, F401

__all__ = ['child_checkin_bp']
