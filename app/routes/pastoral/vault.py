# app/routes/pastoral/vault.py
# Full path: WebChurchMan/app/routes/pastoral/vault.py
# File name: vault.py
# Brief, detailed purpose:
#   Blueprint for the Pastoral Vault module (saved sermon sections, reusable content).
#   - Unified library view (private + shared) - mirrors illustrations library style
#   - Manual add/edit/delete (with ownership enforcement)
#   - AJAX quick-save from sermon editor (/save_section_ajax)
#   - AJAX search for "Insert from Vault" modal (/search_ajax) - loads recent on empty query
#   - Safe tags parsing - no JSONDecodeError crash on bad DB data
#   - All routes require Pastoral Group membership (@pastoral_required)
#   - Consistent with illustrations.py: direct DB access, safe helpers, audit logging

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
import json
import pymysql

from . import pastoral_required
from app.models.log import log_change
from app.utils.helpers import contains_censored_word
from app.models.db import get_db

vault_bp = Blueprint('vault', __name__, url_prefix='/vault')


def _safe_load_tags(tags_raw) -> list:
    """Safe parse tags - same helper used in illustrations.py."""
    if tags_raw is None:
        return []
    if isinstance(tags_raw, list):
        return tags_raw
    if isinstance(tags_raw, str):
        try:
            parsed = json.loads(tags_raw)
            return parsed if isinstance(parsed, list) else [str(parsed)]
        except json.JSONDecodeError:
            return [t.strip() for t in tags_raw.split(',') if t.strip()]
    return []


def _collect_text_for_censor(data: dict) -> str:
    """Combine vault text fields for a single censorship scan."""
    tags = data.get('tags', '')
    if isinstance(tags, list):
        tags = ', '.join(tags)
    fields = [
        data.get('title', ''),
        data.get('content', ''),
        data.get('scripture_reference', '') or '',
        data.get('source_url', '') or '',
        data.get('notes', '') or '',
        tags,
    ]
    return ' '.join(str(f) for f in fields)


@vault_bp.route('/')
@pastoral_required()
def library():
    """Main Vault library - private + shared items, with optional search (mirrors illustrations)."""
    user_id = session['user_id']
    q = request.args.get('q', '').strip()

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    items = []

    sql = """
        SELECT pv.*, 'section' AS type, pv.source_url
        FROM pastoral_vault pv
        WHERE pv.user_id = %s OR pv.user_id IS NULL
    """
    params = [user_id]

    if q:
        like = f"%{q}%"
        sql += " AND (pv.title LIKE %s OR pv.content LIKE %s OR pv.scripture_reference LIKE %s OR pv.source_url LIKE %s OR pv.notes LIKE %s OR pv.tags LIKE %s)"
        params += [like] * 6

    cur.execute(sql, params)
    items = list(cur.fetchall())

    # Safe tags + common fields
    for item in items:
        item['tag_list'] = _safe_load_tags(item.get('tags'))
        item['source'] = item.get('source_url') or ''
        item['can_edit'] = (item.get('user_id') == user_id or session.get('user_role') in ['Admin', 'Owner'])

    # Sort newest first
    items.sort(key=lambda x: x.get('created_at') or '0000-00-00 00:00:00', reverse=True)

    total_count = len(items)

    # Edit handling
    edit_id = request.args.get('edit_id')
    edit_item = None
    if edit_id:
        try:
            edit_id = int(edit_id)
            cur.execute("""
                SELECT pv.*, 'section' AS type, pv.source_url AS source
                FROM pastoral_vault pv
                WHERE pv.id = %s AND (pv.user_id = %s OR pv.user_id IS NULL)
            """, (edit_id, user_id))
            edit_item = cur.fetchone()
            if edit_item:
                edit_item['tag_list'] = _safe_load_tags(edit_item.get('tags'))
                edit_item['tags_input'] = ', '.join(edit_item['tag_list'])
        except ValueError:
            flash('Invalid item ID.', 'error')

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        section_type = request.form.get('section_type', 'point')
        scripture_reference = request.form.get('scripture_reference', '').strip() or None
        source_url = request.form.get('source', '').strip()
        notes = request.form.get('notes', '').strip()
        tags_input = request.form.get('tags', '').strip()
        visibility = request.form.get('visibility', 'private')

        if not title or not content:
            flash('Title and content required.', 'error')
            return redirect(request.url)

        tag_list = [t.strip() for t in tags_input.split(',') if t.strip()]
        tags_json = json.dumps(tag_list)

        check_text = f"{title} {content} {scripture_reference or ''} {source_url} {notes} {tags_input}"
        if contains_censored_word(check_text):
            flash('Prohibited content detected.', 'error')
            return redirect(request.url)

        owner_id = user_id if visibility == 'private' else None

        try:
            if edit_item:
                cur.execute("""
                    UPDATE pastoral_vault
                    SET title = %s, content = %s, section_type = %s, scripture_reference = %s,
                        source_url = %s, notes = %s, tags = %s, user_id = %s, visibility = %s
                    WHERE id = %s
                """, (title, content, section_type, scripture_reference, source_url, notes, tags_json, owner_id, visibility, edit_id))
                db.commit()
                log_change(user_id, 'vault_update', edit_id, title, 'Updated vault item')
                flash('Vault item updated.', 'success')
            else:
                cur.execute("""
                    INSERT INTO pastoral_vault (
                        user_id, title, content, section_type, scripture_reference,
                        source_url, notes, tags, visibility
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (owner_id, title, content, section_type, scripture_reference, source_url, notes, tags_json, visibility))
                new_id = cur.lastrowid
                db.commit()
                log_change(user_id, 'vault_create', new_id, title, 'Created vault item')
                flash('Vault item created.', 'success')
            return redirect(url_for('pastoral.vault.library'))
        except Exception as e:
            flash(f'Database error: {str(e)}', 'error')

    return render_template(
        'pastoral/vault_library.html',
        items=items,
        total_count=total_count,
        q=q,
        edit_item=edit_item
    )


@vault_bp.route('/save_section_ajax', methods=['POST'])
@pastoral_required()
def save_section_ajax():
    """AJAX: Quick-save current sermon section to vault."""
    user_id = session['user_id']
    payload = request.get_json(silent=True) or {}

    title = (payload.get('title') or '').strip()
    content = (payload.get('content') or '').strip()
    notes = (payload.get('notes') or '').strip()
    empty_content = not content or content in ('<p><br></p>', '<p></p>')

    if not title and empty_content and not notes:
        return jsonify({
            'status': 'error',
            'message': 'Add a title, content, or private notes to save to Vault'
        }), 400

    if not title:
        st = (payload.get('section_type') or 'section').replace('_', ' ')
        title = f'Untitled {st.title()}'

    visibility = payload.get('visibility', 'private')
    if visibility not in ['private', 'pastoral_group']:
        visibility = 'private'

    owner_id = user_id if visibility == 'private' else None

    data = {
        'title': title,
        'content': content if not empty_content else '<p></p>',
        'section_type': payload.get('section_type', 'point'),
        'scripture_reference': payload.get('scripture_reference', '').strip() or None,
        'source_url': payload.get('source_url', '').strip() or None,
        'notes': payload.get('notes', '').strip() or None,
        'visibility': visibility,
        'tags': json.dumps(payload.get('tags', []))
    }

    if contains_censored_word(_collect_text_for_censor(data)):
        return jsonify({'status': 'error', 'message': 'Prohibited content detected'}), 400

    try:
        db = get_db()
        cur = db.cursor()
        cur.execute("""
            INSERT INTO pastoral_vault (
                user_id, title, content, section_type, scripture_reference,
                source_url, notes, tags, visibility
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (owner_id, data['title'], data['content'], data['section_type'],
              data['scripture_reference'], data['source_url'], data['notes'],
              data['tags'], data['visibility']))
        new_id = cur.lastrowid
        db.commit()
        log_change(user_id, 'vault_create', new_id, data['title'][:50], 'Quick-saved sermon section to Vault')
        return jsonify({'status': 'success', 'id': new_id})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@vault_bp.route('/search_ajax')
@pastoral_required()
def search_ajax():
    """AJAX search for Insert from Vault modal - only vault items, safe on empty query."""
    user_id = session['user_id']
    query = request.args.get('q', '').strip()
    limit = int(request.args.get('limit', 50))

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    sql = """
        SELECT pv.*, 'section' AS type, pv.source_url
        FROM pastoral_vault pv
        WHERE pv.user_id = %s OR pv.user_id IS NULL
    """
    params = [user_id]

    if query:
        like = f"%{query}%"
        sql += " AND (pv.title LIKE %s OR pv.content LIKE %s OR pv.scripture_reference LIKE %s OR pv.source_url LIKE %s OR pv.notes LIKE %s OR pv.tags LIKE %s)"
        params += [like] * 6

    sql += " ORDER BY pv.created_at DESC LIMIT %s"
    params.append(limit)

    try:
        cur.execute(sql, params)
        items = list(cur.fetchall())

        for item in items:
            item['tag_list'] = _safe_load_tags(item.get('tags'))

        return jsonify({'items': items})

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Vault search failed: {str(e)}'
        }), 500