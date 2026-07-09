# MYVINECHURCH.ONLINE/app/routes/public/prayers/__init__.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/prayers/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Public Prayers sub-blueprint initializer.
# url_prefix='/prayers' under /public parent → clean /public/prayers
# bp name 'public_prayers' → reliable full endpoints public.public_prayers.*

from flask import Blueprint

prayers_bp = Blueprint(
    'public_prayers',
    __name__,
    url_prefix='/prayers',
    template_folder='../../../templates/public/prayers',
    static_folder='../../../static'
)

# Import views/routes
from . import views

