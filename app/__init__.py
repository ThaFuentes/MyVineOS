# MYVINECHURCH.ONLINE/app/__init__.py
# Full path: MYVINECHURCH.ONLINE/app/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Flask application factory for MYVINECHURCH.ONLINE.
# - Loads .env + MariaDB configuration
# - Initializes DB schema silently on first request
# - Registers ALL blueprints (PRIVATE FIRST so logged-in users always hit private routes)
# - Explicit nested public sub-blueprint support (public_events, public_sermons, public_dreams, etc.)
# - Explicit the_gathering parent + dashboard sub-blueprint support
# - Injects global settings, Jinja filters, and template context processors
# - 100% rebuilt to match the exact clean, modular style we perfected on the public/events and the_gathering/dashboard modules
# - Only change: Hardcoded root redirect to '/public/' to bypass blueprint naming issues.

from flask import Flask, g, session, redirect, url_for, request, render_template, flash
from markupsafe import Markup, escape
from datetime import datetime
import os
import importlib
# Load environment variables from project root
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
# ──────────────────────────────────────────────────────────────────────────────
# Core model & utility imports
# ──────────────────────────────────────────────────────────────────────────────
from app.builddb.builddb import build_all
from .models.db import close_db
from .models.owner import owner_exists
from .models.settings import get_settings
from app.utils.helpers import censor_text
from app.models.pastoral.shared import is_in_pastoral_group
from app.utils.permissions import user_has_permission
from app.routes.the_gathering.dashboard.utils import format_manager_datetime
def create_app():
    """
    Create and configure the Flask application instance.
    Returns fully initialized app ready for WSGI / development server.
    """
    from app.utils.production_secrets import validate_production_secrets
    validate_production_secrets()

    static_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static'))
    app = Flask(__name__, static_folder=static_folder)
    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'dev-insecure-change-this-immediately-2026'
    # Additional Flask security configs
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = 86400
    app.config['PREFERRED_URL_SCHEME'] = 'https' if os.getenv('REQUIRE_HTTPS', 'False').lower() in ('1','true','yes') else 'http'
    if os.getenv("DEBUG_MODE", "False").lower() != "true":
        app.config['DEBUG'] = False
        app.config['TESTING'] = False
    app.config['MYSQL_HOST'] = os.environ.get('MYSQL_HOST', 'localhost')
    app.config['MYSQL_USER'] = os.environ.get('MYSQL_USER', 'churchuser')
    app.config['MYSQL_PASSWORD'] = os.environ.get('MYSQL_PASSWORD', '')
    app.config['MYSQL_DATABASE'] = os.environ.get('MYSQL_DATABASE', 'church_management')
    app.config['MYSQL_PORT'] = int(os.environ.get('MYSQL_PORT', 3306))
    app.config['FERNET_KEY'] = os.environ.get('FERNET_KEY')
    app.config['UPLOAD_FOLDER'] = os.path.abspath(os.path.join(app.root_path, '..', 'uploads'))
    app.config['EXPORT_FOLDER'] = os.path.abspath(os.path.join(app.root_path, '..', 'export'))
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['EXPORT_FOLDER'], exist_ok=True)
    app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024
    app.teardown_appcontext(close_db)

    # Apply full PoweredByTop security early so its before_request runs first for all protection
    try:
        from poweredbytop import init_security
        init_security(app)
    except Exception as sec_err:
        print("WARNING: Could not init PoweredByTop security early: " + str(sec_err))
    # Silent DB schema initialization (skippable for tests / import verification with no DB)
    if not (os.getenv("SKIP_DB_BUILD") in ("1", "true", "yes", "TRUE") or os.getenv("TESTING") == "1"):
        with app.app_context():
            build_all(verbose=False)
    # Global settings
    @app.before_request
    def load_global_settings():
        g.settings = get_settings()

    @app.before_request
    def load_viewer_moderation_context():
        from app.utils.account_moderation import refresh_viewer_context
        refresh_viewer_context()
    # GLOBAL WATCHMAN DEBUG (only in debug mode to avoid leaking info in prod)
    if os.getenv("DEBUG_MODE", "False").lower() == "true":
        @app.before_request
        def watchman_debug():
            if request.path.startswith('/static/'):
                return
            print(f"\n" + "!"*70)
            print(f"[WATCHMAN] Request Path: {request.path}")
            print(f"[WATCHMAN] Blueprint: {request.blueprint}")
            print(f"[WATCHMAN] Endpoint: {request.endpoint}")
            print(f"[WATCHMAN] Session User: {session.get('user_id', 'GUEST')}")
            print(f"[WATCHMAN] Session Role: {session.get('user_role', 'NONE')}")
            print(f"!"*70 + "\n")
    # Custom Jinja filters & context processors
    @app.template_filter('nl2br')
    def nl2br_filter(value: str) -> Markup:
        if not value:
            return Markup('')
        return Markup(escape(value).replace('\n', '<br>\n'))
    app.jinja_env.filters['censor'] = censor_text
    @app.template_filter('relative_time')
    def relative_time_filter(value):
        if not value:
            return 'never'
        now = datetime.utcnow()
        if hasattr(value, 'tzinfo') and value.tzinfo:
            now = now.replace(tzinfo=value.tzinfo)
        diff = now - value
        seconds = diff.total_seconds()
        if seconds < 60:
            return 'just now'
        elif seconds < 3600:
            return f"{int(seconds//60)} minute{'s' if int(seconds//60) != 1 else ''} ago"
        elif seconds < 86400:
            return f"{int(seconds//3600)} hour{'s' if int(seconds//3600) != 1 else ''} ago"
        elif seconds < 2592000:
            return f"{int(seconds//86400)} day{'s' if int(seconds//86400) != 1 else ''} ago"
        elif seconds < 31536000:
            return f"{int(seconds//2592000)} month{'s' if int(seconds//2592000) != 1 else ''} ago"
        else:
            return f"{int(seconds//31536000)} year{'s' if int(seconds//31536000) != 1 else ''} ago"
    @app.template_filter('escape_js')
    def escape_js_filter(value):
        if not value:
            return ''
        value = str(value)
        for old, new in [('\\', '\\\\'), ("'", "\\'"), ('"', '\\"'), ('\n', '\\n'), ('\r', '\\r'), ('\t', '\\t')]:
            value = value.replace(old, new)
        return value
    app.jinja_env.filters['format_manager_datetime'] = format_manager_datetime
    @app.context_processor
    def inject_permissions():
        from app.routes.members.utils import (
            can_view_members,
            can_manage_members,
            can_manage_users,
        )
        from app.routes.donations.utils import can_view_donations, can_manage_donations
        from app.routes.bills.utils import can_manage_bills
        from app.routes.inventory.utils import can_manage_inventory
        from app.routes.attendance.utils import can_manage_attendance
        from app.routes.help.utils import can_manage_help
        return dict(
            user_has_permission=user_has_permission,
            can_view_members=can_view_members,
            can_manage_members=can_manage_members,
            can_manage_users=can_manage_users,
            can_view_donations=can_view_donations,
            can_manage_donations=can_manage_donations,
            can_manage_bills=can_manage_bills,
            can_manage_inventory=can_manage_inventory,
            can_manage_attendance=can_manage_attendance,
            can_manage_help=can_manage_help,
        )
    @app.context_processor
    def inject_pastoral_access():
        from flask import session as flask_session
        return dict(in_pastoral_group=is_in_pastoral_group(flask_session.get('user_id')))

    @app.context_processor
    def inject_gathering_place_access():
        from flask import session as flask_session
        try:
            from app.routes.groups.gathering_place import can_access_gathering_place
            ok = can_access_gathering_place(
                flask_session.get('user_id'),
                flask_session.get('user_role'),
            )
        except Exception:
            ok = False
        return dict(can_access_gathering_place=ok)

    @app.context_processor
    def inject_worship_access():
        from flask import session as flask_session
        try:
            from app.models.worship.shared import can_view_worship, can_manage_worship
            uid = flask_session.get('user_id')
            return dict(
                can_access_worship=can_view_worship(uid),
                can_manage_worship=lambda: can_manage_worship(uid),
            )
        except Exception:
            return dict(can_access_worship=False, can_manage_worship=lambda: False)

    # CSRF token for templates (works with PBT CSRF in security pipeline)
    @app.context_processor
    def inject_csrf_token():
        try:
            from poweredbytop.core.security import get_csrf_token
            return dict(csrf_token=get_csrf_token)
        except Exception:
            return dict(csrf_token=lambda: '')

    @app.context_processor
    def inject_church_display_name():
        from flask import g as flask_g
        settings = flask_g.get('settings') or {}
        raw = settings.get('church_name')
        name = str(raw).strip() if raw else ''
        return dict(church_display_name=name or None)

    @app.context_processor
    def inject_current_user():
        """Lightweight session user for templates that reference current_user."""
        uid = session.get('user_id')
        if not uid:
            return dict(current_user=None)

        class _CurrentUser:
            __slots__ = ('id', 'role', 'username')

            def __init__(self, user_id, role, username):
                self.id = user_id
                self.role = role or 'Member'
                self.username = username or ''

            def __str__(self):
                return self.username or 'User'

            def __bool__(self):
                return True

        return dict(current_user=_CurrentUser(
            uid,
            session.get('user_role'),
            session.get('username'),
        ))

    @app.context_processor
    def inject_custom_modules():
        from flask import session as flask_session
        try:
            from app.routes.custom_modules.queries import get_dashboard_modules
            mods = get_dashboard_modules(
                flask_session.get('user_id'),
                flask_session.get('user_role'),
                bool(flask_session.get('user_id')),
            )
        except Exception:
            mods = []
        return dict(dashboard_custom_modules=mods)

    @app.context_processor
    def inject_notification_context():
        from flask import session as flask_session
        try:
            from app.utils.email_notifications import get_notification_settings
            notif_settings = get_notification_settings()
        except Exception:
            notif_settings = {}
        pending_count = 0
        if flask_session.get('user_role') in ('Owner', 'Admin'):
            try:
                from app.routes.auth.queries import count_pending_registrations
                pending_count = count_pending_registrations()
            except Exception:
                pass
        return dict(
            notification_settings=notif_settings,
            pending_registration_count=pending_count,
        )
    # ──────────────────────────────────────────────────────────────────────────────
    # BLUEPRINT REGISTRATION – PRIVATE FIRST (logged-in users always win)
    # ──────────────────────────────────────────────────────────────────────────────
    # Private blueprints (flat structure – no nesting)
    private_blueprints = [
        'auth',
        'dashboard',
        'events',
        'dreams',
        'prayers',
        'announcements',
        'sermons',
        'prophecies',
        'profile',
        'members',
        'donations',
        'settings',
        'groups',
        'log',
        'tickets',
        'attendance',
        'bills',
        'inventory',
        'bible',
        'legal',
        'pastoral',
        'worship',
        'support_tickets',
        'custom_modules',
        'help',
    ]
    for name in private_blueprints:
        try:
            module = importlib.import_module(f'app.routes.{name}')
            blueprint = getattr(module, f'{name}_bp')
            app.register_blueprint(blueprint)
            print(f"Registered private blueprint: {name}")
        except (ImportError, AttributeError) as e:
            print(f"Skipped private blueprint: {name} ({e})")
        except Exception as e:
            print(f"ERROR registering private blueprint {name}: {e}")
    # ──────────────────────────────────────────────────────────────────────────────
    # EXPLICIT REGISTRATION FOR the_gathering (nested dashboard)
    # ──────────────────────────────────────────────────────────────────────────────
    try:
        from app.routes.the_gathering import the_gathering_bp
        app.register_blueprint(the_gathering_bp)
        print("Explicitly registered the_gathering blueprint (nested dashboard active)")
    except Exception as e:
        print(f"FAILED to register the_gathering blueprint: {e}")
    # ──────────────────────────────────────────────────────────────────────────────
    # PUBLIC PARENT BLUEPRINT – LAST
    # ──────────────────────────────────────────────────────────────────────────────
    # Public lives under /public (parent url_prefix) with sub-blueprints:
    #   /public/ (dashboard feed), /public/dreams, /public/events, /public/prayers,
    #   /public/prophecies, /public/announcements, /public/sermons, /public/donate
    # Endpoints are namespaced e.g. 'public.public_dreams.public_dreams' to avoid
    # any collision with private top-level 'dreams', 'events' etc. (registered first).
    # The_gathering (manager) uses its own nested 'the_gathering.xxx' endpoints.
    try:
        from app.routes.public import public_bp
        app.register_blueprint(public_bp)
        print("Registered public parent blueprint (nested sub-blueprints active – homepage + comments fixed)")
    except Exception as e:
        print(f"FAILED to register public blueprint: {e}")
    # ──────────────────────────────────────────────────────────────────────────────
    # Root Route
    # ──────────────────────────────────────────────────────────────────────────────
    @app.route('/')
    def index():
        if session.get('user_id'):
            return redirect(url_for('dashboard.dashboard'))
        if not owner_exists():
            flash('Initial setup required – please register the first Owner.', 'info')
            return redirect(url_for('auth.register'))
        return redirect(url_for('public.public_dashboard.public_dashboard'))
    # OWNER ENFORCEMENT
    @app.before_request
    def enforce_owner_registration():
        if os.environ.get('TESTING') == '1':
            return
        if (request.path.startswith('/static/') or
            (request.endpoint and request.endpoint.startswith('auth.'))):
            return
        if not owner_exists():
            flash('Initial setup required – please register the first Owner.', 'info')
            return redirect(url_for('auth.register'))
    # Error Handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404
    @app.errorhandler(500)
    def internal_error(e):
        return render_template('errors/500.html'), 500
    @app.errorhandler(403)
    def forbidden(e):
        # PBT security blocks (csrf, rate, rep, vet, etc), role denials, etc.
        if not session.get('user_id') or (request.endpoint and request.endpoint.startswith('auth.')):
            flash('Security check failed or access denied. Please reload the login page and try again.', 'error')
            return redirect(url_for('auth.login'))
        flash('Security check failed. Please reload the page and try again.', 'error')
        return redirect(request.referrer or url_for('dashboard.dashboard'))

    # Security headers (applied to all responses)
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        # Basic CSP - adjust as needed for the app's needs (allows inline for current styles/scripts)
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "object-src 'none'; "
            "script-src 'self' 'unsafe-inline' https:; "
            "style-src 'self' 'unsafe-inline' https:; "
            "img-src 'self' data: https:; "
            "font-src 'self' https:; "
            "connect-src 'self' https:;"
        )
        if request.is_secure or os.getenv('REQUIRE_HTTPS', 'False').lower() == 'true':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    return app