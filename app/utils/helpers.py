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
    Registered as Jinja filter 'censor' in app/__init__.py.
    """
    if not text:
        return ""
    words = get_censored_words()
    if not words:
        return text

    # Sort longer phrases first
    words = sorted(words, key=len, reverse=True)
    censored = text
    for word in words:
        if not word:
            continue
        if ' ' in word:  # Phrase - exact match
            pattern = re.compile(re.escape(word), re.IGNORECASE)
        else:  # Single word - word boundaries
            pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
        censored = pattern.sub("*****", censored)
    return censored


# ----------------------------------------------------------------------
# Flash Message Helper
# ----------------------------------------------------------------------
def flash_message(message: str, category: str = 'info') -> None:
    """Flash a message with consistent categories for uniform UI feedback."""
    flash(message, category)