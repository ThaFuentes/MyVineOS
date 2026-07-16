# app/routes/pastoral/illustrations.py
# Full path: WebChurchMan/app/routes/pastoral/illustrations.py
# File name: illustrations.py
# Brief, detailed purpose:
#   Routes and Blueprint for the ILLUSTRATION LIBRARY (pastoral area only) - Reusable TEXT content for sermons.
#   - Pure text/verbal library: written illustrations, stories, memories, analogies, reusable sermon blocks (NOT JPEG imagery or visual images).
#   - Pastors save reusable verbal content here from sermon builder (e.g. a near-death experience story) to reuse without re-typing.
#   - Unified with saved sermon Sections from Vault (auto-included as 'section' type).
#   - Type badge: "Illustration" (manual text) vs "Section" (saved from sermon builder).
#   - Search title/content/tags/notes/source (source = reference like book/experience, free text).
#   - Buttons: Insert into Sermon (injects content into editor section), View, Edit, Delete.
#   - Dock for quick access across sessions.
#   - Add New manual text illustration.
#   - Supports rich content (Quill editor).
#   - Robust for desktop pastoral use.

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, abort
import json
import pymysql

from . import pastoral_required
from app.models.log import log_change
from app.utils.helpers import contains_censored_word
from app.models.db import get_db
from app.models.pastoral.illustrations import (
    get_illustration_by_id,
    create_illustration,
    update_illustration,
    delete_illustration,
    get_visible_illustrations
)
from app.models.pastoral.vault import delete_vault_item
from app.models.pastoral.content_export import (
    format_illustration_markdown,
    illustration_to_docx,
    safe_filename,
    send_markdown_download,
    send_docx_download,
    zip_named_bytes,
)

illustrations_bp = Blueprint('illustrations', __name__, url_prefix='/illustrations')


def _fetch_library_item(item_id: int, user_id: int, kind: str | None = None) -> dict | None:
    """Load illustration or vault section by id (optionally forced kind)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    kind = (kind or '').strip().lower() or None

    if kind in (None, 'illustration', 'illus'):
        cur.execute(
            """
            SELECT il.*, 'illustration' AS type, il.source AS source_url
            FROM illustration_library il
            WHERE il.id = %s AND (il.user_id = %s OR il.user_id IS NULL)
            """,
            (item_id, user_id),
        )
        row = cur.fetchone()
        if row:
            return row
        if kind in ('illustration', 'illus'):
            return None

    if kind in (None, 'section', 'vault'):
        cur.execute(
            """
            SELECT pv.*, 'section' AS type, pv.source_url
            FROM pastoral_vault pv
            WHERE pv.id = %s AND (pv.user_id = %s OR pv.user_id IS NULL)
            """,
            (item_id, user_id),
        )
        return cur.fetchone()
    return None


@illustrations_bp.route('/quick_add', methods=['POST'])
@pastoral_required()
def quick_add():
    """AJAX endpoint to quickly save a text block as illustration from sermon editor or elsewhere."""
    user_id = session['user_id']
    data = request.get_json() or request.form
    title = (data.get('title') or 'Untitled Illustration').strip()
    content = (data.get('content') or '').strip()
    source = (data.get('source') or '').strip()
    tags = data.get('tags') or ''
    if not content:
        return jsonify({'error': 'Content required'}), 400
    try:
        new_id = create_illustration({
            'title': title,
            'content': content,
            'source': source,
            'tags': tags,
            'visibility': 'private'
        }, user_id)
        return jsonify({'success': True, 'id': new_id, 'title': title})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@illustrations_bp.route('/list_json', methods=['GET'])
@pastoral_required()
def list_json():
    """Simple JSON list of user's illustrations for insert modals in editor."""
    user_id = session['user_id']
    q = request.args.get('q', '').strip()
    items = get_visible_illustrations(user_id, search=q if q else None)
    # Return minimal for insert: id, title, content (text)
    simple = [{'id': i['id'], 'title': i.get('title'), 'content': i.get('content'), 'source': i.get('source','')} for i in items[:50]]
    return jsonify(simple)


def _safe_load_tags(tags_raw) -> list:
    if tags_raw is None:
        return []
    if isinstance(tags_raw, list):
        return tags_raw
    if isinstance(tags_raw, str):
        try:
            return json.loads(tags_raw)
        except json.JSONDecodeError:
            return []
    return []


@illustrations_bp.route('/library', methods=['GET', 'POST'])
@pastoral_required()
def library():
    user_id = session['user_id']
    user_role = session.get('user_role', 'Member')
    q = request.args.get('q', '').strip()
    edit_id = request.args.get('edit_id')

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    items = []

    # Campus isolation fragment (shared for both tables)
    try:
        from app.models.campuses import content_campus_filter_sql
        illus_campus_frag, illus_campus_params = content_campus_filter_sql(
            'il.campus_id', user_id=user_id, owner_column='il.user_id'
        )
        vault_campus_frag, vault_campus_params = content_campus_filter_sql(
            'pv.campus_id', user_id=user_id, owner_column='pv.user_id'
        )
    except Exception:
        illus_campus_frag, illus_campus_params = '', []
        vault_campus_frag, vault_campus_params = '', []

    # Illustrations
    illus_sql = """
        SELECT il.*, 'illustration' AS type, il.source AS source_url
        FROM illustration_library il
        WHERE (il.user_id = %s OR il.user_id IS NULL)
    """
    params = [user_id]
    illus_sql += illus_campus_frag
    params += list(illus_campus_params)

    if q:
        like = f"%{q}%"
        illus_sql += " AND (il.title LIKE %s OR il.content LIKE %s OR il.source LIKE %s OR il.tags LIKE %s OR il.notes LIKE %s)"
        params += [like] * 5

    cur.execute(illus_sql, params)
    items.extend(list(cur.fetchall()))

    # Vault sections
    vault_sql = """
        SELECT pv.*, 'section' AS type, pv.source_url
        FROM pastoral_vault pv
        WHERE (pv.user_id = %s OR pv.user_id IS NULL)
    """
    params = [user_id]
    vault_sql += vault_campus_frag
    params += list(vault_campus_params)

    if q:
        like = f"%{q}%"
        vault_sql += " AND (pv.title LIKE %s OR pv.content LIKE %s OR pv.scripture_reference LIKE %s OR pv.source_url LIKE %s OR pv.notes LIKE %s)"
        params += [like] * 5

    cur.execute(vault_sql, params)
    items.extend(list(cur.fetchall()))

    # Parse tags, add common fields, set can_edit
    for item in items:
        item['tag_list'] = _safe_load_tags(item.get('tags'))
        item['source_url'] = item.get('source_url') or item.get('source') or ''
        item['can_edit'] = (item.get('user_id') == user_id or user_role in ['Admin', 'Owner'])

    # Sort by created_at DESC
    items.sort(key=lambda x: x.get('created_at') or '0000-00-00 00:00:00', reverse=True)

    total_count = len(items)

    # Dock
    docked_ids = session.get('docked_items', [])
    for item in items:
        item['is_docked'] = item['id'] in docked_ids

    # Edit handling - both types
    edit_item = None
    if edit_id:
        try:
            edit_id = int(edit_id)
            edit_item = get_illustration_by_id(edit_id, user_id)
            if not edit_item:
                # Try vault
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
        source = request.form.get('source', '').strip()
        notes = request.form.get('notes', '').strip()
        tags_input = request.form.get('tags', '').strip()
        visibility = request.form.get('visibility', 'private')
        section_type = request.form.get('section_type')
        scripture_reference = request.form.get('scripture_reference', '').strip() or None

        if not title or not content:
            flash('Title and content are required.', 'error')
            return redirect(request.url)

        tag_list = [t.strip() for t in tags_input.split(',') if t.strip()]
        tags_json = json.dumps(tag_list)

        check_text = f"{title} {content} {source} {notes} {tags_input} {scripture_reference or ''}"
        if contains_censored_word(check_text):
            flash('Prohibited content detected.', 'error')
            return redirect(request.url)

        owner_id = user_id if visibility == 'private' else None

        try:
            if edit_item:
                if edit_item['type'] == 'section':
                    data = {
                        'title': title,
                        'content': content,
                        'section_type': section_type or 'point',
                        'scripture_reference': scripture_reference,
                        'source_url': source,
                        'notes': notes,
                        'tags': tags_json,
                        'visibility': visibility,
                    }
                    # Assume update_vault_item exists - add if not
                    # update_vault_item(edit_id, data, owner_id)
                    cur.execute("""
                        UPDATE pastoral_vault
                        SET title = %s, content = %s, section_type = %s, scripture_reference = %s,
                            source_url = %s, notes = %s, tags = %s, user_id = %s, visibility = %s
                        WHERE id = %s
                    """, (title, content, section_type or 'point', scripture_reference, source, notes, tags_json, owner_id, visibility, edit_id))
                    db.commit()
                    log_change(user_id, 'vault_update', edit_id, title, 'Updated saved section')
                else:
                    data = {
                        'title': title,
                        'content': content,
                        'source': source,
                        'notes': notes,
                        'tags': tags_json
                    }
                    update_illustration(edit_id, data, owner_id)
                    log_change(user_id, 'illustration_update', edit_id, title, 'Updated illustration')
                flash('Item updated.', 'success')
            else:
                # New is always illustration
                data = {
                    'title': title,
                    'content': content,
                    'source': source,
                    'notes': notes,
                    'tags': tags_json
                }
                new_id = create_illustration(data, owner_id)
                log_change(user_id, 'illustration_create', new_id, title, 'Created illustration')
                flash('Illustration created.', 'success')
            return redirect(url_for('pastoral.illustrations.library'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')

    return render_template(
        'pastoral/illustrations_library.html',
        items=items,
        total_count=total_count,
        q=q,
        edit_item=edit_item,
        docked_count=len(docked_ids)
    )


@illustrations_bp.route('/view/<int:item_id>')
@pastoral_required()
def view(item_id: int):
    user_id = session['user_id']
    kind = request.args.get('type') or request.args.get('kind')
    item = _fetch_library_item(item_id, user_id, kind)

    if not item:
        flash('Item not found or access denied.', 'error')
        return redirect(url_for('pastoral.illustrations.library'))

    item['tag_list'] = _safe_load_tags(item.get('tags'))

    return render_template(
        'pastoral/illustration_view.html',
        item=item
    )


@illustrations_bp.route('/download/<int:item_id>')
@pastoral_required()
def download(item_id: int):
    """Download one illustration or vault section as Markdown or DOCX (creator-owned content)."""
    user_id = session['user_id']
    kind = request.args.get('type') or request.args.get('kind')
    fmt = (request.args.get('format') or 'md').strip().lower()
    item = _fetch_library_item(item_id, user_id, kind)
    if not item:
        abort(404)

    item_kind = item.get('type') or 'illustration'
    item['tag_list'] = _safe_load_tags(item.get('tags'))
    base = safe_filename(item.get('title') or f'{item_kind}_{item_id}')

    log_change(
        user_id,
        'export',
        item_id,
        item.get('title'),
        f'Downloaded {item_kind} as {fmt}',
    )

    if fmt in ('docx', 'doc', 'word'):
        doc = illustration_to_docx(item, kind=item_kind)
        return send_docx_download(doc, f'{base}.docx')

    body = format_illustration_markdown(item, kind=item_kind)
    return send_markdown_download(body, f'{base}.md')


@illustrations_bp.route('/download/all')
@pastoral_required()
def download_all():
    """ZIP of all illustrations + vault sections visible to the creator."""
    user_id = session['user_id']
    fmt = (request.args.get('format') or 'md').strip().lower()
    as_docx = fmt in ('docx', 'doc', 'word')

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute(
        """
        SELECT il.*, 'illustration' AS type, il.source AS source_url
        FROM illustration_library il
        WHERE il.user_id = %s OR il.user_id IS NULL
        ORDER BY il.created_at DESC
        """,
        (user_id,),
    )
    items = list(cur.fetchall() or [])

    cur.execute(
        """
        SELECT pv.*, 'section' AS type, pv.source_url
        FROM pastoral_vault pv
        WHERE pv.user_id = %s OR pv.user_id IS NULL
        ORDER BY pv.created_at DESC
        """,
        (user_id,),
    )
    items.extend(list(cur.fetchall() or []))

    if not items:
        flash('No library content to download yet.', 'error')
        return redirect(url_for('pastoral.illustrations.library'))

    files = []
    for item in items:
        item['tag_list'] = _safe_load_tags(item.get('tags'))
        kind = item.get('type') or 'illustration'
        base = safe_filename(item.get('title') or f'{kind}_{item.get("id")}')
        folder = 'illustrations' if kind == 'illustration' else 'vault_sections'
        if as_docx:
            from app.models.pastoral.content_export import docx_bytes

            doc = illustration_to_docx(item, kind=kind)
            files.append((f'{folder}/{base}.docx', docx_bytes(doc).read()))
        else:
            body = format_illustration_markdown(item, kind=kind)
            files.append((f'{folder}/{base}.md', body.encode('utf-8')))

    log_change(
        user_id,
        'export_bulk',
        None,
        None,
        f'Downloaded {len(files)} library items as {"docx" if as_docx else "md"} zip',
    )
    return zip_named_bytes(files, 'MyVine_Illustrations_Library_{date}.zip')


@illustrations_bp.route('/delete/<int:item_id>', methods=['POST'])
@pastoral_required()
def delete(item_id: int):
    user_id = session['user_id']

    # Try illustration
    if delete_illustration(item_id, user_id):
        log_change(user_id, 'illustration_delete', item_id, None, 'Deleted illustration')
        flash('Illustration permanently deleted.', 'success')
    else:
        # Try vault
        delete_vault_item(item_id, user_id)
        log_change(user_id, 'vault_delete', item_id, None, 'Deleted saved section')
        flash('Saved section permanently deleted.', 'success')

    return redirect(url_for('pastoral.illustrations.library'))


@illustrations_bp.route('/dock', methods=['POST'])
@pastoral_required()
def dock():
    data = request.get_json(silent=True) or {}
    item_ids = data.get('item_ids', [])
    if not item_ids:
        # Single-item form style
        one = data.get('item_id') or request.form.get('item_id')
        if one:
            item_ids = [int(one)]
    if not item_ids:
        return jsonify({'status': 'error', 'message': 'No items selected'}), 400

    docked = list(session.get('docked_items', []) or [])
    for item_id in item_ids:
        try:
            iid = int(item_id)
        except (TypeError, ValueError):
            continue
        if iid not in docked:
            docked.append(iid)
    session['docked_items'] = docked
    session.modified = True

    return jsonify({'status': 'success', 'count': len(docked), 'docked_items': docked})


@illustrations_bp.route('/undock', methods=['POST'])
@pastoral_required()
def undock():
    """Remove one or more items from the sermon dock."""
    data = request.get_json(silent=True) or {}
    item_ids = data.get('item_ids', [])
    one = data.get('item_id') or request.form.get('item_id')
    if one and not item_ids:
        item_ids = [one]
    if not item_ids:
        return jsonify({'status': 'error', 'message': 'No items selected'}), 400

    remove = set()
    for item_id in item_ids:
        try:
            remove.add(int(item_id))
        except (TypeError, ValueError):
            pass
    docked = [i for i in (session.get('docked_items') or []) if int(i) not in remove]
    session['docked_items'] = docked
    session.modified = True
    return jsonify({'status': 'success', 'count': len(docked), 'docked_items': docked})


@illustrations_bp.route('/toggle_dock', methods=['POST'])
@pastoral_required()
def toggle_dock():
    """Dock or undock a single illustration/section (per-card control)."""
    data = request.get_json(silent=True) or {}
    raw = data.get('item_id') or request.form.get('item_id')
    try:
        item_id = int(raw)
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'message': 'Invalid item'}), 400

    docked = list(session.get('docked_items', []) or [])
    # normalize to ints
    docked = [int(x) for x in docked]
    if item_id in docked:
        docked = [x for x in docked if x != item_id]
        is_docked = False
    else:
        docked.append(item_id)
        is_docked = True
    session['docked_items'] = docked
    session.modified = True
    return jsonify({
        'status': 'success',
        'is_docked': is_docked,
        'count': len(docked),
        'docked_items': docked,
    })


@illustrations_bp.route('/clear_dock', methods=['POST'])
@pastoral_required()
def clear_dock():
    session.pop('docked_items', None)
    session.modified = True
    return jsonify({'status': 'success', 'count': 0})


@illustrations_bp.route('/insert/<int:sermon_id>', methods=['POST'])
@pastoral_required()
def insert_into_sermon(sermon_id: int):
    user_id = session['user_id']
    data = request.get_json() or {}
    item_id = data.get('item_id')
    if not item_id:
        return jsonify({'status': 'error', 'message': 'No item selected'}), 400

    # Unified - try illustration, then vault
    item = get_illustration_by_id(item_id, user_id)
    if not item:
        # Try vault
        cur = get_db().cursor(pymysql.cursors.DictCursor)
        cur.execute("""
            SELECT pv.*, 'section' AS type
            FROM pastoral_vault pv
            WHERE pv.id = %s AND (pv.user_id = %s OR pv.user_id IS NULL)
        """, (item_id, user_id))
        item = cur.fetchone()

    if not item:
        return jsonify({'status': 'error', 'message': 'Item not found or access denied'}), 404

    source_line = f"<p><em>Source: {item.get('source_url') or item.get('source', '')}</em></p>" if item.get('source_url') or item.get('source') else ""
    html = f"""
    <div class="inserted-content" data-item-id="{item_id}">
        <h3>{item['title']}</h3>
        <blockquote>{item['content']}</blockquote>
        {source_line}
    </div>
    """.strip()

    from app.models.pastoral.sermons import get_sermon_by_id, get_sermon_sections, save_sermon_sections

    sermon = get_sermon_by_id(sermon_id, user_id)
    if not sermon:
        return jsonify({'status': 'error', 'message': 'Sermon not found or access denied'}), 404

    sections = get_sermon_sections(sermon_id)
    source_ref = item.get('source_url') or item.get('source', '')
    if sections:
        last = dict(sections[-1])
        last['content'] = (last.get('content') or '') + html
        if not last.get('source') and source_ref:
            last['source'] = source_ref
        sections[-1] = last
    else:
        sections = [{
            'section_type': 'illustration',
            'title': item['title'],
            'content': html,
            'scripture_reference': '',
            'source': source_ref,
            'notes': '',
        }]
    save_sermon_sections(sermon_id, sections)

    item_type = item.get('type', 'content')
    log_change(
        user_id,
        'insert',
        sermon_id,
        str(item_id),
        f'Inserted {item_type} {item_id} into sermon {sermon_id}',
    )
    return jsonify({'status': 'success', 'html': html, 'persisted': True})