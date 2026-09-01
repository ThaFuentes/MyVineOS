from flask import Blueprint

bible_bp = Blueprint('bible', __name__, url_prefix='/bible')

from . import views  # noqa: E402, F401

__all__ = ['bible_bp']