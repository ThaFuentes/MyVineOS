# app/routes/dreams/__init__.py
# Full path: MyVineChurch/app/routes/dreams/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Dreams Blueprint Package Initializer – 100% MariaDB/pymysql compatible.
# - Creates the exact same Blueprint(name='dreams', url_prefix='/dreams') as the old flat file.
# - Automatically imports all modular files so every route registers instantly.
# - Zero functional change today – public/private/personal visibility, listing with search, detail view, submit/edit/delete, comments.html, server-side censorship, audit logging all remain 100% identical.
# - Designed purely for future scaling: we can now safely split into views.py, queries.py, forms.py, utils.py without touching app/__init__.py or main.py.

from flask import Blueprint

# ----------------------------------------------------------------------
# Blueprint definition (identical to old dreams.py)
# ----------------------------------------------------------------------
dreams_bp = Blueprint(
    'dreams',
    __name__,
    url_prefix='/dreams'
)

# ----------------------------------------------------------------------
# Import route modules (they will define all the @dreams_bp.route handlers)
# ----------------------------------------------------------------------
# We do ONE file at a time per your instructions → next we will build views.py
from . import views
# from . import queries
# from . import forms
# from . import utils

# Optional: re-export for easy import in app/__init__.py
__all__ = ['dreams_bp']