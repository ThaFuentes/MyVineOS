from flask import Blueprint

legal_bp = Blueprint('legal', __name__, url_prefix='/legal')

from . import views, utils  # noqa: E402, F401

__all__ = ['legal_bp']