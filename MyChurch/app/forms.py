from flask import flash
from app.utils.helpers import contains_censored_word


def validate_notice_form(form_data):
    category_id = form_data.get('category_id', '').strip()
    title = form_data.get('title', '').strip()
    content = form_data.get('content', '').strip()
    summary = form_data.get('summary', '').strip()
    is_active = 1 if form_data.get('is_active') else 0
    sort_order = form_data.get('sort_order', '0').strip() or '0'

    if not category_id or not str(category_id).isdigit():
        flash('Please select a category.', 'error')
        return None
    if not title:
        flash('Title is required.', 'error')
        return None
    if not content:
        flash('Content is required.', 'error')
        return None
    if contains_censored_word(f'{title} {summary} {content}'):
        flash('Notice contains a prohibited word or phrase.', 'error')
        return None

    try:
        sort_order = int(sort_order)
    except ValueError:
        sort_order = 0

    return {
        'category_id': int(category_id),
        'title': title,
        'summary': summary,
        'content': content,
        'is_active': bool(is_active),
        'sort_order': sort_order,
    }