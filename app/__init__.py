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
# 
# Core model & utility imports
# 
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
    def enforce_module_toggles():
        """Soft-block optional modules the church turned off (nav already hides them)."""
        if request.path.startswith('/static/') or request.method == 'OPTIONS':
            return
        if session.get('user_role') in ('Owner', 'Admin'):
            return
        ep = request.endpoint or ''
        if not ep or ep.startswith('settings.') or ep.startswith('auth.'):
            return
        try:
            from app.models.module_toggles import (
                get_module_toggles,
                is_module_enabled,
                module_for_endpoint,
            )
            key = module_for_endpoint(ep)
            if not key:
                return
            toggles = get_module_toggles(getattr(g, 'settings', None))
            if is_module_enabled(key, toggles):
                return
            flash('That area is not enabled for this church right now.', 'info')
            if session.get('user_id'):
                return redirect(url_for('dashboard.dashboard'))
            # Guests: do not bounce into private dashboard
            try:
                return redirect(url_for('public.public_dashboard.public_dashboard'))
            except Exception:
                return redirect(url_for('auth.login'))
        except Exception:
            return

    @app.before_request
    def load_viewer_moderation_context():
        from app.utils.account_moderation import refresh_viewer_context
        refresh_viewer_context()

    @app.before_request
    def enforce_private_area_login():
        """
        Defense-in-depth: private app areas always require a session.
        Public surface stays under /public/, /legal/, and auth entry routes.
        """
        if request.method == 'OPTIONS':
            return
        path = request.path or ''
        if path.startswith('/static/'):
            return
        if session.get('user_id'):
            return

        # Explicitly public / auth / legal / tokens
        public_prefixes = (
            '/public/', '/legal/', '/login', '/register', '/logout',
            '/request-reset-password', '/forgot-username', '/resend-verification',
            '/verify-email', '/reset-password', '/check-email',
            '/sw.js',
        )
        if path == '/' or any(path == p or path.startswith(p) for p in public_prefixes):
            return
        # Volunteer email token respond (one-time link)
        if path.startswith('/volunteers/respond/'):
            return
        # Worship public display tokens
        if path.startswith('/worship/screen/') or path.startswith('/worship/prompter/'):
            return
        # Attendance kiosk with token is handled in-route; block bare kiosk POST via login
        if path.startswith('/attendance/kiosk') and request.method == 'GET':
            # kiosk GET may use token query; leave to view
            return

        # Private operational prefixes — must be logged in
        private_prefixes = (
            '/dashboard', '/settings', '/profile', '/members', '/donations',
            '/bills', '/accounting', '/inventory', '/attendance', '/child-checkin',
            '/volunteers', '/tickets', '/support-tickets', '/pastoral',
            '/worship', '/security', '/ai-insights', '/communications', '/study',
            '/modules', '/log', '/the_gathering', '/campus', '/help/manage',
            '/events', '/prayers', '/dreams', '/sermons', '/announcements',
            '/prophecies', '/help',
            # NOTE: /bible is NOT private — visitors may read freely.
            # Save actions (highlight/note/favorite) stay login-gated in bible routes.
        )
        # Guest-safe: dual-mode community list pages can stay readable without login
        # but POST mutations still require CSRF + should not create private content.
        # Guest-safe reads: public community lists + full open Bible reader + text APIs.
        # Operational Help, groups, dashboard, finance, pastoral, etc. require login.
        pr = path.rstrip('/')
        guest_read_ok = (
            pr in (
                '/prayers', '/dreams', '/sermons', '/announcements', '/prophecies',
            )
            # Entire Bible reader + read APIs are public (writes still @login_required)
            or path == '/bible'
            or path.startswith('/bible/')
            or (
                path.startswith('/prayers/')
                and request.method == 'GET'
            )
            or (
                path.startswith('/dreams/')
                and request.method == 'GET'
                and '/submit' not in path
                and '/edit' not in path
                and '/delete' not in path
                and '/comment' not in path
            )
            or (
                path.startswith('/sermons/')
                and request.method == 'GET'
                and '/edit' not in path
                and '/delete' not in path
            )
            or (
                path.startswith('/announcements/')
                and request.method == 'GET'
                and '/edit' not in path
                and '/delete' not in path
                and '/create' not in path
            )
            or (
                path.startswith('/prophecies/')
                and request.method == 'GET'
                and '/edit' not in path
                and '/delete' not in path
            )
        )
        # Mutations never guest-open except moderated guest prayer at /prayers/add (CSRF required)
        # Bible POST/DELETE writes are handled by @login_required on those routes (JSON 401) —
        # do not hard-redirect the whole app when a guest taps highlight/favorite.
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            if pr == '/prayers/add':
                return
            if path == '/bible' or path.startswith('/bible/'):
                return  # let bible views decide (JSON 401 vs success)
            if any(path == p or path.startswith(p + '/') or path.startswith(p) for p in private_prefixes):
                flash('Please log in to continue.', 'error')
                return redirect(url_for('auth.login', next=request.url))
            return

        if guest_read_ok:
            return

        if any(path == p or path.startswith(p + '/') or path.startswith(p) for p in private_prefixes):
            flash('Please log in to access this area.', 'error')
            return redirect(url_for('auth.login', next=request.url))

    @app.before_request
    def enforce_session_integrity():
        """Reject stale/banned sessions so forms cannot run as a dead account."""
        if request.path.startswith('/static/'):
            return
        uid = session.get('user_id')
        if not uid:
            return
        try:
            from app.models.users import get_user_by_id
            user = get_user_by_id(uid)
            if not user:
                session.clear()
                flash('Your session is no longer valid. Please log in again.', 'error')
                return redirect(url_for('auth.login'))
            # Soft ban / hard ban flags if present
            if user.get('is_banned') or user.get('banned'):
                session.clear()
                flash('This account is not allowed to sign in.', 'error')
                return redirect(url_for('auth.login'))
            # Keep role in session aligned with DB
            role = user.get('role')
            if role and session.get('user_role') != role:
                session['user_role'] = role
        except Exception:
            # Never break the site if users model hiccups
            return

    @app.before_request
    def sync_display_preferences():
        """Church default theme for guests + personal overrides for members."""
        if request.path.startswith('/static/'):
            return
        try:
            from app.utils.ui_prefs import sync_ui_prefs_from_db
            sync_ui_prefs_from_db(session)
        except Exception as pref_err:
            # Never block page loads if prefs columns missing
            if os.getenv('DEBUG_MODE', '').lower() == 'true':
                print(f'sync_display_preferences: {pref_err}')

    @app.before_request
    def sync_campus_session():
        """Default multi-campus scope for logged-in users."""
        if request.path.startswith('/static/'):
            return
        if not session.get('user_id'):
            return
        try:
            from app.models.campuses import ensure_session_campus_default
            ensure_session_campus_default()
        except Exception:
            pass

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
        from app.routes.donations.utils import (
            can_view_donations,
            can_manage_donations,
            can_create_donations,
            can_edit_donations,
            can_delete_donations,
        )
        from app.routes.bills.utils import (
            can_manage_bills,
            can_access_bills,
            can_create_bills,
            can_edit_bills,
            can_delete_bills,
            can_view_bills,
        )
        from app.routes.accounting.utils import (
            can_access_accounting,
            can_view_accounting,
            can_create_accounting,
            can_edit_accounting,
            can_delete_accounting,
        )
        from app.routes.inventory.utils import can_manage_inventory
        from app.routes.attendance.utils import can_manage_attendance
        from app.routes.help.utils import can_manage_help
        from app.routes.prophecies.utils import can_create_prophecies, can_moderate_prophecies
        from app.routes.dreams.utils import can_create_dreams, can_moderate_dreams
        from app.routes.prayers.utils import can_create_prayers, can_moderate_prayers
        from app.utils.community_participation import (
            can_create_community_content,
            can_interact_community,
        )

        def can_access_volunteers_admin():
            return (
                user_has_permission('manage_volunteers')
                or user_has_permission('manage_attendance')
            )

        def can_access_communications():
            return user_has_permission('send_emails')

        return dict(
            user_has_permission=user_has_permission,
            can_view_members=can_view_members,
            can_manage_members=can_manage_members,
            can_manage_users=can_manage_users,
            can_view_donations=can_view_donations,
            can_manage_donations=can_manage_donations,
            can_create_donations=can_create_donations,
            can_edit_donations=can_edit_donations,
            can_delete_donations=can_delete_donations,
            can_manage_bills=can_manage_bills,
            can_view_bills=can_view_bills,
            can_create_bills=can_create_bills,
            can_edit_bills=can_edit_bills,
            can_delete_bills=can_delete_bills,
            can_access_bills=can_access_bills,
            can_access_accounting=can_access_accounting,
            can_view_accounting=can_view_accounting,
            can_create_accounting=can_create_accounting,
            can_edit_accounting=can_edit_accounting,
            can_delete_accounting=can_delete_accounting,
            can_access_volunteers_admin=can_access_volunteers_admin,
            can_access_communications=can_access_communications,
            can_manage_inventory=can_manage_inventory,
            can_manage_attendance=can_manage_attendance,
            can_manage_help=can_manage_help,
            can_create_prophecies=can_create_prophecies,
            can_moderate_prophecies=can_moderate_prophecies,
            can_create_dreams=can_create_dreams,
            can_moderate_dreams=can_moderate_dreams,
            can_create_prayers=can_create_prayers,
            can_moderate_prayers=can_moderate_prayers,
            can_create_community_content=can_create_community_content,
            can_interact_community=can_interact_community,
        )
    @app.context_processor
    def inject_pastoral_access():
        """in_pastoral_group kept as alias = Access key access_pastoral (or Owner/Admin)."""
        from flask import session as flask_session
        from app.utils.permissions import user_has_permission as _has
        uid = flask_session.get('user_id')
        # Prefer live permission check so Access UI matches nav immediately
        can = False
        try:
            can = bool(uid and (
                flask_session.get('user_role') in ('Owner', 'Admin')
                or _has('access_pastoral')
            ))
        except Exception:
            can = is_in_pastoral_group(uid)
        return dict(in_pastoral_group=can, can_access_pastoral=can)

    @app.context_processor
    def inject_campus_context():
        try:
            from app.models.campuses import inject_campus_context as _campus_ctx
            return _campus_ctx()
        except Exception:
            return dict(
                multi_campus_enabled=False,
                campuses=[],
                active_campus=None,
                active_campus_id=None,
                viewing_all_campuses=True,
            )

    @app.context_processor
    def inject_module_toggles():
        """Optional modules Owner/Admin can enable or disable (nav + dashboard tiles)."""
        try:
            from app.models.module_toggles import get_module_toggles, is_module_enabled
            from flask import g as flask_g
            toggles = get_module_toggles(getattr(flask_g, 'settings', None) or None)

            def module_on(key: str) -> bool:
                return is_module_enabled(key, toggles)

            return dict(module_toggles=toggles, module_on=module_on)
        except Exception:
            def module_on(_key: str) -> bool:
                return True
            return dict(module_toggles={}, module_on=module_on)

    @app.context_processor
    def inject_promotions_nav():
        """Show Partners nav only when module is on and at least one card is published."""
        try:
            from app.models.promotions import is_promotions_visible
            return dict(promotions_nav_visible=is_promotions_visible())
        except Exception:
            return dict(promotions_nav_visible=False)

    @app.context_processor
    def inject_endpoint_exists():
        def endpoint_exists(name: str) -> bool:
            try:
                return name in app.view_functions
            except Exception:
                return False
        return dict(endpoint_exists=endpoint_exists)

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

    @app.context_processor
    def inject_security_console_access():
        """Nav flag for Security console (role, permission, or named grant)."""
        try:
            from app.routes.security.utils import can_access_security_console
            return dict(can_access_security_console=can_access_security_console())
        except Exception:
            return dict(can_access_security_console=False)

    @app.context_processor
    def inject_outgoing_from_email():
        """Current activation/mail From address (Settings → Email default account)."""
        try:
            from app.utils.emailer import get_outgoing_from_address
            return dict(outgoing_from_email=get_outgoing_from_address())
        except Exception:
            return dict(outgoing_from_email=None)
    # 
    # BLUEPRINT REGISTRATION - PRIVATE FIRST (logged-in users always win)
    # 
    # Private blueprints (flat structure - no nesting)
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
        'security',
        'ai_insights',
        'curriculum',
        'child_checkin',
        'communications',
        'volunteers',
        'accounting',
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
    # 
    # EXPLICIT REGISTRATION FOR the_gathering (nested dashboard)
    # 
    try:
        from app.routes.the_gathering import the_gathering_bp
        app.register_blueprint(the_gathering_bp)
        print("Explicitly registered the_gathering blueprint (nested dashboard active)")
    except Exception as e:
        print(f"FAILED to register the_gathering blueprint: {e}")
    try:
        from app.routes.campus_switch import campus_switch_bp
        app.register_blueprint(campus_switch_bp)
        print("Registered campus_switch blueprint")
    except Exception as e:
        print(f"Skipped campus_switch blueprint: {e}")
    # 
    # PUBLIC PARENT BLUEPRINT - LAST
    # 
    # Public lives under /public (parent url_prefix) with sub-blueprints:
    #   /public/ (dashboard feed), /public/dreams, /public/events, /public/prayers,
    #   /public/prophecies, /public/announcements, /public/sermons, /public/donate
    # Endpoints are namespaced e.g. 'public.public_dreams.public_dreams' to avoid
    # any collision with private top-level 'dreams', 'events' etc. (registered first).
    # The_gathering (manager) uses its own nested 'the_gathering.xxx' endpoints.
    try:
        from app.routes.public import public_bp
        app.register_blueprint(public_bp)
        print("Registered public parent blueprint (nested sub-blueprints active - homepage + comments fixed)")
    except Exception as e:
        print(f"FAILED to register public blueprint: {e}")
    # 
    # Root Route
    # 
    @app.route('/')
    def index():
        if session.get('user_id'):
            return redirect(url_for('dashboard.dashboard'))
        if not owner_exists():
            flash('Initial setup required - please register the first Owner.', 'info')
            return redirect(url_for('auth.register'))
        return redirect(url_for('public.public_dashboard.public_dashboard'))

    # PWA service worker at site root so it can scope to "/" and cache /static only
    @app.route('/sw.js')
    def service_worker():
        from flask import send_from_directory, make_response
        resp = make_response(send_from_directory(app.static_folder, 'sw.js'))
        resp.headers['Content-Type'] = 'application/javascript; charset=utf-8'
        resp.headers['Service-Worker-Allowed'] = '/'
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp

    # OWNER ENFORCEMENT
    @app.before_request
    def enforce_owner_registration():
        if os.environ.get('TESTING') == '1':
            return
        if (request.path.startswith('/static/') or
            request.path == '/sw.js' or
            (request.endpoint and request.endpoint.startswith('auth.'))):
            return
        if not owner_exists():
            flash('Initial setup required - please register the first Owner.', 'info')
            return redirect(url_for('auth.register'))
    # Error Handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404
    @app.errorhandler(500)
    def internal_error(e):
        # Always log so hosting (Passenger) has a trail when the themed page hides the cause
        try:
            app.logger.exception('HTTP 500 on %s: %s', getattr(request, 'path', '?'), e)
        except Exception:
            pass
        try:
            import traceback
            print('HTTP 500:\n' + traceback.format_exc(), flush=True)
        except Exception:
            pass
        return render_template('errors/500.html'), 500
    @app.errorhandler(403)
    def forbidden(e):
        # PBT security blocks (csrf, rate, rep, vet, etc), role denials, etc.
        # AJAX callers (display prefs, etc.) need JSON — not a dashboard redirect.
        wants_json = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or (request.accept_mimetypes.best and 'application/json' in request.accept_mimetypes.best)
            or (request.path or '').rstrip('/').endswith('/ui-preferences')
        )
        if wants_json:
            from flask import jsonify
            return jsonify({
                'ok': False,
                'error': 'Security check failed. Reload the page and try again.',
            }), 403
        if not session.get('user_id') or (request.endpoint and request.endpoint.startswith('auth.')):
            flash(
                'Login was blocked by a security check (often a timed-out form on mobile). '
                'Please wait a moment, reload this page, and try again.',
                'error',
            )
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