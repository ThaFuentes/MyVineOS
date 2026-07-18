# app/routes/pastoral/__init__.py
# Full path: WebChurchMan/app/routes/pastoral/__init__.py
# File name: __init__.py
# Brief, detailed purpose:
#   Central factory for the Pastoral Area blueprint (/pastoral prefix).
#   - Defines pastoral_required decorator (login + Pastoral Group membership)
#   - Registers root dashboard route (/pastoral/) with upcoming_service context for the "Next Upcoming Service" card
#   - Explicitly imports and registers all sub-module blueprints
#   - Uses explicit imports -> fully compatible with Python 3.14+
#   - Core sub-modules fail loud if missing; optional ones fail silently
#   - All pastoral routes protected by @pastoral_required
#   UPDATED: Dashboard route now fetches and passes upcoming_service to template (fixes UndefinedError)
#   UPDATED: Added registration for vault_integration blueprint (seamless sermon  vault quick-save & search)

from flask import Blueprint, flash, redirect, render_template, session, url_for
from typing import Callable, Optional

from app.utils.decorators import login_required
from app.models.pastoral.shared import is_in_pastoral_group
from app.models.pastoral.service_plans import get_upcoming_service  # NEW: for Next Upcoming Service card

# Create main pastoral blueprint
pastoral_bp = Blueprint(
    'pastoral',
    __name__,
    url_prefix='/pastoral',
    template_folder='templates/pastoral',
    static_folder='static/pastoral'
)


# --------------------------------------------------------------------------
# Permission Helpers
# --------------------------------------------------------------------------
def has_pastoral_permission(user_id: Optional[int], required_permission: Optional[str] = None) -> bool:
    """
    Pastoral area gate:
    - Owner/Admin: always
    - access_pastoral group permission
    - membership in Pastoral Group (system_key / name)
    Staff do NOT auto-enter pastoral without a group or key.
    """
    if not user_id:
        return False

    from app.utils.permissions import role_has_full_access, user_has_permission

    if role_has_full_access(session.get('user_role')):
        return True
    if user_has_permission('access_pastoral'):
        return True
    if is_in_pastoral_group(user_id):
        return True

    if required_permission and user_has_permission(required_permission):
        return True

    return False


def pastoral_required(permission: Optional[str] = None) -> Callable:
    """
    Decorator: requires login + Pastoral Group membership.
    Redirects with flash message on failure.
    """

    def decorator(view_func: Callable) -> Callable:
        @login_required
        def wrapper(*args, **kwargs):
            user_id = session.get('user_id')
            if not has_pastoral_permission(user_id, permission):
                flash('This area is restricted to the Pastoral Team only.', 'error')
                return redirect(url_for('dashboard.dashboard'))
            return view_func(*args, **kwargs)

        wrapper.__name__ = view_func.__name__
        return wrapper

    return decorator


# --------------------------------------------------------------------------
# Root Route - Pastoral Command Center
# --------------------------------------------------------------------------
@pastoral_bp.route('/')
@pastoral_required()
def dashboard_pastoral():
    """
    Main entry point for Pastoral Command Center.
    Renders the command-center style dashboard with quick-access cards
    and a prominent "Next Upcoming Service" card (real plan or recurring default).
    """
    upcoming_service = get_upcoming_service()
    return render_template(
        'pastoral/dashboard_pastoral.html',
        upcoming_service=upcoming_service,
        page_title="Pastoral Command Center"
    )


# --------------------------------------------------------------------------
# Explicit Sub-Module Blueprint Registration
#   -> Explicit imports only - no __import__ or package= keyword
#   -> Core modules fail loud if missing (raise ImportError)
#   -> Optional modules fail silently
# --------------------------------------------------------------------------

# Core / required pastoral sub-modules
try:
    from .bible import bible_bp
    pastoral_bp.register_blueprint(bible_bp)
except (ImportError, AttributeError) as e:
    raise ImportError(f"Critical: Failed to load bible sub-module: {e}")

try:
    from .care import care_bp
    pastoral_bp.register_blueprint(care_bp)
except (ImportError, AttributeError) as e:
    raise ImportError(f"Critical: Failed to load care sub-module: {e}")

try:
    from .illustrations import illustrations_bp
    pastoral_bp.register_blueprint(illustrations_bp)
except (ImportError, AttributeError) as e:
    raise ImportError(f"Critical: Failed to load illustrations sub-module: {e}")

try:
    from .planning import planning_bp
    pastoral_bp.register_blueprint(planning_bp)
except (ImportError, AttributeError) as e:
    raise ImportError(f"Critical: Failed to load planning sub-module: {e}")

try:
    from .podium import podium_bp
    pastoral_bp.register_blueprint(podium_bp)
except (ImportError, AttributeError) as e:
    raise ImportError(f"Critical: Failed to load podium sub-module: {e}")

try:
    from .sermons_core import sermons_bp
    pastoral_bp.register_blueprint(sermons_bp)
except (ImportError, AttributeError) as e:
    raise ImportError(f"Critical: Failed to load sermons_core sub-module: {e}")

try:
    from .sermons_export import export_bp
    pastoral_bp.register_blueprint(export_bp)
except (ImportError, AttributeError) as e:
    raise ImportError(f"Critical: Failed to load sermons_export sub-module: {e}")

try:
    from .vault import vault_bp
    pastoral_bp.register_blueprint(vault_bp)
except (ImportError, AttributeError) as e:
    raise ImportError(f"Critical: Failed to load vault sub-module: {e}")

# NEW: Vault  Sermon integration endpoints (quick-save & search)
try:
    from .vault_integration import vault_integration_bp
    pastoral_bp.register_blueprint(vault_integration_bp)
except (ImportError, AttributeError):
    pass  # Optional - graceful if file not yet created

# Optional / newer modules (silent fail if not yet implemented)
try:
    from . import ai_assistant  # noqa: F401 - registers routes on pastoral_bp
except (ImportError, AttributeError):
    pass

try:
    from .curriculum import curriculum_bp
    pastoral_bp.register_blueprint(curriculum_bp)
except (ImportError, AttributeError) as e:
    raise ImportError(f"Critical: Failed to load curriculum sub-module: {e}")

# Expose decorator at blueprint level (rarely needed, but useful)
pastoral_bp.pastoral_required = pastoral_required