# app/routes/pastoral/bible.py - Bible study, upload, search, Strong's integration.

from flask import (
    Blueprint, render_template, request, jsonify, abort, flash, redirect, url_for, session, Response,
)
from werkzeug.utils import secure_filename
import json
import os
import re
import tempfile

from . import pastoral_required
from app.utils.decorators import role_required
from app.models.log import log_change
from app.models.pastoral.bible import (
    get_bible_translations,
    set_bible_default,
    delete_bible_translation,
    import_bible_translation,
    normalize_uploaded_bible_json,
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
    get_default_translation_code,
)
from app.models.pastoral.bible_online import (
    get_unified_chapter,
    list_online_translations,
    combined_translation_options,
    ONLINE_QUICK_VERSIONS,
    save_highlight,
    delete_highlight,
    clear_verse_highlight,
    save_note,
    delete_note,
    get_note,
    list_all_notes,
    list_notes,
    format_note_export,
    format_notes_export,
    note_to_illustration,
    scripture_selection_to_illustration,
    toggle_favorite,
    delete_favorite,
    list_all_favorites,
    ensure_annotation_tables,
    HIGHLIGHT_COLORS,
    get_user_preferred_translation,
    set_user_preferred_translation,
    resolve_user_translation,
    get_user_bible_place,
    save_user_bible_place,
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
    try:
        ensure_annotation_tables()
    except Exception as exc:
        print(f'bible annotation tables: {exc}')
    translations = get_bible_translations()
    books = get_bible_books()
    user_id = session['user_id']
    sermon_id = request.args.get('sermon_id', type=int)
    sermon = None
    if sermon_id:
        sermon = get_sermon_by_id(sermon_id, user_id)
    sermons = get_visible_sermons(user_id, limit=50)
    church_default = get_default_translation_code()
    place = get_user_bible_place(user_id) or {}
    user_preferred = place.get('translation') or get_user_preferred_translation(user_id)
    # Personal study version overrides church default
    selected = resolve_user_translation(user_id)
    version_options = combined_translation_options()
    # Always plain JSON-safe types (Jinja |tojson crashes on Undefined)
    last_book = place.get('book') or 'John'
    try:
        last_chapter = int(place.get('chapter') or 1)
    except (TypeError, ValueError):
        last_chapter = 1
    try:
        last_verse = int(place.get('verse') or 1)
    except (TypeError, ValueError):
        last_verse = 1
    return render_template(
        'pastoral/bible_study.html',
        translations=translations or [],
        version_options=version_options or [],
        online_quick=ONLINE_QUICK_VERSIONS,
        church_default=church_default,
        user_preferred=user_preferred,
        selected_translation=selected,
        last_book=str(last_book),
        last_chapter=last_chapter,
        last_verse=last_verse,
        books=books or [],
        sermon=sermon,
        sermon_id=sermon_id if sermon else None,
        sermons=sermons or [],
        highlight_colors=list(HIGHLIGHT_COLORS),
        page_title='Bible Study',
    )


@bible_bp.route('/preferred', methods=['POST'])
@pastoral_required()
def set_preferred_translation():
    """Personal study version + place — overrides church default for this user only."""
    user_id = session['user_id']
    data = request.get_json(silent=True) or {}
    code = (
        request.form.get('translation')
        or data.get('translation')
        or data.get('translation_code')
        or ''
    ).strip()
    clear = request.form.get('clear') or data.get('clear')
    try:
        if clear or code in ('', '__church__', '__default__'):
            saved = set_user_preferred_translation(user_id, None)
            place = get_user_bible_place(user_id)
            msg = 'Using the church default translation again.'
        else:
            place = save_user_bible_place(
                user_id,
                translation=code,
                book=data.get('book'),
                chapter=data.get('chapter'),
                verse=data.get('verse'),
                set_translation=True,
            )
            saved = place.get('translation') or code
            msg = f'Your study Bible is saved as {saved}.'
        log_change(
            user_id, 'update', None, saved or 'church',
            f'Personal Bible preference → {saved or "church default"}',
        )
        return jsonify({
            'ok': True,
            'preferred': saved,
            'effective': resolve_user_translation(user_id),
            'church_default': get_default_translation_code(),
            'place': place,
            'message': msg,
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@bible_bp.route('/place', methods=['POST'])
@pastoral_required()
def save_bible_place():
    """Quietly save last book/chapter/verse for resume later."""
    user_id = session['user_id']
    data = request.get_json(silent=True) or {}
    try:
        place = save_user_bible_place(
            user_id,
            translation=data.get('translation'),
            book=data.get('book'),
            chapter=data.get('chapter'),
            verse=data.get('verse'),
            set_translation=bool(data.get('translation')),
        )
        return jsonify({'ok': True, 'place': place})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


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
                parsed = normalize_uploaded_bible_json(bible_data)
                # metadata.shortname (KJV/ASV dumps) or filename stem (kjv.json → KJV)
                if not parsed.get('code'):
                    stem = os.path.splitext(filename)[0].strip()
                    if stem:
                        parsed['code'] = stem.upper()[:20]
                        if not parsed.get('name'):
                            parsed['name'] = stem.upper()
                if not parsed.get('code'):
                    raise ValueError(
                        "Translation code is required "
                        "(expected metadata.shortname, translation, code, or filename like kjv.json)"
                    )
                if not parsed.get('name'):
                    parsed['name'] = parsed['code']
                count = import_bible_translation(
                    parsed['code'],
                    parsed['name'],
                    parsed['verses'],
                    set_default=bool(parsed.get('set_default')),
                )
                flash(
                    f'Imported {count:,} verses for {parsed["name"]} ({parsed["code"]}).',
                    'success',
                )
                log_change(
                    session['user_id'], 'upload', None, parsed['code'],
                    f'Imported Bible translation {parsed["code"]} ({count} verses)',
                )
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


@bible_bp.route('/online/translations')
@pastoral_required()
def online_translations():
    """Browse Free Bible API catalog — read online, no install required."""
    q = request.args.get('q', '').strip()
    lang = request.args.get('lang', 'eng').strip() or 'eng'
    try:
        rows = list_online_translations(query=q or None, language=lang, limit=80)
        return jsonify({'translations': rows, 'ok': True})
    except Exception as e:
        return jsonify({'translations': [], 'ok': False, 'error': str(e)}), 502


@bible_bp.route('/chapter/<book>/<int:chapter>')
@pastoral_required()
def bible_chapter(book, chapter):
    """Local install if available; otherwise stream from online Bible API (no bulk download)."""
    user_id = session.get('user_id')
    translation = request.args.get('translation')
    book = normalize_book_name(book)
    try:
        data = get_unified_chapter(book, chapter, translation=translation, user_id=user_id)
    except Exception as e:
        return jsonify({'error': str(e), 'book': book, 'chapter': chapter}), 404
    if not data or not data.get('verses'):
        abort(404)
    return jsonify(data)


@bible_bp.route('/highlight', methods=['POST'])
@pastoral_required()
def bible_highlight_save():
    user_id = session['user_id']
    data = request.get_json(silent=True) or {}
    try:
        row = save_highlight(
            user_id=user_id,
            translation=(data.get('translation') or data.get('annotation_key') or '').strip(),
            book=data.get('book', ''),
            chapter=int(data.get('chapter') or 0),
            verse_start=int(data.get('verse_start') or data.get('verse') or 0),
            verse_end=int(data.get('verse_end') or data.get('verse') or 0) or None,
            color=(data.get('color') or 'yellow'),
        )
        return jsonify({'ok': True, 'highlight': row})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@bible_bp.route('/highlight/<int:highlight_id>', methods=['DELETE'])
@pastoral_required()
def bible_highlight_delete(highlight_id):
    ok = delete_highlight(session['user_id'], highlight_id)
    return jsonify({'ok': ok})


@bible_bp.route('/highlight/clear', methods=['POST'])
@pastoral_required()
def bible_highlight_clear():
    data = request.get_json(silent=True) or {}
    n = clear_verse_highlight(
        session['user_id'],
        (data.get('translation') or '').strip(),
        data.get('book', ''),
        int(data.get('chapter') or 0),
        int(data.get('verse') or 0),
    )
    return jsonify({'ok': True, 'removed': n})


@bible_bp.route('/note', methods=['POST'])
@pastoral_required()
def bible_note_save():
    user_id = session['user_id']
    data = request.get_json(silent=True) or {}
    try:
        row = save_note(
            user_id=user_id,
            translation=(data.get('translation') or data.get('annotation_key') or '').strip(),
            book=data.get('book', ''),
            chapter=int(data.get('chapter') or 0),
            body=data.get('body') or data.get('text') or '',
            verse_start=int(data.get('verse_start') or data.get('verse') or 0),
            verse_end=int(data.get('verse_end') or data.get('verse') or 0) or None,
            note_id=int(data['id']) if data.get('id') else None,
            title=data.get('title'),
            scripture_text=data.get('scripture_text') or data.get('scripture'),
            tags=data.get('tags'),
            scope=data.get('scope') or 'verse',
        )
        log_change(user_id, 'bible_note', row.get('id'), row.get('display_title'), 'Saved Bible study note')
        return jsonify({'ok': True, 'note': row})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@bible_bp.route('/note/<int:note_id>', methods=['GET'])
@pastoral_required()
def bible_note_get(note_id):
    row = get_note(session['user_id'], note_id)
    if not row:
        return jsonify({'ok': False, 'error': 'Note not found'}), 404
    return jsonify({'ok': True, 'note': row})


@bible_bp.route('/note/<int:note_id>', methods=['DELETE'])
@pastoral_required()
def bible_note_delete(note_id):
    ok = delete_note(session['user_id'], note_id)
    return jsonify({'ok': ok})


@bible_bp.route('/notes')
@pastoral_required()
def bible_notes_list():
    """JSON library of the user's Bible notes (searchable, reusable)."""
    q = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 100)), 300)
    rows = list_all_notes(session['user_id'], search=q or None, limit=limit)
    return jsonify({'ok': True, 'notes': rows, 'count': len(rows)})


@bible_bp.route('/note/<int:note_id>/to_illustration', methods=['POST'])
@pastoral_required()
def bible_note_to_illustration(note_id):
    """Copy a study note into the Illustration Library for sermon reuse."""
    user_id = session['user_id']
    data = request.get_json(silent=True) or {}
    try:
        result = note_to_illustration(
            user_id,
            note_id,
            visibility=data.get('visibility') or 'private',
        )
        log_change(
            user_id, 'illustration_create', result['illustration_id'], result['title'],
            f'Illustration from Bible note #{note_id}',
        )
        return jsonify({
            'ok': True,
            **result,
            'library_url': url_for('pastoral.illustrations.library'),
            'message': 'Saved to Illustration Library — reuse it in sermons anytime.',
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@bible_bp.route('/selection/to_illustration', methods=['POST'])
@pastoral_required()
def bible_selection_to_illustration():
    """Save selected scripture (+ optional note text) as a reusable illustration."""
    user_id = session['user_id']
    data = request.get_json(silent=True) or {}
    try:
        result = scripture_selection_to_illustration(
            user_id=user_id,
            reference=data.get('reference') or '',
            text=data.get('text') or data.get('scripture_text') or '',
            translation=data.get('translation'),
            note_body=data.get('body') or data.get('note') or '',
            visibility=data.get('visibility') or 'private',
        )
        log_change(
            user_id, 'illustration_create', result['illustration_id'], result['title'],
            'Illustration from Bible selection',
        )
        return jsonify({
            'ok': True,
            **result,
            'library_url': url_for('pastoral.illustrations.library'),
            'message': 'Saved to Illustration Library.',
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@bible_bp.route('/note/<int:note_id>/download')
@pastoral_required()
def bible_note_download(note_id):
    """Download one note as a .md text file."""
    note = get_note(session['user_id'], note_id)
    if not note:
        abort(404)
    body = format_note_export(note)
    safe = re.sub(r'[^\w\-.]+', '_', (note.get('display_title') or f'note-{note_id}'))[:80]
    return Response(
        body,
        mimetype='text/markdown; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{safe}.md"'},
    )


@bible_bp.route('/notes/download')
@pastoral_required()
def bible_notes_download_bulk():
    """
    Download notes as a single .md file.
    Query: q=search | book= & chapter= & translation=
    """
    user_id = session['user_id']
    book = request.args.get('book', '').strip()
    chapter = request.args.get('chapter', type=int)
    translation = request.args.get('translation', '').strip()
    q = request.args.get('q', '').strip()

    if book and chapter:
        book = normalize_book_name(book) or book
        # When translation omitted, pull chapter notes across translations for this user
        if translation:
            notes = list_notes(user_id, translation, book, chapter)
        else:
            all_notes = list_all_notes(user_id, limit=300)
            notes = [
                n for n in all_notes
                if n.get('book') == book and int(n.get('chapter') or 0) == chapter
            ]
        heading = f"Bible notes — {book} {chapter}"
        fname = f"bible-notes-{book}-{chapter}.md".replace(' ', '_')
    else:
        notes = list_all_notes(user_id, search=q or None, limit=300)
        heading = "My Bible Study Notes"
        fname = "bible-study-notes.md"

    if not notes:
        flash('No notes to download.', 'error')
        return redirect(url_for('pastoral.bible.bible_study'))

    body = format_notes_export(notes, heading=heading)
    return Response(
        body,
        mimetype='text/markdown; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{fname}"'},
    )


@bible_bp.route('/favorite', methods=['POST'])
@pastoral_required()
def bible_favorite_toggle():
    data = request.get_json(silent=True) or {}
    try:
        result = toggle_favorite(
            user_id=session['user_id'],
            scope=data.get('scope') or 'verse',
            book=data.get('book', ''),
            chapter=int(data.get('chapter') or 0),
            verse=int(data.get('verse') or 0),
            translation=(data.get('translation') or data.get('annotation_key') or '').strip(),
            scripture_text=data.get('scripture_text') or data.get('text'),
        )
        return jsonify({'ok': True, **result})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@bible_bp.route('/favorites')
@pastoral_required()
def bible_favorites_list():
    q = request.args.get('q', '').strip()
    scope = request.args.get('scope', '').strip() or None
    rows = list_all_favorites(
        session['user_id'],
        scope=scope,
        search=q or None,
        limit=min(int(request.args.get('limit', 200)), 400),
    )
    return jsonify({'ok': True, 'favorites': rows, 'count': len(rows)})


@bible_bp.route('/favorite/<int:favorite_id>', methods=['DELETE'])
@pastoral_required()
def bible_favorite_delete(favorite_id):
    return jsonify({'ok': delete_favorite(session['user_id'], favorite_id)})


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
        title = f"Sermon - {reference}" if reference else "New Sermon from Bible Study"
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