# MYVINECHURCH.ONLINE/app/routes/public/prophecies/__init__.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/prophecies/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Public Prophecies sub-blueprint initializer.
# url_prefix='/prophecies' under /public -> /public/prophecies
# 'public_prophecies' bp -> endpoints public.public_prophecies.* (no more collisions or hyphen paths)

from flask import Blueprint

prophecies_bp = Blueprint(
    'public_prophecies',
    __name__,
    url_prefix='/prophecies',
    template_folder='../../../templates/public/prophecies',
    static_folder='../../../static'
)

# Import views/routes (next file we will rebuild)
from . import views

