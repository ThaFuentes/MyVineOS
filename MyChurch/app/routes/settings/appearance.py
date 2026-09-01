# Settings → Welcome page (photos, featured spots, which sections guests see).

from flask import render_template, request, redirect, url_for, flash, session

from app.models.db import get_db
from app.models.log import log_change
from app.utils.appearance import (
    get_appearance,
    list_hero_images,
    save_hero_image,
    delete_hero_image,
    set_hero_enabled,
    list_welcome_features,
    save_welcome_feature,
    delete_welcome_feature,
    set_welcome_feature_enabled,
    move_welcome_feature,
    sanitize_public_href,
)
from app.utils.html_sanitize import sanitize_plain_text
from . import settings_bp, has_section_permission, load_settings


def _checked(name):
    return 1 if request.form.get(name) in ('1', 'on', 'true', 'yes') else 0


@settings_bp.route('/appearance', methods=['GET', 'POST'])
def appearance():
    if request.method == 'POST' and not has_section_permission('general'):
        flash('Insufficient permission to edit appearance.', 'error')
        return redirect(url_for('settings.appearance'))

    db = get_db()
    user_id = session['user_id']
    action = request.form.get('action')

    if request.method == 'POST':
        if action == 'save_copy':
            welcome_mode = request.form.get('welcome_hero_mode') or 'theme'
            login_mode = request.form.get('login_hero_mode') or 'theme'
            if welcome_mode not in ('theme', 'image', 'rotating'):
                welcome_mode = 'theme'
            if login_mode not in ('theme', 'image', 'rotating'):
                login_mode = 'theme'
            try:
                welcome_interval = max(3, min(30, int(request.form.get('welcome_hero_interval_sec') or 6)))
            except (TypeError, ValueError):
                welcome_interval = 6
            try:
                login_interval = max(3, min(30, int(request.form.get('login_hero_interval_sec') or 8)))
            except (TypeError, ValueError):
                login_interval = 8
            cur = db.cursor()
            cur.execute(
                """
                UPDATE settings SET
                    welcome_tagline = %s,
                    welcome_verse = %s,
                    welcome_kicker = %s,
                    welcome_hero_mode = %s,
                    welcome_hero_interval_sec = %s,
                    login_hero_mode = %s,
                    login_hero_interval_sec = %s,
                    welcome_show_services = %s,
                    welcome_show_about = %s,
                    welcome_show_events = %s,
                    welcome_show_verse = %s,
                    welcome_show_featured = %s,
                    welcome_show_quick_links = %s,
                    welcome_show_ctas = %s,
                    welcome_featured_heading = %s,
                    welcome_cta1_label = %s,
                    welcome_cta1_url = %s,
                    welcome_cta2_label = %s,
                    welcome_cta2_url = %s
                WHERE id = 1
                """,
                (
                    sanitize_plain_text(request.form.get('welcome_tagline')) or None,
                    sanitize_plain_text(request.form.get('welcome_verse')) or None,
                    sanitize_plain_text(request.form.get('welcome_kicker'))[:160] or None,
                    welcome_mode,
                    welcome_interval,
                    login_mode,
                    login_interval,
                    _checked('welcome_show_services'),
                    _checked('welcome_show_about'),
                    _checked('welcome_show_events'),
                    _checked('welcome_show_verse'),
                    _checked('welcome_show_featured'),
                    _checked('welcome_show_quick_links'),
                    _checked('welcome_show_ctas'),
                    sanitize_plain_text(request.form.get('welcome_featured_heading'))[:160] or None,
                    sanitize_plain_text(request.form.get('welcome_cta1_label'))[:80] or None,
                    sanitize_public_href(request.form.get('welcome_cta1_url')) or None,
                    sanitize_plain_text(request.form.get('welcome_cta2_label'))[:80] or None,
                    sanitize_public_href(request.form.get('welcome_cta2_url')) or None,
                ),
            )
            db.commit()
            log_change(user_id, 'update', None, None, 'Updated welcome page appearance')
            flash('Welcome page saved.', 'success')
            return redirect(url_for('settings.appearance'))

        if action == 'upload_hero':
            surface = request.form.get('surface') or 'welcome'
            if surface not in ('welcome', 'login'):
                surface = 'welcome'
            try:
                save_hero_image(surface, request.files.get('hero_image'), request.form.get('caption') or '')
                flash('Image added.', 'success')
            except Exception as exc:
                flash(str(exc) or 'Could not save that image.', 'error')
            return redirect(url_for('settings.appearance'))

        if action == 'delete_hero':
            try:
                delete_hero_image(int(request.form.get('image_id') or 0))
                flash('Image removed.', 'success')
            except Exception:
                flash('Could not remove that image.', 'error')
            return redirect(url_for('settings.appearance'))

        if action == 'toggle_hero':
            try:
                set_hero_enabled(
                    int(request.form.get('image_id') or 0),
                    request.form.get('enabled') == '1',
                )
                flash('Image updated.', 'success')
            except Exception:
                flash('Could not update that image.', 'error')
            return redirect(url_for('settings.appearance'))

        if action == 'save_feature':
            feature_id = request.form.get('feature_id')
            try:
                save_welcome_feature(
                    request.form,
                    request.files.get('feature_image'),
                    int(feature_id) if feature_id else None,
                )
                flash('Welcome highlight saved.', 'success')
            except ValueError as exc:
                flash(str(exc), 'error')
            except Exception:
                flash('Could not save that highlight.', 'error')
            return redirect(url_for('settings.appearance'))

        if action == 'delete_feature':
            try:
                delete_welcome_feature(int(request.form.get('feature_id') or 0))
                flash('Highlight removed.', 'success')
            except Exception:
                flash('Could not remove that highlight.', 'error')
            return redirect(url_for('settings.appearance'))

        if action == 'toggle_feature':
            try:
                set_welcome_feature_enabled(
                    int(request.form.get('feature_id') or 0),
                    request.form.get('enabled') == '1',
                )
                flash('Highlight updated.', 'success')
            except Exception:
                flash('Could not update that highlight.', 'error')
            return redirect(url_for('settings.appearance'))

        if action in ('move_feature_up', 'move_feature_down'):
            try:
                move_welcome_feature(
                    int(request.form.get('feature_id') or 0),
                    'up' if action == 'move_feature_up' else 'down',
                )
            except Exception:
                flash('Could not reorder that highlight.', 'error')
            return redirect(url_for('settings.appearance'))

    settings = load_settings()
    return render_template(
        'settings/appearance.html',
        settings=settings,
        appearance=get_appearance(settings),
        welcome_images=list_hero_images('welcome', enabled_only=False),
        login_images=list_hero_images('login', enabled_only=False),
        welcome_features=list_welcome_features(enabled_only=False),
    )
