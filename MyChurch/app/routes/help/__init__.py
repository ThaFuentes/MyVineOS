from flask import Blueprint

help_bp = Blueprint('help', __name__, url_prefix='/help')

from . import views  # noqa: E402,F401

__all__ = ['help_bp']