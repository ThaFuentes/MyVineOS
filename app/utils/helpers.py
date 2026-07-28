# WebChurchMan/app/utils/helpers.py
# Full path: WebChurchMan/app/utils/helpers.py
# File name: helpers.py
# Brief, detailed purpose: Centralized utility functions used throughout the application.
#   - Consistent date parsing, formatting, validation, and today's date string.
#   - Global censored words system: fetch EXCLUSIVELY from settings table (TEXT column, \n-separated).
#   - Censor check and replacement functions (for submission blocking + Jinja display filter).
#   - Flash message helper for uniform user feedback.
#   - All functions are lightweight, safe (handle None/invalid input gracefully), and avoid circular imports.
#   FULL REBUILD: Preserved all original date helpers exactly.
#   Censored words are now 100% DB-driven (no defaults, no JSON - plain \n-separated TEXT).
#   contains_censored_word() for server-side validation (fresh DB query each call).
#   censor_text() for display - fresh DB query each call (reflects changes immediately, no restart needed).
#   Completely silent on all DB errors (no console spam) - returns [] if anything wrong (column missing, no row, connection issue).
#   Uses DictCursor + safe .get() for maximum robustness.

import re
from datetime import datetime, date
from typing import List, Optional

from flask import flash
from app.models.db import get_db
import pymysql


# ----------------------------------------------------------------------
# Date Handling Utilities
# ----------------------------------------------------------------------
STANDARD_DATE_FORMAT = '%Y-%m-%d'


def parse_date(date_str: Optional[str], format: str = STANDARD_DATE_FORMAT) -> Optional[date]:
    """Safely parse a date string into a Python date object. Returns None if invalid/empty."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), format).date()
    except ValueError:
        return None


def format_date(date_obj: Optional[datetime | date], format: str = STANDARD_DATE_FORMAT) -> str:
    """Format a date/datetime object into a string. Returns empty string if invalid."""
    if not date_obj or not isinstance(date_obj, (datetime, date)):
        return ''
    return date_obj.strftime(format)


def today_string(format: str = STANDARD_DATE_FORMAT) -> str:
    """Return today's date as a formatted string."""
    return datetime.now().strftime(format)


def is_valid_date(date_str: Optional[str], format: str = STANDARD_DATE_FORMAT) -> bool:
    """Validate if a string is a valid date in the specified format."""
    return parse_date(date_str, format) is not None


# ----------------------------------------------------------------------
# Global Censored Words System (100% DB-driven, fresh query each call, silent on errors)
# ----------------------------------------------------------------------
def get_censored_words() -> List[str]:
    """
    Load the admin-defined censored words/phrases from the settings table.
    - Stored as plain TEXT with one entry per line (\n-separated).
    - Returns empty list if no row, column missing, NULL, empty, or any DB error -> censoring disabled silently.
    - Returns stripped words (original case preserved for replacement).
    """
    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute("SELECT censored_words FROM settings WHERE id = 1")
        row = cur.fetchone()
        cur.close()

        # Safe access - handles missing row, missing column, NULL value
        text = row.get('censored_words', '') if row else ''
        text = (text or '').strip()
        if text:
            return [w.strip() for w in text.split('\n') if w.strip()]
    except Exception:
        # Completely silent - any issue -> no censoring, no logs, no spam
        pass

    return []  # Empty list = censoring disabled


# Identity spam / ad injection (names, usernames) — common on open registration sites
_SPAM_IDENTITY_PATTERNS = [
    re.compile(r'https?://', re.I),
    re.compile(r'www\.', re.I),
    re.compile(r'\bgraph\.org\b', re.I),
    re.compile(r'\bbit\.ly\b', re.I),
    re.compile(r'\bt\.me\b', re.I),
    re.compile(r'\btelegram\b', re.I),
    re.compile(r'transfer\s+to\s+you', re.I),
    re.compile(r'\bbalance[-\s]?\d', re.I),
    re.compile(r'us[-\s]?dollars?', re.I),
    re.compile(r'crypto|bitcoin|usdt|wallet\s*address', re.I),
    re.compile(r'>>>|<<<'),
    re.compile(r'🏷|💲|💰'),
    re.compile(r'\bhs=[a-f0-9]{16,}', re.I),
]


def identity_spam_reason(*parts: Optional[str]) -> Optional[str]:
    """
    Return a short reason if name/username fields look like ad/scam injection.
    Used on register, profile, and member create/edit so Access titles
    cannot become “Transfer to you graph.org…” spam.
    """
    blob = ' '.join(str(p or '') for p in parts).strip()
    if not blob:
        return None
    if len(blob) > 200:
        return 'Name is too long.'
    for part in parts:
        s = (part or '').strip()
        if not s:
            continue
        if len(s) > 80:
            return 'Each name field must be 80 characters or less.'
        # Real human names should not be bare domains or query strings
        if re.search(r'[?&=]', s) and re.search(r'\.[a-z]{2,}', s, re.I):
            return 'Names cannot contain website links or tracking codes.'
    for pat in _SPAM_IDENTITY_PATTERNS:
        if pat.search(blob):
            return (
                'That name or username looks like spam or a website link. '
                'Use a real first and last name only.'
            )
    return None


def contains_censored_word(text: Optional[str]) -> bool:
    """
    Case-insensitive check if text contains any censored word/phrase.
    Uses word boundaries (\b) for single words to prevent partial matches.
    Phrases matched exactly.
    Returns False if text is empty or no censored words configured.
    Fresh DB query each call.
    """
    if not text:
        return False
    words = get_censored_words()
    if not words:
        return False

    # Sort longer phrases first for accurate matching
    words = sorted(words, key=len, reverse=True)
    text_lower = text.lower()
    for word in words:
        if not word:
            continue
        lower_word = word.lower()
        if ' ' in lower_word:  # Phrase - exact match
            if lower_word in text_lower:
                return True
        else:  # Single word - word boundaries
            pattern = r"\b" + re.escape(lower_word) + r"\b"
            if re.search(pattern, text_lower):
                return True
    return False


def censor_text(text: Optional[str]) -> str:
    """
    Replace any censored words/phrases in text with '*****'.
    Returns original text unchanged if no censored words are configured.
    Fresh DB query each call - always reflects current settings.
    Plain-string only (no HTML). Use jinja_censor_filter for templates.
    """
    if not text:
        return ""
    # Work on plain text; collapse accidental HTML line-break tags to newlines
    # so stored "<br>" spam / old bad data still censors as prose.
    work = str(text)
    work = re.sub(r'(?i)<br\s*/?>', '\n', work)
    words = get_censored_words()
    if not words:
        return work

    # Sort longer phrases first
    words = sorted(words, key=len, reverse=True)
    censored = work
    for word in words:
        if not word:
            continue
        if ' ' in word:  # Phrase - exact match
            pattern = re.compile(re.escape(word), re.IGNORECASE)
        else:  # Single word - word boundaries
            pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
        censored = pattern.sub("*****", censored)
    return censored


def normalize_user_plaintext(value) -> str:
    """
    Normalize user multi-line text for safe display.
    - Real newlines (\n, \r\n)
    - Literal &lt;br&gt; or raw <br> that got stored by mistake → newlines
    """
    if value is None:
        return ''
    text = str(value)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # HTML breaks from a previous nl2br pass: prefer one newline (eat optional \n after)
    text = re.sub(r'(?i)<br\s*/?>\n?', '\n', text)
    # Escaped break tags users literally see as &lt;br&gt;
    text = re.sub(r'(?i)&lt;br\s*/?&gt;\n?', '\n', text)
    # Collapse 3+ blank lines to a paragraph gap
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def jinja_nl2br(value) -> 'Markup':
    """
    Escape user text and turn newlines into real HTML line breaks.
    Safe against XSS. Tolerates text that already contains <br> as text.

    Important: markupsafe.Markup.replace() escapes the *replacement* string.
    So we must inject Markup('<br>…'), not a plain '<br>…', or users see
    the literal characters &lt;br&gt; / <br> on the page (prayer bug).
    """
    from markupsafe import Markup, escape
    if value is None or value == '':
        return Markup('')
    plain = normalize_user_plaintext(value)
    # escape text, then insert real <br> breaks (Markup replacement is not re-escaped)
    return escape(plain).replace('\n', Markup('<br>\n'))


def jinja_censor(value):
    """
    Jinja filter: censor without destroying nl2br Markup.

    Broken pipeline was:  text | nl2br | censor
    → nl2br returns Markup with real <br>, old censor returned plain str,
    → Jinja auto-escaped and users saw literal "<br>".

    This filter:
    - Plain str  → plain censored str (chain with | nl2br)
    - Markup     → re-apply breaks as Markup after censoring
    """
    from markupsafe import Markup, escape
    if value is None or value == '':
        return Markup('') if isinstance(value, Markup) else ''

    if isinstance(value, Markup):
        plain = normalize_user_plaintext(str(value))
        censored = censor_text(plain)
        return escape(censored).replace('\n', Markup('<br>\n'))

    # Plain string (or already pre-censored in a view): keep plain so |nl2br works
    return censor_text(str(value))


# ----------------------------------------------------------------------
# Flash Message Helper
# ----------------------------------------------------------------------
def flash_message(message: str, category: str = 'info') -> None:
    """Flash a message with consistent categories for uniform UI feedback."""
    flash(message, category)