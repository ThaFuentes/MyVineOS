# Mass email, SMS, automated workflows & drip campaigns.

from flask import Blueprint

communications_bp = Blueprint(
    'communications',
    __name__,
    url_prefix='/communications',
)

from . import views  # noqa: E402, F401

__all__ = ['communications_bp']
