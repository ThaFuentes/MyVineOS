# app/models/pastoral/bible.py
# Offline Bible translations, canonical books, verse lookup, Strong's lexicon.

import re
import pymysql
from app.models.db import get_db

BIBLE_BOOKS = [
    ("Genesis", "Gen", "OT", 1), ("Exodus", "Exod", "OT", 2), ("Leviticus", "Lev", "OT", 3),
    ("Numbers", "Num", "OT", 4), ("Deuteronomy", "Deut", "OT", 5), ("Joshua", "Josh", "OT", 6),
    ("Judges", "Judg", "OT", 7), ("Ruth", "Ruth", "OT", 8), ("1 Samuel", "1Sam", "OT", 9),
    ("2 Samuel", "2Sam", "OT", 10), ("1 Kings", "1Kgs", "OT", 11), ("2 Kings", "2Kgs", "OT", 12),
    ("1 Chronicles", "1Chr", "OT", 13), ("2 Chronicles", "2Chr", "OT", 14), ("Ezra", "Ezra", "OT", 15),
    ("Nehemiah", "Neh", "OT", 16), ("Esther", "Est", "OT", 17), ("Job", "Job", "OT", 18),
    ("Psalms", "Ps", "OT", 19), ("Proverbs", "Prov", "OT", 20), ("Ecclesiastes", "Eccl", "OT", 21),
    ("Song of Solomon", "Song", "OT", 22), ("Isaiah", "Isa", "OT", 23), ("Jeremiah", "Jer", "OT", 24),
    ("Lamentations", "Lam", "OT", 25), ("Ezekiel", "Ezek", "OT", 26), ("Daniel", "Dan", "OT", 27),
    ("Hosea", "Hos", "OT", 28), ("Joel", "Joel", "OT", 29), ("Amos", "Amos", "OT", 30),
    ("Obadiah", "Obad", "OT", 31), ("Jonah", "Jonah", "OT", 32), ("Micah", "Mic", "OT", 33),
    ("Nahum", "Nah", "OT", 34), ("Habakkuk", "Hab", "OT", 35), ("Zephaniah", "Zeph", "OT", 36),
    ("Haggai", "Hag", "OT", 37), ("Zechariah", "Zech", "OT", 38), ("Malachi", "Mal", "OT", 39),
    ("Matthew", "Matt", "NT", 40), ("Mark", "Mark", "NT", 41), ("Luke", "Luke", "NT", 42),
    ("John", "John", "NT", 43), ("Acts", "Acts", "NT", 44), ("Romans", "Rom", "NT", 45),
    ("1 Corinthians", "1Cor", "NT", 46), ("2 Corinthians", "2Cor", "NT", 47), ("Galatians", "Gal", "NT", 48),
    ("Ephesians", "Eph", "NT", 49), ("Philippians", "Phil", "NT", 50), ("Colossians", "Col", "NT", 51),
    ("1 Thessalonians", "1Thess", "NT", 52), ("2 Thessalonians", "2Thess", "NT", 53),
    ("1 Timothy", "1Tim", "NT", 54), ("2 Timothy", "2Tim", "NT", 55), ("Titus", "Titus", "NT", 56),
    ("Philemon", "Phlm", "NT", 57), ("Hebrews", "Heb", "NT", 58), ("James", "Jas", "NT", 59),
    ("1 Peter", "1Pet", "NT", 60), ("2 Peter", "2Pet", "NT", 61), ("1 John", "1John", "NT", 62),
    ("2 John", "2John", "NT", 63), ("3 John", "3John", "NT", 64), ("Jude", "Jude", "NT", 65),
    ("Revelation", "Rev", "NT", 66),
]

BOOK_ALIASES = {}
for name, abbrev, _test, _ord in BIBLE_BOOKS:
    BOOK_ALIASES[name.lower()] = name
    BOOK_ALIASES[abbrev.lower()] = name
BOOK_ALIASES.update({
    "1 sam": "1 Samuel", "2 sam": "2 Samuel", "1 kgs": "1 Kings", "2 kgs": "2 Kings",
    "1 chr": "1 Chronicles", "2 chr": "2 Chronicles", "1 cor": "1 Corinthians",
    "2 cor": "2 Corinthians", "1 thess": "1 Thessalonians", "2 thess": "2 Thessalonians",
    "1 tim": "1 Timothy", "2 tim": "2 Timothy", "1 pet": "1 Peter", "2 pet": "2 Peter",
    "1 jn": "1 John", "2 jn": "2 John", "3 jn": "3 John", "jn": "John", "psalm": "Psalms",
    "revelation": "Revelation", "rev": "Revelation",
    # scrollmapper / OSIS Roman-numeral book names
    "i samuel": "1 Samuel", "ii samuel": "2 Samuel", "i kings": "1 Kings", "ii kings": "2 Kings",
    "i chronicles": "1 Chronicles", "ii chronicles": "2 Chronicles",
    "i corinthians": "1 Corinthians", "ii corinthians": "2 Corinthians",
    "i thessalonians": "1 Thessalonians", "ii thessalonians": "2 Thessalonians",
    "i timothy": "1 Timothy", "ii timothy": "2 Timothy",
    "i peter": "1 Peter", "ii peter": "2 Peter",
    "i john": "1 John", "ii john": "2 John", "iii john": "3 John",
    "revelation of john": "Revelation",
})

# Public-domain translations available via scripts/import_bible_data.py (scrollmapper/bible_databases)
PUBLIC_DOMAIN_TRANSLATIONS = {
    "KJV": "King James Version",
    "ASV": "American Standard Version",
    "BBE": "Bible in Basic English",
}


def normalize_book_name(book: str) -> str | None:
    if not book:
        return None
    key = book.strip().lower().replace(".", "")
    if key in BOOK_ALIASES:
        return BOOK_ALIASES[key]
    for name, abbrev, _, _ in BIBLE_BOOKS:
        if book.strip().lower() == name.lower() or book.strip().lower() == abbrev.lower():
            return name
    return book.strip()


def parse_reference(ref: str) -> dict | None:
    """Parse references like John 3:16, Rom 8:28-30, 1 John 3:16."""
    if not ref:
        return None
    m = re.match(
        r"^\s*((?:\d\s+)?[A-Za-z]+(?:\s+of\s+[A-Za-z]+)?)\s+(\d+)\s*:\s*(\d+)(?:\s*-\s*(\d+))?\s*$",
        ref.strip(),
    )
    if not m:
        return None
    book = normalize_book_name(m.group(1))
    return {
        "book": book,
        "chapter": int(m.group(2)),
        "verse_start": int(m.group(3)),
        "verse_end": int(m.group(4) or m.group(3)),
    }


def get_bible_translations():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT code, name, is_default,
               (SELECT COUNT(*) FROM bible_verses bv WHERE bv.translation = bible_translations.code) AS verse_count
        FROM bible_translations
        ORDER BY name
    """)
    return cur.fetchall()


def get_default_translation_code() -> str | None:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT code FROM bible_translations WHERE is_default = 1 LIMIT 1")
    row = cur.fetchone()
    return row["code"] if row else None


def set_bible_default(code: str):
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE bible_translations SET is_default = 0")
    cur.execute("UPDATE bible_translations SET is_default = 1 WHERE code = %s", (code,))
    db.commit()


def delete_bible_translation(code: str):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM bible_verses WHERE translation = %s", (code,))
    cur.execute("DELETE FROM bible_translations WHERE code = %s", (code,))
    db.commit()


def import_bible_translation(code: str, name: str, verses: list, set_default: bool = False) -> int:
    """Replace or create a translation from a flat verses array."""
    if not code or not name:
        raise ValueError("Translation code and name are required")
    if not verses:
        raise ValueError("No verses found in upload")

    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM bible_verses WHERE translation = %s", (code,))
    cur.execute("""
        INSERT INTO bible_translations (code, name, is_default)
        VALUES (%s, %s, 0)
        ON DUPLICATE KEY UPDATE name = VALUES(name)
    """, (code, name))

    if set_default:
        cur.execute("UPDATE bible_translations SET is_default = 0")
        cur.execute("UPDATE bible_translations SET is_default = 1 WHERE code = %s", (code,))

    batch = []
    count = 0
    for v in verses:
        book = normalize_book_name(v.get("book", ""))
        chapter = int(v.get("chapter", 0))
        verse = int(v.get("verse", 0))
        text = (v.get("text") or "").strip()
        if not book or chapter < 1 or verse < 1 or not text:
            continue
        batch.append((code, book, chapter, verse, text))
        if len(batch) >= 500:
            cur.executemany("""
                INSERT INTO bible_verses (translation, book, chapter, verse, text)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE text = VALUES(text)
            """, batch)
            count += len(batch)
            batch = []
    if batch:
        cur.executemany("""
            INSERT INTO bible_verses (translation, book, chapter, verse, text)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE text = VALUES(text)
        """, batch)
        count += len(batch)
    db.commit()
    return count


def get_bible_books():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT id, name, abbrev, testament, sort_order FROM bible_books ORDER BY sort_order")
    rows = cur.fetchall()
    if rows:
        return rows
    return [
        {"id": i + 1, "name": n, "abbrev": a, "testament": t, "sort_order": o}
        for i, (n, a, t, o) in enumerate(BIBLE_BOOKS)
    ]


def bible_search(query: str, translation: str = None, limit: int = 30):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    query = (query or "").strip()
    if not query:
        return []

    ref = parse_reference(query)
    if ref:
        sql = """
            SELECT translation, book, chapter, verse, text,
                   CONCAT(book, ' ', chapter, ':', verse) AS reference
            FROM bible_verses
            WHERE book = %s AND chapter = %s AND verse BETWEEN %s AND %s
        """
        params = [ref["book"], ref["chapter"], ref["verse_start"], ref["verse_end"]]
        if translation:
            sql += " AND translation = %s"
            params.append(translation)
        sql += " ORDER BY translation, verse LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        return cur.fetchall()

    if not translation:
        translation = get_default_translation_code()

    try:
        sql = """
            SELECT translation, book, chapter, verse, text,
                   CONCAT(book, ' ', chapter, ':', verse) AS reference,
                   MATCH(text) AGAINST (%s IN NATURAL LANGUAGE MODE) AS relevance
            FROM bible_verses
            WHERE MATCH(text) AGAINST (%s IN NATURAL LANGUAGE MODE)
        """
        params = [query, query]
        if translation:
            sql += " AND translation = %s"
            params.append(translation)
        sql += " ORDER BY relevance DESC, book, chapter, verse LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        return cur.fetchall()
    except Exception:
        sql = """
            SELECT translation, book, chapter, verse, text,
                   CONCAT(book, ' ', chapter, ':', verse) AS reference
            FROM bible_verses
            WHERE text LIKE %s
        """
        params = [f"%{query}%"]
        if translation:
            sql += " AND translation = %s"
            params.append(translation)
        sql += " ORDER BY book, chapter, verse LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        return cur.fetchall()


def bible_get_chapter(book: str, chapter: int, translation: str = None):
    book = normalize_book_name(book)
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    sql = "SELECT verse, text FROM bible_verses WHERE book = %s AND chapter = %s"
    params = [book, chapter]
    if translation:
        sql += " AND translation = %s"
        params.append(translation)
    else:
        sql += """
            AND translation = (
                SELECT code FROM bible_translations WHERE is_default = 1 LIMIT 1
            )
        """
    sql += " ORDER BY verse"
    cur.execute(sql, params)
    return cur.fetchall()


def bible_get_verse(book: str, chapter: int, verse: int, translation: str = None):
    book = normalize_book_name(book)
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    sql = """
        SELECT translation, book, chapter, verse, text,
               CONCAT(book, ' ', chapter, ':', verse) AS reference
        FROM bible_verses
        WHERE book = %s AND chapter = %s AND verse = %s
    """
    params = [book, chapter, verse]
    if translation:
        sql += " AND translation = %s"
        params.append(translation)
    else:
        sql += """
            AND translation = (
                SELECT code FROM bible_translations WHERE is_default = 1 LIMIT 1
            )
        """
    cur.execute(sql, params)
    return cur.fetchone()


def get_chapter_count(book: str, translation: str = None) -> int:
    book = normalize_book_name(book)
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    sql = "SELECT MAX(chapter) AS max_ch FROM bible_verses WHERE book = %s"
    params = [book]
    if translation:
        sql += " AND translation = %s"
        params.append(translation)
    cur.execute(sql, params)
    row = cur.fetchone()
    return int((row or {}).get('max_ch') or 0)


def get_strongs_entry(number: str):
    if not number:
        return None
    number = number.strip().upper()
    if not number[0] in ("H", "G"):
        return None
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM strongs_lexicon WHERE number = %s", (number,))
    return cur.fetchone()


def search_strongs_lexicon(query: str, limit: int = 40):
    q = (query or "").strip()
    if not q:
        return []
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    if re.match(r"^[HG]\d+$", q, re.I):
        cur.execute("SELECT * FROM strongs_lexicon WHERE number = %s", (q.upper(),))
        row = cur.fetchone()
        return [row] if row else []
    like = f"%{q}%"
    cur.execute("""
        SELECT * FROM strongs_lexicon
        WHERE number LIKE %s OR lemma LIKE %s OR transliteration LIKE %s OR definition LIKE %s
        ORDER BY number
        LIMIT %s
    """, (like, like, like, like, limit))
    return cur.fetchall()


def get_strongs_for_verse(book: str, chapter: int, verse: int):
    book = normalize_book_name(book)
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT so.strongs_number, so.word_index, so.surface_word,
               sl.lemma, sl.transliteration, sl.definition, sl.language
        FROM strongs_occurrences so
        JOIN strongs_lexicon sl ON sl.number = so.strongs_number
        WHERE so.book = %s AND so.chapter = %s AND so.verse = %s
        ORDER BY so.word_index
    """, (book, chapter, verse))
    return cur.fetchall()


def get_strongs_occurrences(number: str, limit: int = 50):
    number = (number or "").strip().upper()
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT book, chapter, verse, word_index, surface_word
        FROM strongs_occurrences
        WHERE strongs_number = %s
        ORDER BY book, chapter, verse
        LIMIT %s
    """, (number, limit))
    return cur.fetchall()


def import_strongs_lexicon(entries: list) -> int:
    if not entries:
        return 0
    db = get_db()
    cur = db.cursor()
    batch = []
    count = 0
    for e in entries:
        number = (e.get("number") or "").strip().upper()
        if not number:
            continue
        batch.append((
            number,
            e.get("language") or ("hebrew" if number.startswith("H") else "greek"),
            e.get("lemma", ""),
            e.get("transliteration", ""),
            e.get("definition", ""),
        ))
        if len(batch) >= 500:
            cur.executemany("""
                INSERT INTO strongs_lexicon (number, language, lemma, transliteration, definition)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    language = VALUES(language),
                    lemma = VALUES(lemma),
                    transliteration = VALUES(transliteration),
                    definition = VALUES(definition)
            """, batch)
            count += len(batch)
            batch = []
    if batch:
        cur.executemany("""
            INSERT INTO strongs_lexicon (number, language, lemma, transliteration, definition)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                language = VALUES(language),
                lemma = VALUES(lemma),
                transliteration = VALUES(transliteration),
                definition = VALUES(definition)
        """, batch)
        count += len(batch)
    db.commit()
    return count


def verses_from_scrollmapper(data: dict, translation_code: str | None = None) -> list[dict]:
    """Convert scrollmapper bible_databases JSON into flat verse records."""
    verses = []
    if isinstance(data.get("verses"), list):
        return data["verses"]
    for book_obj in data.get("books") or []:
        book = normalize_book_name(book_obj.get("name", ""))
        if not book:
            continue
        for chapter_obj in book_obj.get("chapters") or []:
            chapter = int(chapter_obj.get("chapter") or 0)
            if chapter < 1:
                continue
            for verse_obj in chapter_obj.get("verses") or []:
                verse = int(verse_obj.get("verse") or 0)
                text = (verse_obj.get("text") or "").strip()
                if verse < 1 or not text:
                    continue
                verses.append({
                    "book": book,
                    "chapter": chapter,
                    "verse": verse,
                    "text": text,
                })
    return verses


def entries_from_strongs_json(data) -> list[dict]:
    """Normalize OpenScriptures / mormon-documentation-project Strong's JSON."""
    rows = data if isinstance(data, list) else (data.get("entries") or [])
    entries = []
    for row in rows:
        number = (row.get("number") or "").strip().upper()
        if not number:
            continue
        entries.append({
            "number": number,
            "language": "hebrew" if number.startswith("H") else "greek",
            "lemma": row.get("lemma") or "",
            "transliteration": row.get("transliteration") or row.get("pronounce") or row.get("xlit") or "",
            "definition": row.get("definition") or row.get("description") or row.get("strongs_def") or "",
        })
    return entries


def import_strongs_occurrences(rows: list) -> int:
    if not rows:
        return 0
    db = get_db()
    cur = db.cursor()
    count = 0
    for r in rows:
        book = normalize_book_name(r.get("book", ""))
        if not book:
            continue
        number = (r.get("strongs_number") or r.get("number") or "").strip().upper()
        if not number:
            continue
        cur.execute("""
            INSERT INTO strongs_occurrences (strongs_number, book, chapter, verse, word_index, surface_word)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE surface_word = VALUES(surface_word)
        """, (
            number,
            book,
            int(r.get("chapter", 0)),
            int(r.get("verse", 0)),
            int(r.get("word_index", 0)),
            r.get("surface_word", ""),
        ))
        count += 1
    db.commit()
    return count


def seed_canon_books(cursor):
    for name, abbrev, testament, sort_order in BIBLE_BOOKS:
        cursor.execute("""
            INSERT IGNORE INTO bible_books (name, abbrev, testament, sort_order)
            VALUES (%s, %s, %s, %s)
        """, (name, abbrev, testament, sort_order))


def seed_sample_bible_and_strongs(cursor):
    """Seed KJV John 3 + sample Strong's entries when DB is empty."""
    cursor.execute("SELECT COUNT(*) FROM bible_translations")
    if cursor.fetchone()[0]:
        return

    john3 = [
        (1, "There was a man of the Pharisees, named Nicodemus, a ruler of the Jews:"),
        (2, "The same came to Jesus by night, and said unto him, Rabbi, we know that thou art a teacher come from God: for no man can do these miracles that thou doest, except God be with him."),
        (3, "Jesus answered and said unto him, Verily, verily, I say unto thee, Except a man be born again, he cannot see the kingdom of God."),
        (4, "Nicodemus saith unto him, How can a man be born when he is old? can he enter the second time into his mother's womb, and be born?"),
        (5, "Jesus answered, Verily, verily, I say unto thee, Except a man be born of water and of the Spirit, he cannot enter into the kingdom of God."),
        (6, "That which is born of the flesh is flesh; and that which is born of the Spirit is spirit."),
        (7, "Marvel not that I said unto thee, Ye must be born again."),
        (8, "The wind bloweth where it listeth, and thou hearest the sound thereof, but canst not tell whence it cometh, and whither it goeth: so is every one that is born of the Spirit."),
        (9, "Nicodemus answered and said unto him, How can these things be?"),
        (10, "Jesus answered and said unto him, Art thou a master of Israel, and knowest not these things?"),
        (11, "Verily, verily, I say unto thee, We speak that we do know, and testify that we have seen; and ye receive not our witness."),
        (12, "If I have told you earthly things, and ye believe not, how shall ye believe, if I tell you of heavenly things?"),
        (13, "And no man hath ascended up to heaven, but he that came down from heaven, even the Son of man which is in heaven."),
        (14, "And as Moses lifted up the serpent in the wilderness, even so must the Son of man be lifted up:"),
        (15, "That whosoever believeth in him should not perish, but have eternal life."),
        (16, "For God so loved the world, that he gave his only begotten Son, that whosoever believeth in him should not perish, but have everlasting life."),
        (17, "For God sent not his Son into the world to condemn the world; but that the world through him might be saved."),
        (18, "He that believeth on him is not condemned: but he that believeth not is condemned already, because he hath not believed in the name of the only begotten Son of God."),
        (19, "And this is the condemnation, that light is come into the world, and men loved darkness rather than light, because their deeds were evil."),
        (20, "For every one that doeth evil hateth the light, neither cometh to the light, lest his deeds should be reproved."),
        (21, "But he that doeth truth cometh to the light, that his deeds may be made manifest, that they are wrought in God."),
    ]
    cursor.execute("""
        INSERT INTO bible_translations (code, name, is_default) VALUES ('KJV', 'King James Version (sample John 3)', 1)
    """)
    for verse, text in john3:
        cursor.execute("""
            INSERT INTO bible_verses (translation, book, chapter, verse, text)
            VALUES ('KJV', 'John', 3, %s, %s)
        """, (verse, text))

    strongs_entries = [
        ("G26", "greek", "ἀγάπη", "agape", "love, i.e. affection or benevolence; specially a love-feast"),
        ("G2316", "greek", "θεός", "theos", "a deity, especially the supreme Divinity; God"),
        ("G2889", "greek", "κόσμος", "kosmos", "orderly arrangement, i.e. decoration; by implication the world"),
        ("G5207", "greek", "υἱός", "huios", "a son; rarely used for other close male kin"),
        ("G4100", "greek", "πιστεύω", "pisteuo", "to have faith in, upon, or with respect to, a person or thing"),
        ("G622", "greek", "ἀπόλλυμι", "apollumi", "to destroy fully, to perish, or lose"),
        ("G2222", "greek", "ζωή", "zoe", "life, literally or figuratively"),
        ("H2617", "hebrew", "חֶסֶד", "chesed", "kindness, piety, mercy, love, lovingkindness"),
    ]
    for number, language, lemma, translit, definition in strongs_entries:
        cursor.execute("""
            INSERT IGNORE INTO strongs_lexicon (number, language, lemma, transliteration, definition)
            VALUES (%s, %s, %s, %s, %s)
        """, (number, language, lemma, translit, definition))

    john316_occurrences = [
        ("G2316", "John", 3, 16, 2, "God"),
        ("G26", "John", 3, 16, 4, "loved"),
        ("G2889", "John", 3, 16, 6, "world"),
        ("G5207", "John", 3, 16, 12, "Son"),
        ("G4100", "John", 3, 16, 16, "believeth"),
        ("G622", "John", 3, 16, 19, "perish"),
        ("G2222", "John", 3, 16, 23, "life"),
    ]
    for number, book, chapter, verse, word_index, surface in john316_occurrences:
        cursor.execute("""
            INSERT IGNORE INTO strongs_occurrences (strongs_number, book, chapter, verse, word_index, surface_word)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (number, book, chapter, verse, word_index, surface))