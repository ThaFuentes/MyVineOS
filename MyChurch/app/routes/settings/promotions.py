# Settings: Ministry Partners (missionaries, prophets, partner ministries).

from flask import (
    current_app, flash, redirect, render_template, request, session, url_for,
)

from app.models import promotions as promo_model
from app.models.log import log_change
from app.models.module_toggles import get_module_toggles, is_module_enabled, save_module_toggles

from . import has_section_permission, settings_bp


def _can_edit() -> bool:
    return session.get('user_role') in ('Owner', 'Admin') or has_section_permission('general')


@settings_bp.route('/promotions', methods=['GET', 'POST'])
@settings_bp.route('/partners', methods=['GET', 'POST'])
def promotions_manage():
    if not _can_edit():
        flash('Only Owner/Admin can manage Ministry Partners.', 'error')
        return redirect(url_for('settings.general'))

    promo_model.ensure_table()
    user_id = session['user_id']

    if request.method == 'POST':
        action = (request.form.get('action') or '').strip()

        if action == 'set_feature':
            # Show or completely hide Ministry Partners on the public/member site
            want_on = request.form.get('enabled') in ('1', 'true', 'on', 'yes')
            toggles = get_module_toggles()
            toggles['promotions'] = want_on
            save_module_toggles(toggles)
            log_change(
                user_id, 'update', None, None,
                'Enabled Ministry Partners on site' if want_on else 'Removed Ministry Partners from site',
            )
            if want_on:
                flash(
                    'Ministry Partners can appear on the site. Publish at least one partner so the link shows.',
                    'success',
                )
            else:
                flash(
                    'Ministry Partners is hidden from the whole site (nav, home tile, and public page).',
                    'success',
                )
            return redirect(url_for('settings.promotions_manage'))

        if action == 'save_page':
            promo_model.save_page_meta(
                request.form.get('page_title') or '',
                request.form.get('page_intro') or '',
            )
            log_change(user_id, 'update', None, None, 'Updated Ministry Partners page header')
            flash('Page header saved. Leave fields blank to hide them on the public page.', 'success')
            return redirect(url_for('settings.promotions_manage'))

        if action == 'add':
            title = (request.form.get('title') or '').strip()
            if not title:
                flash('Name / header is required.', 'error')
                return redirect(url_for('settings.promotions_manage'))
            image_path = None
            f = request.files.get('image')
            if f and f.filename:
                try:
                    image_path = promo_model.save_image(f, current_app)
                except ValueError as e:
                    flash(str(e), 'error')
                    return redirect(url_for('settings.promotions_manage'))
            new_id = promo_model.create_promotion({
                'title': title,
                'subtitle': request.form.get('subtitle'),
                'body_text': request.form.get('body_text'),
                'image_path': image_path,
                'link_url': request.form.get('link_url'),
                'link_label': request.form.get('link_label'),
                'badge': request.form.get('badge'),
                'is_published': 'is_published' in request.form,
            }, user_id)
            log_change(user_id, 'create', new_id, title, f'Added ministry partner: {title}')
            flash('Partner added.', 'success')
            return redirect(url_for('settings.promotions_manage'))

        promo_id = request.form.get('promo_id', type=int)
        if not promo_id:
            flash('Missing partner.', 'error')
            return redirect(url_for('settings.promotions_manage'))

        existing = promo_model.get_promotion(promo_id)
        if not existing:
            flash('Partner not found.', 'error')
            return redirect(url_for('settings.promotions_manage'))

        if action == 'update':
            title = (request.form.get('title') or '').strip()
            if not title:
                flash('Name / header is required.', 'error')
                return redirect(url_for('settings.promotions_manage'))
            data = {
                'title': title,
                'subtitle': request.form.get('subtitle'),
                'body_text': request.form.get('body_text'),
                'link_url': request.form.get('link_url'),
                'link_label': request.form.get('link_label'),
                'badge': request.form.get('badge'),
                'is_published': 'is_published' in request.form,
            }
            f = request.files.get('image')
            if f and f.filename:
                try:
                    new_img = promo_model.save_image(f, current_app)
                    if existing.get('image_path'):
                        promo_model.delete_image_file(existing['image_path'], current_app)
                    data['image_path'] = new_img
                except ValueError as e:
                    flash(str(e), 'error')
                    return redirect(url_for('settings.promotions_manage'))
            if request.form.get('remove_image') == '1' and existing.get('image_path'):
                promo_model.delete_image_file(existing['image_path'], current_app)
                data['image_path'] = None
            promo_model.update_promotion(promo_id, data, user_id)
            log_change(user_id, 'update', promo_id, title, f'Updated ministry partner: {title}')
            flash('Partner updated.', 'success')
            return redirect(url_for('settings.promotions_manage'))

        if action == 'delete':
            name = existing.get('title') or str(promo_id)
            promo_model.delete_promotion(promo_id, current_app)
            log_change(user_id, 'delete', promo_id, name, f'Deleted ministry partner: {name}')
            flash('Partner removed.', 'success')
            return redirect(url_for('settings.promotions_manage'))

        if action in ('move_up', 'move_down'):
            ok = promo_model.reorder_promotion(promo_id, 'up' if action == 'move_up' else 'down')
            if ok:
                log_change(
                    user_id, 'update', promo_id, existing.get('title'),
                    f"Reordered ministry partner {action.replace('_', ' ')}",
                )
                flash('Order updated.', 'success')
            else:
                flash('Already at the end of the list.', 'info')
            return redirect(url_for('settings.promotions_manage'))

        if action == 'toggle_publish':
            new_pub = not bool(existing.get('is_published'))
            promo_model.update_promotion(promo_id, {'is_published': new_pub}, user_id)
            flash(
                'Published on the Partners page.' if new_pub else 'Unpublished — no longer shown on the site.',
                'success',
            )
            return redirect(url_for('settings.promotions_manage'))

        flash('Unknown action.', 'error')
        return redirect(url_for('settings.promotions_manage'))

    items = promo_model.list_promotions(published_only=False)
    meta = promo_model.get_page_meta()
    feature_enabled = is_module_enabled('promotions', get_module_toggles())
    published_count = sum(1 for i in items if i.get('is_published'))
    return render_template(
        'settings/promotions.html',
        items=items,
        page_title=meta.get('page_title') or '',
        page_intro=meta.get('page_intro') or '',
        published_count=published_count,
        feature_enabled=feature_enabled,
        site_visible=feature_enabled and published_count > 0,
    )
