# Member Bible study — read, search, copy, Strong's lookup (shared translation DB with pastoral).

from flask import render_template, request, jsonify, abort

from app.utils.decorators import login_required
from app.models.pastoral.bible import (
    get_bible_translations,
    get_bible_books,
    bible_search,
    bible_get_chapter,
    bible_get_verse,
    get_chapter_count,
    get_strongs_entry,
    search_strongs_lexicon,
    get_strongs_for_verse,
    get_strongs_occurrences,
    normalize_book_name,
)

from . import bible_bp


@bible_bp.route('/')
@bible_bp.route('/study')
@login_required
def member_study():
    translations = get_bible_translations()
    books = get_bible_books()
    return render_template(
        'bible/member_study.html',
        translations=translations,
        books=books,
        page_title='Bible',
    )


@bible_bp.route('/search')
@login_required
def member_search():
    query = request.args.get('q', '').strip()
    translation = request.args.get('translation')
    limit = int(request.args.get('limit', 30))
    if not query:
        return jsonify({'verses': []})
    return jsonify({'verses': bible_search(query, translation, limit)})


@bible_bp.route('/chapter/<book>/<int:chapter>')
@login_required
def member_chapter(book, chapter):
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
@login_required
def member_verse(book, chapter, verse):
    translation = request.args.get('translation')
    row = bible_get_verse(book, chapter, verse, translation)
    if not row:
        abort(404)
    row['strongs'] = get_strongs_for_verse(row['book'], chapter, verse)
    return jsonify(row)


@bible_bp.route('/strongs/<number>')
@login_required
def member_strongs_detail(number):
    entry = get_strongs_entry(number)
    if not entry:
        abort(404)
    entry['occurrences'] = get_strongs_occurrences(number, limit=50)
    return jsonify(entry)


@bible_bp.route('/strongs/search')
@login_required
def member_strongs_search():
    q = request.args.get('q', '').strip()
    limit = int(request.args.get('limit', 40))
    return jsonify({'entries': search_strongs_lexicon(q, limit)})