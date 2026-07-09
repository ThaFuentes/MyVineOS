from flask import Blueprint

custom_modules_bp = Blueprint('custom_modules', __name__, url_prefix='/modules')

from . import views  # noqa: E402, F401