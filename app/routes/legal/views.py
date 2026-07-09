from functools import wraps
from flask import render_template, request, redirect, url_for, flash, session, abort
from app.utils.decorators import login_required
from app.utils.permissions import user_has_permission
from app.models.log import log_change
from app.models import legal as legal_model
from . import legal_bp
from .forms import validate_notice_form
from .utils import starter_for_category


def manage_legal_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not user_has_permission('manage_legal_notices'):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _create_form_context(notice=None, category_slug=None):
    categories = legal_model.get_all_categories()
    preselect_category_id = None
    starter_title = ''
    starter_content = ''

    if notice:
        preselect_category_id = notice.get('category_id')
    elif category_slug:
        cat = legal_model.get_category_by_slug(category_slug)
        if cat:
            preselect_category_id = cat['id']
            starter = starter_for_category(category_slug)
            if starter:
                starter_title, starter_content = starter

    return {
        'notice': notice,
        'categories': categories,
        'preselect_category_id': preselect_category_id,
        'starter_title': starter_title,
        'starter_content': starter_content,
        'lock_category': bool(category_slug and not notice),
    }


@legal_bp.route('/')
def legal_index():
    can_manage = user_has_permission('manage_legal_notices')
    categories = legal_model.get_active_notices_grouped(published_only=True)
    community_guidelines = legal_model.get_active_notice_for_category('community_guidelines')
    category_overview = legal_model.get_category_publication_overview() if can_manage else None
    return render_template(
        'legal/index.html',
        categories=categories,
        community_guidelines=community_guidelines,
        category_overview=category_overview,
        can_manage=can_manage,
    )


@legal_bp.route('/notice/<slug>')
def view_notice(slug):
    notice = legal_model.get_notice_by_slug(slug, active_only=True)
    if not notice:
        abort(404)

    related = []
    community_guidelines = None
    if notice['category_slug'] == 'comment_policy':
        community_guidelines = legal_model.get_active_notice_for_category('community_guidelines')

    for cat in legal_model.get_active_notices_grouped(published_only=True):
        for n in cat['notices']:
            if n['slug'] != slug:
                related.append({
                    'title': n['title'],
                    'slug': n['slug'],
                    'category_name': cat['category_name'],
                })

    return render_template(
        'legal/view.html',
        notice=notice,
        related=related[:6],
        community_guidelines=community_guidelines,
        can_manage=user_has_permission('manage_legal_notices'),
    )


@legal_bp.route('/manage')
@manage_legal_required
def manage_list():
    categories = legal_model.get_categories_for_manage()
    published_count = sum(1 for c in categories if c['status'] == 'published')
    total_notices = sum(c['notice_count'] for c in categories)
    return render_template(
        'legal/manage.html',
        categories=categories,
        published_count=published_count,
        total_categories=len(categories),
        total_notices=total_notices,
    )


@legal_bp.route('/manage/category/<category_slug>')
@manage_legal_required
def manage_category(category_slug):
    """Shortcut: edit the primary notice in a category, or start a new one."""
    cat = legal_model.get_category_by_slug(category_slug)
    if not cat:
        abort(404)

    categories = legal_model.get_categories_for_manage()
    match = next((c for c in categories if c['slug'] == category_slug), None)
    if match and match['notices']:
        return redirect(url_for('legal.edit_notice', notice_id=match['notices'][0]['id']))
    return redirect(url_for('legal.create_notice', category=category_slug))


@legal_bp.route('/manage/create', methods=['GET', 'POST'])
@manage_legal_required
def create_notice():
    category_slug = request.args.get('category', '').strip()

    if request.method == 'POST':
        cleaned = validate_notice_form(request.form)
        if cleaned:
            notice_id = legal_model.create_notice(
                category_id=cleaned['category_id'],
                title=cleaned['title'],
                content=cleaned['content'],
                summary=cleaned['summary'],
                is_active=cleaned['is_active'],
                sort_order=cleaned['sort_order'],
                created_by=session.get('user_id'),
            )
            log_change(
                session['user_id'],
                'create',
                notice_id,
                cleaned['title'],
                'Created legal notice',
            )
            flash('Legal notice saved.', 'success')
            return redirect(url_for('legal.manage_list'))

    return render_template(
        'legal/edit.html',
        **_create_form_context(category_slug=category_slug or None),
    )


@legal_bp.route('/manage/edit/<int:notice_id>', methods=['GET', 'POST'])
@manage_legal_required
def edit_notice(notice_id):
    notice = legal_model.get_notice_by_id(notice_id)
    if not notice:
        abort(404)

    if request.method == 'POST':
        cleaned = validate_notice_form(request.form)
        if cleaned:
            legal_model.update_notice(
                notice_id=notice_id,
                category_id=cleaned['category_id'],
                title=cleaned['title'],
                content=cleaned['content'],
                summary=cleaned['summary'],
                is_active=cleaned['is_active'],
                sort_order=cleaned['sort_order'],
                updated_by=session.get('user_id'),
            )
            log_change(
                session['user_id'],
                'update',
                notice_id,
                cleaned['title'],
                'Updated legal notice',
            )
            flash('Legal notice saved.', 'success')
            return redirect(url_for('legal.manage_list'))

    return render_template(
        'legal/edit.html',
        **_create_form_context(notice=notice),
    )


@legal_bp.route('/manage/toggle/<int:notice_id>', methods=['POST'])
@manage_legal_required
def toggle_notice(notice_id):
    notice = legal_model.get_notice_by_id(notice_id)
    if not notice:
        abort(404)

    new_state = not bool(notice['is_active'])
    legal_model.set_notice_active(notice_id, new_state, session.get('user_id'))
    log_change(
        session['user_id'],
        'update',
        notice_id,
        notice['title'],
        f"Legal notice {'published' if new_state else 'unpublished'}",
    )
    flash(
        f"{'Published' if new_state else 'Unpublished'}: {notice['title']}.",
        'success',
    )
    return redirect(request.referrer or url_for('legal.manage_list'))


@legal_bp.route('/manage/delete/<int:notice_id>', methods=['POST'])
@manage_legal_required
def delete_notice(notice_id):
    notice = legal_model.get_notice_by_id(notice_id)
    if not notice:
        abort(404)
    legal_model.delete_notice(notice_id)
    log_change(
        session['user_id'],
        'delete',
        notice_id,
        notice['title'],
        'Deleted legal notice',
    )
    flash('Legal notice deleted.', 'success')
    return redirect(url_for('legal.manage_list'))