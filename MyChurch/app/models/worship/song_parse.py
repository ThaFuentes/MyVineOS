# Worship song text / chord-chart parsing (rules first) + helpers for AI assist.
# Supports ChordPro ([C]lyrics), chord-over-lyrics, and [Verse]/[Chorus] markers.

from __future__ import annotations

import re
from typing import Any, Optional

from app.models.worship.sections import (
    default_play_order_from_sections,
    normalize_sections,
    parse_lyrics_to_sections,
)

SECTION_MARKER = re.compile(
    r'^\s*[\[\{\(]?\s*'
    r'(verse\s*\d*|v\s*\d*|chorus|ch|bridge|br|pre-?chorus|prechorus|tag|intro|outro|'
    r'ending|interlude|instrumental|turnaround|coda|refrain)'
    r'\s*[\]\}\)]?\s*:?\s*$',
    re.I,
)

# Line that is mostly chord tokens (G, Am, D/F#, Cmaj7, etc.)
_CHORD_TOKEN = re.compile(
    r"^(?:[A-G](?:#|b)?(?:maj|min|m|sus|add|dim|aug|M)?\d*(?:/[A-G](?:#|b)?)?)$",
    re.I,
)
_CHORD_LINE = re.compile(
    r'^\s*(?:[A-G](?:#|b)?(?:maj|min|m|sus|add|dim|aug|M)?\d*(?:/[A-G](?:#|b)?)?'
    r'(?:\s+|$)){1,16}\s*$',
    re.I,
)
# ChordPro inline chord: [C] [G/B] [Am7] [Cmaj7] — not [Chorus]/[Verse 1]
_CHORDPRO_INLINE = re.compile(
    r'\[([A-G](?:#|b)?(?:maj|min|m|sus|add|dim|aug|M)?\d*(?:/[A-G](?:#|b)?)?)\]'
)


def looks_like_chord_line(line: str) -> bool:
    s = (line or '').strip()
    if not s or len(s) > 80:
        return False
    if SECTION_MARKER.match(s):
        return False
    # Pure chord line with spaces
    if _CHORD_LINE.match(s):
        tokens = s.split()
        if tokens and all(_CHORD_TOKEN.match(t) for t in tokens):
            return True
    return False


def has_chordpro_markup(text: str) -> bool:
    """True when text has real inline ChordPro chords (not section labels)."""
    return bool(_CHORDPRO_INLINE.search(text or ''))


def chordpro_to_display(line: str) -> str:
    """Keep ChordPro as-is for storage (prompter/band can read [C] form)."""
    return line


def merge_chord_over_lyrics(chord_line: str, lyric_line: str) -> str:
    """
    Convert spaced chord-over-lyrics into approximate ChordPro inline form.
    Best-effort: place [Chord] before the lyric character under each chord column.
    """
    chords = chord_line.rstrip('\n')
    lyrics = lyric_line.rstrip('\n')
    if not chords.strip():
        return lyrics
    if not lyrics.strip():
        return chords

    # Find chord tokens with column positions
    positions = []
    for m in re.finditer(r'\S+', chords):
        positions.append((m.start(), m.group(0)))
    if not positions:
        return lyrics

    # Build from end so indices stay valid
    out = list(lyrics)
    # Pad lyrics if chords extend past end
    max_col = max(p for p, _ in positions)
    if len(out) <= max_col:
        out.extend([' '] * (max_col - len(out) + 1))

    for col, chord in reversed(positions):
        col = min(col, len(out))
        # Insert [chord] at column
        insert = f'[{chord}]'
        out[col:col] = list(insert)
    return ''.join(out).rstrip()


def normalize_chart_text(raw: str) -> str:
    """Normalize line endings; convert chord-over-lyrics pairs into ChordPro-ish lines."""
    text = (raw or '').replace('\r\n', '\n').replace('\r', '\n')
    if has_chordpro_markup(text):
        return text

    lines = text.split('\n')
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if looks_like_chord_line(line) and nxt is not None and not looks_like_chord_line(nxt) and not SECTION_MARKER.match(nxt.strip()):
            out.append(merge_chord_over_lyrics(line, nxt))
            i += 2
            continue
        out.append(line)
        i += 1
    return '\n'.join(out)


def _section_type_from_label(label: str) -> str:
    low = (label or '').lower()
    if 'pre' in low and 'chorus' in low:
        return 'prechorus'
    if 'chorus' in low or low in ('ch', 'refrain'):
        return 'chorus'
    if 'bridge' in low or low == 'br':
        return 'bridge'
    if 'tag' in low:
        return 'tag'
    if 'intro' in low:
        return 'intro'
    if 'outro' in low or 'ending' in low:
        return 'outro'
    if 'interlude' in low or 'instrumental' in low or 'turnaround' in low:
        return 'interlude'
    return 'verse'


def parse_chart_to_sections(raw: str) -> list[dict]:
    """
    Rules parser: section markers + chord-over-lyrics / ChordPro body.
    Returns worship sections list (id, type, label, content, sort, repeat).
    """
    text = normalize_chart_text(raw)
    if not text.strip():
        return []

    # Prefer existing marker parser when no chords; still works with chords
    lines = text.split('\n')
    sections: list[dict] = []
    label = 'Lyrics'
    stype = 'verse'
    buf: list[str] = []
    sort = 0

    def flush():
        nonlocal sort, buf
        content = '\n'.join(buf).strip()
        if not content:
            buf = []
            return
        sort += 1
        sections.append({
            'id': f's{sort}',
            'type': stype,
            'label': label,
            'content': content,
            'sort': sort,
            'repeat': 1,
        })
        buf = []

    for line in lines:
        stripped = line.strip()
        if SECTION_MARKER.match(stripped):
            flush()
            clean = stripped.strip('[](){} :')
            label = re.sub(r'\s+', ' ', clean).strip()
            # Title-case labels
            label = label.title() if label else 'Section'
            stype = _section_type_from_label(label)
            continue
        buf.append(line)
    flush()

    if sections:
        return sections
    # Fallback: whole song as one block
    return [{
        'id': 's1',
        'type': 'verse',
        'label': 'Lyrics',
        'content': text.strip(),
        'sort': 1,
        'repeat': 1,
    }]


def sections_to_lyrics_raw(sections: list) -> str:
    chunks = []
    for sec in sections or []:
        label = sec.get('label') or sec.get('type') or 'Section'
        content = (sec.get('content') or '').strip()
        if not content:
            continue
        chunks.append(f'[{label}]\n{content}')
    return '\n\n'.join(chunks)


def parse_song_text(
    raw: str,
    *,
    title_hint: str = '',
    artist_hint: str = '',
    use_ai: str | bool = 'auto',
) -> dict[str, Any]:
    """
    Full parse pipeline for worship charts.
    use_ai: 'rules' | 'auto' | 'ai'
    Returns: title, artist, ccli_song_number, copyright_line, lyrics_raw, sections, play_order,
             parse_mode, ai_used, notes
    """
    from app.utils.ai_assist_parse import (
        ai_configured,
        ai_parse_worship_song,
        normalize_parse_mode,
    )

    mode = normalize_parse_mode(
        'ai' if use_ai is True else ('rules' if use_ai is False else str(use_ai))
    )
    text = (raw or '').strip()
    rules_sections = parse_chart_to_sections(text) if text else []
    if not rules_sections and text:
        rules_sections = parse_lyrics_to_sections(text)

    result = {
        'title': (title_hint or '').strip() or _guess_title(text),
        'artist': (artist_hint or '').strip() or '',
        'ccli_song_number': '',
        'copyright_line': '',
        'lyrics_raw': sections_to_lyrics_raw(rules_sections) if rules_sections else text,
        'sections': normalize_sections(rules_sections, text),
        'play_order': [],
        'parse_mode': 'rules',
        'ai_used': False,
        'notes': '',
    }
    result['play_order'] = default_play_order_from_sections(result['sections'])

    # Quality: markers or multiple sections or chord markup = strong rules
    strong = (
        len(result['sections']) >= 2
        or has_chordpro_markup(text)
        or bool(SECTION_MARKER.search(text))
    )
    need_ai = mode == 'ai' or (mode == 'auto' and text and not strong)
    if not need_ai or not text:
        return result
    if not ai_configured():
        if mode == 'ai':
            result['notes'] = 'AI not configured — used rules parse only.'
        return result

    ai_data, ai_err = ai_parse_worship_song(text, title_hint=result['title'], artist_hint=result['artist'])
    if not ai_data:
        result['notes'] = ai_err or 'AI parse failed — kept rules.'
        return result

    # Prefer AI structure for labels/order but merge content carefully
    ai_sections = normalize_sections(ai_data.get('sections') or [], text)
    if ai_sections and _content_coverage(ai_sections, text) >= 0.45:
        result['sections'] = ai_sections
        result['parse_mode'] = 'rules+ai'
        result['ai_used'] = True
        if ai_data.get('title'):
            result['title'] = str(ai_data['title']).strip()[:200] or result['title']
        if ai_data.get('artist'):
            result['artist'] = str(ai_data['artist']).strip()[:200]
        if ai_data.get('ccli_song_number'):
            result['ccli_song_number'] = str(ai_data['ccli_song_number']).strip()[:40]
        if ai_data.get('copyright_line'):
            result['copyright_line'] = str(ai_data['copyright_line']).strip()[:255]
        if ai_data.get('play_order'):
            result['play_order'] = [str(x) for x in ai_data['play_order'] if x]
        else:
            result['play_order'] = default_play_order_from_sections(result['sections'])
        result['lyrics_raw'] = sections_to_lyrics_raw(result['sections'])
    else:
        result['notes'] = 'AI structure incomplete — kept rules parse with full chart text.'

    return result


def _guess_title(text: str) -> str:
    for line in (text or '').split('\n'):
        s = line.strip()
        if not s or looks_like_chord_line(s) or SECTION_MARKER.match(s):
            continue
        # Strip chordpro for title guess
        s = _CHORDPRO_INLINE.sub('', s).strip()
        if s and len(s) < 80:
            return s[:200]
    return 'Untitled Song'


def _content_coverage(sections: list, original: str) -> float:
    """Rough share of alphanumeric chars from original that appear in sections."""
    def alnum(s: str) -> str:
        return re.sub(r'[^a-z0-9]+', '', (s or '').lower())

    orig = alnum(original)
    if not orig:
        return 1.0
    body = alnum('\n'.join((s.get('content') or '') for s in sections))
    if not body:
        return 0.0
    # How much of original is represented (cap 1.0)
    # Simple ratio of lengths after strip chords brackets
    return min(1.0, len(body) / max(len(orig), 1))


def extract_text_from_upload(filename: str, raw_bytes: bytes) -> str:
    """Extract plain text from .txt/.md/.chordpro/.docx uploads."""
    name = (filename or '').lower()
    if name.endswith(('.txt', '.md', '.chopro', '.chordpro', '.cho', '.crd')):
        return raw_bytes.decode('utf-8', errors='replace')
    if name.endswith('.docx'):
        try:
            from io import BytesIO
            from docx import Document
            doc = Document(BytesIO(raw_bytes))
            return '\n'.join(p.text for p in doc.paragraphs)
        except Exception as e:
            raise ValueError(f'Could not read Word file: {e}') from e
    # PDF: try simple text extract if available
    if name.endswith('.pdf'):
        try:
            from io import BytesIO
            # pypdf optional
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(raw_bytes))
            parts = []
            for page in reader.pages:
                parts.append(page.extract_text() or '')
            text = '\n'.join(parts).strip()
            if text:
                return text
            raise ValueError('PDF had no extractable text (may be a scanned image).')
        except ImportError as e:
            raise ValueError('PDF support not installed. Upload .txt, ChordPro, or .docx instead.') from e
    raise ValueError('Unsupported file type. Use .txt, .chordpro, .docx, or paste text.')
