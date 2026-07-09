# MYVINECHURCH.ONLINE/app/routes/public/sermons/__init__.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/sermons/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Public Sermons sub-blueprint initializer.
# url_prefix='/sermons' under public parent (/public) -> /public/sermons
# 'public_sermons' name -> public.public_sermons.* endpoints (collision-free).

from flask import Blueprint

sermons_bp = Blueprint(
    'public_sermons',
    __name__,
    url_prefix='/sermons',
    template_folder='../../../templates/public/sermons',
    static_folder='../../../static'
)

# Import views/routes
from . import views

# print(" public/sermons sub-blueprint ready at /public/sermons (public.public_sermons.*)")