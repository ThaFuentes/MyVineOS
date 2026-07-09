# MYVINECHURCH.ONLINE/app/routes/public/dreams/__init__.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/dreams/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Public Dreams & Visions sub-blueprint initializer.
# url_prefix='/dreams' under the parent public_bp (which has /public) → full path /public/dreams
# Uses dedicated 'public_dreams' blueprint name for unambiguous url_for('public.public_dreams....')
# Points to templates/public/dreams. Registered via public/__init__.py .

from flask import Blueprint

dreams_bp = Blueprint(
    'public_dreams',
    __name__,
    url_prefix='/dreams',
    template_folder='../../../templates/public/dreams',
    static_folder='../../../static'
)

# Import views/routes (next file we will rebuild)
from . import views

