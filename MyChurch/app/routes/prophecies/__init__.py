# app/routes/prophecies/__init__.py
# Full path: MyVineChurch/app/routes/prophecies/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Prophecies Blueprint Package Initializer.

from flask import Blueprint

prophecies_bp = Blueprint(
    'prophecies',
    __name__,
    url_prefix='/prophecies'
)

from . import views
from . import queries
from . import forms
from . import utils

__all__ = ['prophecies_bp']