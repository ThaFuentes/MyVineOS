from flask import Blueprint

ai_insights_bp = Blueprint('ai_insights', __name__, url_prefix='/ai-insights')

from . import views  # noqa: E402,F401
