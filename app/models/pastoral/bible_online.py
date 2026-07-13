# Online Bible reading (HelloAO Free Use API) + personal highlights/notes.
# Users can pick a version and read chapter-by-chapter with no bulk download.

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

import pymysql

from app.models.db import get_db
from app.models.pastoral import bible as bible_mod
from app.models.pastoral.bible import (
    normalize_book_name,
    bible_get_chapter,
    get_chapter_count,
    get_strongs_for_verse,
)

HELLOAO_API_BASE = "https://bible.helloao.org/api"
HELLOAO_USER_AGENT = "MyVineOS-BibleReader/1.0"
HELLOAO_TIMEOUT_SEC = 45
DEFAULT_ONLINE_TRANSLATION = "BSB"

# Canonical book name → primary USFM id (HelloAO)
BOOK_TO_USFM = {
    "Genesis": "GEN", "Exodus": "EXO", "Leviticus": "LEV", "Numbers": "NUM",
    "Deuteronomy": "DEU", "Joshua": "JOS", "Judges": "JDG", "Ruth": "RUT",
    "1 Samuel": "1SA", "2 Samuel": "2SA", "1 Kings": "1KI", "2 Kings": "2KI",
    "1 Chronicles": "1CH", "2 Chronicles": "2CH", "Ezra": "EZR", "Nehemiah": "NEH",
    "Esther": "EST", "Job": "JOB", "Psalms": "PSA", "Proverbs": "PRO",
    "Ecclesiastes": "ECC", "Song of Solomon": "SNG", "Isaiah": "ISA", "Jeremiah": "JER",
    "Lamentations": "LAM", "Ezekiel": "EZK", "Daniel": "DAN", "Hosea": "HOS",
    "Joel": "JOL", "Amos": "AMO", "Obadiah": "OBA", "Jonah": "JON", "Micah": "MIC",
    "Nahum": "NAM", "Habakkuk": "HAB", "Zephaniah": "ZEP", "Haggai": "HAG",
    "Zechariah": "ZEC", "Malachi": "MAL", "Matthew": "MAT", "Mark": "MRK",
    "Luke": "LUK", "John": "JHN", "Acts": "ACT", "Romans": "ROM",
    "1 Corinthians": "1CO", "2 Corinthians": "2CO", "Galatians": "GAL", "Ephesians": "EPH",
    "Philippians": "PHP", "Colossians": "COL", "1 Thessalonians": "1TH",
    "2 Thessalonians": "2TH", "1 Timothy": "1TI", "2 Timothy": "2TI", "Titus": "TIT",
    "Philemon": "PHM", "Hebrews": "HEB", "James": "JAS", "1 Peter": "1PE",
    "2 Peter": "2PE", "1 John": "1JN", "2 John": "2JN", "3 John": "3JN",
    "Jude": "JUD", "Revelation": "REV",
}
USFM_TO_BOOK = {usfm: name for name, usfm in BOOK_TO_USFM.items()}

# Curated, widely taught messianic / NT fulfillment links (supplement openbible cross-refs).
# Shape: book → chapter → verse → [links]
CURATED_XREFS = {
    "Isaiah": {
        7: {
            14: [{"book": "Matthew", "chapter": 1, "verse": 22, "end_verse": 23, "label": "Virgin birth of Jesus", "kind": "messianic", "score": 100}],
        },
        9: {
            6: [{"book": "Luke", "chapter": 2, "verse": 11, "label": "Child born — Savior", "kind": "messianic", "score": 95},
                {"book": "John", "chapter": 1, "verse": 1, "end_verse": 14, "label": "Word became flesh", "kind": "messianic", "score": 90}],
        },
        40: {
            3: [{"book": "Matthew", "chapter": 3, "verse": 1, "end_verse": 3, "label": "John prepares the way", "kind": "messianic", "score": 100},
                {"book": "Mark", "chapter": 1, "verse": 2, "end_verse": 3, "label": "Voice in the wilderness", "kind": "messianic", "score": 100}],
        },
        53: {
            3: [{"book": "John", "chapter": 1, "verse": 10, "end_verse": 11, "label": "He came to His own", "kind": "messianic", "score": 90}],
            4: [{"book": "Matthew", "chapter": 8, "verse": 16, "end_verse": 17, "label": "Jesus bore our sicknesses", "kind": "messianic", "score": 100}],
            5: [{"book": "1 Peter", "chapter": 2, "verse": 24, "label": "By His wounds you are healed", "kind": "messianic", "score": 100},
                {"book": "Romans", "chapter": 4, "verse": 25, "label": "Delivered for our offenses", "kind": "messianic", "score": 85}],
            6: [{"book": "1 Peter", "chapter": 2, "verse": 25, "label": "Sheep gone astray", "kind": "messianic", "score": 95}],
            7: [{"book": "Acts", "chapter": 8, "verse": 32, "end_verse": 35, "label": "Philip preaches Jesus from Isaiah", "kind": "messianic", "score": 100},
                {"book": "Matthew", "chapter": 26, "verse": 63, "label": "Silent before accusers", "kind": "messianic", "score": 85}],
            9: [{"book": "Matthew", "chapter": 27, "verse": 57, "end_verse": 60, "label": "Buried with the rich", "kind": "messianic", "score": 90}],
            12: [{"book": "Mark", "chapter": 15, "verse": 27, "end_verse": 28, "label": "Numbered with transgressors", "kind": "messianic", "score": 95}],
        },
        61: {
            1: [{"book": "Luke", "chapter": 4, "verse": 17, "end_verse": 21, "label": "Jesus reads this in Nazareth", "kind": "messianic", "score": 100}],
        },
    },
    "Malachi": {
        3: {
            1: [{"book": "Matthew", "chapter": 11, "verse": 10, "label": "Messenger before the Lord", "kind": "messianic", "score": 100},
                {"book": "Mark", "chapter": 1, "verse": 2, "label": "I send My messenger", "kind": "messianic", "score": 100}],
        },
        4: {
            5: [{"book": "Matthew", "chapter": 11, "verse": 13, "end_verse": 14, "label": "John as Elijah to come", "kind": "messianic", "score": 100},
                {"book": "Luke", "chapter": 1, "verse": 17, "label": "Spirit and power of Elijah", "kind": "messianic", "score": 95}],
        },
    },
    "Micah": {
        5: {
            2: [{"book": "Matthew", "chapter": 2, "verse": 4, "end_verse": 6, "label": "Born in Bethlehem", "kind": "messianic", "score": 100}],
        },
    },
    "Zechariah": {
        9: {
            9: [{"book": "Matthew", "chapter": 21, "verse": 4, "end_verse": 5, "label": "Triumphal entry", "kind": "messianic", "score": 100},
                {"book": "John", "chapter": 12, "verse": 14, "end_verse": 15, "label": "King on a donkey", "kind": "messianic", "score": 100}],
        },
        12: {
            10: [{"book": "John", "chapter": 19, "verse": 34, "end_verse": 37, "label": "They will look on Him they pierced", "kind": "messianic", "score": 100}],
        },
    },
    "Psalms": {
        22: {
            1: [{"book": "Matthew", "chapter": 27, "verse": 46, "label": "My God, why have You forsaken Me?", "kind": "messianic", "score": 100}],
            16: [{"book": "John", "chapter": 20, "verse": 25, "end_verse": 27, "label": "Hands and feet pierced", "kind": "messianic", "score": 95}],
            18: [{"book": "John", "chapter": 19, "verse": 23, "end_verse": 24, "label": "Lots for His garments", "kind": "messianic", "score": 100}],
        },
        110: {
            1: [{"book": "Matthew", "chapter": 22, "verse": 43, "end_verse": 45, "label": "The Lord said to my Lord", "kind": "messianic", "score": 100},
                {"book": "Acts", "chapter": 2, "verse": 34, "end_verse": 36, "label": "Peter preaches Christ exalted", "kind": "messianic", "score": 100}],
        },
    },
    "Genesis": {
        3: {
            15: [{"book": "Galatians", "chapter": 4, "verse": 4, "label": "Seed of the woman — Christ", "kind": "messianic", "score": 90},
                 {"book": "Romans", "chapter": 16, "verse": 20, "label": "Crush the serpent", "kind": "messianic", "score": 80}],
        },
        22: {
            8: [{"book": "John", "chapter": 1, "verse": 29, "label": "God will provide the Lamb", "kind": "messianic", "score": 85}],
        },
    },
    "Daniel": {
        7: {
            13: [{"book": "Matthew", "chapter": 26, "verse": 64, "label": "Son of Man coming on clouds", "kind": "messianic", "score": 100},
                 {"book": "Revelation", "chapter": 1, "verse": 7, "label": "Every eye will see Him", "kind": "messianic", "score": 90}],
        },
    },
    "Hosea": {
        11: {
            1: [{"book": "Matthew", "chapter": 2, "verse": 14, "end_verse": 15, "label": "Out of Egypt I called My Son", "kind": "messianic", "score": 100}],
        },
    },
}

# Standard Protestant chapter counts (for navigation without extra API calls)
BOOK_CHAPTER_COUNTS = {
    "Genesis": 50, "Exodus": 40, "Leviticus": 27, "Numbers": 36, "Deuteronomy": 34,
    "Joshua": 24, "Judges": 21, "Ruth": 4, "1 Samuel": 31, "2 Samuel": 24,
    "1 Kings": 22, "2 Kings": 25, "1 Chronicles": 29, "2 Chronicles": 36, "Ezra": 10,
    "Nehemiah": 13, "Esther": 10, "Job": 42, "Psalms": 150, "Proverbs": 31,
    "Ecclesiastes": 12, "Song of Solomon": 8, "Isaiah": 66, "Jeremiah": 52,
    "Lamentations": 5, "Ezekiel": 48, "Daniel": 12, "Hosea": 14, "Joel": 3,
    "Amos": 9, "Obadiah": 1, "Jonah": 4, "Micah": 7, "Nahum": 3, "Habakkuk": 3,
    "Zephaniah": 3, "Haggai": 2, "Zechariah": 14, "Malachi": 4, "Matthew": 28,
    "Mark": 16, "Luke": 24, "John": 21, "Acts": 28, "Romans": 16,
    "1 Corinthians": 16, "2 Corinthians": 13, "Galatians": 6, "Ephesians": 6,
    "Philippians": 4, "Colossians": 4, "1 Thessalonians": 5, "2 Thessalonians": 3,
    "1 Timothy": 6, "2 Timothy": 4, "Titus": 3, "Philemon": 1, "Hebrews": 13,
    "James": 5, "1 Peter": 5, "2 Peter": 3, "1 John": 5, "2 John": 1, "3 John": 1,
    "Jude": 1, "Revelation": 22,
}

# Curated online versions shown immediately (no install)
ONLINE_QUICK_VERSIONS = [
    {"id": "BSB", "code": "BSB", "name": "Berean Standard Bible", "online": True},
    {"id": "ENGWEBP", "code": "WEB", "name": "World English Bible", "online": True},
    {"id": "eng_kjv", "code": "KJV", "name": "King James Version (online)", "online": True},
    {"id": "eng_asv", "code": "ASV", "name": "American Standard Version (online)", "online": True},
    {"id": "eng_bbe", "code": "BBE", "name": "Bible in Basic English (online)", "online": True},
    {"id": "eng_dby", "code": "DBY", "name": "Darby Translation", "online": True},
    {"id": "eng_ylt", "code": "YLT", "name": "Young's Literal Translation", "online": True},
    {"id": "eng_web", "code": "WEB2", "name": "World English Bible (alt)", "online": True},
]

HIGHLIGHT_COLORS = ("yellow", "green", "blue", "pink", "orange", "purple")
NOTE_SCOPES = ("verse", "chapter", "book")
FAVORITE_SCOPES = ("verse", "chapter", "book")


def ensure_user_bible_pref_column():
    """Personal Bible prefs on users: version + last reading place."""
    db = get_db()
    cur = db.cursor()
    for col, coldef in (
        ("preferred_bible_translation", "VARCHAR(40) NULL"),
        ("bible_last_book", "VARCHAR(50) NULL"),
        ("bible_last_chapter", "INT UNSIGNED NULL"),
        ("bible_last_verse", "INT UNSIGNED NULL"),
    ):
        try:
            cur.execute(f"ALTER TABLE users ADD COLUMN {col} {coldef}")
            db.commit()
        except Exception:
            pass


def get_user_preferred_translation(user_id: int | None) -> str | None:
    """User's saved Bible version (e.g. online:BSB or KJV), or None for church default."""
    place = get_user_bible_place(user_id)
    return place.get("translation") if place else None


def get_user_bible_place(user_id: int | None) -> dict:
    """
    Saved study place for a member:
      {translation, book, chapter, verse}
    Empty fields mean “not set yet.”
    """
    empty = {"translation": None, "book": None, "chapter": None, "verse": None}
    if not user_id:
        return empty
    try:
        ensure_user_bible_pref_column()
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute(
            """
            SELECT preferred_bible_translation, bible_last_book,
                   bible_last_chapter, bible_last_verse
              FROM users WHERE id = %s LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return empty
        code = (row.get("preferred_bible_translation") or "").strip() or None
        book = (row.get("bible_last_book") or "").strip() or None
        if book:
            book = normalize_book_name(book) or book
        chapter = row.get("bible_last_chapter")
        verse = row.get("bible_last_verse")
        try:
            chapter = int(chapter) if chapter is not None else None
        except (TypeError, ValueError):
            chapter = None
        try:
            verse = int(verse) if verse is not None else None
        except (TypeError, ValueError):
            verse = None
        if chapter is not None and chapter < 1:
            chapter = None
        if verse is not None and verse < 1:
            verse = None
        return {
            "translation": code[:40] if code else None,
            "book": book,
            "chapter": chapter,
            "verse": verse,
        }
    except Exception as exc:
        print(f"get_user_bible_place: {exc}")
        return empty


def set_user_preferred_translation(user_id: int, code: str | None) -> str | None:
    """
    Persist personal Bible version. Empty/None clears (falls back to church default).
    Accepts local codes (KJV) or online refs (online:BSB).
    """
    if not user_id:
        raise ValueError("user_id is required")
    ensure_user_bible_pref_column()
    code = (code or "").strip() or None
    if code:
        code = code[:40]
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE users SET preferred_bible_translation = %s WHERE id = %s",
        (code, user_id),
    )
    if cur.rowcount == 0:
        raise RuntimeError(f"No user row updated for id={user_id}")
    db.commit()
    return code


def save_user_bible_place(
    user_id: int,
    translation: str | None = None,
    book: str | None = None,
    chapter: int | None = None,
    verse: int | None = None,
    set_translation: bool = True,
) -> dict:
    """
    Save where the user is studying. Always updates provided fields.
    set_translation=True also stores preferred version so it overrides church default.
    """
    if not user_id:
        raise ValueError("user_id is required")
    ensure_user_bible_pref_column()

    updates = []
    params: list = []

    if set_translation and translation is not None:
        tr = (translation or "").strip()[:40] or None
        updates.append("preferred_bible_translation = %s")
        params.append(tr)

    if book is not None:
        b = normalize_book_name((book or "").strip()) or (book or "").strip() or None
        updates.append("bible_last_book = %s")
        params.append(b)

    if chapter is not None:
        try:
            ch = int(chapter)
        except (TypeError, ValueError):
            ch = None
        if ch is not None and ch < 1:
            ch = None
        updates.append("bible_last_chapter = %s")
        params.append(ch)

    if verse is not None:
        try:
            v = int(verse)
        except (TypeError, ValueError):
            v = None
        if v is not None and v < 1:
            v = None
        updates.append("bible_last_verse = %s")
        params.append(v)

    if not updates:
        return get_user_bible_place(user_id)

    params.append(user_id)
    db = get_db()
    cur = db.cursor()
    cur.execute(
        f"UPDATE users SET {', '.join(updates)} WHERE id = %s",
        params,
    )
    db.commit()
    return get_user_bible_place(user_id)


def resolve_user_translation(user_id: int | None = None, explicit: str | None = None) -> str:
    """
    Effective translation for study:
      1) explicit (this request)
      2) user's preferred version
      3) church default (local install)
      4) online BSB
    """
    explicit = (explicit or "").strip() or None
    if explicit:
        return explicit
    pref = get_user_preferred_translation(user_id)
    if pref:
        return pref
    church = bible_mod.get_default_translation_code()
    if church:
        return church
    return f"online:{DEFAULT_ONLINE_TRANSLATION}"


def ensure_annotation_tables():
    """Create highlights/notes/favorites tables if missing (safe to call repeatedly)."""
    ensure_user_bible_pref_column()
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bible_highlights (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            user_id INT UNSIGNED NOT NULL,
            translation VARCHAR(40) NOT NULL,
            book VARCHAR(50) NOT NULL,
            chapter INT UNSIGNED NOT NULL,
            verse_start INT UNSIGNED NOT NULL,
            verse_end INT UNSIGNED NOT NULL,
            color VARCHAR(20) NOT NULL DEFAULT 'yellow',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            KEY idx_hl_user_passage (user_id, translation, book, chapter),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bible_notes (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            user_id INT UNSIGNED NOT NULL,
            translation VARCHAR(40) NOT NULL,
            book VARCHAR(50) NOT NULL,
            chapter INT UNSIGNED NOT NULL DEFAULT 0,
            verse_start INT UNSIGNED NOT NULL DEFAULT 0,
            verse_end INT UNSIGNED NOT NULL DEFAULT 0,
            scope VARCHAR(20) NOT NULL DEFAULT 'verse',
            title VARCHAR(255) NULL,
            body TEXT NOT NULL,
            scripture_text TEXT NULL,
            tags VARCHAR(255) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            KEY idx_note_user_passage (user_id, translation, book, chapter),
            KEY idx_note_user_updated (user_id, updated_at),
            KEY idx_note_scope (user_id, scope),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    # Favorites: heart a verse, chapter, or whole book
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bible_favorites (
            id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            user_id INT UNSIGNED NOT NULL,
            translation VARCHAR(40) NOT NULL DEFAULT '',
            book VARCHAR(50) NOT NULL,
            chapter INT UNSIGNED NOT NULL DEFAULT 0,
            verse INT UNSIGNED NOT NULL DEFAULT 0,
            scope VARCHAR(20) NOT NULL DEFAULT 'verse',
            scripture_text TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uniq_fav (user_id, scope, book, chapter, verse, translation),
            KEY idx_fav_user (user_id, created_at),
            KEY idx_fav_scope (user_id, scope),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)
    # Safe column adds for older tables
    for col, coldef in (
        ("title", "VARCHAR(255) NULL"),
        ("scripture_text", "TEXT NULL"),
        ("tags", "VARCHAR(255) NULL"),
        ("scope", "VARCHAR(20) NOT NULL DEFAULT 'verse'"),
    ):
        try:
            cur.execute(f"ALTER TABLE bible_notes ADD COLUMN {col} {coldef}")
        except Exception:
            pass
    db.commit()


def helloao_fetch_json(path: str, timeout: int = HELLOAO_TIMEOUT_SEC):
    path = (path or "").lstrip("/")
    url = f"{HELLOAO_API_BASE}/{path}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": HELLOAO_USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Bible API HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Bible API network error: {e.reason}") from e
    except TimeoutError as e:
        raise RuntimeError("Bible API timed out") from e
    return json.loads(raw.decode("utf-8"))


def flatten_content(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    parts = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            if item.get("text"):
                parts.append(str(item["text"]))
            elif item.get("heading"):
                parts.append(str(item["heading"]))
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def parse_translation_ref(ref: str | None) -> tuple[str, str | None]:
    """
    Return (source, id):
      source: 'local' | 'online'
      id: local code or HelloAO translation id
    Values may be:
      - KJV (local if installed, else try online)
      - online:BSB or api:BSB
      - empty → local default, else online BSB
    """
    ref = (ref or "").strip()
    if not ref:
        local = bible_mod.get_default_translation_code()
        if local:
            return "local", local
        return "online", DEFAULT_ONLINE_TRANSLATION
    lower = ref.lower()
    if lower.startswith("online:") or lower.startswith("api:"):
        return "online", ref.split(":", 1)[1].strip()
    # Local if installed
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT 1 FROM bible_translations WHERE code = %s LIMIT 1", (ref,))
        if cur.fetchone():
            return "local", ref
    except Exception:
        pass
    # Treat unknown codes as online API ids
    return "online", ref


def list_online_translations(query: str | None = None, language: str = "eng", limit: int = 60) -> list[dict]:
    data = helloao_fetch_json("available_translations.json", timeout=40)
    q = (query or "").strip().lower()
    lang = (language or "eng").strip().lower()
    out = []
    for t in data.get("translations") or []:
        if int(t.get("numberOfBooks") or 0) < 27:
            continue
        tlang = (t.get("language") or "").lower()
        tlen = (t.get("languageEnglishName") or t.get("languageName") or "").lower()
        if lang and lang not in ("all",):
            if lang in ("eng", "en", "english"):
                if tlang not in ("eng", "en") and "english" not in tlen:
                    continue
            elif lang not in tlang and lang not in tlen:
                continue
        if q:
            blob = " ".join([
                t.get("id") or "",
                t.get("shortName") or "",
                t.get("name") or "",
                t.get("englishName") or "",
            ]).lower()
            if q not in blob:
                continue
        tid = t.get("id") or ""
        short = t.get("shortName") or tid
        name = t.get("englishName") or t.get("name") or short
        out.append({
            "id": tid,
            "code": short,
            "name": name,
            "value": f"online:{tid}",
            "online": True,
            "number_of_books": t.get("numberOfBooks"),
            "total_verses": t.get("totalNumberOfVerses"),
            "license_url": t.get("licenseUrl") or "",
        })
        if len(out) >= limit:
            break
    out.sort(key=lambda r: (r.get("name") or "").lower())
    return out


def _format_xref_ref(book: str, chapter: int, verse: int, end_verse: int | None = None) -> str:
    if end_verse and end_verse != verse:
        return f"{book} {chapter}:{verse}-{end_verse}"
    return f"{book} {chapter}:{verse}"


def _usfm_book_name(usfm: str) -> str:
    return USFM_TO_BOOK.get((usfm or "").upper()) or normalize_book_name(usfm) or usfm


def fetch_open_cross_refs(book: str, chapter: int, min_score: int = 20, per_verse: int = 8) -> dict[int, list[dict]]:
    """
    Load OpenBible cross-references for a chapter via HelloAO dataset.
    Returns {verse_num: [{book, chapter, verse, end_verse, score, kind, label, reference}, ...]}
    """
    book = normalize_book_name(book) or book
    usfm = BOOK_TO_USFM.get(book)
    if not usfm:
        return {}
    try:
        payload = helloao_fetch_json(f"d/open-cross-ref/{usfm}/{int(chapter)}.json", timeout=30)
    except Exception as exc:
        print(f"cross-ref fetch failed: {exc}")
        return {}

    content = ((payload.get("chapter") or {}).get("content")) or []
    out: dict[int, list[dict]] = {}
    for block in content:
        if not isinstance(block, dict):
            continue
        vnum = int(block.get("verse") or 0)
        if vnum < 1:
            continue
        refs = []
        for r in block.get("references") or []:
            try:
                score = int(r.get("score") or 0)
            except (TypeError, ValueError):
                score = 0
            if score < min_score:
                continue
            rbook = _usfm_book_name(r.get("book") or "")
            rch = int(r.get("chapter") or 0)
            rv = int(r.get("verse") or 0)
            if not rbook or rch < 1 or rv < 1:
                continue
            end_v = r.get("endVerse") or r.get("end_verse")
            end_v = int(end_v) if end_v else None
            # Flag likely messianic when OT points strongly into the Gospels/Acts/NT christology
            kind = "related"
            if book in (
                "Genesis", "Psalms", "Isaiah", "Jeremiah", "Micah", "Zechariah",
                "Malachi", "Daniel", "Hosea", "Joel", "Amos", "Zephaniah", "Haggai",
            ) and rbook in (
                "Matthew", "Mark", "Luke", "John", "Acts", "Romans", "Hebrews",
                "1 Peter", "Revelation", "Galatians", "Philippians",
            ) and score >= 40:
                kind = "messianic"
            refs.append({
                "book": rbook,
                "chapter": rch,
                "verse": rv,
                "end_verse": end_v,
                "score": score,
                "kind": kind,
                "label": "",
                "reference": _format_xref_ref(rbook, rch, rv, end_v),
            })
        refs.sort(key=lambda x: (-x["score"], x["book"], x["chapter"], x["verse"]))
        out[vnum] = refs[:per_verse]
    return out


def curated_xrefs_for_chapter(book: str, chapter: int) -> dict[int, list[dict]]:
    book = normalize_book_name(book) or book
    chapter = int(chapter)
    chapter_map = (CURATED_XREFS.get(book) or {}).get(chapter) or {}
    out: dict[int, list[dict]] = {}
    for vnum, links in chapter_map.items():
        cleaned = []
        for r in links:
            end_v = r.get("end_verse") or r.get("endVerse")
            end_v = int(end_v) if end_v else None
            cleaned.append({
                "book": r["book"],
                "chapter": int(r["chapter"]),
                "verse": int(r["verse"]),
                "end_verse": end_v,
                "score": int(r.get("score") or 100),
                "kind": r.get("kind") or "messianic",
                "label": r.get("label") or "",
                "reference": _format_xref_ref(r["book"], int(r["chapter"]), int(r["verse"]), end_v),
            })
        out[int(vnum)] = cleaned
    return out


def merge_cross_refs(primary: dict[int, list[dict]], secondary: dict[int, list[dict]], per_verse: int = 10) -> dict[int, list[dict]]:
    """Merge xref maps; primary wins on duplicates, keep highest score."""
    out: dict[int, list[dict]] = {}
    all_verses = set(primary) | set(secondary)
    for v in all_verses:
        seen = set()
        merged = []
        for src in (primary.get(v) or [], secondary.get(v) or []):
            for r in src:
                key = (r["book"], r["chapter"], r["verse"], r.get("end_verse"))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(r)
        merged.sort(key=lambda x: (
            0 if x.get("kind") == "messianic" else 1,
            -(x.get("score") or 0),
        ))
        out[v] = merged[:per_verse]
    return out


def get_chapter_cross_refs(book: str, chapter: int) -> dict[str, list[dict]]:
    """
    Combined curated + openbible cross-refs for a chapter.
    Keys are string verse numbers for JSON friendliness.
    """
    curated = curated_xrefs_for_chapter(book, chapter)
    open_refs = fetch_open_cross_refs(book, chapter, min_score=22, per_verse=8)
    # Curated first so messianic labels stick
    merged = merge_cross_refs(curated, open_refs, per_verse=10)
    return {str(k): v for k, v in sorted(merged.items())}


def helloao_get_chapter(translation_id: str, book: str, chapter: int) -> dict:
    """Fetch one chapter from HelloAO and return unified chapter payload."""
    book = normalize_book_name(book) or book
    usfm = BOOK_TO_USFM.get(book)
    if not usfm:
        raise ValueError(f"Unknown book: {book}")
    translation_id = (translation_id or DEFAULT_ONLINE_TRANSLATION).strip()
    chapter = int(chapter)
    payload = helloao_fetch_json(f"{translation_id}/{usfm}/{chapter}.json", timeout=HELLOAO_TIMEOUT_SEC)
    chapter_block = payload.get("chapter") or {}
    content = chapter_block.get("content") if isinstance(chapter_block, dict) else []
    verses = []
    for block in content or []:
        if not isinstance(block, dict) or block.get("type") != "verse":
            continue
        num = int(block.get("number") or 0)
        text = flatten_content(block.get("content"))
        if num >= 1 and text:
            verses.append({"verse": num, "text": text})
    max_ch = BOOK_CHAPTER_COUNTS.get(book) or int(
        (payload.get("book") or {}).get("numberOfChapters") or chapter
    )
    meta = payload.get("translation") or {}
    return {
        "book": book,
        "chapter": chapter,
        "translation": meta.get("shortName") or translation_id,
        "translation_id": translation_id,
        "source": "online",
        "max_chapter": max_ch,
        "verses": verses,
        "strongs": {},
        "name": meta.get("englishName") or meta.get("name") or translation_id,
    }


def get_unified_chapter(
    book: str,
    chapter: int,
    translation: str | None = None,
    user_id: int | None = None,
    include_annotations: bool = True,
) -> dict:
    """
    Load a chapter from local DB if installed, otherwise stream from online API.
    No bulk download required for online versions.
    """
    book = normalize_book_name(book) or book
    chapter = int(chapter)
    source, tid = parse_translation_ref(translation)

    result = None
    if source == "local" and tid:
        verses = bible_get_chapter(book, chapter, tid)
        if verses:
            strongs_map = {}
            for v in verses:
                strongs_map[v["verse"]] = get_strongs_for_verse(book, chapter, v["verse"])
            result = {
                "book": book,
                "chapter": chapter,
                "translation": tid,
                "translation_id": tid,
                "source": "local",
                "max_chapter": get_chapter_count(book, tid) or BOOK_CHAPTER_COUNTS.get(book, chapter),
                "verses": verses,
                "strongs": strongs_map,
            }

    if result is None:
        online_id = tid if source == "online" else (tid or DEFAULT_ONLINE_TRANSLATION)
        # If local miss, fall back to online using same code or default BSB
        try:
            result = helloao_get_chapter(online_id or DEFAULT_ONLINE_TRANSLATION, book, chapter)
        except Exception:
            if online_id != DEFAULT_ONLINE_TRANSLATION:
                result = helloao_get_chapter(DEFAULT_ONLINE_TRANSLATION, book, chapter)
            else:
                raise

    if include_annotations and user_id and result:
        ref = result.get("translation_id") or result.get("translation") or ""
        # Prefer stable annotation key: online:ID or local code
        ann_key = f"online:{result['translation_id']}" if result.get("source") == "online" else result.get("translation")
        try:
            ensure_annotation_tables()
            result["highlights"] = list_highlights(user_id, ann_key, book, chapter)
            # Verse notes for this chapter + chapter-level + book-level notes
            result["notes"] = list_notes_for_reader(user_id, ann_key, book, chapter)
            result["favorites"] = list_favorites_for_reader(user_id, ann_key, book, chapter)
            result["annotation_key"] = ann_key
        except Exception as exc:
            print(f"annotation load: {exc}")
            result["highlights"] = []
            result["notes"] = []
            result["favorites"] = {"verses": [], "chapter": False, "book": False, "items": []}
            result["annotation_key"] = ann_key if "ann_key" in dir() else ref

    # Cross-references + curated messianic links (best-effort; never block chapter text)
    if result:
        try:
            result["cross_refs"] = get_chapter_cross_refs(book, chapter)
        except Exception as exc:
            print(f"cross_refs: {exc}")
            result["cross_refs"] = {}

    return result


def list_highlights(user_id: int, translation: str, book: str, chapter: int) -> list[dict]:
    """
    Highlights for a passage — follow the book/chapter (not locked to one translation).
    Switching KJV → BSB still shows your yellow marks on the same verses.
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    book = normalize_book_name(book) or book
    # Prefer rows for current translation first, then any other version for same passage
    cur.execute(
        """
        SELECT id, translation, book, chapter, verse_start, verse_end, color, created_at
          FROM bible_highlights
         WHERE user_id = %s AND book = %s AND chapter = %s
         ORDER BY
           CASE WHEN translation = %s THEN 0 ELSE 1 END,
           verse_start, id
        """,
        (user_id, book, chapter, translation or ""),
    )
    rows = cur.fetchall() or []
    # Dedupe overlapping ranges preferring current translation's color
    seen = set()
    out = []
    for r in rows:
        key = (int(r.get("verse_start") or 0), int(r.get("verse_end") or 0))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _note_reference(row: dict) -> str:
    book = row.get("book") or ""
    chapter = int(row.get("chapter") or 0)
    vs = int(row.get("verse_start") or 0)
    ve = int(row.get("verse_end") or vs)
    scope = (row.get("scope") or "verse").lower()
    if scope == "book":
        return f"{book} (whole book)"
    if scope == "chapter":
        return f"{book} {chapter}" if chapter else book
    if vs and ve and vs != ve:
        return f"{book} {chapter}:{vs}-{ve}"
    if vs:
        return f"{book} {chapter}:{vs}"
    return f"{book} {chapter}".strip() if chapter else book


def _enrich_note_row(r: dict) -> dict:
    r["scope"] = (r.get("scope") or "verse").lower()
    r["reference"] = _note_reference(r)
    r["display_title"] = (r.get("title") or r["reference"] or "Note").strip()
    return r


def list_notes(user_id: int, translation: str, book: str, chapter: int) -> list[dict]:
    """Verse-level notes for a single chapter (legacy helper)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        """
        SELECT id, translation, book, chapter, verse_start, verse_end, scope,
               title, body, scripture_text, tags, created_at, updated_at
          FROM bible_notes
         WHERE user_id = %s AND translation = %s AND book = %s AND chapter = %s
           AND COALESCE(scope, 'verse') = 'verse'
         ORDER BY verse_start, id
        """,
        (user_id, translation, book, chapter),
    )
    return [_enrich_note_row(r) for r in (cur.fetchall() or [])]


def list_notes_for_reader(user_id: int, translation: str, book: str, chapter: int) -> list[dict]:
    """
    Notes for the open passage, across translations.

    Study notes follow the reference (John 3:16), not a single Bible version —
    so switching from KJV to BSB still shows your notes. The stored translation
    is kept as metadata (which text you were reading when you wrote it).
    """
    ensure_annotation_tables()
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    book = normalize_book_name(book) or book
    cur.execute(
        """
        SELECT id, translation, book, chapter, verse_start, verse_end, scope,
               title, body, scripture_text, tags, created_at, updated_at
          FROM bible_notes
         WHERE user_id = %s
           AND book = %s
           AND (
                (COALESCE(scope, 'verse') = 'verse' AND chapter = %s)
             OR (scope = 'chapter' AND chapter = %s)
             OR (scope = 'book')
           )
         ORDER BY
           FIELD(COALESCE(scope, 'verse'), 'book', 'chapter', 'verse'),
           CASE WHEN translation = %s THEN 0 ELSE 1 END,
           verse_start, id
        """,
        (user_id, book, chapter, chapter, translation or ""),
    )
    return [_enrich_note_row(r) for r in (cur.fetchall() or [])]


def list_all_notes(
    user_id: int,
    search: str | None = None,
    limit: int = 100,
    scope: str | None = None,
) -> list[dict]:
    """All of a user's Bible notes (library), newest first. Search title/tags/body."""
    ensure_annotation_tables()
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    sql = """
        SELECT id, translation, book, chapter, verse_start, verse_end, scope,
               title, body, scripture_text, tags, created_at, updated_at
          FROM bible_notes
         WHERE user_id = %s
    """
    params: list = [user_id]
    if scope and scope in NOTE_SCOPES:
        sql += " AND COALESCE(scope, 'verse') = %s"
        params.append(scope)
    if search:
        like = f"%{search.strip()}%"
        sql += """
           AND (title LIKE %s OR body LIKE %s OR scripture_text LIKE %s
                OR book LIKE %s OR tags LIKE %s OR translation LIKE %s)
        """
        params.extend([like] * 6)
    sql += " ORDER BY updated_at DESC, id DESC LIMIT %s"
    params.append(int(limit))
    cur.execute(sql, params)
    return [_enrich_note_row(r) for r in (cur.fetchall() or [])]


def get_note(user_id: int, note_id: int) -> dict | None:
    ensure_annotation_tables()
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        """
        SELECT id, translation, book, chapter, verse_start, verse_end, scope,
               title, body, scripture_text, tags, created_at, updated_at
          FROM bible_notes
         WHERE id = %s AND user_id = %s
         LIMIT 1
        """,
        (note_id, user_id),
    )
    row = cur.fetchone()
    return _enrich_note_row(row) if row else None


def format_note_export(note: dict, include_meta: bool = True) -> str:
    """Plain-text / markdown-friendly export of one note."""
    ref = note.get("reference") or _note_reference(note)
    title = (note.get("title") or ref or "Bible note").strip()
    lines = [f"# {title}", ""]
    if include_meta:
        lines.append(f"Reference: {ref}")
        if note.get("translation"):
            lines.append(f"Translation: {note['translation']}")
        if note.get("tags"):
            lines.append(f"Tags: {note['tags']}")
        lines.append("")
    if note.get("scripture_text"):
        lines.append("## Scripture")
        lines.append("")
        lines.append(f"> {note['scripture_text'].strip()}")
        lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append((note.get("body") or "").strip())
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def format_notes_export(notes: list[dict], heading: str | None = None) -> str:
    parts = []
    if heading:
        parts.append(f"# {heading}\n")
    for i, n in enumerate(notes):
        if i:
            parts.append("\n---\n")
        parts.append(format_note_export(n))
    return "\n".join(parts).strip() + "\n"


def save_highlight(
    user_id: int,
    translation: str,
    book: str,
    chapter: int,
    verse_start: int,
    verse_end: int | None = None,
    color: str = "yellow",
) -> dict:
    ensure_annotation_tables()
    book = normalize_book_name(book) or book
    verse_start = int(verse_start)
    verse_end = int(verse_end or verse_start)
    if verse_end < verse_start:
        verse_start, verse_end = verse_end, verse_start
    color = (color or "yellow").lower()
    if color not in HIGHLIGHT_COLORS:
        color = "yellow"
    translation = (translation or "").strip()[:40]
    db = get_db()
    cur = db.cursor()
    # Replace overlapping single-verse highlight for simplicity when same range
    cur.execute(
        """
        DELETE FROM bible_highlights
         WHERE user_id = %s AND translation = %s AND book = %s AND chapter = %s
           AND verse_start = %s AND verse_end = %s
        """,
        (user_id, translation, book, chapter, verse_start, verse_end),
    )
    cur.execute(
        """
        INSERT INTO bible_highlights
            (user_id, translation, book, chapter, verse_start, verse_end, color)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (user_id, translation, book, chapter, verse_start, verse_end, color),
    )
    db.commit()
    return {
        "id": cur.lastrowid,
        "translation": translation,
        "book": book,
        "chapter": chapter,
        "verse_start": verse_start,
        "verse_end": verse_end,
        "color": color,
    }


def delete_highlight(user_id: int, highlight_id: int) -> bool:
    ensure_annotation_tables()
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "DELETE FROM bible_highlights WHERE id = %s AND user_id = %s",
        (highlight_id, user_id),
    )
    db.commit()
    return cur.rowcount > 0


def clear_verse_highlight(user_id: int, translation: str, book: str, chapter: int, verse: int) -> int:
    """Remove highlights covering a single verse."""
    ensure_annotation_tables()
    book = normalize_book_name(book) or book
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        DELETE FROM bible_highlights
         WHERE user_id = %s AND translation = %s AND book = %s AND chapter = %s
           AND verse_start <= %s AND verse_end >= %s
        """,
        (user_id, translation, book, chapter, verse, verse),
    )
    db.commit()
    return cur.rowcount


def save_note(
    user_id: int,
    translation: str,
    book: str,
    chapter: int = 0,
    body: str = "",
    verse_start: int = 0,
    verse_end: int | None = None,
    note_id: int | None = None,
    title: str | None = None,
    scripture_text: str | None = None,
    tags: str | None = None,
    scope: str = "verse",
) -> dict:
    ensure_annotation_tables()
    book = normalize_book_name(book) or book
    body = (body or "").strip()
    if not body:
        raise ValueError("Note text is required")
    scope = (scope or "verse").lower()
    if scope not in NOTE_SCOPES:
        scope = "verse"

    chapter = int(chapter or 0)
    verse_start = int(verse_start or 0)
    verse_end = int(verse_end or verse_start or 0)
    if scope == "book":
        chapter, verse_start, verse_end = 0, 0, 0
    elif scope == "chapter":
        if chapter < 1:
            raise ValueError("Chapter is required for chapter notes")
        verse_start, verse_end = 0, 0
    else:
        if chapter < 1 or verse_start < 1:
            raise ValueError("Chapter and verse are required for verse notes")
        if verse_end < verse_start:
            verse_start, verse_end = verse_end, verse_start

    translation = (translation or "").strip()[:40]
    title = (title or "").strip()[:255] or None
    scripture_text = (scripture_text or "").strip() or None
    tags = (tags or "").strip()[:255] or None
    if not title:
        if scope == "book":
            title = f"{book} — book note"
        elif scope == "chapter":
            title = f"{book} {chapter} — chapter note"
        else:
            title = (
                f"{book} {chapter}:{verse_start}"
                + (f"-{verse_end}" if verse_end != verse_start else "")
            )

    db = get_db()
    cur = db.cursor()
    if note_id:
        cur.execute(
            """
            UPDATE bible_notes
               SET body = %s, verse_start = %s, verse_end = %s, translation = %s,
                   title = %s, scripture_text = COALESCE(%s, scripture_text),
                   tags = COALESCE(%s, tags), book = %s, chapter = %s, scope = %s
             WHERE id = %s AND user_id = %s
            """,
            (
                body, verse_start, verse_end, translation,
                title, scripture_text, tags, book, chapter, scope,
                note_id, user_id,
            ),
        )
        db.commit()
        nid = note_id
    else:
        cur.execute(
            """
            INSERT INTO bible_notes
                (user_id, translation, book, chapter, verse_start, verse_end,
                 scope, title, body, scripture_text, tags)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id, translation, book, chapter, verse_start, verse_end,
                scope, title, body, scripture_text, tags,
            ),
        )
        db.commit()
        nid = cur.lastrowid

    return get_note(user_id, nid) or {
        "id": nid,
        "scope": scope,
        "translation": translation,
        "book": book,
        "chapter": chapter,
        "verse_start": verse_start,
        "verse_end": verse_end,
        "title": title,
        "body": body,
        "display_title": title,
    }


# ---------------------------------------------------------------------------
# Favorites — heart a verse, chapter, or whole book
# ---------------------------------------------------------------------------

def _favorite_label(row: dict) -> str:
    scope = (row.get("scope") or "verse").lower()
    book = row.get("book") or ""
    chapter = int(row.get("chapter") or 0)
    verse = int(row.get("verse") or 0)
    if scope == "book":
        return book
    if scope == "chapter":
        return f"{book} {chapter}"
    return f"{book} {chapter}:{verse}"


def list_favorites_for_reader(user_id: int, translation: str, book: str, chapter: int) -> dict:
    """Favorites for the open passage — carry across translations (same verse/book)."""
    ensure_annotation_tables()
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    book = normalize_book_name(book) or book
    cur.execute(
        """
        SELECT id, translation, book, chapter, verse, scope, scripture_text, created_at
          FROM bible_favorites
         WHERE user_id = %s
           AND book = %s
           AND (
                (scope = 'verse' AND chapter = %s)
             OR (scope = 'chapter' AND chapter = %s)
             OR (scope = 'book')
           )
        """,
        (user_id, book, chapter, chapter),
    )
    rows = cur.fetchall() or []
    verse_favs = []
    chapter_fav = False
    book_fav = False
    for r in rows:
        r["scope"] = (r.get("scope") or "verse").lower()
        r["label"] = _favorite_label(r)
        if r["scope"] == "verse":
            verse_favs.append(int(r.get("verse") or 0))
        elif r["scope"] == "chapter":
            chapter_fav = True
        elif r["scope"] == "book":
            book_fav = True
    return {
        "verses": [v for v in verse_favs if v],
        "chapter": chapter_fav,
        "book": book_fav,
        "items": rows,
    }


def list_all_favorites(
    user_id: int,
    scope: str | None = None,
    search: str | None = None,
    limit: int = 200,
) -> list[dict]:
    ensure_annotation_tables()
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    sql = """
        SELECT id, translation, book, chapter, verse, scope, scripture_text, created_at
          FROM bible_favorites
         WHERE user_id = %s
    """
    params: list = [user_id]
    if scope and scope in FAVORITE_SCOPES:
        sql += " AND scope = %s"
        params.append(scope)
    if search:
        like = f"%{search.strip()}%"
        sql += " AND (book LIKE %s OR scripture_text LIKE %s OR translation LIKE %s)"
        params.extend([like, like, like])
    sql += " ORDER BY created_at DESC, id DESC LIMIT %s"
    params.append(int(limit))
    cur.execute(sql, params)
    rows = cur.fetchall() or []
    for r in rows:
        r["scope"] = (r.get("scope") or "verse").lower()
        r["label"] = _favorite_label(r)
    return rows


def toggle_favorite(
    user_id: int,
    scope: str,
    book: str,
    chapter: int = 0,
    verse: int = 0,
    translation: str = "",
    scripture_text: str | None = None,
) -> dict:
    """
    Toggle a favorite. scope: verse | chapter | book.
    Returns {favorited: bool, favorite: row|None}.
    """
    ensure_annotation_tables()
    scope = (scope or "verse").lower()
    if scope not in FAVORITE_SCOPES:
        raise ValueError("scope must be verse, chapter, or book")
    book = normalize_book_name(book) or book
    if not book:
        raise ValueError("book is required")
    chapter = int(chapter or 0)
    verse = int(verse or 0)
    translation = (translation or "").strip()[:40]
    if scope == "book":
        chapter, verse = 0, 0
    elif scope == "chapter":
        if chapter < 1:
            raise ValueError("chapter required")
        verse = 0
    else:
        if chapter < 1 or verse < 1:
            raise ValueError("chapter and verse required for verse favorites")

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    # Match by passage (not translation) so hearts follow the reference across versions
    cur.execute(
        """
        SELECT id FROM bible_favorites
         WHERE user_id = %s AND scope = %s AND book = %s AND chapter = %s
           AND verse = %s
         LIMIT 1
        """,
        (user_id, scope, book, chapter, verse),
    )
    existing = cur.fetchone()
    if existing:
        cur.execute(
            "DELETE FROM bible_favorites WHERE id = %s AND user_id = %s",
            (existing["id"], user_id),
        )
        db.commit()
        return {"favorited": False, "favorite": None, "scope": scope, "label": _favorite_label({
            "scope": scope, "book": book, "chapter": chapter, "verse": verse,
        })}

    cur.execute(
        """
        INSERT INTO bible_favorites
            (user_id, translation, book, chapter, verse, scope, scripture_text)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (user_id, translation, book, chapter, verse, scope, (scripture_text or "").strip() or None),
    )
    db.commit()
    fav = {
        "id": cur.lastrowid,
        "scope": scope,
        "book": book,
        "chapter": chapter,
        "verse": verse,
        "translation": translation,
        "scripture_text": scripture_text,
    }
    fav["label"] = _favorite_label(fav)
    return {"favorited": True, "favorite": fav, "scope": scope, "label": fav["label"]}


def delete_favorite(user_id: int, favorite_id: int) -> bool:
    ensure_annotation_tables()
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "DELETE FROM bible_favorites WHERE id = %s AND user_id = %s",
        (favorite_id, user_id),
    )
    db.commit()
    return cur.rowcount > 0


def delete_note(user_id: int, note_id: int) -> bool:
    ensure_annotation_tables()
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM bible_notes WHERE id = %s AND user_id = %s", (note_id, user_id))
    db.commit()
    return cur.rowcount > 0


def note_to_illustration(
    user_id: int,
    note_id: int,
    visibility: str = "private",
) -> dict:
    """
    Copy a Bible note into the Illustration Library so it can be reused
    in sermons like other illustrations.
    """
    from app.models.pastoral.illustrations import create_illustration

    note = get_note(user_id, note_id)
    if not note:
        raise ValueError("Note not found")

    ref = note.get("reference") or _note_reference(note)
    title = (note.get("title") or ref or "Bible note").strip()
    parts = []
    if note.get("scripture_text"):
        parts.append(f"<p><strong>{ref}</strong></p>")
        parts.append(f"<blockquote>{note['scripture_text']}</blockquote>")
    parts.append(f"<p>{(note.get('body') or '').replace(chr(10), '<br>')}</p>")
    content = "\n".join(parts)
    source = f"Bible Study · {ref}"
    if note.get("translation"):
        source += f" ({note['translation']})"
    tags = note.get("tags") or "bible,study-note"
    if "bible" not in tags.lower():
        tags = f"bible,{tags}"

    new_id = create_illustration(
        {
            "title": title,
            "content": content,
            "source": source,
            "tags": tags,
            "visibility": visibility if visibility in ("private", "pastoral_group") else "private",
        },
        user_id,
    )
    return {
        "illustration_id": new_id,
        "title": title,
        "note_id": note_id,
        "reference": ref,
    }


def scripture_selection_to_illustration(
    user_id: int,
    reference: str,
    text: str,
    translation: str | None = None,
    note_body: str | None = None,
    visibility: str = "private",
) -> dict:
    """Save selected scripture (+ optional note) directly as a reusable illustration."""
    from app.models.pastoral.illustrations import create_illustration

    reference = (reference or "").strip() or "Scripture"
    text = (text or "").strip()
    note_body = (note_body or "").strip()
    if not text and not note_body:
        raise ValueError("Scripture text or note body required")

    parts = [f"<p><strong>{reference}</strong></p>"]
    if text:
        parts.append(f"<blockquote>{text}</blockquote>")
    if note_body:
        parts.append(f"<p>{note_body.replace(chr(10), '<br>')}</p>")
    source = "Bible Study"
    if translation:
        source += f" · {translation}"
    new_id = create_illustration(
        {
            "title": reference if not note_body else f"{reference} — note",
            "content": "\n".join(parts),
            "source": source,
            "tags": "bible,scripture,study-note" if note_body else "bible,scripture",
            "visibility": visibility if visibility in ("private", "pastoral_group") else "private",
        },
        user_id,
    )
    return {"illustration_id": new_id, "title": reference}


def combined_translation_options(online_limit: int = 40) -> list[dict]:
    """Installed locals + curated online + small online catalog sample."""
    options = []
    try:
        for t in bible_mod.get_bible_translations():
            options.append({
                "value": t["code"],
                "code": t["code"],
                "name": t["name"],
                "online": False,
                "is_default": bool(t.get("is_default")),
                "verse_count": t.get("verse_count"),
            })
    except Exception as exc:
        print(f"local translations: {exc}")

    for t in ONLINE_QUICK_VERSIONS:
        options.append({
            "value": f"online:{t['id']}",
            "code": t["code"],
            "name": t["name"],
            "online": True,
            "is_default": False,
        })
    return options
