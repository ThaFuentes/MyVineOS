from flask import flash

from .queries import slugify, category_slug_exists, article_slug_exists


def validate_category_form(form_data, cur, category_id=None):
    name = (form_data.get('name') or '').strip()
    slug = (form_data.get('slug') or '').strip() or slugify(name)
    description = (form_data.get('description') or '').strip() or None
    sort_order = int(form_data.get('sort_order') or 0)
    is_published = form_data.get('is_published') == '1'

    if not name:
        flash('Category name is required.', 'error')
        return None

    slug = slugify(slug)
    if category_slug_exists(cur, slug, exclude_id=category_id):
        flash('That category URL slug is already in use. Choose a different slug.', 'error')
        return None

    return {
        'name': name,
        'slug': slug,
        'description': description,
        'sort_order': sort_order,
        'is_published': is_published,
    }


def validate_article_form(form_data, cur, article_id=None):
    title = (form_data.get('title') or '').strip()
    slug = (form_data.get('slug') or '').strip() or slugify(title)
    summary = (form_data.get('summary') or '').strip() or None
    body_md = (form_data.get('body_md') or '').strip()
    permission_key = (form_data.get('permission_key') or '').strip() or None
    sort_order = int(form_data.get('sort_order') or 0)
    is_published = form_data.get('is_published') == '1'

    category_raw = (form_data.get('category_id') or '').strip()
    category_id_val = int(category_raw) if category_raw.isdigit() else None

    if not title:
        flash('Guide title is required.', 'error')
        return None
    if not body_md:
        flash('Guide instructions are required. Write the steps in the large text box.', 'error')
        return None

    slug = slugify(slug)
    if article_slug_exists(cur, slug, exclude_id=article_id):
        flash('That guide URL slug is already in use. Choose a different slug.', 'error')
        return None

    return {
        'title': title,
        'slug': slug,
        'summary': summary,
        'body_md': body_md,
        'category_id': category_id_val,
        'permission_key': permission_key,
        'sort_order': sort_order,
        'is_published': is_published,
    }