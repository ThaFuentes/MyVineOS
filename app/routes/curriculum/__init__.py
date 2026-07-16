# Member-facing curriculum / discipleship study paths.

from flask import Blueprint

curriculum_bp = Blueprint(
    'curriculum',
    __name__,
    url_prefix='/study',
)

from . import views  # noqa: E402, F401

__all__ = ['curriculum_bp']
