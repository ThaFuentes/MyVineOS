# MYVINECHURCH.ONLINE/app/routes/support_tickets/__init__.py
from flask import Blueprint

support_tickets_bp = Blueprint(
    'support_tickets',
    __name__,
    url_prefix='/support-tickets',
    template_folder='../../templates/support_tickets',
    static_folder='../../../static'
)

from . import views

print("YVINECHURCH.ONLINE support_tickets sub-blueprint initialized successfully (url_prefix='/support-tickets')")