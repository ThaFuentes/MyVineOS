# Member + public Bible — visitors can read / Strong's / search;
# highlights, notes, favorites, and saved place require login.

from flask import (
    render_template, request, jsonify, abort, session, Response, url_for,
)

from app.utils.decorators import login_required
from app.models.pastoral.bible import (
    get_bible_translations,
    get_bible_books,
    bible_search,
    get_strongs_entry,
    search_strongs_lexicon,
    get_strongs_occurrences,
    normalize_book_name,
    book_to_slug,
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
    format_note_export,
    format_notes_export,
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

from . import bible_bp


def _login_required_json():
    """JSON 401 for AJAX personalization when guest hits a write endpoint."""
    return jsonify({
        'ok': False,
        'login_required': True,
        'error': 'Log in to use study features like highlights, notes, and favorites.',
        'login_url': url_for('auth.login', next=request.url),
    }), 401


@bible_bp.route('/')
@bible_bp.route('/study')
def member_study():
    """Bible reader for everyone.

    Guests can read, search, Strong's, and cross-refs.
    Highlights, notes, favorites, and saved place require login.
    """
    user_id = session.get('user_id')
    is_logged_in = bool(user_id)

    if is_logged_in:
        try:
            ensure_annotation_tables()
        except Exception as exc:
            print(f'member bible tables: {exc}')

    translations = get_bible_translations()
    books = get_bible_books()
    church_default = get_default_translation_code()

    if is_logged_in:
        place = get_user_bible_place(user_id) or {}
        user_preferred = place.get('translation') or get_user_preferred_translation(user_id)
        # Personal choice wins over church default
        selected = resolve_user_translation(user_id)
        last_book = place.get('book') or 'John'
        try:
            last_chapter = int(place.get('chapter') or 1)
        except (TypeError, ValueError):
            last_chapter = 1
        try:
            last_verse = int(place.get('verse') or 1)
        except (TypeError, ValueError):
            last_verse = 1
    else:
        # Visitors: church default only, no saved place (nothing personal in DB)
        place = {}
        user_preferred = None
        selected = resolve_user_translation(None)
        last_book = 'John'
        last_chapter = 1
        last_verse = 1

    return render_template(
        'bible/member_study.html',
        # Same public top/bottom nav as Welcome/homepage for guests
        base_layout='base.html' if is_logged_in else 'base_public.html',
        translations=translations or [],
        version_options=combined_translation_options() or [],
        online_quick=ONLINE_QUICK_VERSIONS,
        church_default=church_default,
        user_preferred=user_preferred,
        selected_translation=selected,
        last_book=str(last_book),
        last_chapter=last_chapter,
        last_verse=last_verse,
        books=books or [],
        highlight_colors=list(HIGHLIGHT_COLORS),
        is_logged_in=is_logged_in,
        login_url=url_for('auth.login', next=request.path),
        page_title='Bible',
    )


@bible_bp.route('/preferred', methods=['POST'])
@login_required
def member_set_preferred_translation():
    """Save personal Bible version + optional reading place (overrides church default)."""
    user_id = session['user_id']
    data = request.get_json(silent=True) or {}
    code = (
        request.form.get('translation')
        or data.get('translation')
        or data.get('translation_code')
        or ''
    ).strip()
    clear = request.form.get('clear') or data.get('clear')
    book = data.get('book')
    chapter = data.get('chapter')
    verse = data.get('verse')
    try:
        if clear or code in ('', '__church__', '__default__'):
            saved = set_user_preferred_translation(user_id, None)
            place = get_user_bible_place(user_id)
            msg = 'Using the church default translation again.'
        else:
            place = save_user_bible_place(
                user_id,
                translation=code,
                book=book,
                chapter=chapter,
                verse=verse,
                set_translation=True,
            )
            saved = place.get('translation') or code
            msg = f'Your study Bible is saved as {saved}.'
            if place.get('book') and place.get('chapter'):
                msg += f" Resume at {place['book']} {place['chapter']}."
        return jsonify({
            'ok': True,
            'preferred': saved,
            'effective': resolve_user_translation(user_id),
            'church_default': get_default_translation_code(),
            'place': place if not clear else get_user_bible_place(user_id),
            'message': msg,
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@bible_bp.route('/place', methods=['POST'])
@login_required
def member_save_bible_place():
    """Quietly save last book/chapter/verse (+ version if sent) for resume later."""
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


@bible_bp.route('/online/translations')
def member_online_translations():
    """Public: list streamable versions (no personal data)."""
    q = request.args.get('q', '').strip()
    lang = request.args.get('lang', 'eng').strip() or 'eng'
    try:
        rows = list_online_translations(query=q or None, language=lang, limit=80)
        return jsonify({'translations': rows, 'ok': True})
    except Exception as e:
        return jsonify({'translations': [], 'ok': False, 'error': str(e)}), 502


@bible_bp.route('/search')
def member_search():
    """Public: reference / full-text search of installed text only."""
    query = request.args.get('q', '').strip()
    translation = request.args.get('translation')
    limit = int(request.args.get('limit', 30))
    if not query:
        return jsonify({'verses': []})
    if translation and (translation.startswith('online:') or translation.startswith('api:')):
        return jsonify({
            'verses': [],
            'message': 'Full-text search needs an installed translation. Try a reference like John 3:16.',
        })
    return jsonify({'verses': bible_search(query, translation, limit)})


@bible_bp.route('/chapter/<path:book>/<int:chapter>')
@bible_bp.route('/chapter/<book>/<int:chapter>')
def member_chapter(book, chapter):
    """Public chapter text + Strong's + cross-refs. Annotations only when logged in.

    Numbered books (1 Samuel, 1 John, …) are accepted as slugs ('1-samuel') or names.
    """
    user_id = session.get('user_id')
    translation = request.args.get('translation')
    book = normalize_book_name(request.args.get('book') or book)
    try:
        data = get_unified_chapter(
            book,
            chapter,
            translation=translation,
            user_id=user_id if user_id else None,
            include_annotations=bool(user_id),
        )
    except Exception as e:
        return jsonify({'error': str(e), 'book': book, 'chapter': chapter}), 404
    if not data or not data.get('verses'):
        abort(404)
    if data.get('book'):
        data['book_slug'] = book_to_slug(data['book'])
    if not user_id:
        # Explicit empty personal data for guests (no DB personalization)
        data.setdefault('highlights', [])
        data.setdefault('notes', [])
        data.setdefault('favorites', {'verses': [], 'chapter': False, 'book': False, 'items': []})
        data['guest'] = True
    return jsonify(data)


@bible_bp.route('/verse/<path:book>/<int:chapter>/<int:verse>')
@bible_bp.route('/verse/<book>/<int:chapter>/<int:verse>')
def member_verse(book, chapter, verse):
    """Public single-verse payload (text + Strong's)."""
    user_id = session.get('user_id')
    translation = request.args.get('translation')
    book = normalize_book_name(request.args.get('book') or book)
    try:
        data = get_unified_chapter(
            book,
            chapter,
            translation=translation,
            user_id=user_id if user_id else None,
            include_annotations=bool(user_id),
        )
    except Exception:
        abort(404)
    for v in data.get('verses') or []:
        if int(v.get('verse') or 0) == int(verse):
            return jsonify({
                'translation': data.get('translation'),
                'book': data.get('book'),
                'chapter': data.get('chapter'),
                'verse': verse,
                'text': v.get('text'),
                'reference': f"{data.get('book')} {data.get('chapter')}:{verse}",
                'strongs': (data.get('strongs') or {}).get(verse)
                    or (data.get('strongs') or {}).get(str(verse))
                    or [],
            })
    abort(404)


# ---- Highlights ----

@bible_bp.route('/highlight', methods=['POST'])
@login_required
def member_highlight_save():
    data = request.get_json(silent=True) or {}
    try:
        row = save_highlight(
            user_id=session['user_id'],
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
@login_required
def member_highlight_delete(highlight_id):
    return jsonify({'ok': delete_highlight(session['user_id'], highlight_id)})


@bible_bp.route('/highlight/clear', methods=['POST'])
@login_required
def member_highlight_clear():
    data = request.get_json(silent=True) or {}
    n = clear_verse_highlight(
        session['user_id'],
        (data.get('translation') or '').strip(),
        data.get('book', ''),
        int(data.get('chapter') or 0),
        int(data.get('verse') or 0),
    )
    return jsonify({'ok': True, 'removed': n})


# ---- Notes (verse / chapter / book) ----

@bible_bp.route('/note', methods=['POST'])
@login_required
def member_note_save():
    data = request.get_json(silent=True) or {}
    try:
        row = save_note(
            user_id=session['user_id'],
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
        return jsonify({'ok': True, 'note': row})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@bible_bp.route('/note/<int:note_id>', methods=['GET'])
@login_required
def member_note_get(note_id):
    row = get_note(session['user_id'], note_id)
    if not row:
        return jsonify({'ok': False, 'error': 'Note not found'}), 404
    return jsonify({'ok': True, 'note': row})


@bible_bp.route('/note/<int:note_id>', methods=['DELETE'])
@login_required
def member_note_delete(note_id):
    return jsonify({'ok': delete_note(session['user_id'], note_id)})


@bible_bp.route('/notes')
@login_required
def member_notes_list():
    q = request.args.get('q', '').strip()
    scope = request.args.get('scope', '').strip() or None
    limit = min(int(request.args.get('limit', 100)), 300)
    rows = list_all_notes(session['user_id'], search=q or None, limit=limit, scope=scope)
    return jsonify({'ok': True, 'notes': rows, 'count': len(rows)})


@bible_bp.route('/note/<int:note_id>/download')
@login_required
def member_note_download(note_id):
    note = get_note(session['user_id'], note_id)
    if not note:
        abort(404)
    import re
    body = format_note_export(note)
    safe = re.sub(r'[^\w\-.]+', '_', (note.get('display_title') or f'note-{note_id}'))[:80]
    return Response(
        body,
        mimetype='text/markdown; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{safe}.md"'},
    )


@bible_bp.route('/notes/download')
@login_required
def member_notes_download():
    q = request.args.get('q', '').strip()
    scope = request.args.get('scope', '').strip() or None
    notes = list_all_notes(session['user_id'], search=q or None, limit=300, scope=scope)
    if not notes:
        return jsonify({'ok': False, 'error': 'No notes to download'}), 404
    body = format_notes_export(notes, heading='My Bible Study Notes')
    return Response(
        body,
        mimetype='text/markdown; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="bible-study-notes.md"'},
    )


# ---- Favorites (verse / chapter / book) ----

@bible_bp.route('/favorite', methods=['POST'])
@login_required
def member_favorite_toggle():
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
@login_required
def member_favorites_list():
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
@login_required
def member_favorite_delete(favorite_id):
    return jsonify({'ok': delete_favorite(session['user_id'], favorite_id)})


# ---- Strong's (public study tool — no personal data) ----

@bible_bp.route('/strongs/<number>')
def member_strongs_detail(number):
    entry = get_strongs_entry(number)
    if not entry:
        abort(404)
    entry['occurrences'] = get_strongs_occurrences(number, limit=50)
    return jsonify(entry)


@bible_bp.route('/strongs/search')
def member_strongs_search():
    q = request.args.get('q', '').strip()
    limit = int(request.args.get('limit', 40))
    return jsonify({'entries': search_strongs_lexicon(q, limit)})
