# Volunteer scheduling, rotations, accept/decline.

from flask import Blueprint

volunteers_bp = Blueprint(
    'volunteers',
    __name__,
    url_prefix='/volunteers',
)

from . import views  # noqa: E402, F401

__all__ = ['volunteers_bp']
