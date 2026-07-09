# app/routes/pastoral/bible.py — Bible study, upload, search, Strong's integration.

from flask import (
    Blueprint, render_template, request, jsonify, abort, flash, redirect, url_for, session,
)
from werkzeug.utils import secure_filename
import json
import os
import tempfile

from . import pastoral_required
from app.utils.decorators import role_required
from app.models.log import log_change
from app.models.pastoral.bible import (
    get_bible_translations,
    set_bible_default,
    delete_bible_translation,
    import_bible_translation,
    bible_search,
    bible_get_chapter,
    bible_get_verse,
    get_bible_books,
    get_chapter_count,
    get_strongs_entry,
    search_strongs_lexicon,
    get_strongs_for_verse,
    get_strongs_occurrences,
    import_strongs_lexicon,
    import_strongs_occurrences,
    normalize_book_name,
)
from app.models.pastoral.sermons import (
    get_sermon_by_id, get_sermon_sections, save_sermon_sections,
    get_visible_sermons, create_sermon,
)
from app.models.pastoral.illustrations import create_illustration

bible_bp = Blueprint('bible', __name__, url_prefix='/bible')

ALLOWED_EXTENSIONS = {'json'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@bible_bp.route('/study')
@pastoral_required()
def bible_study():
    translations = get_bible_translations()
    books = get_bible_books()
    user_id = session['user_id']
    sermon_id = request.args.get('sermon_id', type=int)
    sermon = None
    if sermon_id:
        sermon = get_sermon_by_id(sermon_id, user_id)
    sermons = get_visible_sermons(user_id, limit=50)
    return render_template(
        'pastoral/bible_study.html',
        translations=translations,
        books=books,
        sermon=sermon,
        sermon_id=sermon_id if sermon else None,
        sermons=sermons,
        page_title='Bible Study',
    )


@bible_bp.route('/upload', methods=['GET', 'POST'])
@pastoral_required()
@role_required(['Admin', 'Owner'])
def bible_upload():
    translations = get_bible_translations()

    if request.method == 'POST':
        action = request.form.get('action', 'upload')

        if action == 'set_default':
            code = request.form.get('translation_code', '').strip()
            if code:
                set_bible_default(code)
                flash(f'Default translation set to {code}.', 'success')
                log_change(session['user_id'], 'update', None, code, 'Set default Bible translation')
            return redirect(url_for('pastoral.bible.bible_upload'))

        if action == 'delete_translation':
            code = request.form.get('translation_code', '').strip()
            if code:
                delete_bible_translation(code)
                flash(f'Translation {code} deleted.', 'success')
                log_change(session['user_id'], 'delete', None, code, 'Deleted Bible translation')
            return redirect(url_for('pastoral.bible.bible_upload'))

        if action == 'upload_strongs_lexicon':
            return _handle_strongs_upload('lexicon')

        if action == 'upload_strongs_occurrences':
            return _handle_strongs_upload('occurrences')

        if 'bible_file' not in request.files:
            flash('No file selected.', 'error')
            return redirect(url_for('pastoral.bible.bible_upload'))

        file = request.files['bible_file']
        if not file.filename:
            flash('No file selected.', 'error')
            return redirect(url_for('pastoral.bible.bible_upload'))

        if file and allowed_file(file.filename):
            temp_dir = tempfile.mkdtemp()
            filename = secure_filename(file.filename)
            file_path = os.path.join(temp_dir, filename)
            file.save(file_path)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    bible_data = json.load(f)
                if not isinstance(bible_data, dict):
                    raise ValueError('JSON must be an object with translation, name, verses')
                code = (bible_data.get('translation') or bible_data.get('code') or '').strip()
                name = (bible_data.get('name') or code).strip()
                verses = bible_data.get('verses') or []
                if not code or not name:
                    raise ValueError('translation code and name are required')
                count = import_bible_translation(
                    code, name, verses,
                    set_default=bool(bible_data.get('set_default')),
                )
                flash(f'Imported {count} verses for {name} ({code}).', 'success')
                log_change(session['user_id'], 'upload', None, code, f'Imported Bible translation {code} ({count} verses)')
            except Exception as e:
                flash(f'Error processing Bible file: {e}', 'error')
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
            return redirect(url_for('pastoral.bible.bible_upload'))

        flash('Invalid file type. Upload .json only.', 'error')
        return redirect(url_for('pastoral.bible.bible_upload'))

    return render_template('pastoral/bible_upload.html', translations=translations)


def _handle_strongs_upload(kind: str):
    field = 'strongs_file'
    if field not in request.files or not request.files[field].filename:
        flash('No Strong\'s JSON file selected.', 'error')
        return redirect(url_for('pastoral.bible.bible_upload'))
    file = request.files[field]
    if not allowed_file(file.filename):
        flash('Invalid file type.', 'error')
        return redirect(url_for('pastoral.bible.bible_upload'))
    try:
        data = json.load(file.stream)
        if kind == 'lexicon':
            entries = data if isinstance(data, list) else data.get('entries', [])
            count = import_strongs_lexicon(entries)
            flash(f'Imported {count} Strong\'s lexicon entries.', 'success')
        else:
            rows = data if isinstance(data, list) else data.get('occurrences', [])
            count = import_strongs_occurrences(rows)
            flash(f'Imported {count} Strong\'s occurrence links.', 'success')
        log_change(session['user_id'], 'upload', None, kind, f'Imported Strong\'s {kind}')
    except Exception as e:
        flash(f'Strong\'s import error: {e}', 'error')
    return redirect(url_for('pastoral.bible.bible_upload'))


@bible_bp.route('/search', methods=['GET', 'POST'])
@pastoral_required()
def bible_search_route():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        query = (data.get('query') or data.get('q') or '').strip()
        translation = data.get('translation')
        limit = int(data.get('limit', 30))
    else:
        query = request.args.get('q', '').strip()
        translation = request.args.get('translation')
        limit = int(request.args.get('limit', 30))

    if not query:
        return jsonify({'verses': []})

    verses = bible_search(query, translation, limit)
    return jsonify({'verses': verses})


@bible_bp.route('/chapter/<book>/<int:chapter>')
@pastoral_required()
def bible_chapter(book, chapter):
    translation = request.args.get('translation')
    book = normalize_book_name(book)
    verses = bible_get_chapter(book, chapter, translation)
    if not verses:
        abort(404)
    strongs_map = {}
    for v in verses:
        strongs_map[v['verse']] = get_strongs_for_verse(book, chapter, v['verse'])
    return jsonify({
        'book': book,
        'chapter': chapter,
        'translation': translation,
        'max_chapter': get_chapter_count(book, translation),
        'verses': verses,
        'strongs': strongs_map,
    })


@bible_bp.route('/verse/<book>/<int:chapter>/<int:verse>')
@pastoral_required()
def bible_verse(book, chapter, verse):
    translation = request.args.get('translation')
    row = bible_get_verse(book, chapter, verse, translation)
    if not row:
        abort(404)
    row['strongs'] = get_strongs_for_verse(row['book'], chapter, verse)
    return jsonify(row)


@bible_bp.route('/strongs/<number>')
@pastoral_required()
def strongs_detail(number):
    entry = get_strongs_entry(number)
    if not entry:
        abort(404)
    entry['occurrences'] = get_strongs_occurrences(number, limit=100)
    return jsonify(entry)


@bible_bp.route('/strongs/search')
@pastoral_required()
def strongs_search_route():
    q = request.args.get('q', '').strip()
    limit = int(request.args.get('limit', 40))
    return jsonify({'entries': search_strongs_lexicon(q, limit)})


@bible_bp.route('/quick_sermon', methods=['POST'])
@pastoral_required()
def quick_sermon():
    """Create a blank sermon linked to Bible Study (optionally with a passage)."""
    user_id = session['user_id']
    data = request.get_json(silent=True) or {}
    reference = (data.get('reference') or data.get('primary_passage') or '').strip()
    title = (data.get('title') or '').strip()
    if not title:
        title = f"Sermon — {reference}" if reference else "New Sermon from Bible Study"
    sermon_id = create_sermon({
        'title': title,
        'primary_passage': reference or None,
        'visibility': 'private',
    }, user_id)
    log_change(user_id, 'create', sermon_id, title, 'Quick sermon from Bible Study')
    return jsonify({
        'status': 'success',
        'sermon_id': sermon_id,
        'title': title,
        'edit_url': url_for('pastoral.sermons.edit', sermon_id=sermon_id),
        'study_url': url_for('pastoral.bible.bible_study', sermon_id=sermon_id),
    })


@bible_bp.route('/save_illustration', methods=['POST'])
@pastoral_required()
def save_illustration():
    """Save scripture or Strong's text to the illustration library."""
    user_id = session['user_id']
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or 'Scripture note').strip()
    content = (data.get('content') or '').strip()
    source = (data.get('source') or '').strip()
    if not content:
        book = normalize_book_name(data.get('book', ''))
        chapter = data.get('chapter')
        verse = data.get('verse')
        if book and chapter and verse:
            row = bible_get_verse(book, int(chapter), int(verse), data.get('translation'))
            if row:
                title = row['reference']
                content = row['text']
                source = data.get('translation') or source
    if not content:
        return jsonify({'status': 'error', 'message': 'Content required'}), 400
    new_id = create_illustration({
        'title': title,
        'content': content,
        'source': source,
        'tags': data.get('tags') or 'bible,scripture',
        'visibility': 'private',
    }, user_id)
    log_change(user_id, 'illustration_create', new_id, title, 'Saved from Bible Study')
    return jsonify({
        'status': 'success',
        'id': new_id,
        'title': title,
        'library_url': url_for('pastoral.illustrations.library'),
    })


@bible_bp.route('/insert/<int:sermon_id>', methods=['POST'])
@pastoral_required()
def insert_verse_into_sermon(sermon_id: int):
    """Persist a scripture block into the sermon sections table."""
    user_id = session['user_id']
    sermon = get_sermon_by_id(sermon_id, user_id)
    if not sermon:
        return jsonify({'status': 'error', 'message': 'Sermon not found or access denied'}), 404

    data = request.get_json(silent=True) or {}
    reference = (data.get('reference') or '').strip()
    text = (data.get('text') or '').strip()
    if not reference or not text:
        book = normalize_book_name(data.get('book', ''))
        chapter = data.get('chapter')
        verse = data.get('verse')
        if book and chapter and verse:
            row = bible_get_verse(book, int(chapter), int(verse), data.get('translation'))
            if row:
                reference = row['reference']
                text = row['text']
    if not reference or not text:
        return jsonify({'status': 'error', 'message': 'Reference and text required'}), 400

    html = f"""
    <div class="inserted-scripture" data-reference="{reference}">
        <p><strong>{reference}</strong></p>
        <blockquote>{text}</blockquote>
    </div>
    """.strip()

    sections = get_sermon_sections(sermon_id)
    if sections:
        last = dict(sections[-1])
        last['content'] = (last.get('content') or '') + html
        if not last.get('scripture_reference'):
            last['scripture_reference'] = reference
        sections[-1] = last
    else:
        sections = [{
            'section_type': 'scripture',
            'title': reference,
            'content': html,
            'scripture_reference': reference,
            'source': data.get('translation') or '',
            'notes': '',
        }]

    save_sermon_sections(sermon_id, sections)
    log_change(user_id, 'insert', sermon_id, reference, 'Inserted scripture into sermon from Bible Study')
    return jsonify({'status': 'success', 'html': html, 'reference': reference, 'persisted': True})