from flask import Blueprint

church_bp = Blueprint('church', __name__, url_prefix='/church')

from . import views  # noqa: E402, F401
from . import social_routes  # noqa: E402, F401
from . import moderation  # noqa: E402, F401
