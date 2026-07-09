# MYVINECHURCH.ONLINE/app/routes/tickets/__init__.py
# Full path: MYVINECHURCH.ONLINE/app/routes/tickets/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Blueprint initializer for the **Ticket Manager** module (SOLELY for ticket_managers group + Admins/Owner).
# This folder is now 100% isolated as the administrative ticket management area.
# • Full queue view, assign, respond, bulk actions, status updates, and archive for ALL tickets.
# • Regular users have ZERO access here (they use the new support_tickets blueprint).
# • url_prefix='/tickets' kept exactly as before so existing admin navigation and links require zero changes.
# • Follows the exact modular pattern used by public/events, dreams, prayers, and the new support_tickets structure.
# • Template folder points to templates/tickets (manager-specific templates will be rebuilt next).

from flask import Blueprint

tickets_bp = Blueprint(
    'tickets',
    __name__,
    url_prefix='/tickets',                    # ← kept for Ticket Manager
    template_folder='../../../templates/tickets',
    static_folder='../../../static'
)

# Import views/routes (views.py will be rebuilt next – one file at a time)
from . import views

