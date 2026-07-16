# Parse pastor-authored DOCX / plain-text sermons into MyVineOS sections.
#
# Optimized for real MyVine export-style docs and hand-written sermon Word files:
#   H1 title · H2 Introduction / Sermon Content / Verses and Notes
#   Body markers: Point N:, Section N:, 1. Title, Story:, Application:, Closing:
#   Scripture walk-throughs: Hosea 1:1-2 standing alone as a heading
#   Soft line-breaks inside a single Word paragraph are expanded to lines

from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO
from typing import Any, BinaryIO

# ── Date from filename / title ───────────────────────────────────────────────

_DATE_PATTERNS = [
    re.compile(r'(20\d{2})[-_](0[1-9]|1[0-2])[-_](0[1-9]|[12]\d|3[01])'),
    re.compile(r'(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])'),
    re.compile(r'(0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])[-/](20\d{2})'),
]

_H2_MAP = {
    'introduction': 'introduction',
    'intro': 'introduction',
    'opening': 'introduction',
    'sermon content': 'body',
    'sermon body': 'body',
    'body': 'body',
    'main points': 'body',
    'message': 'body',
    # Prep / research area → sermon.notes ("Notes & References"), not podium sections
    'verses and notes': 'notes',
    'verses & notes': 'notes',
    'notes and references': 'notes',
    'notes & references': 'notes',
    'notes & refs': 'notes',
    'notes and refs': 'notes',
    'references': 'notes',
    'research': 'notes',
    'personal prep': 'notes',
    'prep notes': 'notes',
    'delivery tips': 'notes',
    'full scripture': 'notes',
    'scripture': 'notes',
    'scripture notes': 'notes',
    'notes': 'notes',
    'application': 'application',
    'conclusion': 'conclusion',
    'closing': 'conclusion',
    'invitation': 'application',
    'altar call': 'application',
}

# Explicit section starts (whole-line)
_POINT_LINE = re.compile(
    r'^(?:\*\*)?\s*'
    r'(?:'
    r'(?:point|section|part)\s*(\d+)\s*[:.\-–—]\s*(.+?)'           # Point 1: Title
    r'|(?:point|section|part)\s*(\d+)\s*'                           # Point 1
    r'|(\d{1,2})[.)]\s+\**([A-Za-z].{2,120}?)\**'                   # 1. Title / 1) **Title**
    r'|([IVXLC]{1,6})\.\s+\**([A-Za-z].{2,120}?)\**'                # I. Title
    r'|(story)\s*[:.\-–—]\s*(.+?)'                                  # Story: …
    r'|(first story|second story|third story|fourth story)\s*[–—\-:]?\s*(.*?)'
    r'|(application|conclusion|closing|invitation|altar call)\s*[:.\-–—]\s*(.*?)'
    r')\s*(?:\*\*)?\s*$',
    re.I,
)

# Standalone scripture reference as a mini-heading (Hosea 1:1-2, Matthew 6:8 (NIrV))
_SCRIPTURE_HEAD = re.compile(
    r'^(?:\*\*)?\s*'
    r'('
    r'(?:[1-3]\s*)?'
    r'(?:Genesis|Exodus|Leviticus|Numbers|Deuteronomy|Joshua|Judges|Ruth|'
    r'Samuel|Kings|Chronicles|Ezra|Nehemiah|Esther|Job|Psalm|Psalms|Proverb|Proverbs|'
    r'Ecclesiastes|Song(?:\s+of\s+(?:Songs|Solomon))?|Isaiah|Jeremiah|Lamentations|'
    r'Ezekiel|Daniel|Hosea|Joel|Amos|Obadiah|Jonah|Micah|Nahum|Habakkuk|Zephaniah|'
    r'Haggai|Zechariah|Malachi|Matthew|Mark|Luke|John|Acts|Romans|Corinthians|'
    r'Galatians|Ephesians|Philippians|Colossians|Thessalonians|Timothy|Titus|'
    r'Philemon|Hebrews|James|Peter|Jude|Revelation|'
    r'Gen|Exod?|Lev|Num|Deut|Josh|Judg|Sam|Kgs|Chr|Neh|Ps|Prov|Eccl|Isa|Jer|Ezek|Dan|'
    r'Hos|Amos|Mic|Matt|Mk|Lk|Jn|Rom|Cor|Gal|Eph|Phil|Col|Thess|Tim|Heb|Jas|Pet|Rev|Deu)'
    r'\.?'
    r'(?:\s+\d+(?::\d+(?:\s*[-–—,]\s*\d+)*)?(?:\s*[-–—]\s*\d+(?::\d+)?)?)?'
    r'(?:\s*\([^)]{0,20}\))?'
    r')\s*(?:\*\*)?\s*$',
    re.I,
)

_NOTE_LINE = re.compile(r'^(?:note|verse|scripture)\s*:\s*(.*)$', re.I)

_MD_BOLD_HEAD = re.compile(r'^\*\*(.+?)\*\*$')

_VERSE_REF_INLINE = re.compile(
    r'((?:[1-3]\s*)?[A-Za-z][A-Za-z\s]{1,20}?)\s+(\d+)(?::(\d+(?:\s*[-–—]\s*\d+)?))?',
)


def extract_service_date(*candidates: str | None) -> str | None:
    for raw in candidates:
        if not raw:
            continue
        text = str(raw)
        for pat in _DATE_PATTERNS:
            m = pat.search(text)
            if not m:
                continue
            g = m.groups()
            try:
                if len(g[0]) == 4:
                    y, mo, d = int(g[0]), int(g[1]), int(g[2])
                else:
                    mo, d, y = int(g[0]), int(g[1]), int(g[2])
                return datetime(y, mo, d).strftime('%Y-%m-%d')
            except ValueError:
                continue
    return None


def _plain_paragraphs_from_docx(stream: BinaryIO) -> list[tuple[str, str]]:
    from docx import Document

    if hasattr(stream, 'seek'):
        stream.seek(0)
    doc = Document(stream)
    out: list[tuple[str, str]] = []
    for para in doc.paragraphs:
        style = (para.style.name if para.style else 'Normal') or 'Normal'
        text = (para.text or '').replace('\xa0', ' ')
        # Expand soft line breaks / multi-line Word paragraphs into real lines
        # so Point 1 / Story: markers mid-paragraph are detectable.
        if '\n' in text or '\v' in text or '\x0b' in text:
            parts = re.split(r'[\n\v\x0b]+', text)
            for i, part in enumerate(parts):
                # first part keeps style; subsequent are Normal continuations
                out.append((style if i == 0 else 'Normal', part.strip() if i else part.rstrip()))
        else:
            out.append((style, text.rstrip()))
    return out


def _paragraphs_from_text(text: str) -> list[tuple[str, str]]:
    """
    Plain text / markdown → (style, text) pairs.
    Whole-line labels like "Introduction", "Sermon Content", "Verses and Notes"
    are promoted to Heading 2 so buckets (and Notes & References) work without Word styles.
    """
    lines = (text or '').replace('\r\n', '\n').replace('\r', '\n').split('\n')
    out: list[tuple[str, str]] = []
    saw_title = False
    for line in lines:
        t = line.rstrip()
        s = t.strip()
        if s.startswith('### '):
            out.append(('Heading 3', s[4:].strip()))
            continue
        if s.startswith('## '):
            out.append(('Heading 2', s[3:].strip()))
            continue
        if s.startswith('# '):
            out.append(('Heading 1', s[2:].strip()))
            saw_title = True
            continue
        # Bare major labels (common in exported/pastor-typed .txt)
        bare = re.sub(r'[:.\-–—]+\s*$', '', s)
        bare = re.sub(r'^\*+|\*+$', '', bare).strip()
        mapped = _normalize_h2(bare) if bare else None
        if mapped and len(bare) <= 48:
            out.append(('Heading 2', bare))
            continue
        # First non-empty non-heading line as title if nothing else set
        if s and not saw_title and len(s) <= 120 and not _POINT_LINE.match(s):
            out.append(('Heading 1', s))
            saw_title = True
            continue
        out.append(('Normal', t))
    return out


def _normalize_h2(label: str) -> str | None:
    key = re.sub(r'\s+', ' ', (label or '').strip().lower()).rstrip(':')
    key = re.sub(r'^\*+|\*+$', '', key).strip()
    return _H2_MAP.get(key)


def _strip_md(s: str) -> str:
    s = (s or '').strip()
    s = re.sub(r'^\*\*(.+)\*\*$', r'\1', s)
    s = re.sub(r'^__(.+)__$', r'\1', s)
    s = s.replace('**', '').replace('__', '')
    return s.strip()


def _is_title_ish_line(line: str) -> bool:
    """Heuristic: short standalone heading (used sparingly after blank lines)."""
    s = _strip_md(line)
    if not s or len(s) < 10 or len(s) > 85:
        return False
    if s.endswith(('…', '...')):
        return False
    # Skip labels that are mid-sermon callouts, not real sections
    if re.match(r'^(scripture references?|bible verses?|references?|sources?)\s*:?\s*$', s, re.I):
        return False
    if (s.startswith(('"', '“', "'")) and s.endswith(('"', '”', "'"))) and len(s) > 40:
        return False
    if s.endswith('.') and len(s) > 50:
        return False
    if s.endswith((',', ';')) and len(s) > 30:
        return False
    if s[0].islower():
        return False
    if _NOTE_LINE.match(s):
        return False
    # Strong heading openers
    if re.match(
        r'^(?:The\s+|A\s+|An\s+)?(?:Biblical|Hebrew|Greek|Story|Spark|Meaning|'
        r'FIRST|SECOND|THIRD)\b',
        s,
        re.I,
    ):
        return True
    if re.match(r'^(?:What |Our Present|Our |Living from)\b', s):
        return True
    # Title Case short line, no terminal period (strict)
    words = re.findall(r"[A-Za-z']+", s)
    if 2 <= len(words) <= 10 and not s.endswith(('.', '!', '?')):
        caps = sum(1 for w in words if w[0].isupper())
        if caps == len(words) and len(s) <= 70:
            return True
        if caps / len(words) >= 0.8 and len(s) <= 55:
            return True
    return False


def caps_ratio(words: list[str]) -> float:
    if not words:
        return 0.0
    return sum(1 for w in words if w[0].isupper()) / len(words)


def _classify_marker(line: str) -> dict | None:
    """
    If line starts a new section, return {title, section_type, lead_content?}.
    lead_content = leftover text on the same line after a short keyword marker.
    """
    s = _strip_md(line)
    if not s:
        return None

    m = _POINT_LINE.match(s)
    if m:
        if m.group(1):  # Point N: title
            num, title = m.group(1), (m.group(2) or '').strip()
            return {
                'title': f'Point {num}: {title}' if title else f'Point {num}',
                'section_type': 'point',
            }
        if m.group(3):  # Point N
            return {'title': f'Point {m.group(3)}', 'section_type': 'point'}
        if m.group(4):  # 1. Title
            return {
                'title': f'{m.group(4)}. {(m.group(5) or "").strip()}'.strip(),
                'section_type': 'point',
            }
        if m.group(6):  # I. Title
            return {
                'title': f'{m.group(6)}. {(m.group(7) or "").strip()}'.strip(),
                'section_type': 'point',
            }
        if m.group(8):  # Story:
            rest = (m.group(9) or '').strip()
            return {
                'title': f'Story: {rest}' if rest else 'Story',
                'section_type': 'illustration',
            }
        if m.group(10):  # FIRST STORY
            label = m.group(10).strip().title()
            rest = (m.group(11) or '').strip()
            return {
                'title': f'{label}{(" — " + rest) if rest else ""}',
                'section_type': 'illustration',
            }
        if m.group(12):  # Application / Conclusion / Closing
            kind = m.group(12).strip().lower()
            rest = (m.group(13) or '').strip()
            stype = {
                'application': 'application',
                'invitation': 'application',
                'altar call': 'application',
                'conclusion': 'conclusion',
                'closing': 'conclusion',
            }.get(kind, 'point')
            # If rest is short → it's a subtitle; if long → body on same line
            if rest and len(rest) > 90:
                return {
                    'title': kind.title(),
                    'section_type': stype,
                    'lead_content': rest,
                }
            title = f'{kind.title()}: {rest}' if rest else kind.title()
            return {'title': title, 'section_type': stype}

    sm = _SCRIPTURE_HEAD.match(s)
    if sm and len(s) <= 60:
        return {
            'title': sm.group(1).strip(),
            'section_type': 'scripture',
            'scripture_reference': sm.group(1).strip(),
        }

    mb = _MD_BOLD_HEAD.match(s)
    if mb:
        inner = mb.group(1).strip()
        # Skip redundant "**Sermon Content**"
        if _normalize_h2(inner):
            return None
        if len(inner) <= 90:
            return {'title': inner, 'section_type': 'point'}

    return None


def _split_body_into_points(body: str) -> list[dict[str, str]]:
    """Split Sermon Content into podium sections using markers + title heuristics."""
    if not (body or '').strip():
        return []

    raw_lines = body.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    # Normalize whitespace-only → blank
    lines = [ln.rstrip() for ln in raw_lines]

    chunks: list[dict] = []
    current_title = 'Sermon Content'
    current_type = 'point'
    current_ref = ''
    current_lines: list[str] = []
    used_explicit_marker = False
    # Track blank-line-before for title-ish detection
    prev_blank = True

    def flush():
        nonlocal current_title, current_type, current_ref, current_lines
        # Drop pure blank content
        text = '\n'.join(current_lines).strip()
        # Remove a duplicated heading if first line repeats title
        if text:
            first = text.split('\n', 1)[0].strip()
            if _strip_md(first).lower() == _strip_md(current_title).lower():
                text = text.split('\n', 1)[1].strip() if '\n' in text else ''
        if not text and not current_ref:
            current_lines = []
            return
        chunks.append({
            'section_type': current_type,
            'title': current_title[:200] or 'Sermon Content',
            'content': text,
            'notes': '',
            'scripture_reference': current_ref or '',
            'source': '',
        })
        current_lines = []
        current_ref = ''

    for ln in lines:
        stripped = ln.strip()
        if not stripped:
            if current_lines and current_lines[-1] != '':
                current_lines.append('')
            prev_blank = True
            continue

        marker = _classify_marker(stripped)
        if marker:
            if current_lines or chunks:
                flush()
            else:
                current_lines = []
            used_explicit_marker = True
            current_title = marker['title']
            current_type = marker['section_type']
            current_ref = marker.get('scripture_reference') or ''
            if marker.get('lead_content'):
                current_lines.append(marker['lead_content'])
            prev_blank = False
            continue

        # Opening subtitle: first real line of the body is title-ish
        if not chunks and not current_lines and _is_title_ish_line(stripped):
            current_title = _strip_md(stripped)
            current_type = 'point'
            current_ref = ''
            used_explicit_marker = True
            prev_blank = False
            continue

        # Soft title-ish after a blank line once we already have material
        if prev_blank and _is_title_ish_line(stripped) and (current_lines or chunks):
            flush()
            used_explicit_marker = True
            current_title = _strip_md(stripped)
            current_type = 'point'
            current_ref = ''
            prev_blank = False
            continue

        current_lines.append(stripped)
        prev_blank = False

    flush()

    # If heuristic split produced only one blob and no markers, try scripture-head scan
    if len(chunks) <= 1 and not used_explicit_marker:
        chunks = _split_by_scripture_heads(body) or chunks

    # Re-split only generic / untitled mega-blobs — keep real Point/Story titles intact
    expanded: list[dict] = []
    for c in chunks:
        content = c.get('content') or ''
        title = (c.get('title') or '').strip()
        low = title.lower()
        generic = (
            not title
            or low in ('sermon content', 'body', 'message', 'main points', 'point')
            or low.startswith('sermon content')
        )
        # Named points/stories can be long on purpose; only explode if extreme
        limit = 4500 if generic else 20000
        if len(content) > limit:
            soft = _split_long_prose(content, title or 'Sermon Content')
            if len(soft) > 1:
                expanded.extend(soft)
                continue
        expanded.append(c)
    chunks = expanded

    # Drop empties
    chunks = [c for c in chunks if (c.get('content') or '').strip() or c.get('scripture_reference')]

    # Merge tiny lead-in "Sermon Content" stubs into the next real section
    chunks = _merge_tiny_lead_ins(chunks)

    if not chunks:
        return [{
            'section_type': 'point',
            'title': 'Sermon Content',
            'content': body.strip(),
            'notes': '',
            'scripture_reference': '',
            'source': '',
        }]
    return chunks


def _merge_tiny_lead_ins(chunks: list[dict]) -> list[dict]:
    """Absorb a short generic preamble into the following section."""
    if len(chunks) < 2:
        return chunks
    out: list[dict] = []
    i = 0
    while i < len(chunks):
        c = chunks[i]
        content = (c.get('content') or '').strip()
        title = (c.get('title') or '').strip().lower()
        generic = title in ('sermon content', 'body', 'message', 'main points', 'point')
        tiny = len(content) < 400
        if generic and tiny and i + 1 < len(chunks):
            nxt = dict(chunks[i + 1])
            lead = content
            if lead:
                nxt['content'] = (lead + '\n\n' + (nxt.get('content') or '')).strip()
            out.append(nxt)
            i += 2
            continue
        out.append(c)
        i += 1
    return out


def _split_by_scripture_heads(body: str) -> list[dict]:
    lines = body.split('\n')
    chunks: list[dict] = []
    title = 'Sermon Content'
    ref = ''
    buf: list[str] = []
    found = 0

    def flush():
        nonlocal buf, title, ref
        text = '\n'.join(buf).strip()
        if not text and not ref:
            buf = []
            return
        chunks.append({
            'section_type': 'scripture' if ref else 'point',
            'title': title,
            'content': text,
            'notes': '',
            'scripture_reference': ref,
            'source': '',
        })
        buf = []

    for ln in lines:
        s = ln.strip()
        m = _SCRIPTURE_HEAD.match(s) if s else None
        if m and len(s) <= 60:
            flush()
            found += 1
            title = m.group(1).strip()
            ref = title
            continue
        if s:
            buf.append(s)
        elif buf and buf[-1] != '':
            buf.append('')
    flush()
    return chunks if found >= 2 else []


def _split_long_prose(text: str, base_title: str) -> list[dict]:
    """Last resort: split long body into ~2–8 podium-sized chunks."""
    # Prefer double-newline paragraphs; if the doc is one-line-per-sentence
    # (common in Word), fall back to single-newline lines as units.
    paras = [p.strip() for p in re.split(r'\n\s*\n+', text.strip()) if p.strip()]
    if len(paras) < 4:
        lines = [ln.strip() for ln in text.split('\n') if ln.strip()]
        if len(lines) < 8:
            return []
        # Bundle short lines into ~paragraph units of 2–4 lines
        paras = []
        buf: list[str] = []
        for ln in lines:
            buf.append(ln)
            joined = ' '.join(buf)
            if len(joined) >= 220 or _is_title_ish_line(ln) or _classify_marker(ln):
                paras.append('\n'.join(buf))
                buf = []
        if buf:
            paras.append('\n'.join(buf))
    if len(paras) < 4:
        return []

    target = max(1000, min(2200, len(text) // 5))
    groups: list[list[str]] = []
    cur: list[str] = []
    size = 0
    for p in paras:
        first = p.split('\n')[0].strip()
        looks_head = bool(_classify_marker(first)) or _is_title_ish_line(first) or (
            len(first) <= 70
            and first
            and first[0].isupper()
            and not first.endswith(('.', '!', '?', '"', '”'))
        )
        if cur and size > 700 and (size + len(p) > target or (looks_head and size > 900)):
            groups.append(cur)
            cur = [p]
            size = len(p)
        else:
            cur.append(p)
            size += len(p) + 2
    if cur:
        groups.append(cur)
    if len(groups) < 2:
        return []
    out = []
    for i, g in enumerate(groups, 1):
        content = '\n\n'.join(g)
        first = _strip_md(g[0].split('\n')[0].strip())
        if _classify_marker(first) or _is_title_ish_line(first) or (
            8 <= len(first) <= 90 and not first.endswith('.')
        ):
            title = first
            rest_first = g[0].split('\n', 1)[1].strip() if '\n' in g[0] else ''
            body_parts = ([rest_first] if rest_first else []) + g[1:]
            content = '\n\n'.join(body_parts).strip() or content
        else:
            title = f'{base_title} — part {i}'
        out.append({
            'section_type': 'point',
            'title': title[:200],
            'content': content.strip(),
            'notes': '',
            'scripture_reference': '',
            'source': '',
        })
    return out


def _html_from_text(text: str) -> str:
    parts = []
    for para in re.split(r'\n\s*\n', (text or '').strip()):
        para = para.strip()
        if not para:
            continue
        # Bold markdown
        safe = (
            para.replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
        )
        safe = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', safe)
        safe = safe.replace('\n', '<br>\n')
        parts.append(f'<p>{safe}</p>')
    return '\n'.join(parts) if parts else '<p></p>'


def _split_notes(notes_blob: str) -> list[dict]:
    """Each 'Note: …' becomes its own scripture/notes section when possible."""
    if not notes_blob or notes_blob.strip().lower() in (
        'no verses or notes provided.',
        'no verses or notes provided',
    ):
        return []

    # Prefer splitting on Note: at line starts
    pieces = re.split(r'(?m)(?=^(?:Note|Verse|Scripture)\s*:)', notes_blob.strip())
    pieces = [p.strip() for p in pieces if p.strip()]
    if len(pieces) <= 1:
        # Try bullet-ish scripture lines
        return [{
            'section_type': 'illustration',
            'title': 'Verses and Notes',
            'content': notes_blob.strip(),
            'notes': '',
            'scripture_reference': _first_ref(notes_blob) or '',
            'source': '',
        }]

    out = []
    for i, piece in enumerate(pieces, 1):
        m = _NOTE_LINE.match(piece.split('\n', 1)[0].strip())
        body = piece
        title = f'Note {i}'
        ref = ''
        if m:
            rest = m.group(1).strip()
            ref = _first_ref(rest) or _first_ref(piece) or ''
            # Use first line / ref as title
            first_line = rest.split('\n')[0].strip()
            if ref and len(first_line) < 80:
                title = first_line[:120] if first_line else ref
            elif ref:
                title = ref
            else:
                title = (first_line[:80] + '…') if len(first_line) > 80 else (first_line or title)
            # content without "Note:" prefix on first line
            lines = piece.split('\n')
            if lines and _NOTE_LINE.match(lines[0].strip()):
                body = '\n'.join([rest] + lines[1:]).strip()
        else:
            ref = _first_ref(piece) or ''
            if ref:
                title = ref
        out.append({
            'section_type': 'scripture' if ref else 'illustration',
            'title': title[:200],
            'content': body,
            'notes': '',
            'scripture_reference': ref,
            'source': '',
        })
    # If too many tiny notes, merge into groups of ~4 for podium usability
    if len(out) > 12:
        merged = []
        for i in range(0, len(out), 4):
            group = out[i:i + 4]
            titles = ', '.join(g['title'] for g in group[:3])
            if len(group) > 3:
                titles += '…'
            merged.append({
                'section_type': 'illustration',
                'title': f'Scripture notes ({i // 4 + 1})',
                'content': '\n\n'.join(g['content'] for g in group),
                'notes': '',
                'scripture_reference': group[0].get('scripture_reference') or '',
                'source': '',
            })
        return merged
    return out


def _first_ref(text: str) -> str | None:
    if not text:
        return None
    m = _VERSE_REF_INLINE.search(text[:200])
    if not m:
        return None
    book, ch, vs = m.group(1).strip(), m.group(2), m.group(3)
    # Filter false positives
    if book.lower() in ('the', 'a', 'an', 'in', 'on', 'to', 'of', 'and', 'or', 'chapter', 'verse'):
        return None
    if vs:
        return f'{book} {ch}:{vs}'.replace('  ', ' ')
    return f'{book} {ch}'.replace('  ', ' ')


def parse_sermon_document(
    stream: BinaryIO | bytes | str,
    *,
    filename: str | None = None,
    as_html: bool = True,
    use_ai: str | bool = 'auto',
) -> dict[str, Any]:
    """
    Parse a sermon DOCX or plain text into title, service_date, sections.

    use_ai:
      - False/'rules' — deterministic structure only
      - True/'ai'     — always try AI structure assist after rules
      - 'auto'        — AI only when rule parse looks weak (one blob / few sections)
    """
    from app.utils.ai_assist_parse import (
        ai_parse_sermon_structure,
        normalize_parse_mode,
        sermon_rules_quality,
    )

    mode = normalize_parse_mode(
        'ai' if use_ai is True else ('rules' if use_ai is False else str(use_ai))
    )

    if isinstance(stream, bytes):
        stream = BytesIO(stream)
    fname = filename or ''
    lower = fname.lower()

    plain_for_ai = ''
    if isinstance(stream, str):
        plain_for_ai = stream
        paragraphs = _paragraphs_from_text(stream)
    else:
        try:
            if hasattr(stream, 'seek'):
                stream.seek(0)
            # Prefer docx when extension says so or sniff fails softly
            if lower.endswith(('.txt', '.md')):
                raise ValueError('text file')
            paragraphs = _plain_paragraphs_from_docx(stream)
            plain_for_ai = '\n'.join(t for _, t in paragraphs if (t or '').strip())
        except Exception:
            if hasattr(stream, 'seek'):
                stream.seek(0)
            raw = stream.read() if hasattr(stream, 'read') else b''
            if isinstance(raw, bytes):
                raw = raw.decode('utf-8', errors='replace')
            plain_for_ai = raw
            paragraphs = _paragraphs_from_text(raw)

    # Title = first H1 / Title style
    title = ''
    for style, text in paragraphs:
        t = (text or '').strip()
        if not t:
            continue
        if style.startswith('Heading 1') or style == 'Title':
            title = t
            break
    if not title:
        for style, text in paragraphs:
            t = (text or '').strip()
            if t:
                title = t
                break
    if not title:
        base = re.sub(r'\.[^.]+$', '', fname.split('/')[-1] if fname else '')
        base = re.sub(r'[_-]+', ' ', base)
        base = re.sub(r'\s*20\d{2}[-_ ]\d{1,2}[-_ ]\d{1,2}.*$', '', base).strip()
        title = base or 'Imported Sermon'

    buckets: dict[str, list[str]] = {
        'introduction': [],
        'body': [],
        'notes': [],
        'application': [],
        'conclusion': [],
        'other': [],
    }
    current = 'other'
    for style, text in paragraphs:
        t = text if text is not None else ''
        stripped = t.strip()
        if style.startswith('Heading 1') or style == 'Title':
            if stripped == title:
                continue
        if style.startswith('Heading 2'):
            mapped = _normalize_h2(stripped)
            if mapped:
                current = mapped
            else:
                # Unknown H2 becomes a body subheading
                current = 'body'
                if stripped:
                    buckets['body'].append(stripped)
            continue
        if style.startswith('Heading 3') and stripped:
            buckets[current].append(stripped)
            continue
        # Skip redundant body echo of "Sermon Content"
        if current == 'body' and _normalize_h2(stripped) == 'body':
            continue
        buckets[current].append(t)

    def join_bucket(key: str) -> str:
        lines = buckets.get(key) or []
        out: list[str] = []
        blank = False
        for ln in lines:
            if not (ln or '').strip():
                if not blank and out:
                    out.append('')
                blank = True
            else:
                out.append(ln.strip() if isinstance(ln, str) else ln)
                blank = False
        return '\n'.join(out).strip()

    sections: list[dict] = []

    intro = join_bucket('introduction')
    if intro:
        sections.append({
            'section_type': 'introduction',
            'title': 'Introduction',
            'content': _html_from_text(intro) if as_html else intro,
            'notes': '',
            'scripture_reference': '',
            'source': '',
        })

    body = join_bucket('body')
    if body:
        for chunk in _split_body_into_points(body):
            content = chunk['content']
            sections.append({
                'section_type': chunk['section_type'],
                'title': chunk['title'],
                'content': _html_from_text(content) if as_html else content,
                'notes': chunk.get('notes') or '',
                'scripture_reference': chunk.get('scripture_reference') or '',
                'source': '',
            })

    for key, default_title, stype in (
        ('application', 'Application', 'application'),
        ('conclusion', 'Conclusion', 'conclusion'),
    ):
        text = join_bucket(key)
        if text:
            sections.append({
                'section_type': stype,
                'title': default_title,
                'content': _html_from_text(text) if as_html else text,
                'notes': '',
                'scripture_reference': '',
                'source': '',
            })

    notes_blob = join_bucket('notes')
    other = join_bucket('other')
    # If "other" is leftover before any H2, prepend to intro or body
    if other and other != title:
        if not intro and not body:
            sections.insert(0, {
                'section_type': 'point',
                'title': 'Sermon Content',
                'content': _html_from_text(other) if as_html else other,
                'notes': '',
                'scripture_reference': '',
                'source': '',
            })

    primary = None
    # Verses / Notes / References → sermon-level Notes & References field (not podium sections)
    prep_notes = (notes_blob or '').strip()
    if prep_notes:
        primary = _first_ref(prep_notes)

    if not sections:
        all_text = '\n'.join(
            t.strip() for _, t in paragraphs if (t or '').strip() and t.strip() != title
        ).strip()
        sections.append({
            'section_type': 'point',
            'title': 'Sermon Content',
            'content': _html_from_text(all_text) if as_html else all_text,
            'notes': '',
            'scripture_reference': '',
            'source': '',
        })

    # Prefer primary passage from first section scripture if still empty
    if not primary:
        for sec in sections:
            if sec.get('scripture_reference'):
                primary = sec['scripture_reference']
                break

    # Pull any mis-filed prep/notes sections out of the podium list → prep_notes
    sections, prep_notes = _redirect_prep_sections_to_notes(sections, prep_notes)

    service_date = extract_service_date(fname, title)

    result = {
        'title': title[:500],
        'service_date': service_date,
        'primary_passage': primary or '',
        # Editor field: "Notes & References (personal prep… not printed by default)"
        'notes': prep_notes or '',
        'sections': sections,
        'source_filename': fname,
        'parse_mode': 'rules',
        'ai_used': False,
    }

    quality = sermon_rules_quality(result)
    result['rules_quality'] = quality
    # Auto: only invite AI when rules clearly failed to structure (not when already good)
    need_ai = mode == 'ai' or (mode == 'auto' and quality < 55)
    if not need_ai or not plain_for_ai.strip():
        return result

    from app.utils.ai_assist_parse import materialize_ai_sermon_sections

    ai_data, ai_err = ai_parse_sermon_structure(
        plain_for_ai, filename=fname, rules_hint=result
    )
    if not ai_data:
        result['ai_error'] = ai_err or 'AI structure assist failed — kept your full rules parse'
        return result

    # CRITICAL: never use model-written body text. Slice original lines by AI ranges.
    # materialize assigns EVERY original line so content is never dropped.
    ai_sections, meta = materialize_ai_sermon_sections(
        ai_data,
        as_html=as_html,
        html_from_text=_html_from_text,
    )
    if meta.get('rejected') or not ai_sections:
        result['ai_error'] = meta.get('reason') or ai_err or 'AI structure rejected — kept full rules parse'
        result['ai_coverage'] = meta.get('coverage')
        return result

    # Compare TOTAL content: podium sections + Notes & References (prep)
    def _count_chars(secs, notes_text=''):
        from app.utils.ai_assist_parse import _plain_len
        total = sum(_plain_len(s.get('content') or '') for s in (secs or []))
        total += _plain_len(notes_text or '')
        return total

    ai_prep = (meta.get('prep_notes') or '').strip()
    existing_prep = (result.get('notes') or '').strip()
    merged_prep = (
        (existing_prep + '\n\n' + ai_prep).strip()
        if existing_prep and ai_prep and ai_prep not in existing_prep
        else (ai_prep or existing_prep)
    )

    rules_chars = _count_chars(sections, result.get('notes') or '')
    ai_chars = _count_chars(ai_sections, merged_prep or ai_prep)
    # Soft check only: if AI somehow still lost a lot, keep rules (should be rare now)
    if rules_chars > 400 and ai_chars < rules_chars * 0.55:
        result['ai_error'] = (
            f'AI structure still looked incomplete ({ai_chars} vs {rules_chars} chars) — kept full rules parse'
        )
        result['ai_coverage'] = meta.get('coverage')
        return result

    # Safety: never leave notes-type rows on the podium list
    podium, more_prep = _redirect_prep_sections_to_notes(ai_sections, merged_prep)
    result['sections'] = podium
    result['notes'] = more_prep
    result['parse_mode'] = 'rules+ai' if sections else 'ai'
    result['ai_used'] = True
    result['ai_coverage'] = meta.get('coverage')
    result['ai_chars'] = ai_chars
    result['rules_chars'] = rules_chars

    # Metadata only — still never rewrite body
    if ai_data.get('title'):
        ai_title = str(ai_data.get('title')).strip()
        if ai_title and (
            not result.get('title')
            or result['title'] in ('Imported Sermon',)
            or result['title'].lower() == (fname or '').lower()
        ):
            result['title'] = ai_title[:500]
    if ai_data.get('primary_passage') and not result.get('primary_passage'):
        result['primary_passage'] = str(ai_data.get('primary_passage'))[:200]
    if not result.get('primary_passage'):
        for sec in podium:
            if sec.get('scripture_reference'):
                result['primary_passage'] = sec['scripture_reference']
                break
        if not result.get('primary_passage') and result.get('notes'):
            result['primary_passage'] = _first_ref(result['notes']) or ''
    if ai_data.get('service_date') and not result.get('service_date'):
        result['service_date'] = str(ai_data.get('service_date'))[:10]

    return result


def _plain_from_section_content(content: str) -> str:
    """HTML section content → plain text for the prep Notes & References box."""
    text = content or ''
    text = re.sub(r'(?i)<br\s*/?>', '\n', text)
    text = re.sub(r'(?i)</p\s*>', '\n\n', text)
    text = re.sub(r'(?i)<p[^>]*>', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _is_prep_notes_section(sec: dict) -> bool:
    """True if this belongs in sermon Notes & References, not the podium outline."""
    st = (sec.get('section_type') or '').strip().lower()
    title = (sec.get('title') or '').strip().lower()
    if st in ('notes', 'reference', 'references', 'research'):
        return True
    if re.match(
        r'^(verses?\s*(and|&)?\s*notes|notes\s*(and|&)?\s*references?|notes\s*(and|&)?\s*refs|'
        r'references?|research|personal prep|prep notes|delivery tips|full scripture|scripture notes)\b',
        title,
    ):
        return True
    return False


def _redirect_prep_sections_to_notes(
    sections: list[dict],
    existing_notes: str = '',
) -> tuple[list[dict], str]:
    """
    Move Verses/Notes/References sections out of the podium list into the
    sermon-level Notes & References field (personal prep, not printed by default).
    """
    podium: list[dict] = []
    prep_parts: list[str] = []
    if (existing_notes or '').strip():
        prep_parts.append(existing_notes.strip())

    for sec in sections or []:
        if _is_prep_notes_section(sec):
            plain = _plain_from_section_content(sec.get('content') or '')
            if not plain:
                continue
            label = (sec.get('title') or 'Notes & References').strip()
            # Avoid double-labeling if content already starts with the heading
            if plain.lower().startswith(label.lower()):
                prep_parts.append(plain)
            else:
                prep_parts.append(f'{label}\n{plain}')
            # Also preserve any per-section notes field
            extra = (sec.get('notes') or '').strip()
            if extra and extra not in plain:
                prep_parts.append(extra)
            continue
        podium.append(sec)

    # Re-number Section N after removals so outline stays clean
    n = 0
    for sec in podium:
        st = (sec.get('section_type') or '').lower()
        title = (sec.get('title') or '').strip()
        if st in ('point', 'body', 'scripture') or re.match(r'^section\s+\d+$', title, re.I):
            if st in ('point', 'body') or re.match(r'^section\s+\d+$', title, re.I):
                n += 1
                if st != 'scripture':
                    sec['section_type'] = 'point'
                    sec['title'] = f'Section {n}'

    combined = '\n\n'.join(p for p in prep_parts if p).strip()
    return podium, combined
