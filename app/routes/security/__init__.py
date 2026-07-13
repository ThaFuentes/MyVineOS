# Security console — PoweredByTop attacks, bans, account locks, access grants.

from flask import Blueprint

security_bp = Blueprint('security', __name__, url_prefix='/security')

from . import views  # noqa: E402,F401

__all__ = ['security_bp']
