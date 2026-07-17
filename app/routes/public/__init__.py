# MYVINECHURCH.ONLINE/app/routes/public/__init__.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/__init__.py
# File name: __init__.py
# Brief, detailed purpose: Main public blueprint package initializer.
# public_bp now has url_prefix='/public' so all community features live cleanly under /public/dreams, /public/events, etc.
# Registers the sub-blueprints (public_dashboard for the feed at /public/, plus public_dreams etc.).
# Sub bps use names like 'public_dreams' so full endpoints are 'public.public_dreams.public_dreams' (unambiguous).
# Private bps (short names at /dreams etc.) are registered earlier but paths no longer collide.

from flask import Blueprint, flash, redirect, url_for, request, session, jsonify

# 
# Main public blueprint (url_prefix='/public' for clean public community area)
# 
public_bp = Blueprint(
    'public',
    __name__,
    url_prefix='/public',
    template_folder='../templates/public',
    static_folder='../static'
)

# 
# Register all public feature sub-blueprints
# (Each sub-module defines its own bp in its __init__.py)
# 

# Public Dashboard (homepage feed) - becomes /public/ and /public/public
from .public_dashboard import dashboard_bp
public_bp.register_blueprint(dashboard_bp)

# Announcements -> /public/announcements
from .announcements import announcements_bp
public_bp.register_blueprint(announcements_bp)

# Dreams & Visions -> /public/dreams
from .dreams import dreams_bp
public_bp.register_blueprint(dreams_bp)

# Events (potluck, signups, comments) -> /public/events
from .events import events_bp
public_bp.register_blueprint(events_bp)

# Prayers -> /public/prayers
from .prayers import prayers_bp
public_bp.register_blueprint(prayers_bp)

# Prophecies -> /public/prophecies
from .prophecies import prophecies_bp
public_bp.register_blueprint(prophecies_bp)

# Sermons -> /public/sermons
from .sermons import sermons_bp
public_bp.register_blueprint(sermons_bp)

# print(" public routes initialized under /public/ with clean nested endpoints (public.public_xxx.*)")

# ----------------------------------------------------------------------
# Donate (online giving public page)
# Currently a minimal implementation so url_for('public.donate') and the nav tab work without 404/BuildError.
# The tab is only shown when settings.online_donations_enabled is truthy.
# TODO: Create templates/public/donate.html + proper query of online donation options (see settings/online_giving.py load_online_options).
# ----------------------------------------------------------------------
@public_bp.route('/donate')
def donate():
    """Public-facing donate / online giving landing."""
    # For now, send users to the rich public community feed (where they can see announcements etc.)
    # and give a helpful flash. Future: dedicated page listing Stripe/PayPal/Venmo/QR options from DB.
    flash('Thank you for supporting the ministry! Online giving options and links are available from our team or will appear here soon.', 'info')
    return redirect(url_for('public.public_dashboard.public_dashboard'))


@public_bp.route('/promotions')
@public_bp.route('/partners')
def promotions_list():
    """Public + member page for Ministry Partners (missionaries, prophets, ministries)."""
    from flask import abort, render_template, session
    from app.models import promotions as promo_model
    from app.models.module_toggles import get_module_toggles, is_module_enabled

    if not is_module_enabled('promotions', get_module_toggles()):
        abort(404)
    items = promo_model.list_promotions(published_only=True)
    if not items:
        abort(404)
    meta = promo_model.get_page_meta()
    is_logged_in = bool(session.get('user_id'))
    return render_template(
        'public/promotions.html',
        base_layout='base.html' if is_logged_in else 'base_public.html',
        items=items,
        page_title=meta.get('page_title') or 'Ministry Partners',
        page_intro=meta.get('page_intro') or '',
        is_logged_in=is_logged_in,
    )


@public_bp.route('/promotions/image/<path:filename>')
@public_bp.route('/partners/image/<path:filename>')
def promotion_image(filename):
    """Serve Ministry Partner photos (public)."""
    from flask import abort, current_app, send_from_directory
    from app.models import promotions as promo_model
    # Path traversal guard
    name = (filename or '').replace('\\', '/').split('/')[-1]
    if not name or name.startswith('.'):
        abort(404)
    folder = promo_model.promotions_upload_dir(current_app)
    return send_from_directory(folder, name)


@public_bp.route('/ui-preferences', methods=['POST'])
def ui_preferences():
    """
    Display prefs for visitors and members on public pages.
    Always stores in this browser session. Logged-in users also persist to their account.
    """
    from app.utils.ui_prefs import (
        apply_ui_prefs_to_session,
        save_user_ui_prefs,
        normalize_theme,
        normalize_font_scale,
        normalize_bible_scale,
        get_church_default_theme,
        CHURCH_DEFAULT_TOKEN,
    )

    payload = request.get_json(silent=True) or {}
    theme = (
        request.form.get('theme')
        or payload.get('theme')
        or request.values.get('theme')
        or session.get('user_theme')
    )
    font_scale = (
        request.form.get('font_scale')
        or payload.get('font_scale')
        or request.values.get('font_scale')
        or session.get('ui_font_scale')
    )
    bible_scale = (
        request.form.get('bible_scale')
        or payload.get('bible_scale')
        or request.values.get('bible_scale')
        or session.get('bible_font_scale')
    )

    raw_theme = (theme or '').strip().lower()
    follow_church = raw_theme in ('', CHURCH_DEFAULT_TOKEN, 'default', 'church-default')
    font_scale = normalize_font_scale(font_scale)
    bible_scale = normalize_bible_scale(bible_scale)
    church = get_church_default_theme()

    if follow_church:
        effective = church
        session['guest_display_prefs'] = False
        session['ui_use_personal_theme'] = 0
    else:
        effective = normalize_theme(theme)
        session['guest_display_prefs'] = True
        session['ui_use_personal_theme'] = 1

    apply_ui_prefs_to_session(
        session,
        theme=CHURCH_DEFAULT_TOKEN if follow_church else effective,
        font_scale=font_scale,
        bible_scale=bible_scale,
        use_personal=not follow_church,
        church_default=church,
    )
    session.modified = True

    saved = {
        'theme': effective,
        'font_scale': font_scale,
        'bible_scale': bible_scale,
        'use_personal': not follow_church,
        'church_default': church,
    }
    user_id = session.get('user_id')
    if user_id:
        try:
            saved = save_user_ui_prefs(user_id, theme, font_scale, bible_scale)
            apply_ui_prefs_to_session(
                session,
                theme=saved['theme'] if saved.get('use_personal') else CHURCH_DEFAULT_TOKEN,
                font_scale=saved['font_scale'],
                bible_scale=saved['bible_scale'],
                use_personal=bool(saved.get('use_personal')),
                church_default=saved.get('church_default'),
            )
            session['ui_use_personal_theme'] = 1 if saved.get('use_personal') else 0
        except Exception as exc:
            print(f"public.ui_preferences account save: {exc}")
            return jsonify({'ok': True, **saved, 'persisted': 'session'})

    return jsonify({
        'ok': True,
        **saved,
        'persisted': 'account' if user_id else 'session',
    })
