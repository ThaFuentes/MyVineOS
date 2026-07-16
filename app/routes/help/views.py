import json
from datetime import datetime

import pymysql
from flask import (
    render_template, request, redirect, url_for, flash, session, abort,
    Response,
)

from app.models.db import get_db
from app.models.log import log_change
from app.utils.decorators import login_required, permission_required
from app.utils.help_render import render_help_markdown
from app.routes.groups.utils import KNOWN_PERMISSIONS

from . import help_bp
from .utils import can_manage_help
from . import forms
from .queries import (
    list_published_articles,
    group_articles_by_category,
    search_articles,
    get_article_by_slug,
    get_related_articles,
    get_user_pinned_ids,
    list_pinned_articles,
    pin_article,
    unpin_article,
    is_article_pinned,
    list_all_categories,
    list_all_articles,
    get_category_by_id,
    get_article_by_id,
    create_category,
    update_category,
    delete_category,
    create_article,
    update_article,
    delete_article,
    list_published_categories,
)


def _permission_choices():
    return sorted(KNOWN_PERMISSIONS.items(), key=lambda x: x[1])


# ---------------------------------------------------------------------------
# User-facing Help Center
# ---------------------------------------------------------------------------

@help_bp.route('/')
@login_required
def help_index():
    tab = request.args.get('tab', 'browse')
    if tab not in ('browse', 'search', 'pinned'):
        tab = 'browse'

    q = request.args.get('q', '').strip()
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    user_id = session['user_id']

    pinned_ids = get_user_pinned_ids(cur, user_id)
    search_results = []
    pinned_articles = []
    browse_groups = []

    if tab == 'search' and q:
        search_results = search_articles(cur, q)
    elif tab == 'pinned':
        pinned_articles = list_pinned_articles(cur, user_id)
    else:
        articles = list_published_articles(cur)
        browse_groups = group_articles_by_category(cur, articles)

    return render_template(
        'help/index.html',
        tab=tab,
        query=q,
        browse_groups=browse_groups,
        search_results=search_results,
        pinned_articles=pinned_articles,
        pinned_ids=pinned_ids,
        can_manage=can_manage_help(),
    )


@help_bp.route('/article/<slug>')
@login_required
def help_article(slug):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    user_id = session['user_id']

    article = get_article_by_slug(cur, slug)
    if not article:
        abort(404)

    body_html = render_help_markdown(article['body_md'])
    related = get_related_articles(cur, article)
    pinned = is_article_pinned(cur, user_id, article['id'])

    return render_template(
        'help/article.html',
        article=article,
        body_html=body_html,
        related=related,
        is_pinned=pinned,
        can_manage=can_manage_help(),
    )


@help_bp.route('/pin/<int:article_id>', methods=['POST'])
@login_required
def help_pin(article_id):
    db = get_db()
    cur = db.cursor()
    if pin_article(cur, session['user_id'], article_id):
        db.commit()
        flash('Guide pinned to your list.', 'success')
    else:
        flash('Could not pin that guide.', 'error')
    return redirect(request.referrer or url_for('help.help_index', tab='pinned'))


@help_bp.route('/unpin/<int:article_id>', methods=['POST'])
@login_required
def help_unpin(article_id):
    db = get_db()
    cur = db.cursor()
    unpin_article(cur, session['user_id'], article_id)
    db.commit()
    flash('Guide removed from your pinned list.', 'success')
    return redirect(request.referrer or url_for('help.help_index', tab='pinned'))


# ---------------------------------------------------------------------------
# Admin - manage categories & articles
# ---------------------------------------------------------------------------

@help_bp.route('/manage')
@permission_required('manage_help')
def manage_index():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    categories = list_all_categories(cur)
    articles = list_all_articles(cur)
    return render_template(
        'help/manage/index.html',
        categories=categories,
        articles=articles,
    )


@help_bp.route('/manage/export')
@permission_required('manage_help')
def manage_export():
    """Download portable Help pack (slug-based JSON for git / other installs)."""
    from app.models.help_pack import pack_to_json

    body = pack_to_json()
    stamp = datetime.utcnow().strftime('%Y%m%d')
    log_change(session['user_id'], 'export', change_details='Exported portable help pack JSON')
    return Response(
        body,
        mimetype='application/json; charset=utf-8',
        headers={
            'Content-Disposition': f'attachment; filename="myvine_help_pack_{stamp}.json"',
        },
    )


@help_bp.route('/manage/import', methods=['POST'])
@permission_required('manage_help')
def manage_import():
    """Re-upload a myvine_help_v1 JSON pack (merge by slug; does not delete local-only guides)."""
    from app.models.help_pack import import_pack

    f = request.files.get('file')
    if not f or not f.filename:
        flash('Choose a help pack .json file to upload.', 'error')
        return redirect(url_for('help.manage_index'))
    try:
        raw = f.read()
        stats = import_pack(raw, user_id=session.get('user_id') or 1, replace_bodies=True)
    except Exception as e:
        flash(f'Help import failed: {e}', 'error')
        return redirect(url_for('help.manage_index'))

    log_change(
        session['user_id'], 'import',
        change_details=(
            f"Imported help pack: cats +{stats['categories_created']}/~{stats['categories_updated']}, "
            f"articles +{stats['articles_created']}/~{stats['articles_updated']}"
        ),
    )
    flash(
        f"Help pack imported. Categories: {stats['categories_created']} new, "
        f"{stats['categories_updated']} updated. Guides: {stats['articles_created']} new, "
        f"{stats['articles_updated']} updated."
        + (f" Skipped {stats['skipped']} invalid rows." if stats.get('skipped') else ''),
        'success',
    )
    return redirect(url_for('help.manage_index'))


@help_bp.route('/manage/categories/add', methods=['GET', 'POST'])
@help_bp.route('/manage/categories/edit/<int:category_id>', methods=['GET', 'POST'])
@permission_required('manage_help')
def manage_category(category_id=None):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    category = get_category_by_id(cur, category_id) if category_id else None

    if request.method == 'POST':
        clean = forms.validate_category_form(request.form, cur, category_id=category_id)
        if not clean:
            return render_template(
                'help/manage/category_form.html',
                category=category,
                form=request.form,
                editing=bool(category_id),
            )
        try:
            if category_id:
                update_category(cur, category_id, clean)
                log_change(session['user_id'], 'update', category_id, 'help_category',
                           f"Updated help category: {clean['name']}")
                flash('Category updated.', 'success')
            else:
                new_id = create_category(cur, clean)
                log_change(session['user_id'], 'create', new_id, 'help_category',
                           f"Created help category: {clean['name']}")
                flash('Category created.', 'success')
            db.commit()
            return redirect(url_for('help.manage_index'))
        except Exception as e:
            db.rollback()
            flash('Failed to save category.', 'error')
            print(f"Help category save error: {e}")

    return render_template(
        'help/manage/category_form.html',
        category=category,
        form=None,
        editing=bool(category_id),
    )


@help_bp.route('/manage/categories/delete/<int:category_id>', methods=['POST'])
@permission_required('manage_help')
def manage_category_delete(category_id):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    category = get_category_by_id(cur, category_id)
    if not category:
        flash('Category not found.', 'error')
        return redirect(url_for('help.manage_index'))
    try:
        delete_category(cur, category_id)
        db.commit()
        log_change(session['user_id'], 'delete', category_id, 'help_category',
                   f"Deleted help category: {category['name']}")
        flash('Category deleted. Its guides are now uncategorized.', 'success')
    except Exception as e:
        db.rollback()
        flash('Failed to delete category.', 'error')
        print(f"Help category delete error: {e}")
    return redirect(url_for('help.manage_index'))


@help_bp.route('/manage/articles/add', methods=['GET', 'POST'])
@help_bp.route('/manage/articles/edit/<int:article_id>', methods=['GET', 'POST'])
@permission_required('manage_help')
def manage_article(article_id=None):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    article = get_article_by_id(cur, article_id) if article_id else None
    categories = list_all_categories(cur)
    permission_choices = _permission_choices()

    if request.method == 'POST':
        clean = forms.validate_article_form(request.form, cur, article_id=article_id)
        if not clean:
            return render_template(
                'help/manage/article_form.html',
                article=article,
                categories=categories,
                permission_choices=permission_choices,
                form=request.form,
                editing=bool(article_id),
            )
        try:
            if article_id:
                update_article(cur, article_id, clean, session['user_id'])
                log_change(session['user_id'], 'update', article_id, 'help_article',
                           f"Updated help guide: {clean['title']}")
                flash('Guide updated.', 'success')
            else:
                new_id = create_article(cur, clean, session['user_id'])
                log_change(session['user_id'], 'create', new_id, 'help_article',
                           f"Created help guide: {clean['title']}")
                flash('Guide created.', 'success')
            db.commit()
            return redirect(url_for('help.manage_index'))
        except Exception as e:
            db.rollback()
            flash('Failed to save guide.', 'error')
            print(f"Help article save error: {e}")

    prefill_category = request.args.get('category_id')
    return render_template(
        'help/manage/article_form.html',
        article=article,
        categories=categories,
        permission_choices=permission_choices,
        form={'category_id': prefill_category} if prefill_category and not article else None,
        editing=bool(article_id),
    )


@help_bp.route('/manage/articles/delete/<int:article_id>', methods=['POST'])
@permission_required('manage_help')
def manage_article_delete(article_id):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    article = get_article_by_id(cur, article_id)
    if not article:
        flash('Guide not found.', 'error')
        return redirect(url_for('help.manage_index'))
    try:
        delete_article(cur, article_id)
        db.commit()
        log_change(session['user_id'], 'delete', article_id, 'help_article',
                   f"Deleted help guide: {article['title']}")
        flash('Guide deleted.', 'success')
    except Exception as e:
        db.rollback()
        flash('Failed to delete guide.', 'error')
        print(f"Help article delete error: {e}")
    return redirect(url_for('help.manage_index'))